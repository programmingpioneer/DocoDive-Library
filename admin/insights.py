"""Real aggregate activity and content reports with accessible drill-down links."""

from datetime import datetime, timedelta
from flask import current_app, render_template, request, url_for, jsonify, abort
from .security import identity
from studio_auth import AuthError


def store():
    return current_app.extensions["account_store"]


def metric(label, value, endpoint, **args):
    return dict(label=label, value=int(value or 0), url=url_for(endpoint, **args))


def report(kind="all", days=30):
    since = datetime.utcnow() - timedelta(days=days)
    db = store()

    def count(sql, args=()):
        row = db.query(sql, args, one=True)
        return row[0] if row else 0

    cards = [
        metric(
            "Registered users", count("SELECT COUNT(*) FROM users"), "admin.list_users"
        ),
        metric(
            "Books", count("SELECT COUNT(*) FROM documents"), "admin.admin_books_list"
        ),
        metric(
            "Awaiting approval",
            count(
                "SELECT COUNT(*) FROM documents WHERE status='pending' AND approved=0"
            ),
            "admin.pending_books",
        ),
        metric(
            "Pending deletions",
            count(
                "SELECT COUNT(*) FROM account_deletions WHERE status IN ('requested','approved')"
            ),
            "admin.pending_deletions",
        ),
        metric(
            "Active members · " + str(days) + "d",
            count(
                "SELECT COUNT(DISTINCT user_id) FROM activity_daily WHERE user_id<>0 AND activity_day>=%s",
                (since.date(),),
            ),
            "admin.tracking",
        ),
        metric(
            "Reviews", count("SELECT COUNT(*) FROM reviews"), "admin.moderation_panel"
        ),
        metric(
            "Comments",
            count("SELECT COUNT(*) FROM book_comments"),
            "admin.moderation_panel",
        ),
        metric(
            "Suggestions",
            count("SELECT COUNT(*) FROM user_feedback"),
            "admin.suggestions_manage",
        ),
    ]
    charts = []

    def chart(title, rows, endpoint, kind="bar", arg=None):
        charts.append(
            dict(
                title=title,
                type=kind,
                labels=[str(r[0]) for r in rows],
                values=[int(r[1] or 0) for r in rows],
                links=[
                    url_for(endpoint, **({arg: str(r[0])} if arg else {})) for r in rows
                ],
            )
        )

    if kind in ("all", "users"):
        chart(
            "New signups",
            db.query(
                "SELECT DATE(created_at),COUNT(*) FROM users WHERE created_at>=%s GROUP BY DATE(created_at) ORDER BY DATE(created_at)",
                (since,),
            ),
            "admin.list_users",
            arg="joined",
        )
        chart(
            "Daily active signed-in members",
            db.query(
                "SELECT activity_day,COUNT(DISTINCT user_id) FROM activity_daily WHERE activity_day>=%s AND user_id<>0 GROUP BY activity_day ORDER BY activity_day",
                (since.date(),),
            ),
            "admin.tracking",
            kind="line",
            arg="day",
        )
        chart(
            "Reading opens",
            db.query(
                "SELECT activity_day,SUM(reads) FROM activity_daily WHERE activity_day>=%s GROUP BY activity_day ORDER BY activity_day",
                (since.date(),),
            ),
            "admin.tracking",
            kind="line",
            arg="day",
        )
    if kind in ("all", "reviews"):
        chart(
            "Review volume",
            db.query(
                "SELECT DATE(created_at),COUNT(*) FROM reviews WHERE created_at>=%s GROUP BY DATE(created_at) ORDER BY DATE(created_at)",
                (since,),
            ),
            "admin.moderation_panel",
            arg="day",
        )
        chart(
            "Rating distribution · all reviews",
            db.query(
                "SELECT rating,COUNT(*) FROM reviews GROUP BY rating ORDER BY rating"
            ),
            "admin.moderation_panel",
            kind="doughnut",
            arg="rating",
        )
        top = db.query(
            "SELECT d.id,d.title,COUNT(r.id) FROM documents d JOIN reviews r ON r.book_id=d.id GROUP BY d.id,d.title ORDER BY COUNT(r.id) DESC LIMIT 8"
        )
        charts.append(
            dict(
                title="Most reviewed books",
                type="bar",
                labels=[r[1] for r in top],
                values=[int(r[2]) for r in top],
                links=[
                    url_for("admin.moderation_panel", book_id=r[0], days=36500)
                    for r in top
                ],
            )
        )
    if kind in ("all", "suggestions"):
        chart(
            "Suggestion volume",
            db.query(
                "SELECT DATE(created_at),COUNT(*) FROM user_feedback WHERE created_at>=%s GROUP BY DATE(created_at) ORDER BY DATE(created_at)",
                (since,),
            ),
            "admin.suggestions_manage",
            arg="day",
        )
        chart(
            "Suggestion topics · submitted subjects",
            db.query(
                "SELECT subject,COUNT(*) FROM user_feedback GROUP BY subject ORDER BY COUNT(*) DESC LIMIT 8"
            ),
            "admin.suggestions_manage",
            arg="q",
        )
        chart(
            "Suggestion response status",
            db.query(
                "SELECT CASE WHEN official_reply IS NULL OR TRIM(official_reply)='' THEN 'unanswered' ELSE 'answered' END AS response_status,COUNT(*) FROM user_feedback GROUP BY response_status"
            ),
            "admin.suggestions_manage",
            kind="doughnut",
            arg="status",
        )
    if kind == "all":
        chart(
            "Book approval status",
            db.query(
                "SELECT COALESCE(status,'unknown'),COUNT(*) FROM documents GROUP BY status"
            ),
            "admin.admin_books_list",
            kind="doughnut",
            arg="status",
        )
        chart(
            "Deletion requests",
            db.query("SELECT status,COUNT(*) FROM account_deletions GROUP BY status"),
            "admin.pending_deletions",
            kind="doughnut",
            arg="status",
        )
        chart(
            "Page responses · guests + members",
            db.query(
                "SELECT activity_day,SUM(page_views) FROM activity_daily WHERE activity_day>=%s GROUP BY activity_day ORDER BY activity_day",
                (since.date(),),
            ),
            "admin.tracking",
            kind="line",
            arg="day",
        )
    return dict(
        cards=cards,
        charts=charts,
        days=days,
        note="Activity begins when tracking is installed. Guest requests are counted as page responses, not unique people. Ratings describe review scores, not inferred text sentiment.",
    )


def add_insights_pages(bp, svc):
    @bp.get("/api/insights")
    def insights_api():
        kind = request.args.get("kind", "all")
        if kind not in ("all", "users", "reviews", "suggestions"):
            abort(400)
        days = request.args.get("days", 30, type=int)
        if days not in (7, 30, 90):
            days = 30
        return jsonify(report(kind, days))

    @bp.get("/tracking")
    def tracking():
        from .directories import csv_response

        day = request.args.get("day", "")
        q = request.args.get("q", "").strip()[:100]
        args = ["%" + q + "%", "%" + q + "%"]
        where = "WHERE (u.username LIKE %s OR u.email LIKE %s)"
        if day:
            try:
                datetime.strptime(day, "%Y-%m-%d")
            except ValueError:
                abort(400)
            where += " AND a.activity_day=%s"
            args.append(day)
        source = " FROM activity_daily a JOIN users u ON u.id=a.user_id " + where
        total = store().query("SELECT COUNT(DISTINCT u.id)" + source, args, one=True)[0]
        page = min(
            max(1, request.args.get("page", 1, type=int)), max(1, (total + 29) // 30)
        )
        exporting = request.args.get("export") == "csv"
        rows = store().query(
            "SELECT u.id,u.username,u.email,SUM(a.page_views),SUM(a.reads),MAX(a.last_seen),SUM(a.downloads)"
            + source
            + " GROUP BY u.id,u.username,u.email ORDER BY MAX(a.last_seen) DESC LIMIT %s OFFSET %s",
            (*args, 5000 if exporting else 30, 0 if exporting else (page - 1) * 30),
        )
        if exporting:
            return csv_response(
                "docodive-member-activity",
                [
                    "ID",
                    "Username",
                    "Email",
                    "Page responses",
                    "Reading opens",
                    "Last seen UTC",
                    "Download links",
                ],
                rows,
            )
        return render_template(
            "admin/tracking.html",
            rows=rows,
            page=page,
            total=total,
            total_pages=max(1, (total + 29) // 30),
            per_page=30,
            has_next=page * 30 < total,
            day=day,
            q=q,
        )

    @bp.get("/users/<int:user_id>/activity")
    def user_activity(user_id):
        row = store().query(
            "SELECT id,username,email,created_at,verified FROM users WHERE id=%s",
            (user_id,),
            one=True,
        )
        if not row:
            abort(404)
        rows = store().query(
            "SELECT activity_day,page_views,reads,downloads,last_seen FROM activity_daily WHERE user_id=%s ORDER BY activity_day DESC LIMIT 90",
            (user_id,),
        )
        pending = store().query(
            "SELECT status FROM account_deletions WHERE user_id=%s AND status IN ('requested','approved')",
            (user_id,),
            one=True,
        )
        return render_template(
            "admin/user_activity.html", user=row, rows=rows, pending=bool(pending)
        )

    @bp.get("/deletions")
    def pending_deletions():
        page = max(1, request.args.get("page", 1, type=int))
        status = request.args.get("status", "")
        where = "status IN ('requested','approved')"
        args = []
        if status in ("requested", "approved", "restored", "cancelled", "deleted"):
            where = "status=%s"
            args.append(status)
        total = store().query(
            "SELECT COUNT(*) FROM account_deletions WHERE " + where, args, one=True
        )[0]
        page = min(page, max(1, (total + 29) // 30))
        rows = store().query(
            "SELECT request_id,user_id,display_name,email,reason,status,requested_at,deadline FROM account_deletions WHERE "
            + where
            + " ORDER BY requested_at DESC LIMIT %s OFFSET %s",
            (*args, 31, (page - 1) * 30),
        )
        recent = store().query(
            "SELECT display_name,email,deleted_at FROM account_deletions WHERE status='deleted' ORDER BY deleted_at DESC LIMIT 30"
        )
        stats = dict(
            store().query(
                "SELECT status,COUNT(*) FROM account_deletions GROUP BY status"
            )
        )
        return render_template(
            "admin/deletions.html",
            rows=rows[:30],
            total=total,
            total_pages=max(1, (total + 29) // 30),
            per_page=30,
            recent=recent,
            stats=stats,
            page=page,
            has_next=len(rows) > 30,
            status=status,
        )

    @bp.post("/deletions/<request_id>/<action>")
    def decide_deletion(request_id, action):
        if action not in ("approve", "cancel"):
            abort(400)
        current_app.extensions["account_lifecycle"].decide(
            request_id, identity()["id"], action == "approve"
        )
        return jsonify(
            success=True,
            message="Decision saved. Approved requests are deleted only after their deadline by the scheduled job.",
        )
