"""Real local SQL transactions in SQLite; MySQL adapter syntax is translated only here."""

import logging
import pathlib
import re
import sqlite3
import unittest
from datetime import datetime, timedelta
from account_store import Store
from studio_auth import StudioAuth, AuthError
from account_lifecycle import AccountLifecycle

ROOT = pathlib.Path(__file__).resolve().parents[1]
sqlite3.register_adapter(datetime, lambda value: value.isoformat(" "))
sqlite3.register_converter(
    "DATETIME", lambda value: datetime.fromisoformat(value.decode())
)


class Cursor:
    def __init__(self, connection):
        self.raw = connection.cursor()

    def execute(self, sql, args=()):
        sql = (
            sql.replace("%s", "?")
            .replace(" FOR UPDATE", "")
            .replace("INSERT IGNORE", "INSERT OR IGNORE")
            .replace("GREATEST(", "MAX(")
        )
        self.raw.execute(sql, args)
        return self

    def fetchone(self):
        return self.raw.fetchone()

    def fetchall(self):
        return self.raw.fetchall()

    @property
    def rowcount(self):
        return self.raw.rowcount

    def close(self):
        self.raw.close()


class DB:
    def __init__(self):
        self.raw = sqlite3.connect(
            ":memory:", detect_types=sqlite3.PARSE_DECLTYPES, isolation_level=None
        )
        self.connection = self
        schema = (ROOT / "migrations/20261029_studio_accounts.sql").read_text()
        schema = re.sub(r",?\s*INDEX\s+\w+\s*\([^)]*\)", "", schema)
        schema = schema.replace(" ENGINE=InnoDB", "")
        self.raw.executescript(schema)
        self.raw.executescript(
            """CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,email TEXT,first_name TEXT,last_name TEXT,created_at DATETIME,password TEXT,verified INTEGER);
        CREATE TABLE documents(id INTEGER PRIMARY KEY,uploaded_by INTEGER);
        CREATE TABLE user_feedback(id INTEGER PRIMARY KEY,user_id INTEGER,like_count INTEGER);
        CREATE TABLE feedback_replies(id INTEGER PRIMARY KEY,user_id INTEGER,feedback_id INTEGER);
        CREATE TABLE feedback_likes(user_id INTEGER,feedback_id INTEGER);
        CREATE TABLE reply_likes(user_id INTEGER,reply_id INTEGER);
        CREATE TABLE reviews(id INTEGER PRIMARY KEY,user_id INTEGER,book_id INTEGER);
        CREATE TABLE review_likes(user_id INTEGER,review_id INTEGER);
        CREATE TABLE book_comments(id INTEGER PRIMARY KEY,user_id INTEGER,parent_id INTEGER,book_id INTEGER);"""
        )
        for table in (
            "favorites",
            "download_history",
            "user_points",
            "user_streaks",
            "notifications",
            "user_preferences",
            "notification_digest_log",
        ):
            self.raw.execute(
                "CREATE TABLE " + table + "(user_id INTEGER,book_id INTEGER)"
            )

    def cursor(self):
        return Cursor(self.raw)

    def start_transaction(self):
        self.raw.execute("BEGIN IMMEDIATE")

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.db = DB()
        self.store = Store(self.db)
        self.now = datetime(2026, 10, 29, 12)
        self.sent = []

        def send(subject, email, body, html_body=None):
            self.sent.append((subject, email, body, html_body))
            return True

        self.send = send
        self.auth = StudioAuth(
            self.store, "test-secret", send, logging.getLogger("test"), lambda: self.now
        )
        self.life = AccountLifecycle(
            self.store,
            send,
            logging.getLogger("test"),
            lambda uid: False,
            lambda: self.now,
        )
        self.db.raw.execute(
            "INSERT INTO users VALUES (1,?,?,?,?,?,?,?)",
            ("reader", "reader@example.test", "A", "Reader", self.now, "old-hash", 1),
        )

    def test_welcome_is_styled_and_queued_once(self):
        self.life.welcome(1)
        self.life.welcome(1)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("Welcome", self.sent[0][3])
        self.assertEqual(
            self.store.query("SELECT COUNT(*) FROM lifecycle_mail", one=True)[0], 1
        )

    def test_score_snapshot_keeps_first_daily_value(self):
        self.db.raw.execute("ALTER TABLE user_points ADD COLUMN points INTEGER")
        self.db.raw.execute("INSERT INTO user_points VALUES (1,NULL,10)")
        self.life.capture_scores()
        self.db.raw.execute("UPDATE user_points SET points=25")
        self.life.capture_scores()
        self.assertEqual(
            self.store.query("SELECT points FROM leaderboard_snapshots", one=True)[0],
            10,
        )
        self.now += timedelta(days=1)
        self.life.capture_scores()
        self.assertEqual(
            len(self.store.query("SELECT * FROM leaderboard_snapshots")), 2
        )

    def test_http_tracking_records_successful_downloads_only(self):
        from flask import Flask, g, redirect
        from unittest.mock import patch
        from account_routes import register_accounts

        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="isolated-test")
        with patch("admin.security.has_role", lambda uid: False):
            register_accounts(
                app, dict(mysql=self.db, send_email_notification=self.send)
            )

        @app.get("/download")
        def download():
            g.download_recorded = True
            return redirect("/file")

        @app.get("/failed-download")
        def failed_download():
            return redirect("/error")

        client = app.test_client()
        with client.session_transaction() as state:
            state["user_id"] = 1
        client.get("/failed-download")
        self.assertEqual(self.store.query("SELECT * FROM activity_daily"), [])
        client.get("/download")
        self.assertEqual(
            self.store.query(
                "SELECT page_views,downloads FROM activity_daily", one=True
            ),
            (0, 1),
        )

    def test_password_upgrade_preserves_legacy_login(self):
        from password_security import (
            generate_password_hash,
            check_password_hash,
            needs_rehash,
        )
        from werkzeug.security import generate_password_hash as legacy_hash

        old = legacy_hash("Example-password-1")
        self.assertTrue(check_password_hash(old, "Example-password-1"))
        self.assertTrue(needs_rehash(old))
        new = generate_password_hash("Example-password-1")
        self.assertTrue(new.startswith("$argon2id$"))
        self.assertTrue(check_password_hash(new, "Example-password-1"))
        self.assertFalse(check_password_hash(new, "wrong"))
        self.assertFalse(needs_rehash(new))

    def issue(self, purpose="admin_login"):
        challenge = self.auth.issue(
            1,
            purpose,
            "browser-binding",
            "reader@example.test",
            "127.0.0.1",
            "argon-hash",
            "fingerprint",
        )
        code = re.search(r"code is (\d{6})", self.sent[-1][2]).group(1)
        return challenge, code

    def test_otp_is_hashed_bound_single_use_and_creates_no_session(self):
        challenge, code = self.issue()
        stored = self.store.query("SELECT code_hash FROM security_otp", one=True)[0]
        self.assertNotEqual(code, stored)
        self.assertEqual(self.store.query("SELECT * FROM admin_login_sessions"), [])
        with self.assertRaises(AuthError):
            self.auth.verify(challenge, "admin_login", "different-browser", code)
        self.assertEqual(
            self.auth.verify(challenge, "admin_login", "browser-binding", code)[0], 1
        )
        with self.assertRaises(AuthError):
            self.auth.verify(challenge, "admin_login", "browser-binding", code)

    def test_otp_expiry_and_three_attempt_limit(self):
        challenge, code = self.issue()
        wrong = "000000" if code != "000000" else "999999"
        for _ in range(3):
            with self.assertRaises(AuthError):
                self.auth.verify(challenge, "admin_login", "browser-binding", wrong)
        with self.assertRaises(AuthError):
            self.auth.verify(challenge, "admin_login", "browser-binding", code)
        self.now += timedelta(seconds=61)
        challenge, code = self.issue()
        self.now += timedelta(minutes=5)
        with self.assertRaises(AuthError):
            self.auth.verify(challenge, "admin_login", "browser-binding", code)

    def test_resend_cooldown_hourly_cap_and_replacement(self):
        old, oldcode = self.issue()
        with self.assertRaises(AuthError):
            self.issue()
        for _ in range(3):
            self.now += timedelta(seconds=61)
            self.issue()
        self.now += timedelta(seconds=61)
        with self.assertRaises(AuthError):
            self.issue()
        with self.assertRaises(AuthError):
            self.auth.verify(old, "admin_login", "browser-binding", oldcode)

    def test_delivery_failure_cannot_authenticate(self):
        self.auth.send_mail = lambda *a, **kw: False
        with self.assertRaises(AuthError):
            self.issue()
        row = self.store.query("SELECT sent,consumed_at FROM security_otp", one=True)
        self.assertEqual(row[0], 0)
        self.assertIsNotNone(row[1])

    def test_persistent_account_throttle_is_independent_of_ip(self):
        for i in range(5):
            self.auth.login_gate("reader@example.test", str(i))
        with self.assertRaises(AuthError):
            self.auth.login_gate("reader@example.test", "new-ip")
        self.now += timedelta(minutes=16)
        self.auth.login_gate("reader@example.test", "new-ip")

    def test_session_expiry_password_change_and_revocation(self):
        token = self.auth.new_session(1, self.auth.digest("old-hash"))
        self.assertTrue(self.auth.valid_session(token, 1))
        self.db.raw.execute("UPDATE users SET password='changed' WHERE id=1")
        self.assertFalse(self.auth.valid_session(token, 1))
        token = self.auth.new_session(1, self.auth.digest("changed"))
        self.auth.revoke(token)
        self.assertFalse(self.auth.valid_session(token, 1))
        token = self.auth.new_session(1, self.auth.digest("changed"))
        self.now += timedelta(hours=8)
        self.assertFalse(self.auth.valid_session(token, 1))

    def test_deletion_requires_approval_and_exact_15_day_grace(self):
        rid = self.life.request_deletion(1, "I no longer need this account.")
        self.assertEqual(self.life.version(1), 1)
        self.assertEqual(self.life.delete_due(), 0)
        self.now += timedelta(days=15)
        self.assertEqual(self.life.delete_due(), 0)  # unapproved stays pending
        with self.assertRaises(AuthError):
            self.life.on_login(1)
        self.life.decide(rid, 99, True)
        self.assertEqual(self.life.delete_due(), 1)
        self.assertEqual(self.life.delete_due(), 0)
        self.assertIsNone(self.store.query("SELECT id FROM users WHERE id=1", one=True))

    def test_restoration_cancels_approved_deletion_and_queues_email_once(self):
        rid = self.life.request_deletion(1, "I no longer need this account.")
        self.life.decide(rid, 99, True)
        self.now += timedelta(days=14)
        self.life.on_login(1)
        self.life.on_login(1)
        self.now += timedelta(days=2)
        self.assertEqual(self.life.delete_due(), 0)
        self.assertEqual(
            self.store.query(
                "SELECT COUNT(*) FROM lifecycle_mail WHERE event_key LIKE 'restored:%'",
                one=True,
            )[0],
            1,
        )

    def test_recently_deleted_identifiers_are_purged_after_30_days(self):
        rid = self.life.request_deletion(1, "I no longer need this account.")
        self.life.decide(rid, 99, True)
        self.now += timedelta(days=15)
        self.life.delete_due()
        self.assertEqual(
            self.store.query("SELECT email FROM account_deletions", one=True)[0],
            "reader@example.test",
        )
        self.now += timedelta(days=30)
        self.life.purge()
        self.assertEqual(self.store.query("SELECT * FROM account_deletions"), [])
        self.assertEqual(self.store.query("SELECT * FROM lifecycle_mail"), [])

    def test_mail_retry_preserves_pending_delivery(self):
        self.life.request_deletion(1, "I no longer need this account.")
        self.life.send_mail = lambda *a, **kw: False
        self.life.deliver_mail()
        self.assertIsNone(
            self.store.query("SELECT sent_at FROM lifecycle_mail", one=True)[0]
        )
        self.life.send_mail = self.send
        self.now += timedelta(minutes=3)
        self.life.deliver_mail()
        self.assertIsNotNone(
            self.store.query("SELECT sent_at FROM lifecycle_mail", one=True)[0]
        )

    def test_missing_or_pending_accounts_never_accept_a_saved_cookie(self):
        version = self.life.on_login(1)
        self.assertTrue(self.life.active_session(1, version))
        rid = self.life.request_deletion(1, "I no longer need this account.")
        self.assertFalse(self.life.active_session(1, version))
        self.assertFalse(self.life.active_session(1, self.life.version(1)))
        self.life.decide(rid, 99, True)
        self.now += timedelta(days=15)
        self.life.delete_due()
        self.assertFalse(self.life.active_session(1, 0))
        with self.assertRaises(AuthError):
            self.life.on_login(1)

    def tearDown(self):
        self.db.raw.close()
