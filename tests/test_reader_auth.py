"""Standalone authentication presentation, without importing the configured app."""
from html.parser import HTMLParser
from pathlib import Path
import unittest
from flask import Flask, render_template, flash, session

ROOT = Path(__file__).resolve().parents[1]


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = {}
        self.inputs = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids[attrs['id']] = attrs
        if tag == 'input':
            self.inputs.append(attrs)


class ReaderAuthTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT/'templates'), static_folder=str(ROOT/'static'))
        self.app.secret_key = 'isolated-reader-auth-test'

    def test_redirected_feedback_and_errors_are_visible_once_and_escaped(self):
        with self.app.test_request_context('/user/login'):
            session['_csrf_token'] = 'test-csrf'
            flash('Password updated. Please sign in.', 'success')
            flash('Login session expired. Please sign in again.', 'danger')
            html = render_template('user/auth.html', mode='login', error='<script>unsafe</script>')
        self.assertEqual(html.count('Password updated. Please sign in.'), 1)
        self.assertEqual(html.count('Login session expired. Please sign in again.'), 1)
        self.assertEqual(html.count('&lt;script&gt;unsafe&lt;/script&gt;'), 1)
        self.assertNotIn('<script>unsafe</script>', html)

    def test_signup_initial_state_keeps_native_navigation_and_csrf(self):
        with self.app.test_request_context('/user/signup', method='POST', data={
            'first_name':'<Reader>', 'email':'reader@example.test', 'password':'never-echo-this-value'}):
            session['_csrf_token'] = 'test-csrf'
            html = render_template('user/auth.html', mode='signup', error='Choose another username.')
        elements = Elements(html)
        self.assertIn('hidden', elements.ids['login-tab'])
        self.assertNotIn('hidden', elements.ids['signup-tab'])
        self.assertEqual(elements.ids['signup-tab-control']['aria-selected'], 'true')
        self.assertEqual(elements.ids['login-tab-control']['href'], '/user/login')
        self.assertIn('name="_csrf_token" value="test-csrf"', html)
        self.assertIn('&lt;Reader&gt;', html)
        self.assertNotIn('never-echo-this-value', html)
        self.assertEqual(elements.ids['signup-password']['autocomplete'], 'new-password')
