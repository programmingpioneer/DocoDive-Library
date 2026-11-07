"""Callback authentication checks using isolated functions and local fakes only."""

import hmac
import json
import secrets
import sqlite3
import types
import unittest

from flask import Flask, jsonify, request

from test_security_regressions import load_function


class CallbackBoundaryTests(unittest.TestCase):
    def callback_scope(self):
        captured = []
        return captured, dict(
            flash=lambda *args: None,
            redirect=lambda url: url,
            url_for=lambda endpoint, **values: endpoint,
            handle_social_login=lambda provider, info: (captured.append((provider, info.copy())) or (None, False)),
        )

    def test_google_callback_passes_verified_email_assertion_to_linking(self):
        for verified in (True, False):
            with self.subTest(verified=verified):
                captured, scope = self.callback_scope()
                profile = dict(id="google-7", email="reader@example.test", verified_email=verified)
                scope.update(
                    session={"google_oauth_state": "expected"},
                    request=types.SimpleNamespace(args={"state": "expected", "code": "local-code"}),
                    hmac=hmac,
                    os=types.SimpleNamespace(getenv=lambda name: None),
                    requests=types.SimpleNamespace(
                        post=lambda *args, **kwargs: types.SimpleNamespace(json=lambda: {"access_token": secrets.token_hex(16)}),
                        get=lambda *args, **kwargs: types.SimpleNamespace(json=lambda: profile.copy()),
                    ),
                )
                load_function("google_callback", scope)()
                self.assertIs(captured[0][1].get("email_verified"), verified)

    def test_github_callback_selects_only_verified_primary_email(self):
        for emails, expected in (
            ([dict(email="primary@example.test", primary=True, verified=True)], "primary@example.test"),
            ([dict(email="unverified@example.test", primary=True, verified=False), dict(email="secondary@example.test", primary=False, verified=True)], None),
        ):
            with self.subTest(has_verified_primary=expected is not None):
                captured, scope = self.callback_scope()

                class Github:
                    def authorize_access_token(self):
                        return {}

                    def get(self, resource):
                        data = dict(id=7, login="reader", email="public@example.test") if resource == "user" else emails
                        return types.SimpleNamespace(json=lambda: data)

                scope["oauth"] = types.SimpleNamespace(github=Github())
                load_function("github_callback", scope)()
                self.assertEqual(captured[0][1]["email"], expected)
                self.assertIs(captured[0][1].get("email_verified"), expected is not None)

    def social_login(self, provider, verified, already_linked=False, email_provider_id=None):
        updates = []

        class SocialCursor:
            rowcount = 1

            def execute(self, sql, args=()):
                if sql.startswith("SELECT id FROM users WHERE email"):
                    self.row = (7, email_provider_id)
                elif "WHERE email = %s" in sql and sql.startswith("SELECT id,"):
                    self.row = (7, email_provider_id)
                elif sql.startswith("SELECT id FROM users WHERE "):
                    self.row = (7,) if already_linked else None
                else:
                    self.row = None
                    updates.append((sql, args))

            def fetchone(self):
                return self.row

            def close(self):
                pass

        db = types.SimpleNamespace(connection=types.SimpleNamespace(cursor=SocialCursor, commit=lambda: None))
        info = dict(sub="provider-7", email="reader@example.test", name="Reader", email_verified=verified)
        result = load_function("handle_social_login", dict(mysql=db))(provider, info)
        return result, updates

    def test_unverified_provider_email_cannot_bind_existing_account(self):
        for provider in ("google", "github", "facebook"):
            with self.subTest(provider=provider):
                result, updates = self.social_login(provider, False)
                self.assertEqual(result, (None, False))
                self.assertEqual(updates, [])

    def test_verified_provider_email_can_bind_existing_account(self):
        for provider in ("google", "github"):
            with self.subTest(provider=provider):
                result, updates = self.social_login(provider, True)
                self.assertEqual(result, (7, False))
                self.assertEqual(len(updates), 1)

    def test_facebook_has_no_verified_email_assertion_for_new_linking(self):
        result, updates = self.social_login("facebook", True)
        self.assertEqual(result, (None, False))
        self.assertEqual(updates, [])

    def test_verified_email_does_not_replace_an_existing_provider_binding(self):
        for provider in ("google", "github"):
            with self.subTest(provider=provider):
                result, updates = self.social_login(provider, True, email_provider_id="different-provider-identity")
                self.assertEqual(result, (None, False))
                self.assertEqual(updates, [])

    def test_concurrent_provider_binding_does_not_sign_in_a_different_identity(self):
        raw = sqlite3.connect(":memory:")
        self.addCleanup(raw.close)
        raw.execute("CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT,google_id TEXT,avatar_url TEXT)")
        raw.execute("INSERT INTO users(id,email) VALUES(7,'reader@example.test')")

        class RaceCursor:
            def __init__(self):
                self.raw = raw.cursor()

            def execute(self, sql, args=()):
                if sql.startswith("UPDATE users SET google_id"):
                    raw.execute("UPDATE users SET google_id='concurrent-identity' WHERE id=7")
                self.raw.execute(sql.replace("%s", "?"), args)

            def fetchone(self):
                return self.raw.fetchone()

            @property
            def rowcount(self):
                return self.raw.rowcount

            def close(self):
                self.raw.close()

        db = types.SimpleNamespace(connection=types.SimpleNamespace(cursor=RaceCursor, commit=raw.commit))
        info = dict(sub="new-identity", email="reader@example.test", name="Reader", email_verified=True)
        result = load_function("handle_social_login", dict(mysql=db))("google", info)
        self.assertEqual(result, (None, False))
        self.assertEqual(raw.execute("SELECT google_id FROM users WHERE id=7").fetchone()[0], "concurrent-identity")

    def test_bound_provider_identity_can_sign_in_without_email_assertion(self):
        for provider in ("google", "github", "facebook"):
            with self.subTest(provider=provider):
                result, updates = self.social_login(provider, False, already_linked=True)
                self.assertEqual(result, (7, False))
                self.assertEqual(updates, [])

    def webhook(self, configured_secret, supplied_secret=None):
        logged = []
        app = Flask(__name__)
        app.config["TESTING"] = True
        scope = dict(
            os=types.SimpleNamespace(getenv=lambda name: configured_secret),
            request=request,
            jsonify=jsonify,
            hmac=hmac,
            json=json,
            app=types.SimpleNamespace(logger=types.SimpleNamespace(info=lambda *args: logged.append(args))),
        )
        app.add_url_rule("/api/brevo/webhook", view_func=load_function("brevo_webhook", scope), methods=["POST"])
        headers = {"X-Webhook-Secret": supplied_secret} if supplied_secret else {}
        return app.test_client().post("/api/brevo/webhook", json={"event": "delivered"}, headers=headers), logged

    def test_webhook_is_unavailable_without_configured_authentication(self):
        response, logged = self.webhook(None)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(logged, [])

    def test_webhook_rejects_missing_or_wrong_authentication(self):
        configured = secrets.token_hex(32)
        for supplied in (None, secrets.token_hex(32)):
            with self.subTest(missing=supplied is None):
                response, logged = self.webhook(configured, supplied)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(logged, [])

    def test_webhook_accepts_configured_authentication(self):
        configured = secrets.token_hex(32)
        response, logged = self.webhook(configured, configured)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "received"})
        self.assertEqual(len(logged), 1)


if __name__ == "__main__":
    unittest.main()
