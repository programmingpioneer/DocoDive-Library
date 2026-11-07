"""Verified deletion requests, restoration, transactional cleanup and retryable email."""

import secrets
import hmac
from datetime import datetime, timedelta
from html import escape
from studio_auth import AuthError

GRACE = timedelta(days=15)
RETENTION = timedelta(days=30)


def mail_html(title, paragraphs):
    return (
        '<div style="background:#eef2ff;padding:32px;font-family:Arial,sans-serif"><div style="max-width:580px;margin:auto;background:#fff;padding:32px;border-radius:20px"><p style="font-weight:bold;color:#4f46e5">DOCODIVE · YOUR ACCOUNT</p><h1 style="font-size:26px">'
        + escape(title)
        + "</h1>"
        + "".join(
            '<p style="line-height:1.7;color:#334155">' + escape(str(p)) + "</p>"
            for p in paragraphs
        )
        + '<p style="color:#64748b">Your learning journey matters to us.</p></div></div>'
    )


class AccountLifecycle:
    def __init__(self, store, send_mail, logger, protected, clock=None):
        self.store, self.send_mail, self.logger, self.protected = (
            store,
            send_mail,
            logger,
            protected,
        )
        self.clock = clock or datetime.utcnow

    def enqueue(self, cur, key, uid, email, title, paragraphs):
        now = self.clock()
        cur.execute(
            "INSERT IGNORE INTO lifecycle_mail (event_key,user_id,recipient,subject,body,html,created_at,next_attempt) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                key,
                uid,
                email,
                title,
                "\n\n".join(map(str, paragraphs)),
                mail_html(title, paragraphs),
                now,
                now,
            ),
        )

    def welcome(self, uid):
        with self.store.transaction() as cur:
            cur.execute("SELECT username,email FROM users WHERE id=%s", (uid,))
            row = cur.fetchone()
            if row:
                self.enqueue(
                    cur,
                    "welcome:" + str(uid),
                    uid,
                    row[1],
                    "Welcome to DocoDive!",
                    [
                        "Welcome, " + row[0] + "!",
                        "Discover books, save your favourites, share reviews and explore the Learning Hub.",
                        "If you registered with email, use your separate verification email to activate your account.",
                    ],
                )
        self.deliver_mail(limit=5)

    def capture_scores(self):
        today = self.clock().date()
        if not self.store.query(
            "SELECT user_id FROM leaderboard_snapshots WHERE snapshot_day=%s LIMIT 1",
            (today,),
            one=True,
        ):
            with self.store.transaction() as cur:
                cur.execute(
                    "INSERT IGNORE INTO leaderboard_snapshots (snapshot_day,user_id,points) SELECT %s,u.id,COALESCE(SUM(p.points),0) FROM users u LEFT JOIN user_points p ON p.user_id=u.id GROUP BY u.id",
                    (today,),
                )
        with self.store.transaction() as cur:
            cur.execute(
                "DELETE FROM leaderboard_snapshots WHERE snapshot_day<%s",
                (today - timedelta(days=90),),
            )

    def version(self, uid):
        row = self.store.query(
            "SELECT session_version FROM account_security WHERE user_id=%s",
            (uid,),
            one=True,
        )
        return row[0] if row else 0

    def active_session(self, uid, version):
        row = self.store.query(
            "SELECT COALESCE(s.session_version,0),d.status FROM users u LEFT JOIN account_security s ON s.user_id=u.id LEFT JOIN account_deletions d ON d.user_id=u.id WHERE u.id=%s",
            (uid,),
            one=True,
        )
        return bool(
            row
            and row[0] == version
            and row[1] not in ("requested", "approved", "deleted")
        )

    def revoke_all(self, cur, uid):
        cur.execute(
            "INSERT IGNORE INTO account_security (user_id,session_version) VALUES (%s,0)",
            (uid,),
        )
        cur.execute(
            "UPDATE account_security SET session_version=session_version+1 WHERE user_id=%s",
            (uid,),
        )
        cur.execute("DELETE FROM admin_login_sessions WHERE user_id=%s", (uid,))

    def request_deletion(self, uid, reason):
        reason = reason.strip()
        if not 10 <= len(reason) <= 2000:
            raise AuthError("Please enter a reason of 10–2,000 characters.")
        if self.protected(uid):
            raise AuthError(
                "Transfer or remove your administrator role before requesting deletion.",
                403,
            )
        now, rid = self.clock(), secrets.token_hex(16)
        with self.store.transaction() as cur:
            cur.execute(
                "SELECT status FROM account_deletions WHERE user_id=%s FOR UPDATE",
                (uid,),
            )
            existing = cur.fetchone()
            if existing and existing[0] in ("requested", "approved", "deleted"):
                raise AuthError("An account deletion request already exists.", 409)
            cur.execute(
                "SELECT username,email,first_name,last_name,created_at FROM users WHERE id=%s FOR UPDATE",
                (uid,),
            )
            user = cur.fetchone()
            if not user:
                raise AuthError("Account not found.", 404)
            name = (" ".join(str(v or "") for v in user[2:4])).strip() or user[0]
            cur.execute("DELETE FROM account_deletions WHERE user_id=%s", (uid,))
            cur.execute(
                "INSERT INTO account_deletions (request_id,user_id,username,display_name,email,reason,status,requested_at,deadline) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    rid,
                    uid,
                    user[0],
                    name,
                    user[1],
                    reason,
                    "requested",
                    now,
                    now + GRACE,
                ),
            )
            self.revoke_all(cur, uid)
            counts = []
            for label, table, column in [
                ("Uploads", "documents", "uploaded_by"),
                ("Downloads", "download_history", "user_id"),
                ("Reviews", "reviews", "user_id"),
                ("Favourites", "favorites", "user_id"),
            ]:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {column}=%s", (uid,))
                counts.append(label + ": " + str(cur.fetchone()[0]))
            self.enqueue(
                cur,
                "requested:" + rid,
                uid,
                user[1],
                "Account deletion requested",
                [
                    "Hello "
                    + name
                    + ", your request has been recorded and all sessions have been signed out.",
                    "Username: "
                    + user[0]
                    + ". Email: "
                    + user[1]
                    + ". Joined: "
                    + str(user[4])
                    + ".",
                    "; ".join(counts),
                    "Reason: " + reason,
                    "Grace period ends: "
                    + str(now + GRACE)
                    + " UTC. Sign in before this time to restore your account.",
                    "Deletion requires administrator approval. Without approval the request stays pending. Public books you uploaded are retained without an account association.",
                ],
            )
        return rid

    def on_login(self, uid, password_hash=None):
        now = self.clock()
        with self.store.transaction() as cur:
            cur.execute(
                "SELECT request_id,status,deadline,email,display_name FROM account_deletions WHERE user_id=%s FOR UPDATE",
                (uid,),
            )
            row = cur.fetchone()
            cur.execute("SELECT id,password FROM users WHERE id=%s FOR UPDATE", (uid,))
            user = cur.fetchone()
            if not user:
                raise AuthError("Account is no longer available.", 403)
            if password_hash is not None and not hmac.compare_digest(user[1] or "", password_hash):
                raise AuthError("Your password changed while signing in. Sign in again with the new password.", 403)
            if (
                row
                and row[1] not in ("restored", "cancelled")
                and (row[1] == "deleted" or now >= row[2])
            ):
                raise AuthError(
                    "The restoration window has ended. Your account is awaiting approved deletion; contact the site administrator.",
                    403,
                )
            if row and row[1] not in ("restored", "cancelled"):
                cur.execute(
                    "UPDATE account_deletions SET status=%s,reason=%s WHERE user_id=%s",
                    ("restored", "", uid),
                )
                self.enqueue(
                    cur,
                    "restored:" + row[0],
                    uid,
                    row[3],
                    "Your account has been restored — welcome back!",
                    [
                        "Welcome back, " + row[4] + ".",
                        "Your deletion request is cancelled. Your profile, books and learning history are available again.",
                    ],
                )
            cur.execute(
                "SELECT session_version FROM account_security WHERE user_id=%s", (uid,)
            )
            version = cur.fetchone()
            return version[0] if version else 0

    def decide(self, rid, admin_id, approve):
        with self.store.transaction() as cur:
            cur.execute(
                "SELECT user_id,status,email,display_name FROM account_deletions WHERE request_id=%s FOR UPDATE",
                (rid,),
            )
            row = cur.fetchone()
            if not row or row[1] not in ("requested", "approved"):
                raise AuthError("This request is no longer pending.", 409)
            if approve and self.protected(row[0]):
                raise AuthError(
                    "Administrator accounts cannot be deleted while their role is active.",
                    403,
                )
            status = "approved" if approve else "cancelled"
            cur.execute(
                "UPDATE account_deletions SET status=%s,approved_by=%s,approved_at=%s WHERE request_id=%s",
                (status, admin_id, self.clock(), rid),
            )
            if not approve:
                self.enqueue(
                    cur,
                    "cancelled:" + rid,
                    row[0],
                    row[2],
                    "Account deletion cancelled",
                    [
                        "Hello " + row[3] + ".",
                        "The administrator cancelled your deletion request. You can sign in again.",
                    ],
                )

    def delete_due(self, limit=50):
        now = self.clock()
        rows = self.store.query(
            "SELECT request_id FROM account_deletions WHERE status=%s AND deadline<=%s ORDER BY deadline LIMIT %s",
            ("approved", now, limit),
        )
        deleted = 0
        for (rid,) in rows:
            with self.store.transaction() as cur:
                cur.execute(
                    "SELECT user_id,username,email,display_name,status,deadline FROM account_deletions WHERE request_id=%s FOR UPDATE",
                    (rid,),
                )
                row = cur.fetchone()
                if not row or row[4] != "approved" or row[5] > now:
                    continue
                uid = row[0]
                if self.protected(uid):
                    continue
                # All writers use this request lock before deleting/restoring the account.
                cur.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (uid,))
                if not cur.fetchone():
                    continue
                self._delete_user_rows(cur, uid)
                cur.execute(
                    "UPDATE account_deletions SET status=%s,reason=%s,deleted_at=%s,retention_until=%s WHERE request_id=%s",
                    ("deleted", "", now, now + RETENTION, rid),
                )
                self.enqueue(
                    cur,
                    "deleted:" + rid,
                    uid,
                    row[2],
                    "Your DocoDive account has been deleted",
                    [
                        "Hello " + row[3] + ".",
                        "Your approved deletion request has been completed after the 15-day grace period.",
                        "The administrative deletion record (name, email and deletion timestamp) is retained for 30 days, then removed.",
                    ],
                )
                deleted += 1
        self.purge()
        return deleted

    def _delete_user_rows(self, cur, uid):
        cur.execute(
            "DELETE FROM review_likes WHERE user_id=%s OR review_id IN (SELECT id FROM reviews WHERE user_id=%s)",
            (uid, uid),
        )
        cur.execute(
            "DELETE FROM reply_likes WHERE user_id=%s OR reply_id IN (SELECT id FROM feedback_replies WHERE user_id=%s OR feedback_id IN (SELECT id FROM user_feedback WHERE user_id=%s))",
            (uid, uid, uid),
        )
        cur.execute(
            "UPDATE user_feedback SET like_count=GREATEST(0,like_count-1) WHERE id IN (SELECT feedback_id FROM feedback_likes WHERE user_id=%s)",
            (uid,),
        )
        cur.execute(
            "DELETE FROM feedback_likes WHERE user_id=%s OR feedback_id IN (SELECT id FROM user_feedback WHERE user_id=%s)",
            (uid, uid),
        )
        cur.execute(
            "DELETE FROM feedback_replies WHERE user_id=%s OR feedback_id IN (SELECT id FROM user_feedback WHERE user_id=%s)",
            (uid, uid),
        )
        cur.execute(
            "DELETE FROM book_comments WHERE parent_id IN (SELECT id FROM (SELECT id FROM book_comments WHERE user_id=%s) AS parents) OR parent_id IN (SELECT -id FROM reviews WHERE user_id=%s)",
            (uid, uid),
        )
        for table in (
            "user_feedback",
            "favorites",
            "download_history",
            "reviews",
            "book_comments",
            "user_points",
            "user_streaks",
            "notifications",
            "user_preferences",
            "notification_digest_log",
            "security_otp",
            "admin_login_sessions",
            "account_security",
            "activity_daily",
            "leaderboard_snapshots",
            "lifecycle_mail",
        ):
            cur.execute(f"DELETE FROM {table} WHERE user_id=%s", (uid,))
        cur.execute(
            "UPDATE documents SET uploaded_by=NULL WHERE uploaded_by=%s", (uid,)
        )
        cur.execute("DELETE FROM users WHERE id=%s", (uid,))

    def purge(self):
        now = self.clock()
        with self.store.transaction() as cur:
            cur.execute(
                "DELETE FROM lifecycle_mail WHERE user_id IN (SELECT user_id FROM account_deletions WHERE retention_until<=%s)",
                (now,),
            )
            cur.execute(
                "DELETE FROM account_deletions WHERE retention_until<=%s", (now,)
            )
            cur.execute(
                "DELETE FROM account_deletions WHERE status IN (%s,%s) AND requested_at<%s",
                ("restored", "cancelled", now - RETENTION),
            )
            cur.execute(
                "DELETE FROM lifecycle_mail WHERE sent_at<%s OR created_at<%s",
                (now - RETENTION, now - RETENTION),
            )
            cur.execute(
                "DELETE FROM security_otp WHERE expires_at<%s",
                (now - timedelta(days=1),),
            )
            cur.execute("DELETE FROM admin_login_sessions WHERE expires_at<%s", (now,))
            cur.execute(
                "DELETE FROM security_rate_limits WHERE window_start<%s",
                (now - timedelta(days=2),),
            )

    def deliver_mail(self, limit=20):
        now = self.clock()
        rows = self.store.query(
            "SELECT event_key FROM lifecycle_mail WHERE sent_at IS NULL AND next_attempt<=%s AND (lease_until IS NULL OR lease_until<%s) ORDER BY created_at LIMIT %s",
            (now, now, limit),
        )
        for (key,) in rows:
            with self.store.transaction() as cur:
                cur.execute(
                    "SELECT recipient,subject,body,html,attempts,sent_at,lease_until FROM lifecycle_mail WHERE event_key=%s FOR UPDATE",
                    (key,),
                )
                row = cur.fetchone()
                if not row or row[5] or (row[6] and row[6] > now):
                    continue
                cur.execute(
                    "UPDATE lifecycle_mail SET lease_until=%s WHERE event_key=%s",
                    (now + timedelta(minutes=2), key),
                )
            try:
                sent = self.send_mail(row[1], row[0], row[2], html_body=row[3])
            except Exception:
                sent = False
            with self.store.transaction() as cur:
                cur.execute(
                    "UPDATE lifecycle_mail SET attempts=%s,sent_at=%s,next_attempt=%s,lease_until=NULL WHERE event_key=%s",
                    (
                        row[4] + 1,
                        now if sent else None,
                        now + timedelta(minutes=min(60, 2 ** min(row[4] + 1, 6))),
                        key,
                    ),
                )
            if not sent:
                self.logger.warning(
                    "lifecycle_email_delivery_failed event=%s", key.split(":")[0]
                )
