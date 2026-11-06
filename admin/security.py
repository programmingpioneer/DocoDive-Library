"""Studio authorization uses a separate session identity and server-side roles."""

import json
from functools import wraps
from flask import current_app, g, request, session, redirect, url_for, abort


def services():
    return current_app.extensions["studio_services"]


def owner_id():
    return str(services()["get_site_setting"]("official_user_id", "") or "")


def admin_ids():
    try:
        values = json.loads(
            services()["get_site_setting"]("studio_admin_ids", "[]") or "[]"
        )
        return (
            {str(int(value)) for value in values} if isinstance(values, list) else set()
        )
    except (ValueError, TypeError):
        return set()


def has_role(user_id):
    return bool(user_id) and (str(user_id) == owner_id() or str(user_id) in admin_ids())


def identity():
    if hasattr(g, "studio_identity"):
        return g.studio_identity
    g.studio_identity = None
    uid = session.get("studio_user_id")
    if (
        not uid
        or not has_role(uid)
        or not current_app.extensions["studio_auth"].valid_session(
            session.get("studio_token"), uid
        )
    ):
        return None
    cur = services()["mysql"].connection.cursor()
    try:
        cur.execute(
            "SELECT id, username, email, verified FROM users WHERE id = %s", (uid,)
        )
        row = cur.fetchone()
    finally:
        cur.close()
    if row and row[3]:
        g.studio_identity = {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "owner": str(row[0]) == owner_id(),
        }
    return g.studio_identity


def required(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        if not identity():
            session.pop("studio_user_id", None)
            return redirect(url_for("admin.login"))
        return fn(*args, **kwargs)

    return guarded


def owner_required():
    user = identity()
    if not user or not user["owner"]:
        abort(403)


def is_studio_request():
    return request.blueprint == "admin" and identity() is not None
