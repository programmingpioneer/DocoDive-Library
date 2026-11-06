"""Directory queries run against disposable SQL data; no app.py import or network."""

import csv
import io
import sqlite3
import unittest
from flask import session, render_template
from admin.directories import users_page, books_page, csv_response
from test_account_services import Cursor
import test_admin_studio


class DirectoryDB:
    def __init__(self):
        self.raw = sqlite3.connect(":memory:", isolation_level=None)
        self.raw.create_function(
            "CONCAT", -1, lambda *values: "".join(str(v or "") for v in values)
        )
        self.connection = self
        self.raw.executescript(
            """CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,email TEXT,verified INTEGER,created_at TEXT,first_name TEXT,last_name TEXT,avatar_url TEXT);
        CREATE TABLE categories(id INTEGER PRIMARY KEY,level TEXT);
        CREATE TABLE documents(id INTEGER PRIMARY KEY,title TEXT,category_id INTEGER,author TEXT,created_at TEXT,image_url TEXT,slug TEXT,status TEXT,approved INTEGER,view_count INTEGER,download_count INTEGER,uploaded_by INTEGER);
        CREATE TABLE download_history(user_id INTEGER,book_id INTEGER);
        CREATE TABLE reviews(user_id INTEGER);
        CREATE TABLE activity_daily(user_id INTEGER,last_seen TEXT);
        CREATE TABLE account_deletions(user_id INTEGER,status TEXT);"""
        )
        for uid in range(1, 36):
            self.raw.execute(
                "INSERT INTO users VALUES(?,?,?,?,?,?,?,NULL)",
                (
                    uid,
                    "member" + str(uid),
                    "member" + str(uid) + "@example.test",
                    uid % 2,
                    "2026-10-20",
                    "Test",
                    str(uid),
                ),
            )
        self.raw.execute("INSERT INTO categories VALUES(1,'Python'),(2,'Design')")
        for bid in range(1, 13):
            self.raw.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,NULL,?,?,?,?,?,?)",
                (
                    bid,
                    "Book " + str(bid),
                    1 if bid % 2 else 2,
                    "An Author",
                    "2026-10-20",
                    "book-" + str(bid),
                    "approved" if bid <= 9 else "pending",
                    int(bid <= 9),
                    bid * 2,
                    bid,
                    1,
                ),
            )
        self.raw.execute("INSERT INTO download_history VALUES(2,1)")
        self.raw.execute("INSERT INTO account_deletions VALUES(2,'requested')")

    def cursor(self):
        return Cursor(self.raw)


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.case = test_admin_studio.StudioTests()
        self.case.setUp()
        self.app = self.case.app
        self.db = DirectoryDB()

    def context(self, url):
        return self.app.test_request_context(url)

    def test_user_filters_and_selection_use_real_records(self):
        with self.context("/admin-studio/users?status=pending&member=2"):
            html = users_page(self.db)
            self.assertIn("member2@example.test", html)
            self.assertNotIn("member3@example.test", html)
            self.assertIn("Deletion pending", html)
            self.assertIn("View member activity", html)
            self.assertNotIn("Edit profile", html)

    def test_user_pagination_and_export_preserve_filters(self):
        with self.context("/admin-studio/users?page=2"):
            html = users_page(self.db)
            self.assertIn("31–35 of 35", html)
            self.assertIn("page=2&amp;member=5", html)
        with self.context("/admin-studio/users?page=2&member=2"):
            html = users_page(self.db)
            self.assertIn("31–35 of 35", html)
            self.assertIn("@member2", html)
        with self.context("/admin-studio/users?activity=downloads&export=csv"):
            response = users_page(self.db)
            rows = list(
                csv.reader(
                    io.StringIO(response.get_data(as_text=True).lstrip("\ufeff"))
                )
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1][1], "member2")
            self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_books_have_nine_rows_and_numeric_pagination(self):
        with self.context("/admin-studio/books"):
            html = books_page(self.db)
            self.assertEqual(html.count('class="studio-book-title"'), 9)
            self.assertIn("1–9 of 12", html)
        with self.context("/admin-studio/books?status=pending&category=1"):
            html = books_page(self.db)
            self.assertIn("Book 11", html)
            self.assertNotIn("Book 10</a>", html)

    def test_search_is_bound_and_sort_is_whitelisted(self):
        from werkzeug.exceptions import BadRequest

        with self.context("/admin-studio/users?q=%27%20OR%201=1--"):
            self.assertIn("No matching members", users_page(self.db))
        with self.context("/admin-studio/books?sort=id;DROP%20TABLE%20users"):
            with self.assertRaises(BadRequest):
                books_page(self.db)
        self.assertEqual(
            self.db.raw.execute("SELECT COUNT(*) FROM users").fetchone()[0], 35
        )

    def test_csv_values_cannot_execute_spreadsheet_formulas(self):
        with self.context("/"):
            response = csv_response(
                "test", ["value"], [["=SUM(1,2)"], [" +123"], ["@cmd"], ["safe"]]
            )
            rows = list(
                csv.reader(
                    io.StringIO(response.get_data(as_text=True).lstrip("\ufeff"))
                )
            )
            self.assertTrue(all(row[0].startswith("'") for row in rows[1:4]))
            self.assertEqual(rows[4][0], "safe")

    def test_leaderboard_totals_exclude_orphaned_point_records(self):
        from admin.studio import leaderboard_summary
        from account_store import Store

        self.db.raw.execute(
            "CREATE TABLE user_points(user_id INTEGER,points INTEGER,action TEXT)"
        )
        self.db.raw.executemany(
            "INSERT INTO user_points VALUES(?,?,?)",
            [
                (1, 20, "read"),
                (2, 10, "admin_adjustment"),
                (999, 1000, "admin_adjustment"),
            ],
        )
        result = leaderboard_summary(Store(self.db).query)
        self.assertEqual(result, dict(points=30, members=35, adjustments=1))

    def test_populated_official_profile_builds_stats_url(self):
        with self.context("/admin-studio/official-profile"):
            session["_csrf_token"] = "test"
            html = render_template(
                "admin/admin_official_profile.html", official_user=(1, "owner", None)
            )
            self.assertIn("/admin-studio/api/user-stats?user_id=1", html)
            self.assertIn("Unavailable", html)


if __name__ == "__main__":
    unittest.main()
