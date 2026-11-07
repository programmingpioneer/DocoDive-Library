"""Run with installed requirements; no production config/database/network access."""

import ast
import pathlib
import types
import unittest
from flask import Flask, request, session
from werkzeug.security import generate_password_hash
from admin.admin_routes import register_admin
from test_security_regressions import load_function
import hmac
import hashlib
from account_store import Store
import secrets
import re
import shutil
import subprocess
from html.parser import HTMLParser
import json
from flask import render_template
from seo import register_seo

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Cursor:
    def __init__(self, db):
        self.db = db
        self.rows = []
        self.rowcount = 0

    def execute(self, sql, args=()):
        self.db.calls.append((sql, args))
        self.rows = []
        if "SELECT id, password, verified FROM users" in sql:
            self.rows = (
                [(1, self.db.password, 1)] if args[0] == "owner@example.test" else []
            )
        elif "SELECT id, username, email, verified FROM users" in sql:
            self.rows = (
                [(args[0], "owner", "owner@example.test", 1)] if self.db.exists else []
            )
        elif "SELECT password,verified,email FROM users" in sql:
            self.rows = [(self.db.password, 1, "owner@example.test")]
        elif "UPDATE users SET password=" in sql:
            self.db.password = args[0]
        elif sql.strip().startswith("SELECT COUNT(") and "GROUP BY" not in sql:
            self.rows = [(0,)]

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class DB:
    def __init__(self):
        self.calls = []
        self.exists = True
        self.password = generate_password_hash("test-password-only")
        self.connection = self

    def cursor(self):
        return Cursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass


class Limiter:
    def limit(self, *a, **k):
        return lambda fn: fn


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(
            __name__,
            template_folder=str(ROOT / "templates"),
            static_folder=str(ROOT / "static"),
        )
        self.app.config.update(TESTING=True, SECRET_KEY="isolated-test-only")
        self.db = DB()
        self.settings = {"official_user_id": "1", "studio_admin_ids": "[]"}
        tree = ast.parse((ROOT / "admin/admin_routes.py").read_text(encoding="utf-8"))
        keys = {
            n.slice.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Subscript)
            and isinstance(n.value, ast.Name)
            and n.value.id == "services"
            and isinstance(n.slice, ast.Constant)
        }
        self.svc = {key: lambda *a, **kw: None for key in keys}
        self.svc.update(
            mysql=self.db,
            limiter=Limiter(),
            get_site_setting=lambda k, default=None: self.settings.get(k, default),
            set_site_setting=lambda k, v: self.settings.update({k: v}),
            check_login_backoff=lambda *a: (False, 0),
            clear_login_backoff=lambda *a: None,
            record_login_failure=lambda *a: None,
            category_to_slug=lambda s: s.lower(),
            GENERIC_MODULES=[],
            IELTS_MODULES=[],
            is_valid_email=lambda e: "@" in e,
        )
        # Real production CSRF function, loaded without evaluating app.py configuration.
        from flask import abort

        guard = load_function(
            "csrf_protect",
            dict(
                request=request,
                session=session,
                abort=abort,
                secrets=secrets,
                hmac=hmac,
            ),
        )
        self.app.before_request(guard)
        self.app.add_url_rule("/", endpoint="home", view_func=lambda: "public")
        self.app.add_url_rule(
            "/user/upload", endpoint="user_upload", view_func=lambda: "upload"
        )
        self.pending_hash = None

        def issue(*args):
            self.pending_hash = (args[5], args[6])
            return "challenge"

        fake_auth = types.SimpleNamespace(
            valid_session=lambda token, uid: token == "test-session",
            login_gate=lambda *a: None,
            login_failed=lambda *a: None,
            issue=issue,
            digest=lambda text: hashlib.sha256(str(text).encode()).hexdigest(),
            verify=lambda *a: (1, *self.pending_hash),
            new_session=lambda *a: "test-session",
            revoke=lambda *a: None,
            audit=lambda *a: None,
        )
        self.app.extensions["studio_auth"] = fake_auth
        self.app.extensions["account_store"] = Store(self.db)
        register_admin(self.app, self.svc)
        # Register public URL shapes for template link construction only. No project startup.
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        for fn in tree.body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            for dec in fn.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "app"
                    and dec.func.attr == "route"
                    and isinstance(dec.args[0], ast.Constant)
                ):
                    if fn.name not in self.app.view_functions:
                        self.app.add_url_rule(
                            dec.args[0].value, fn.name, lambda **kw: "test placeholder"
                        )
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state["studio_token"] = "test-session"

    def token(self):
        self.client.get("/admin-studio/login")
        with self.client.session_transaction() as state:
            return state["_csrf_token"]

    def test_normal_official_user_session_does_not_grant_studio(self):
        with self.client.session_transaction() as state:
            state["user_id"] = 1
        for path in [
            "/admin-studio/dashboard",
            "/admin/dashboard",
            "/moderation",
            "/api/admin/stats",
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertTrue(response.location.endswith("/admin-studio/login"), path)

    def test_studio_login_creates_only_studio_identity(self):
        token = self.token()
        response = self.client.post(
            "/admin-studio/login",
            data={
                "email": "owner@example.test",
                "password": "test-password-only",
                "_csrf_token": token,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/admin-studio/verify"))
        with self.client.session_transaction() as state:
            self.assertNotIn("studio_user_id", state)
        self.assertEqual(self.client.get("/admin-studio/dashboard").status_code, 302)
        response = self.client.post(
            "/admin-studio/verify", data={"code": "123456", "_csrf_token": token}
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as state:
            self.assertEqual(state["studio_user_id"], 1)
            self.assertNotIn("user_id", state)
        self.assertEqual(self.client.get("/admin-studio/dashboard").status_code, 200)

    def test_revoked_role_and_deleted_account_are_denied(self):
        for exists, owner in [(True, "2"), (False, "1")]:
            self.db.exists = exists
            self.settings["official_user_id"] = owner
            with self.client.session_transaction() as state:
                state["studio_user_id"] = 1
            self.assertEqual(self.client.get("/admin-studio/users").status_code, 302)

    def test_legacy_mutation_requires_csrf_and_studio(self):
        with self.client.session_transaction() as state:
            state["studio_user_id"] = 1
        response = self.client.post(
            "/admin/delete/9", headers={"X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(any("DELETE" in sql for sql, args in self.db.calls))

    def test_logout_preserves_reader_session(self):
        token = self.token()
        with self.client.session_transaction() as state:
            state.update(studio_user_id=1, user_id=7)
        self.client.post("/admin-studio/logout", data={"_csrf_token": token})
        with self.client.session_transaction() as state:
            self.assertNotIn("studio_user_id", state)
            self.assertEqual(state["user_id"], 7)

    def test_all_templates_parse(self):
        for path in (ROOT / "templates").rglob("*.html"):
            self.app.jinja_env.parse(path.read_text(encoding="utf-8"))

    def test_studio_pages_render_and_inline_javascript_parses(self):
        with self.client.session_transaction() as state:
            state["studio_user_id"] = 1
        for path in [
            "/admin-studio/upload",
            "/admin-studio/books",
            "/admin-studio/pending",
            "/admin-studio/users",
            "/admin-studio/analytics",
            "/admin-studio/tracking",
            "/admin-studio/deletions",
            "/admin-studio/reviews",
            "/admin-studio/settings",
            "/admin-studio/learning",
            "/admin-studio/suggestions",
            "/admin-studio/leaderboard",
            "/admin-studio/official-profile",
        ]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers["Cache-Control"])
                if shutil.which("node"):
                    for attrs, script in re.findall(
                        r"<script([^>]*)>(.*?)</script>",
                        response.get_data(as_text=True),
                        re.S,
                    ):
                        if "src=" in attrs or "application/ld+json" in attrs:
                            continue
                        check = subprocess.run(
                            ["node", "--check", "-"],
                            input=script,
                            text=True,
                            encoding="utf-8",
                            capture_output=True,
                        )
                        self.assertEqual(check.returncode, 0, check.stderr)

    def test_studio_settings_persist_without_changing_reader_session(self):
        token = self.token()
        with self.client.session_transaction() as state:
            state.update(studio_user_id=1, user_id=7)
        response = self.client.post(
            "/admin-studio/settings",
            data={"_csrf_token": token, "home_title": "A <safe> title"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("A <safe> title", self.settings["studio_content"])
        with self.client.session_transaction() as state:
            self.assertEqual(state["user_id"], 7)

    def test_bad_reply_payload_does_not_write(self):
        token = self.token()
        with self.client.session_transaction() as state:
            state["studio_user_id"] = 1
        for payload in [[], {"reply_text": 42}, {"reply_text": "x" * 5001}]:
            response = self.client.post(
                "/admin-studio/api/review/3/reply",
                json=payload,
                headers={"X-CSRF-Token": token},
            )
            self.assertEqual(response.status_code, 400)
        self.assertFalse(any("INSERT" in sql for sql, args in self.db.calls))

    def test_public_pages_render_metadata_and_javascript(self):
        register_seo(self.app, self.svc)
        self.app.jinja_env.filters["slugify"] = (
            lambda value: str(value).lower().replace(" ", "-")
        )
        book = dict(
            id=4,
            slug="example",
            title='A "book" <example>',
            author="An Author",
            level="Python",
            description="A useful book.",
            language="English",
            image_url=None,
            download_count=0,
            view_count=0,
            avg_rating=0,
            link="/example.pdf",
        )
        context = dict(
            site_content={},
            hub_content={},
            current_user_is_official=False,
            is_moderator=False,
            user_logged_in=False,
            pdfs=[],
            books=[book],
            book=book,
            reviews=[],
            related_books=[],
            search_query="",
            category="Python",
            category_name="Python",
            category_slug="python",
            author_filter="",
            lang_filter="",
            categories=[],
            all_categories=[],
            category_modules=[],
            page=1,
            total_pages=1,
            has_next=False,
            featured_book=None,
            streak=0,
            longest=0,
            recommended_books=[],
            total_books=1,
            total_downloads=0,
            total_users=0,
            total_categories=1,
            recent_reviews=[],
            user_downloads=0,
            user_favorites=0,
            user_reviews=0,
            q="",
            sort="latest",
            books_jsonld={},
            avg_rating=0,
            breakdown={i: 0 for i in range(1, 6)},
            total_reviews=0,
            feedbacks=[],
            leaderboard=[],
            current_user_rank=None,
            current_user_points=0,
        )
        pages = {
            "index": "/",
            "books": "/books",
            "book_detail": "/book/example/4",
            "learning_hub": "/learn/python",
            "reviews": "/reviews",
            "feedback": "/feedback",
            "leaderboard": "/leaderboard",
        }
        for name, path in pages.items():
            with self.subTest(page=name), self.app.test_request_context(path):
                session["_csrf_token"] = "test-token"
                html = render_template("user/" + name + ".html", **context)
                self.assertNotIn('href="/admin', html)
                self.assertIn('rel="canonical"', html)
                for attrs, script in re.findall(
                    r"<script([^>]*)>(.*?)</script>", html, re.S
                ):
                    if "src=" in attrs:
                        continue
                    if "application/ld+json" in attrs or "application/json" in attrs:
                        json.loads(script)
                    elif shutil.which("node"):
                        check = subprocess.run(
                            ["node", "--check", "-"],
                            input=script,
                            text=True,
                            encoding="utf-8",
                            capture_output=True,
                        )
                        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
