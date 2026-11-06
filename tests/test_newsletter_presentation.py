"""Welcome email content, safe links and multipart alternatives without delivery."""

from html.parser import HTMLParser
import unittest

from newsletter_presentation import build_newsletter_welcome


class EmailMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.links, self.tables = [], [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs)
        if tag == "table":
            self.tables.append(attrs)


class NewsletterPresentationTests(unittest.TestCase):
    def build(self, **changes):
        args = dict(library_url="https://example.test/books", learning_url="https://example.test/learn/python",
                    contact_url="https://example.test/contact", privacy_url="https://example.test/privacy",
                    support_email="help@example.test")
        args.update(changes)
        return build_newsletter_welcome(**args)

    def test_welcome_has_real_links_readable_text_and_email_safe_layout(self):
        email = self.build()
        self.assertEqual(email["subject"], "Welcome to DocoDive")
        parser = EmailMarkup()
        parser.feed(email["html"])
        hrefs = [link["href"] for link in parser.links]
        for href in ["https://example.test/books", "https://example.test/learn/python",
                     "https://example.test/contact", "https://example.test/privacy"]:
            self.assertIn(href, hrefs)
            self.assertIn(href, email["text"])
        self.assertTrue(parser.tables)
        self.assertTrue(all(table.get("role") == "presentation" for table in parser.tables))
        self.assertTrue(all(tag not in parser.tags for tag in ["script", "form", "img", "iframe"]))
        self.assertIn("Browse the library", email["html"])
        self.assertIn("newsletter", email["text"].lower())
        self.assertNotIn("verification code", email["text"].lower())
        self.assertNotIn("delivered", email["text"].lower())

    def test_dynamic_link_attributes_cannot_escape_into_markup(self):
        library_url = 'https://example.test/books?q="curious"&edition=<new>'
        email = self.build(library_url=library_url)
        parser = EmailMarkup()
        parser.feed(email["html"])
        self.assertIn(library_url, [link["href"] for link in parser.links])
        self.assertNotIn("new", parser.tags)
        self.assertTrue(all("onclick" not in link for link in parser.links))
        self.assertIn("&lt;new&gt;", email["html"])

    def test_unsafe_or_relative_email_links_are_rejected(self):
        for url in ["javascript:alert(1)", "/books", "https:///books", "https://example.test/\r\ninject"]:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self.build(library_url=url)

    def test_optional_support_address_does_not_create_a_header_or_link_injection(self):
        email = self.build(support_email='help@example.test\r\nBcc: another@example.test')
        parser = EmailMarkup()
        parser.feed(email["html"])
        self.assertFalse(any(link["href"].startswith("mailto:") for link in parser.links))
        self.assertNotIn("Bcc:", email["html"])


if __name__ == "__main__":
    unittest.main()
