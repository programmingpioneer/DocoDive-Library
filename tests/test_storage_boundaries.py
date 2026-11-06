"""Storage boundary checks without importing app configuration or contacting R2."""

import re
import secrets
import unittest

from flask import Flask, jsonify, session, url_for

from test_security_regressions import load_function


class Cursor:
    def __init__(self, rows=(), error=None):
        self.rows = list(rows)
        self.error = error
        self.closed = False

    def execute(self, sql, args=()):
        if self.error:
            raise self.error

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, cursor):
        self.result = cursor

    def cursor(self):
        return self.result


class StorageBoundaryTests(unittest.TestCase):
    def test_distinct_uploads_with_same_title_preserve_both_objects(self):
        objects = {}

        class MemoryStorage:
            def put_object(self, **data):
                objects[data["Key"]] = data["Body"]

        scope = dict(secrets=secrets, r2_client=MemoryStorage(), R2_BUCKET="test", R2_PUBLIC_BASE="https://storage.example.test")
        key_for = load_function("generate_r2_key", scope)
        upload = load_function("upload_to_r2", scope)
        for folder, extension, content_type in (
            ("uploads", ".pdf", "application/pdf"),
            ("covers", ".jpg", "image/jpeg"),
        ):
            with self.subTest(folder=folder):
                objects.clear()
                first = key_for(folder, "Shared_Title", extension)
                second = key_for(folder, "Shared_Title", extension)
                upload(b"original", first, content_type)
                upload(b"replacement", second, content_type)
                self.assertEqual(len(objects), 2)
                self.assertEqual(objects[first], b"original")
                self.assertEqual(objects[second], b"replacement")

    def duplicate_check(self):
        scope = dict(re=re)
        load_function("normalize_for_duplicate_check", scope)
        return load_function("is_duplicate", scope)

    def test_duplicate_check_accepts_borrowed_cursor_without_closing_it(self):
        cursor = Cursor([(1, "Shared Title")])
        self.assertTrue(self.duplicate_check()("Shared Title (2)", "Author", cursor))
        self.assertFalse(cursor.closed)

    def test_duplicate_check_closes_cursor_it_creates(self):
        cursor = Cursor([(1, "Different Title")])
        self.assertFalse(self.duplicate_check()("Shared Title", "Author", Connection(cursor)))
        self.assertTrue(cursor.closed)

    def test_duplicate_check_does_not_accept_upload_after_database_error(self):
        with self.assertRaises(RuntimeError):
            self.duplicate_check()("Shared Title", "Author", Cursor(error=RuntimeError("database unavailable")))

    def test_public_book_api_uses_same_origin_download_gate(self):
        book = (7, "Shared Title", "Python", "https://storage.example.test/private-file.pdf", "Author", "Description", "/cover.jpg", "English", "shared-title")

        class BookCursor:
            def execute(self, sql, args=()):
                self.rows = [book] if "FROM documents d JOIN categories" in sql else []

            def fetchone(self):
                return self.rows[0] if self.rows else None

            def fetchall(self):
                return self.rows

            def close(self):
                pass

        class BookDB:
            connection = None

            def __init__(self):
                self.connection = self

            def cursor(self):
                return BookCursor()

            def commit(self):
                pass

        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY=secrets.token_hex(32))
        app.add_url_rule("/book/<slug>/<int:book_id>/download", endpoint="download_book", view_func=lambda slug, book_id: "gate")
        scope = dict(mysql=BookDB(), session=session, jsonify=jsonify, url_for=url_for, lazy_trickle=lambda book_id: None)
        app.add_url_rule("/api/book/<int:book_id>", view_func=load_function("api_book_detail", scope))
        response = app.test_client().get("/api/book/7")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["link"], "/book/shared-title/7/download")
        self.assertNotIn("storage.example.test", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
