"""Exercise review routes against isolated SQLite, without configured app startup."""

import ast
from datetime import datetime
import hmac
from pathlib import Path
import re
import secrets
import sqlite3
import types
import unittest

from flask import Flask, abort, jsonify, request, session
from admin.admin_routes import register_admin


ROOT = Path(__file__).resolve().parents[1]
sqlite3.register_converter("REVIEW_TIMESTAMP", lambda raw: datetime.fromisoformat(raw.decode()))


class Cursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def execute(self, sql, args=()):
        self.cursor.execute(sql.replace("%s", "?"),
                            tuple(value.isoformat(" ") if isinstance(value, datetime) else value
                                  for value in args))

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()


class Database:
    def __init__(self):
        self.connection = self
        self.db = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
        self.db.create_function("CONCAT", -1, lambda *parts: "".join(parts))
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT,
                first_name TEXT, last_name TEXT, avatar_url TEXT, email TEXT, verified INTEGER);
            CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT, author TEXT,
                slug TEXT, approved INTEGER);
            CREATE TABLE reviews (id INTEGER PRIMARY KEY, user_id INTEGER,
                book_id INTEGER REFERENCES documents(id), rating INTEGER,
                comment TEXT, created_at REVIEW_TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE user_points (user_id INTEGER, points INTEGER,
                action TEXT, book_id INTEGER REFERENCES documents(id));
            CREATE TABLE book_comments (id INTEGER PRIMARY KEY, user_id INTEGER,
                book_id INTEGER REFERENCES documents(id), parent_id INTEGER,
                comment TEXT, created_at REVIEW_TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE review_likes (review_id INTEGER, user_id INTEGER);
            INSERT INTO users VALUES (1,'reader','Ada','Reader',NULL,'reader@example.test',1);
            INSERT INTO documents VALUES (4,'A public book','An Author','a-public-book',1);
            INSERT INTO documents VALUES (5,'Private draft','A Secret','private-draft',0);
        """)

    def cursor(self):
        return Cursor(self.db)

    def commit(self):
        self.db.commit()


class Limiter:
    def __init__(self):
        self.guarded = set()

    def limit(self, value):
        def decorate(fn):
            self.guarded.add(fn.__name__)
            return fn
        return decorate


def isolated_app(database):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="local-review-tests-only")
    limiter = Limiter()
    scope = dict(app=app, mysql=database, limiter=limiter,
                 AUTH_RATELIMIT="5 per minute", PUBLIC_RATELIMIT="60 per minute",
                 request=request, session=session, jsonify=jsonify, abort=abort,
                 hmac=hmac, secrets=secrets, re=re,
                 render_template=lambda name, **data: jsonify(data))
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8-sig"))
    wanted = {"csrf_protect", "award_points", "add_review", "reviews_page",
              "review_book_search"}
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in wanted]
    exec(compile(ast.Module(body=functions, type_ignores=[]), "isolated-reviews", "exec"), scope)
    return app, limiter


class OptionalReviewBackendTests(unittest.TestCase):
    def setUp(self):
        self.database = Database()
        self.addCleanup(self.database.db.close)
        self.app, self.limiter = isolated_app(self.database)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(user_id=1, _csrf_token="review-token")

    def post(self, path="/api/reviews", **fields):
        return self.client.post(path, data={"rating": "4", "comment": "Useful library",
                                            "_csrf_token": "review-token", **fields})

    def test_general_feedback_persists_null_book_and_receives_points(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["book_title"])
        self.assertEqual(self.database.db.execute(
            "SELECT user_id,book_id,rating,comment FROM reviews").fetchall(),
            [(1, None, 4, "Useful library")])
        self.assertEqual(self.database.db.execute(
            "SELECT user_id,points,book_id,action FROM user_points").fetchall(),
            [(1, 5, None, "review")])

    def test_approved_book_works_through_new_and_legacy_routes(self):
        for path, fields in [("/api/reviews", {"book_id": "4"}),
                             ("/book/4/review", {}),
                             ("/book/a-public-book/4/review", {})]:
            with self.subTest(path=path):
                response = self.post(path, **fields)
                self.assertEqual(response.status_code, 200)
        self.assertEqual(self.database.db.execute(
            "SELECT book_id FROM reviews").fetchall(), [(4,), (4,), (4,)])
        self.assertIn("add_review", self.limiter.guarded)

    def test_submission_requires_session_and_global_csrf_on_all_routes(self):
        for path in ["/api/reviews", "/book/4/review", "/book/a-public-book/4/review"]:
            with self.subTest(path=path):
                self.assertEqual(self.post(path, _csrf_token="wrong").status_code, 403)
                with self.client.session_transaction() as state:
                    state.pop("user_id", None)
                self.assertEqual(self.post(path).status_code, 401)
                with self.client.session_transaction() as state:
                    state["user_id"] = 1
        self.assertEqual(self.database.db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)

    def test_blank_book_value_is_general_feedback(self):
        self.assertEqual(self.post(book_id="  ").status_code, 200)
        self.assertEqual(self.database.db.execute("SELECT book_id FROM reviews").fetchall(), [(None,)])

    def test_invalid_input_does_not_persist_or_award_points(self):
        cases = [(dict(book_id="x"), 400), (dict(book_id="0"), 400),
                 (dict(book_id="-4"), 400), (dict(book_id="4.5"), 400),
                 (dict(book_id="999999999999999999999999999999"), 400),
                 (dict(book_id="5"), 404), (dict(book_id="404"), 404),
                 (dict(rating="nope"), 400), (dict(rating="0"), 400),
                 (dict(rating="6"), 400), (dict(comment=" \n "), 400),
                 (dict(comment="x" * 5001), 400)]
        for fields, status in cases:
            with self.subTest(fields=list(fields), value=list(fields.values())[0][:30]):
                self.assertEqual(self.post(**fields).status_code, status)
        self.assertEqual(self.database.db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
        self.assertEqual(self.database.db.execute("SELECT COUNT(*) FROM user_points").fetchone()[0], 0)

    def test_maximum_comment_length_is_accepted(self):
        self.assertEqual(self.post(comment="x" * 5000).status_code, 200)

    def test_legacy_book_routes_keep_rating_only_submissions(self):
        for path in ["/book/4/review", "/book/a-public-book/4/review"]:
            self.assertEqual(self.post(path, comment="").status_code, 200)
        self.assertEqual(self.database.db.execute(
            "SELECT book_id,rating,comment FROM reviews").fetchall(), [(4, 4, ""), (4, 4, "")])

    def test_public_review_metadata_keeps_general_and_hides_unapproved_books(self):
        self.database.db.executemany(
            "INSERT INTO reviews (id,user_id,book_id,rating,comment) VALUES (?,1,?,4,?)",
            [(1, None, "General feedback"), (2, 4, "Book feedback"),
             (3, 5, "Draft feedback")])
        response = self.client.get("/reviews")
        self.assertEqual(response.status_code, 200)
        rows = {row["review_id"]: row for row in response.get_json()["reviews"]}
        self.assertIsNone(rows[1]["book_id"])
        self.assertIsNone(rows[1]["book_title"])
        self.assertIsNone(rows[1]["book_slug"])
        self.assertEqual((rows[2]["book_id"], rows[2]["book_title"], rows[2]["book_slug"]),
                         (4, "A public book", "a-public-book"))
        self.assertEqual(rows[3]["book_id"], 5)
        self.assertIsNone(rows[3]["book_title"])
        self.assertIsNone(rows[3]["book_slug"])
        self.assertEqual(response.get_json()["books"], [{"id": 4, "title": "A public book"}])

    def test_search_is_public_approved_only_and_searches_beyond_native_fallback(self):
        self.database.db.executemany("INSERT INTO documents VALUES (?,?,?,'book',1)",
                                     [(n, f"Book {n:03}", "Common Author") for n in range(10, 140)])
        with self.client.session_transaction() as state:
            state.pop("user_id")
        response = self.client.get("/api/review-books?q=Book%20139")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["books"],
                         [{"id": 139, "title": "Book 139", "author": "Common Author"}])
        self.assertEqual(self.client.get("/api/review-books?q=Private").get_json()["books"], [])
        self.assertEqual(self.client.get("/api/review-books?q=Secret").get_json()["books"], [])
        initial = self.client.get("/api/review-books").get_json()
        self.assertEqual(len(initial["books"]), 20)
        self.assertTrue(initial["has_more"])
        self.assertEqual(set(initial["books"][0]), {"id", "title", "author"})

    def test_search_treats_metacharacters_as_literal_and_bounds_query(self):
        self.database.db.execute("INSERT INTO documents VALUES (6,'100%_Guide','Tester','guide',1)")
        self.assertEqual(self.client.get("/api/review-books?q=%25_").get_json()["books"],
                         [{"id": 6, "title": "100%_Guide", "author": "Tester"}])
        self.assertEqual(self.client.get("/api/review-books", query_string={"q": "x" * 101}).status_code, 400)
        self.assertEqual(self.client.get("/api/review-books", query_string={"q": "x" * 100}).status_code, 200)


class GeneralReviewModerationTests(unittest.TestCase):
    def setUp(self):
        self.database = Database()
        self.addCleanup(self.database.db.close)
        self.app, _ = isolated_app(self.database)
        self.app.template_folder = str(ROOT / "templates")
        self.app.add_url_rule("/", "home", lambda: "Home")
        self.app.add_url_rule("/book/<slug>/<int:book_id>", "book_detail", lambda **kwargs: "Book")
        self.app.add_url_rule("/user/upload", "user_upload", lambda: "Upload")
        tree = ast.parse((ROOT / "admin/admin_routes.py").read_text(encoding="utf-8"))
        keys = {node.slice.value for node in ast.walk(tree)
                if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == "services" and isinstance(node.slice, ast.Constant)}
        services = {key: lambda *args, **kwargs: None for key in keys}
        self.settings = {"official_user_id": "1", "studio_admin_ids": "[]"}
        services.update(mysql=self.database, limiter=Limiter(),
                        get_site_setting=lambda key, default=None: self.settings.get(key, default))
        self.app.extensions["studio_auth"] = types.SimpleNamespace(valid_session=lambda token, uid: token == "test-studio")
        register_admin(self.app, services)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(studio_user_id=1, studio_token="test-studio", _csrf_token="review-token")
        self.database.db.executemany(
            "INSERT INTO reviews (id,user_id,book_id,rating,comment) VALUES (?,1,?,4,?)",
            [(1, None, "General feedback"), (2, 4, "Book feedback")])

    def test_panel_shows_general_review_and_real_book_links(self):
        response = self.client.get("/admin-studio/reviews")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("General feedback", html)
        self.assertIn("DocoDive feedback", html)
        self.assertIn('href="/book/a-public-book/4"', html)
        self.assertNotIn("/book/None", html)
        filtered = self.client.get("/admin-studio/reviews?book_id=4").get_data(as_text=True)
        self.assertIn("Book feedback", filtered)
        self.assertNotIn("General feedback", filtered)

    def test_official_reply_and_delete_keep_general_review_lifecycle(self):
        response = self.client.post("/admin-studio/api/review/1/reply",
                                    json={"reply_text": "Thank you"},
                                    headers={"X-CSRF-Token": "review-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.database.db.execute(
            "SELECT book_id,user_id,parent_id,comment FROM book_comments").fetchall(),
            [(None, 1, -1, "📢 Official reply: Thank you")])
        html = self.client.get("/admin-studio/reviews").get_data(as_text=True)
        self.assertIn("Official reply: Thank you", html)
        self.database.db.execute("INSERT INTO review_likes VALUES (1,1)")
        response = self.client.post("/admin-studio/api/review/1/delete",
                                    headers={"X-CSRF-Token": "review-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.database.db.execute("SELECT id FROM reviews").fetchall(), [(2,)])
        self.assertEqual(self.database.db.execute("SELECT id FROM book_comments").fetchall(), [])
        self.assertEqual(self.database.db.execute("SELECT review_id FROM review_likes").fetchall(), [])

    def test_reader_session_and_invalid_csrf_cannot_moderate_general_reviews(self):
        response = self.client.post("/admin-studio/api/review/1/delete",
                                    headers={"X-CSRF-Token": "wrong"})
        self.assertEqual(response.status_code, 403)
        with self.client.session_transaction() as state:
            state.pop("studio_user_id")
            state["user_id"] = 1
        response = self.client.post("/admin-studio/api/review/1/delete",
                                    headers={"X-CSRF-Token": "review-token"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.database.db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
