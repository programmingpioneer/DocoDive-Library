"""Account lifecycle routes and server-side maintenance entry points."""

import secrets
import time
import threading
from datetime import datetime
from flask import (
    request,
    session,
    redirect,
    url_for,
    render_template,
    jsonify,
    flash,
    g,
)
from account_store import Store
from account_lifecycle import AccountLifecycle
from studio_auth import StudioAuth, AuthError
from reader_settings import ReaderSettings


def register_accounts(app, svc):
    from admin.security import has_role

    store = Store(svc["mysql"])
    auth = StudioAuth(
        store, app.config["SECRET_KEY"], svc["send_email_notification"], app.logger
    )
    lifecycle = AccountLifecycle(
        store, svc["send_email_notification"], app.logger, has_role
    )
    app.extensions.update(
        account_store=store, studio_auth=auth, account_lifecycle=lifecycle
    )
    settings = ReaderSettings(store, auth, lifecycle)
    app.extensions["reader_settings"] = settings
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

    @app.errorhandler(AuthError)
    def account_error(error):
        if (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            return jsonify(error=str(error)), error.status
        return (
            render_template("user/account_error.html", message=str(error)),
            error.status,
        )

    @app.before_request
    def revoke_old_reader_sessions():
        uid = session.get("user_id")
        if (
            uid
            and not request.path.startswith("/static/")
            and not lifecycle.active_session(uid, session.get("account_version", 0))
        ):
            for key in (
                "user_id",
                "user_name",
                "user_display_name",
                "email",
                "avatar_url",
                "account_version",
            ):
                session.pop(key, None)

    @app.route("/user/settings", methods=["GET", "POST"])
    def account_settings():
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("user_login"))
        user = store.query("SELECT username,email FROM users WHERE id=%s", (uid,), one=True)
        if not user:
            raise AuthError("Account not found.", 404)
        error, status = None, 200
        if request.method == "POST":
            try:
                settings.change_password(
                    uid, request.form.get("current_password", ""),
                    request.form.get("password", ""), request.form.get("confirm_password", ""),
                    request.remote_addr or "unknown",
                )
            except AuthError as exc:
                error, status = str(exc), exc.status
            else:
                session.clear()
                flash("Password changed. All sessions have been signed out. Sign in with your new password.", "success")
                return redirect(url_for("user_login"))
        return render_template(
            "user/account_settings.html", username=user[0], email=user[1],
            protected=has_role(uid), code_sent=bool(session.get("deletion_challenge")),
            deletion_return="settings", error=error,
        ), status

    @app.route("/user/account-deletion", methods=["GET", "POST"])
    def account_deletion():
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("user_login"))
        user = store.query(
            "SELECT username,email FROM users WHERE id=%s", (uid,), one=True
        )
        if not user:
            raise AuthError("Account not found.", 404)
        error = None
        if request.method == "POST":
            action = request.form.get("action")
            if has_role(uid):
                raise AuthError(
                    "Transfer or remove your administrator role first.", 403
                )
            if action == "send":
                binding = session.setdefault(
                    "deletion_binding", secrets.token_urlsafe(32)
                )
                session["deletion_challenge"] = auth.issue(
                    uid,
                    "account_delete",
                    binding,
                    user[1],
                    request.remote_addr or "unknown",
                )
                flash("Verification code sent. It expires in 5 minutes.", "success")
                destination = "account_settings" if request.form.get("return_to") == "settings" else "account_deletion"
                return redirect(url_for(destination) + ("#delete-account" if destination == "account_settings" else ""))
            if action == "confirm":
                reason = request.form.get("reason", "").strip()
                if not 10 <= len(reason) <= 2000:
                    raise AuthError("Enter a reason of 10–2,000 characters.")
                confirmed, _, _ = auth.verify(
                    session.get("deletion_challenge", ""),
                    "account_delete",
                    session.get("deletion_binding", ""),
                    request.form.get("code", ""),
                )
                if confirmed != uid:
                    raise AuthError("Verification does not match this account.", 403)
                lifecycle.request_deletion(uid, reason)
                session.clear()
                lifecycle.deliver_mail(limit=5)
                return render_template("user/deletion_requested.html")
            raise AuthError("Invalid action.")
        return render_template(
            "user/account_deletion.html",
            email=user[1],
            code_sent=bool(session.get("deletion_challenge")),
            protected=has_role(uid),
            error=error,
        )

    @app.after_request
    def track_activity(response):
        page_view = (
            request.method == "GET"
            and response.status_code == 200
            and response.mimetype == "text/html"
            and request.blueprint != "admin"
            and not request.path.startswith(("/static/", "/user/account-deletion"))
        )
        download = bool(getattr(g, "download_recorded", False))
        if page_view or download:
            now = datetime.utcnow()
            uid = session.get("user_id", 0)
            try:
                with store.transaction() as cur:
                    cur.execute(
                        "INSERT IGNORE INTO activity_daily (activity_day,user_id,page_views,reads,downloads,last_seen) VALUES (%s,%s,0,0,0,%s)",
                        (now.date(), uid, now),
                    )
                    cur.execute(
                        "UPDATE activity_daily SET page_views=page_views+%s,reads=reads+%s,downloads=downloads+%s,last_seen=%s WHERE activity_day=%s AND user_id=%s",
                        (
                            int(page_view),
                            int(page_view and request.endpoint == "read_book"),
                            int(download),
                            now,
                            now.date(),
                            uid,
                        ),
                    )
            except Exception:
                app.logger.warning(
                    "Activity recording unavailable; check the account migration."
                )
        return response

    def maintenance():
        count = lifecycle.delete_due()
        lifecycle.capture_scores()
        lifecycle.deliver_mail()
        return count

    app.extensions["account_maintenance"] = maintenance

    @app.cli.command("account-maintenance")
    def maintenance_command():
        """Run approved account cleanup, retention purge and queued mail delivery."""
        count = maintenance()
        print("Account maintenance complete; deleted:", count)


def start_account_scheduler(app):
    """Local python app.py worker. Production should schedule the CLI every minute."""

    def run():
        while True:
            try:
                with app.app_context():
                    app.extensions["account_maintenance"]()
            except Exception:
                app.logger.exception(
                    "Account maintenance failed; no completion claimed."
                )
            time.sleep(60)

    threading.Thread(target=run, daemon=True, name="account-maintenance").start()
