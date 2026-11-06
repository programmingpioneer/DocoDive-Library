"""Newsletter persistence and provider boundaries without app startup or network."""

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import unittest

from flask import Flask, abort, flash, jsonify, redirect, request, session, url_for


ROOT = Path(__file__).resolve().parents[1]


class Cursor:
    def __init__(self, database):
        self.database = database
        self.raw = database.raw.cursor()
        self.rowcount = 0

    def execute(self, sql, args=()):
        translated = sql.replace("%s", "?").replace("INSERT IGNORE", "INSERT OR IGNORE")
        translated = translated.replace("UTC_TIMESTAMP(6)", "CURRENT_TIMESTAMP")
        with self.database.lock:
            self.raw.execute(translated, args)
            self.rowcount = self.raw.rowcount

    def close(self):
        with self.database.lock:
            self.raw.close()


class Database:
    def __init__(self):
        self.connection = self
        self.lock = threading.RLock()
        self.raw = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
        self.raw.execute("""CREATE TABLE newsletter_welcomes (
            email_key TEXT PRIMARY KEY, welcome_status TEXT NOT NULL,
            claimed_at TEXT NOT NULL, completed_at TEXT)""")

    def cursor(self):
        return Cursor(self)

    def commit(self):
        with self.lock:
            self.raw.commit()


class Limiter:
    def __init__(self):
        self.guarded = set()

    def limit(self, value):
        def decorate(fn):
            self.guarded.add(fn.__name__)
            return fn
        return decorate


class NewsletterSubscribeTests(unittest.TestCase):
    def setUp(self):
        self.database = Database()
        self.addCleanup(self.database.raw.close)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="newsletter-fixtures-only",
                               PUBLIC_SITE_URL="https://library.example.test",
                               SUPPORT_EMAIL="help@example.test")
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8-sig"))
        # Real endpoint names and URL decorators prevent a fixture-only endpoint
        # from hiding a production BuildError in the welcome email links.
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in {
                    "home", "all_books", "learning_hub", "contact_page", "privacy_policy"}:
                for decorator in node.decorator_list:
                    if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                            and isinstance(decorator.func.value, ast.Name)
                            and decorator.func.value.id == "app" and decorator.func.attr == "route"
                            and decorator.args and isinstance(decorator.args[0], ast.Constant)):
                        self.app.add_url_rule(decorator.args[0].value, node.name, lambda **kwargs: "Fixture")
        self.contacts, self.messages = [], []
        self.contact_result, self.mail_result = True, True
        self.contact_barrier = None
        self.trace_lock = threading.Lock()
        self.limiter = Limiter()

        def contact(email, *args):
            with self.trace_lock:
                self.contacts.append(email)
            if self.contact_barrier:
                self.contact_barrier.wait(timeout=5)
            if isinstance(self.contact_result, Exception):
                raise self.contact_result
            return self.contact_result

        def send(subject, recipient, body, html_body=None):
            with self.trace_lock:
                self.messages.append(dict(subject=subject, recipient=recipient,
                                          text=body, html=html_body))
            if isinstance(self.mail_result, Exception):
                raise self.mail_result
            return self.mail_result

        scope = dict(app=self.app, mysql=self.database, request=request, session=session,
                     abort=abort, flash=flash, jsonify=jsonify, redirect=redirect,
                     url_for=url_for, re=re, hashlib=hashlib, secrets=secrets, hmac=hmac,
                     sync_brevo_contact=contact, send_email_notification=send,
                     limiter=self.limiter, AUTH_RATELIMIT="5 per minute")
        names = {"csrf_protect", "is_valid_email", "newsletter_subscribe",
                 "normalize_newsletter_email", "claim_newsletter_welcome",
                 "record_newsletter_welcome_result", "make_newsletter_welcome_email"}
        functions = [node for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name in names]
        exec(compile(ast.Module(body=functions, type_ignores=[]), "newsletter-fixture", "exec"), scope)

    def post(self, email="Reader@Example.test", ajax=True, base_url=None):
        client = self.app.test_client()
        with client.session_transaction(**({"base_url": base_url} if base_url else {})) as state:
            state["_csrf_token"] = "newsletter-token"
        return client.post("/newsletter/subscribe",
                           data={"email": email, "_csrf_token": "newsletter-token"},
                           headers={"X-Requested-With": "XMLHttpRequest"} if ajax else {},
                           **({"base_url": base_url} if base_url else {}))

    def rows(self):
        return self.database.raw.execute(
            "SELECT email_key,welcome_status FROM newsletter_welcomes").fetchall()

    def test_new_subscription_claims_once_and_sends_polished_text_and_html(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["welcome_email"], "accepted")
        self.assertEqual(self.contacts, ["reader@example.test"])
        self.assertEqual(len(self.messages), 1)
        message = self.messages[0]
        self.assertEqual(message["recipient"], "reader@example.test")
        self.assertIn("Welcome", message["subject"])
        self.assertIn("https://library.example.test/books", message["html"])
        self.assertIn("https://library.example.test/books", message["text"])
        self.assertNotIn("localhost", message["html"])
        self.assertEqual(self.rows(), [(hashlib.sha256(b"reader@example.test").hexdigest(), "accepted")])
        self.assertIn("newsletter_subscribe", self.limiter.guarded)

    def test_repeats_and_case_variants_do_not_send_another_welcome(self):
        self.post(" Reader@Example.test ")
        response = self.post("reader@EXAMPLE.TEST")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["welcome_email"], "already_requested")
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.contacts, ["reader@example.test", "reader@example.test"])

    def test_concurrent_first_subscriptions_have_one_durable_welcome_claim(self):
        self.contact_barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(self.post, ["reader@example.test", "READER@EXAMPLE.TEST"]))
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(sorted(response.get_json()["welcome_email"] for response in responses),
                         ["accepted", "already_requested"])
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(len(self.rows()), 1)

    def test_provider_failure_is_not_reported_as_subscription_success_or_welcome(self):
        for result in [False, RuntimeError("fixture provider unavailable")]:
            self.contact_result = result
            response = self.post()
            self.assertEqual(response.status_code, 500)
            self.assertIn("error", response.get_json())
        self.assertEqual(self.messages, [])
        self.assertEqual(self.rows(), [])

    def test_failed_or_ambiguous_send_is_honest_and_never_retried(self):
        for result in [False, RuntimeError("fixture timeout")]:
            with self.subTest(result=type(result).__name__):
                self.database.raw.execute("DELETE FROM newsletter_welcomes")
                self.messages.clear()
                self.mail_result = result
                response = self.post()
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.get_json()["success"])
                self.assertEqual(response.get_json()["welcome_email"], "unconfirmed")
                self.assertIn("couldn", response.get_json()["message"].lower())
                self.assertEqual(self.rows()[0][1], "unconfirmed")
                self.post()
                self.assertEqual(len(self.messages), 1)

    def test_preexisting_claim_survives_restart_without_automatic_resend(self):
        key = hashlib.sha256(b"reader@example.test").hexdigest()
        self.database.raw.execute("INSERT INTO newsletter_welcomes VALUES (?,'claimed','2026-11-06',NULL)", (key,))
        response = self.post()
        self.assertEqual(response.get_json()["welcome_email"], "already_requested")
        self.assertEqual(self.messages, [])

    def test_missing_ledger_fails_closed_before_email(self):
        self.database.raw.execute("DROP TABLE newsletter_welcomes")
        response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.get_json())
        self.assertEqual(self.messages, [])

    def test_invalid_addresses_never_reach_provider_or_database(self):
        values = ["", "invalid", "a..b@example.test", ".a@example.test", "a.@example.test",
                  "a@-example.test", "a@example-.test", "a@foo..test", "a@" + "x" * 64 + ".test",
                  "a" * 65 + "@example.test", "a@example.test\r\nBcc:other@example.test",
                  "reader@mailinator.com", "a@exa_mple.test", "a@" + "a." * 125 + "test"]
        for value in values:
            with self.subTest(value=value[:40]):
                self.assertEqual(self.post(value).status_code, 400)
        self.assertEqual(self.contacts, [])
        self.assertEqual(self.messages, [])
        self.assertEqual(self.rows(), [])

    def test_native_form_keeps_redirect_and_flash_feedback(self):
        response = self.post(ajax=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/"))
        with self.app.test_client() as client:
            with client.session_transaction() as state:
                state["_csrf_token"] = "newsletter-token"
            response = client.post("/newsletter/subscribe", data={"email": "bad", "_csrf_token": "newsletter-token"})
            self.assertEqual(response.status_code, 302)
            with client.session_transaction() as state:
                self.assertIn("valid email", state["_flashes"][0][1])

    def test_csrf_stays_required_for_native_and_ajax_submissions(self):
        for headers in [{}, {"X-Requested-With": "XMLHttpRequest"}]:
            response = self.app.test_client().post("/newsletter/subscribe", data={"email": "reader@example.test"}, headers=headers)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.contacts, [])
        self.assertEqual(self.messages, [])

    def test_fallback_links_ignore_host_and_use_real_privacy_endpoint(self):
        self.app.config["PUBLIC_SITE_URL"] = ""
        response = self.post(base_url="https://attacker.example.test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("https://docodive-library.onrender.com/privacy", self.messages[0]["html"])
        self.assertIn("https://docodive-library.onrender.com/books", self.messages[0]["text"])
        self.assertNotIn("attacker", self.messages[0]["html"])
        self.assertNotIn("attacker", self.messages[0]["text"])

    def test_unsafe_site_configuration_fails_before_contact_sync_or_claim(self):
        for base in ["http://public.example.test", "https://user:password@example.test",
                     "https://example.test?redirect=bad", "https://example.test/#fragment",
                     "https://example.test/\r\ninjected", "https://example.test:999999",
                     "javascript:alert(1)", "https:///missing-host", "https://example.test/path"]:
            with self.subTest(base=base):
                self.app.config["PUBLIC_SITE_URL"] = base
                self.assertEqual(self.post().status_code, 500)
        self.assertEqual(self.contacts, [])
        self.assertEqual(self.messages, [])
        self.assertEqual(self.rows(), [])

    def test_explicit_local_http_configuration_remains_available_for_preview(self):
        self.app.config["PUBLIC_SITE_URL"] = "http://127.0.0.1:5012"
        response = self.post(base_url="https://attacker.example.test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("http://127.0.0.1:5012/books", self.messages[0]["html"])


if __name__ == "__main__":
    unittest.main()
