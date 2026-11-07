"""Studio pages added around the application's existing administrative workflows."""

import json
import secrets
from flask import (
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from password_security import check_password_hash, generate_password_hash, needs_rehash
from studio_auth import AuthError
import time
from .security import identity, required, owner_id, admin_ids, has_role, owner_required


def leaderboard_summary(query):
    row = (
        query(
            """SELECT
    COALESCE((SELECT SUM(p.points) FROM user_points p JOIN users u ON u.id=p.user_id),0),
    (SELECT COUNT(*) FROM users),
    (SELECT COUNT(*) FROM user_points p JOIN users u ON u.id=p.user_id WHERE p.action='admin_adjustment')""",
            one=True,
        )
        or ()
    )
    return {
        key: (row[i] if len(row) > i else 0)
        for i, key in enumerate(("points", "members", "adjustments"))
    }


def pagination():
    page = max(1, request.args.get("page", 1, type=int))
    return page, 30, (page - 1) * 30


def add_studio_pages(bp, svc):
    mysql = svc["mysql"]

    def query(sql, args=(), one=False):
        cur = mysql.connection.cursor()
        try:
            cur.execute(sql, args)
            return cur.fetchone() if one else cur.fetchall()
        finally:
            cur.close()

    def execute(sql, args=()):
        cur = mysql.connection.cursor()
        try:
            cur.execute(sql, args)
            mysql.connection.commit()
        except Exception:
            mysql.connection.rollback()
            raise
        finally:
            cur.close()

    def setting_json(key):
        try:
            value = json.loads(svc["get_site_setting"](key, "{}") or "{}")
            return value if isinstance(value, dict) else {}
        except (ValueError, TypeError):
            return {}

    @bp.before_request
    def protect_studio():
        if (
            request.endpoint
            not in ("admin.login", "admin.verify_login", "admin.resend_code")
            and not identity()
        ):
            session.pop("studio_user_id", None)
            return redirect(url_for("admin.login"))

    @bp.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @bp.context_processor
    def studio_context():
        return {
            "filter_url": lambda **changes: url_for(
                request.endpoint, **{**request.args.to_dict(), "page": 1, **changes}
            ),
            "studio_user": identity(),
            "is_moderator": True,
            "current_user_is_official": False,
            "page_url": lambda number: url_for(
                request.endpoint, **dict(request.args.to_dict(), page=number)
            ),
        }

    @bp.route("/")
    def index():
        return redirect(url_for("admin.admin_dashboard"))

    def auth_service():
        return current_app.extensions["studio_auth"]

    def clear_pending():
        for key in ("studio_challenge", "studio_binding", "studio_pending_since"):
            session.pop(key, None)

    @bp.route("/login", methods=["GET", "POST"])
    @svc["limiter"].limit("20 per 15 minutes")
    def login():
        if identity():
            return redirect(url_for("admin.admin_dashboard"))
        if request.args.get("restart"):
            clear_pending()
        error, status = None, 200
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()[:254]
            password = request.form.get("password", "")
            auth = auth_service()
            try:
                auth.login_gate(email, request.remote_addr or "unknown")
                row = query(
                    "SELECT id, password, verified FROM users WHERE email = %s",
                    (email,),
                    one=True,
                )
                valid = bool(row and row[1] and check_password_hash(row[1], password))
                if not valid or not row[2] or not has_role(row[0]):
                    auth.login_failed(email)
                    raise AuthError("Unable to sign in with these details.", 401)
                clear_pending()
                binding = secrets.token_urlsafe(32)
                upgraded = (
                    generate_password_hash(password) if needs_rehash(row[1]) else row[1]
                )
                challenge = auth.issue(
                    row[0],
                    "admin_login",
                    binding,
                    email,
                    request.remote_addr or "unknown",
                    upgraded,
                    auth.digest(row[1]),
                )
                session["studio_binding"] = binding
                session["studio_challenge"] = challenge
                session["studio_pending_since"] = time.time()
                auth.audit("admin_password_verified", row[0])
                return redirect(url_for("admin.verify_login"))
            except AuthError as exc:
                error, status = str(exc), exc.status
        return render_template("admin/admin_login.html", error=error), status

    @bp.route("/verify", methods=["GET", "POST"])
    @svc["limiter"].limit("15 per 15 minutes")
    def verify_login():
        if (
            not session.get("studio_challenge")
            or time.time() - session.get("studio_pending_since", 0) > 600
        ):
            clear_pending()
            return redirect(url_for("admin.login"))
        error, status = None, 200
        if request.method == "POST":
            auth = auth_service()
            try:
                uid, upgraded, fingerprint = auth.verify(
                    session["studio_challenge"],
                    "admin_login",
                    session.get("studio_binding", ""),
                    request.form.get("code", ""),
                )
                row = query(
                    "SELECT password,verified,email FROM users WHERE id=%s",
                    (uid,),
                    one=True,
                )
                if (
                    not row
                    or not row[1]
                    or not has_role(uid)
                    or not secrets.compare_digest(
                        auth.digest(row[0]), fingerprint or ""
                    )
                ):
                    clear_pending()
                    raise AuthError("Account access changed. Sign in again.", 403)
                # Atomically update only the password hash that passed the password step.
                cur = mysql.connection.cursor()
                try:
                    cur.execute(
                        "UPDATE users SET password=%s WHERE id=%s AND password=%s",
                        (upgraded, uid, row[0]),
                    )
                    mysql.connection.commit()
                finally:
                    cur.close()
                token = auth.new_session(uid, auth.digest(upgraded))
                session["studio_user_id"] = uid
                session["studio_token"] = token
                session.permanent = True
                clear_pending()
                return redirect(url_for("admin.admin_dashboard"))
            except AuthError as exc:
                error, status = str(exc), exc.status
        return render_template("admin/admin_verify.html", error=error), status

    @bp.post("/verify/resend")
    @svc["limiter"].limit("20 per hour")
    def resend_code():
        if time.time() - session.get("studio_pending_since", 0) > 600:
            clear_pending()
            return redirect(url_for("admin.login"))
        auth = auth_service()
        row = query(
            "SELECT o.user_id,u.email,o.password_hash,o.pw_fingerprint,o.binding_hash FROM security_otp o JOIN users u ON u.id=o.user_id WHERE o.challenge_id=%s AND o.purpose=%s",
            (session.get("studio_challenge", ""), "admin_login"),
            one=True,
        )
        if (
            not row
            or not secrets.compare_digest(
                row[4], auth.digest(session.get("studio_binding", ""))
            )
            or not has_role(row[0])
        ):
            return redirect(url_for("admin.login"))
        try:
            session["studio_challenge"] = auth.issue(
                row[0],
                "admin_login",
                session["studio_binding"],
                row[1],
                request.remote_addr or "unknown",
                row[2],
                row[3],
            )
            return redirect(url_for("admin.verify_login"))
        except AuthError as exc:
            return (
                render_template("admin/admin_verify.html", error=str(exc)),
                exc.status,
            )

    @bp.post("/logout")
    def logout():
        auth_service().revoke(session.get("studio_token"))
        session.pop("studio_user_id", None)
        session.pop("studio_token", None)
        clear_pending()
        return redirect(url_for("admin.login"))

    @bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
    def edit_user(user_id):
        pending = query(
            "SELECT status FROM account_deletions WHERE user_id=%s",
            (user_id,),
            one=True,
        )
        if pending and pending[0] in ("requested", "approved"):
            raise AuthError("Pending-deletion accounts cannot be edited.", 409)

        row = query(
            "SELECT id, username, email, first_name, last_name, verified FROM users WHERE id=%s",
            (user_id,),
            one=True,
        )
        if not row:
            abort(404)
        user = dict(
            zip(("id", "username", "email", "first_name", "last_name", "verified"), row)
        )
        user["role"] = "admin" if has_role(user_id) else "user"
        if has_role(user_id) and user_id != identity()["id"]:
            owner_required()
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip()
            first = request.form.get("first_name", "").strip()
            last = request.form.get("last_name", "").strip()
            role = request.form.get("role", user["role"])
            verified = 1 if request.form.get("verified") else 0
            error = None
            if (
                not username
                or len(username) > 30
                or any(
                    c
                    not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
                    for c in username
                )
            ):
                error = "Use a username of 1–30 letters, numbers, dots, underscores or hyphens."
            elif (
                not svc["is_valid_email"](email)
                or len(email) > 254
                or max(len(first), len(last)) > 100
            ):
                error = (
                    "Please enter a valid email and names of at most 100 characters."
                )
            elif role not in ("user", "admin"):
                error = "Invalid role."
            elif (str(user_id) == owner_id() or user_id == identity()["id"]) and (
                not verified or role != "admin"
            ):
                error = (
                    "You cannot disable your own Studio access or the owner account."
                )
            elif query(
                "SELECT id FROM users WHERE (username=%s OR email=%s) AND id != %s",
                (username, email, user_id),
                one=True,
            ):
                error = "That username or email is already in use."
            if role != user["role"]:
                owner_required()
            if error:
                flash(error, "danger")
                user.update(
                    username=username, email=email, first_name=first, last_name=last
                )
                return render_template("admin/user_edit.html", user=user), 400
            cur = mysql.connection.cursor()
            try:
                cur.execute(
                    "UPDATE users SET username=%s,email=%s,first_name=%s,last_name=%s,verified=%s WHERE id=%s",
                    (username, email, first, last, verified, user_id),
                )
                if role != user["role"]:
                    ids = admin_ids()
                    (
                        ids.add(str(user_id))
                        if role == "admin"
                        else ids.discard(str(user_id))
                    )
                    cur.execute(
                        "REPLACE INTO site_settings (`key`,`value`) VALUES (%s,%s)",
                        ("studio_admin_ids", json.dumps(sorted(ids))),
                    )
                mysql.connection.commit()
            except Exception:
                mysql.connection.rollback()
                raise
            finally:
                cur.close()
            flash("User updated.", "success")
            return redirect(url_for("admin.list_users"))
        return render_template("admin/user_edit.html", user=user)

    @bp.get("/api/user-stats")
    def official_stats():
        uid = request.args.get("user_id", type=int)
        if not uid:
            abort(400)
        row = query(
            "SELECT (SELECT COUNT(*) FROM documents WHERE uploaded_by=%s), (SELECT COUNT(*) FROM book_comments WHERE user_id=%s), (SELECT COALESCE(SUM(points),0) FROM user_points WHERE user_id=%s)",
            (uid, uid, uid),
            one=True,
        )
        return jsonify(dict(zip(("uploads", "comments", "points"), row)))

    @bp.route("/leaderboard", methods=["GET", "POST"])
    def leaderboard_manage():
        if request.method == "POST":
            uid = request.form.get("user_id", type=int)
            points = request.form.get("points", type=int)
            reason = request.form.get("reason", "").strip()
            if (
                not uid
                or points is None
                or not -10000 <= points <= 10000
                or points == 0
                or not 3 <= len(reason) <= 120
            ):
                flash(
                    "Choose a user, a nonzero adjustment between -10,000 and 10,000, and a reason (3–120 characters).",
                    "danger",
                )
            elif not query("SELECT id FROM users WHERE id=%s", (uid,), one=True):
                flash("User not found.", "danger")
            else:
                # Preserve earned activity; adjustments are separate, auditable records.
                execute(
                    "INSERT INTO user_points (user_id,points,action,book_id) VALUES (%s,%s,%s,NULL)",
                    (uid, points, "admin_adjustment"),
                )
                svc["create_notification"](
                    uid,
                    "general",
                    "Your leaderboard points were adjusted: "
                    + str(points)
                    + ". "
                    + reason,
                    "/leaderboard",
                )
                flash("Points adjusted.", "success")
            return redirect(url_for("admin.leaderboard_manage"))
        page, limit, offset = pagination()
        q = request.args.get("q", "").strip()[:100]
        rows = query(
            "SELECT u.id,u.username,COALESCE(SUM(p.points),0),u.avatar_url,(SELECT h.points FROM leaderboard_snapshots h WHERE h.user_id=u.id AND h.snapshot_day<=DATE_SUB(UTC_DATE(),INTERVAL 7 DAY) ORDER BY h.snapshot_day DESC LIMIT 1) FROM users u LEFT JOIN user_points p ON p.user_id=u.id WHERE u.username LIKE %s GROUP BY u.id,u.username,u.avatar_url ORDER BY COALESCE(SUM(p.points),0) DESC,u.id LIMIT %s OFFSET %s",
            ("%" + q + "%", limit + 1, offset),
        )
        stats = leaderboard_summary(query)
        history = query(
            "SELECT CAST(snapshot_day AS CHAR),SUM(points) FROM leaderboard_snapshots WHERE snapshot_day>=DATE_SUB(UTC_DATE(),INTERVAL 7 DAY) GROUP BY snapshot_day ORDER BY snapshot_day"
        )
        return render_template(
            "admin/leaderboard_manage.html",
            stats=stats,
            history=history,
            rows=rows[:limit],
            page=page,
            has_next=len(rows) > limit,
            q=q,
        )

    @bp.get("/suggestions")
    def suggestions_manage():
        page, limit, offset = pagination()
        q = request.args.get("q", "").strip()[:100]
        status = request.args.get("status", "")
        day = request.args.get("day", "")
        where = "(f.subject LIKE %s OR f.message LIKE %s)"
        args = ["%" + q + "%", "%" + q + "%"]
        if status == "answered":
            where += " AND f.official_reply IS NOT NULL AND TRIM(f.official_reply)!=''"
        elif status == "unanswered":
            where += " AND (f.official_reply IS NULL OR TRIM(f.official_reply)='')"
        elif status:
            abort(400)
        if day:
            from datetime import datetime

            try:
                datetime.strptime(day, "%Y-%m-%d")
            except ValueError:
                abort(400)
            where += " AND DATE(f.created_at)=%s"
            args.append(day)
        rows = query(
            "SELECT f.id,f.subject,f.message,f.official_reply,u.username,f.created_at FROM user_feedback f LEFT JOIN users u ON u.id=f.user_id WHERE "
            + where
            + " ORDER BY f.id DESC LIMIT %s OFFSET %s",
            (*args, limit + 1, offset),
        )
        return render_template(
            "admin/suggestions_manage.html",
            rows=rows[:limit],
            page=page,
            has_next=len(rows) > limit,
            q=q,
        )

    @bp.post("/suggestions/<int:feedback_id>/delete")
    def suggestion_delete(feedback_id):
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "DELETE FROM reply_likes WHERE reply_id IN (SELECT id FROM feedback_replies WHERE feedback_id=%s)",
                (feedback_id,),
            )
            cur.execute(
                "DELETE FROM feedback_replies WHERE feedback_id=%s", (feedback_id,)
            )
            cur.execute(
                "DELETE FROM feedback_likes WHERE feedback_id=%s", (feedback_id,)
            )
            cur.execute("DELETE FROM user_feedback WHERE id=%s", (feedback_id,))
            mysql.connection.commit()
        except Exception:
            mysql.connection.rollback()
            raise
        finally:
            cur.close()
        flash("Suggestion deleted.", "success")
        return redirect(url_for("admin.suggestions_manage"))

    @bp.route("/settings", methods=["GET", "POST"])
    def settings():
        content = setting_json("studio_content")
        fields = {
            "home_title": 120,
            "home_intro": 600,
            "about_title": 160,
            "about_body": 4000,
        }
        if request.method == "POST":
            values = {key: request.form.get(key, "").strip() for key in fields}
            if any(len(values[key]) > length for key, length in fields.items()):
                flash("One or more fields exceed the allowed length.", "danger")
                return render_template("admin/settings.html", content=values), 400
            svc["set_site_setting"]("studio_content", json.dumps(values))
            flash(
                "Site content saved. Blank fields use the original content.", "success"
            )
            return redirect(url_for("admin.settings"))
        return render_template("admin/settings.html", content=content)

    @bp.route("/learning", methods=["GET", "POST"])
    def learning_manage():
        categories = query("SELECT id,level FROM categories ORDER BY level")
        valid = {svc["category_to_slug"](r[1]): r[1] for r in categories}
        slug = request.values.get("category", "")
        content = setting_json("studio_learning")
        modules = svc["IELTS_MODULES"] if slug == "ielts" else svc["GENERIC_MODULES"]
        selected = content.get(slug, {})
        if request.method == "POST":
            if slug not in valid:
                abort(400)
            selected = {
                "title": request.form.get("title", "").strip(),
                "description": request.form.get("description", "").strip(),
                "modules": {},
            }
            if len(selected["title"]) > 160 or len(selected["description"]) > 2000:
                abort(400)
            for module in modules:
                title = request.form.get(module["slug"] + "_title", "").strip()
                desc = request.form.get(module["slug"] + "_desc", "").strip()
                if len(title) > 120 or len(desc) > 600:
                    abort(400)
                selected["modules"][module["slug"]] = {"title": title, "desc": desc}
            content[slug] = selected
            svc["set_site_setting"]("studio_learning", json.dumps(content))
            flash("Learning Hub content saved.", "success")
            return redirect(url_for("admin.learning_manage", category=slug))
        return render_template(
            "admin/learning_manage.html",
            categories=valid,
            slug=slug,
            content=selected,
            modules=modules,
        )
