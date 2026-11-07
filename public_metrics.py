"""Measured signed-in audience counts; guests are not unique visitor estimates."""
from datetime import datetime, timedelta


def monthly_active_members(store, today=None):
    today = today or datetime.utcnow().date()
    row = store.query(
        "SELECT COUNT(DISTINCT a.user_id) FROM activity_daily a JOIN users u ON u.id=a.user_id "
        "WHERE a.user_id>0 AND a.activity_day>=%s AND a.activity_day<=%s "
        "AND (a.page_views>0 OR a.reads>0 OR a.downloads>0)",
        (today - timedelta(days=29), today), one=True,
    )
    return int(row[0] or 0)
