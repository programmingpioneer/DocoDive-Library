"""Read-only Studio directories, bounded exports and parameterized filters."""

import csv
import io
from datetime import datetime, timedelta
from flask import abort, render_template, request, Response
from account_store import Store

USER_COLUMNS = (
    "id",
    "username",
    "email",
    "verified",
    "created_at",
    "name",
    "uploads",
    "downloads",
    "reviews",
    "last_seen",
    "deletion_status",
    "avatar_url",
)
USER_SELECT = """SELECT u.id,u.username,u.email,u.verified,u.created_at,
CONCAT(COALESCE(u.first_name,''),' ',COALESCE(u.last_name,'')),
(SELECT COUNT(*) FROM documents WHERE uploaded_by=u.id),
(SELECT COUNT(*) FROM download_history WHERE user_id=u.id),
(SELECT COUNT(*) FROM reviews WHERE user_id=u.id),
(SELECT MAX(last_seen) FROM activity_daily WHERE user_id=u.id),
(SELECT status FROM account_deletions WHERE user_id=u.id),u.avatar_url FROM users u"""


def csv_response(name, headers, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        cells = []
        for value in row:
            text = "" if value is None else str(value)
            if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(
                ("\t", "\r", "\n")
            ):
                text = "'" + text
            cells.append(text)
        writer.writerow(cells)
    response = Response("\ufeff" + output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="' + name + '.csv"'
    response.headers["Cache-Control"] = "private, no-store"
    return response


def users_page(mysql):
    db = Store(mysql)
    q = request.args.get("q", "").strip()[:100]
    joined = request.args.get("joined", "")
    status = request.args.get("status", "")
    activity = request.args.get("activity", "")
    period = request.args.get("period", "")
    sort = request.args.get("sort", "newest")
    if (
        status not in ("", "verified", "unverified", "pending")
        or activity not in ("", "creators", "downloads")
        or period not in ("", "7", "30", "90")
    ):
        abort(400)
    ordering = {
        "newest": "u.id DESC",
        "oldest": "u.id ASC",
        "name": "u.username ASC,u.id ASC",
    }
    if sort not in ordering:
        abort(400)
    where = "(u.username LIKE %s OR u.email LIKE %s OR CONCAT(COALESCE(u.first_name,''),' ',COALESCE(u.last_name,'')) LIKE %s)"
    args = ["%" + q + "%"] * 3
    if joined:
        try:
            datetime.strptime(joined, "%Y-%m-%d")
        except ValueError:
            abort(400)
        where += " AND DATE(u.created_at)=%s"
        args.append(joined)
    if period:
        where += " AND u.created_at>=%s"
        args.append(datetime.utcnow() - timedelta(days=int(period)))
    if status in ("verified", "unverified"):
        where += " AND u.verified=%s"
        args.append(int(status == "verified"))
    if status == "pending":
        where += " AND EXISTS (SELECT 1 FROM account_deletions ad WHERE ad.user_id=u.id AND ad.status IN ('requested','approved'))"
    if activity == "creators":
        where += " AND EXISTS (SELECT 1 FROM documents d WHERE d.uploaded_by=u.id)"
    if activity == "downloads":
        where += " AND EXISTS (SELECT 1 FROM download_history dh WHERE dh.user_id=u.id)"
    total = db.query("SELECT COUNT(*) FROM users u WHERE " + where, args, one=True)[0]
    page = min(
        max(1, request.args.get("page", 1, type=int)), max(1, (total + 29) // 30)
    )
    exporting = request.args.get("export") == "csv"
    rows = db.query(
        USER_SELECT
        + " WHERE "
        + where
        + " ORDER BY "
        + ordering[sort]
        + " LIMIT %s OFFSET %s",
        (*args, 5000 if exporting else 30, 0 if exporting else (page - 1) * 30),
    )
    users = [dict(zip(USER_COLUMNS, row)) for row in rows]
    if exporting:
        return csv_response(
            "docodive-members",
            [
                "ID",
                "Username",
                "Email",
                "Verified",
                "Joined",
                "Name",
                "Uploads",
                "Downloads",
                "Reviews",
                "Last seen UTC",
                "Deletion status",
            ],
            [row[:11] for row in rows],
        )
    raw = (
        db.query(
            "SELECT COUNT(*),COALESCE(SUM(verified=1),0),(SELECT COUNT(DISTINCT uploaded_by) FROM documents),(SELECT COUNT(*) FROM download_history) FROM users",
            one=True,
        )
        or ()
    )
    stats = {
        key: (raw[i] if len(raw) > i else 0)
        for i, key in enumerate(("total", "verified", "creators", "downloads"))
    }
    selected = users[0] if users else None
    selected_id = request.args.get("member", type=int)
    if selected_id:
        selected = next((u for u in users if u["id"] == selected_id), None)
        if selected is None:
            row = db.query(USER_SELECT + " WHERE u.id=%s", (selected_id,), one=True)
            if not row:
                abort(404)
            selected = dict(zip(USER_COLUMNS, row))
    return render_template(
        "admin/admin_users.html",
        users=users,
        selected=selected,
        stats=stats,
        page=page,
        total=total,
        total_pages=max(1, (total + 29) // 30),
        per_page=30,
        has_next=page * 30 < total,
        q=q,
        joined=joined,
        status=status,
        activity=activity,
        period=period,
        sort=sort,
    )


def books_page(mysql):
    db = Store(mysql)
    q = request.args.get("q", "").strip()[:100]
    status = request.args.get("status", "")
    category = request.args.get("category", "")
    sort = request.args.get("sort", "newest")
    ordering = {
        "newest": "d.id DESC",
        "oldest": "d.id ASC",
        "title": "d.title ASC,d.id ASC",
        "reads": "COALESCE(d.view_count,0) DESC,d.id DESC",
    }
    if (
        status not in ("", "pending", "approved", "rejected", "unknown")
        or sort not in ordering
    ):
        abort(400)
    if category and (not category.isdigit() or len(category) > 10):
        abort(400)
    where = "(d.title LIKE %s OR d.author LIKE %s OR c.level LIKE %s)"
    args = ["%" + q + "%"] * 3
    if status:
        where += " AND COALESCE(d.status,'unknown')=%s"
        args.append(status)
    if category:
        where += " AND d.category_id=%s"
        args.append(int(category))
    source = (
        " FROM documents d LEFT JOIN categories c ON c.id=d.category_id WHERE " + where
    )
    total = db.query("SELECT COUNT(*)" + source, args, one=True)[0]
    page = min(max(1, request.args.get("page", 1, type=int)), max(1, (total + 8) // 9))
    exporting = request.args.get("export") == "csv"
    rows = db.query(
        "SELECT d.id,d.title,c.level,d.author,d.created_at,d.image_url,d.slug,d.status,COALESCE(d.view_count,0),COALESCE(d.download_count,0)"
        + source
        + " ORDER BY "
        + ordering[sort]
        + " LIMIT %s OFFSET %s",
        (*args, 5000 if exporting else 9, 0 if exporting else (page - 1) * 9),
    )
    if exporting:
        return csv_response(
            "docodive-books",
            [
                "ID",
                "Title",
                "Category",
                "Author",
                "Uploaded",
                "Cover",
                "Slug",
                "Status",
                "Reading opens",
                "Download links",
            ],
            rows,
        )
    fields = (
        "id",
        "title",
        "level",
        "author",
        "created_at",
        "image_url",
        "slug",
        "status",
        "reads",
        "downloads",
    )
    books = [dict(zip(fields, row)) for row in rows]
    raw = (
        db.query(
            "SELECT COUNT(*),(SELECT COUNT(*) FROM categories),COALESCE(SUM(approved=0 AND status='pending'),0),COALESCE(SUM(view_count),0) FROM documents",
            one=True,
        )
        or ()
    )
    stats = {
        key: (raw[i] if len(raw) > i else 0)
        for i, key in enumerate(("total", "categories", "pending", "reads"))
    }
    categories = db.query("SELECT id,level FROM categories ORDER BY level")
    return render_template(
        "admin/admin_books.html",
        books=books,
        stats=stats,
        categories=categories,
        page=page,
        total=total,
        total_pages=max(1, (total + 8) // 9),
        per_page=9,
        has_next=page * 9 < total,
        q=q,
        status=status,
        category=category,
        sort=sort,
    )
