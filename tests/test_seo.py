"""SEO integration tests against Flask's local client and an in-memory SQL stub."""

import unittest
from xml.etree.ElementTree import fromstring
from flask import Flask, render_template_string
from seo import register_seo


class Cursor:
    def execute(self, sql, args=()):
        self.rows = (
            [(5001,)]
            if "COUNT(*)" in sql
            else [("Python",), ("IELTS",)] if "categories" in sql else [(8, "a-book")]
        )
        self.sql, self.args = sql, args

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class SEOTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, PUBLIC_SITE_URL="https://library.example")

        def metadata(**kwargs):
            return render_template_string("{{ seo_canonical }}|{{ seo_indexable }}")

        for path, endpoint in [
            ("/", "home"),
            ("/books", "all_books"),
            ("/privacy", "privacy_policy"),
            ("/terms", "terms_of_service"),
            ("/user/login", "user_login"),
            ("/learn/<category_slug>", "learning_hub"),
            ("/learn/<slug>/<module>", "category_module"),
            ("/book/<slug>/<int:book_id>", "book_detail"),
        ]:
            self.app.add_url_rule(path, endpoint, metadata)
        self.cursor = Cursor()

        class Database:
            connection = None

            def cursor(db):
                return self.cursor

        db = Database()
        db.connection = db
        register_seo(
            self.app,
            {
                "mysql": db,
                "category_to_slug": str.lower,
                "GENERIC_MODULES": [{"slug": "beginner"}, {"slug": "practice"}],
                "IELTS_MODULES": [{"slug": "reading"}],
            },
        )
        self.client = self.app.test_client()

    def test_paginated_category_canonical_retains_content_identity(self):
        body = self.client.get(
            "/books?page=2&category=python&utm_source=test"
        ).get_data(as_text=True)
        self.assertEqual(
            body, "https://library.example/books?page=2&amp;category=python|True"
        )

    def test_private_and_search_pages_are_noindex(self):
        for path in ["/user/login", "/books?q=test", "/does-not-exist"]:
            self.assertEqual(
                self.client.get(path).headers["X-Robots-Tag"], "noindex, follow"
            )

    def test_public_policy_pages_remain_indexable(self):
        for path in ["/privacy", "/terms"]:
            self.assertNotIn("X-Robots-Tag", self.client.get(path).headers)

    def test_sitemap_splits_books_and_contains_only_canonical_public_pages(self):
        index = self.client.get("/sitemap.xml")
        self.assertEqual(len(fromstring(index.data)), 3)
        pages = self.client.get("/sitemaps/pages.xml").get_data(as_text=True)
        for path in [
            "/books",
            "/privacy",
            "/terms",
            "/learn/python/practice",
            "/learn/ielts/reading",
        ]:
            self.assertIn("https://library.example" + path, pages)
        self.assertNotIn("/user/login", pages)
        self.client.get("/sitemaps/books-2.xml")
        self.assertEqual(self.cursor.args, (5000, 5000))

    def test_robots_exposes_sitemap_and_allows_assets(self):
        body = self.client.get("/robots.txt").get_data(as_text=True)
        self.assertIn("Sitemap: https://library.example/sitemap.xml", body)
        self.assertNotIn("Disallow: /static", body)
