"""Policy documents, section links and navigation render without real services."""
import unittest
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit
from flask import render_template
import test_admin_studio
from seo import register_seo


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.hrefs = set(), []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            self.ids.add(values['id'])
        if tag == 'a' and values.get('href'):
            self.hrefs.append(values['href'])


class LegalPageTests(unittest.TestCase):
    def test_optional_integrations_cannot_bypass_cookie_choices(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root/'templates').rglob('*.html'):
            source = path.read_text(encoding='utf-8')
            self.assertFalse('brevo-conversations.js' in source, str(path))
            self.assertFalse('googletagmanager.com/gtag' in source, str(path))

    def test_policies_have_valid_sections_and_local_navigation(self):
        fixture = test_admin_studio.StudioTests()
        fixture.setUp()
        app = fixture.app
        register_seo(app, fixture.svc)
        app.add_url_rule('/user/settings', 'account_settings', lambda: 'settings')
        app.add_url_rule('/user/account-deletion', 'account_deletion', lambda: 'deletion')
        routes = {'privacy':'/privacy','terms':'/terms','cookies':'/cookies',
                  'data_deletion':'/data-deletion','contact':'/contact',
                  'community_guidelines':'/community-guidelines','accessibility':'/accessibility'}
        adapter = app.url_map.bind('localhost')
        for name, path in routes.items():
            with self.subTest(page=name), app.test_request_context(path):
                html = render_template('user/'+name+'.html')
                self.assertIn('rel="canonical"', html)
                self.assertIn('31 October 2026', html)
                self.assertIn('data-cookie-settings', html)
                links = Links()
                links.feed(html)
                for href in links.hrefs:
                    parsed = urlsplit(href)
                    if parsed.scheme or parsed.netloc:
                        continue
                    if href.startswith('#'):
                        self.assertIn(parsed.fragment, links.ids, href)
                    elif parsed.path.startswith('/'):
                        adapter.match(parsed.path, method='GET')
                if name == 'data_deletion':
                    self.assertIn('15-day grace period', html)
                    self.assertIn('30 days', html)


if __name__ == '__main__':
    unittest.main()
