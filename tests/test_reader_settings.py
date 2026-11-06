"""Reader security and measured counters, using a disposable local database."""
import logging
import unittest
from datetime import datetime, timedelta
from flask import Flask
from unittest.mock import patch
from test_account_services import DB
from account_store import Store
from account_lifecycle import AccountLifecycle
from studio_auth import StudioAuth, AuthError
from password_security import generate_password_hash, check_password_hash

try:
    from reader_settings import ReaderSettings
except ImportError:
    ReaderSettings = None
try:
    from public_metrics import monthly_active_members
except ImportError:
    monthly_active_members = None


class ReaderSettingsTests(unittest.TestCase):
    def setUp(self):
        self.db = DB()
        self.store = Store(self.db)
        self.now = datetime(2026, 10, 31, 12)
        self.auth = StudioAuth(self.store, 'isolated', lambda *a, **k: True,
                               logging.getLogger('test'), lambda: self.now)
        self.life = AccountLifecycle(self.store, lambda *a, **k: True,
                                    logging.getLogger('test'), lambda uid: False,
                                    lambda: self.now)
        self.old_hash = generate_password_hash('current-passphrase')
        self.db.raw.execute('INSERT INTO users(id,username,email,password,verified) VALUES(1,?,?,?,1)',
                            ('reader', 'reader@example.test', self.old_hash))
        self.db.raw.execute('CREATE TABLE password_resets(id INTEGER PRIMARY KEY,email TEXT,token TEXT,expires_at DATETIME)')
        self.db.raw.execute('INSERT INTO password_resets VALUES(1,?,?,?)',
                            ('reader@example.test', 'reset-token', self.now + timedelta(minutes=30)))

    def service(self):
        self.assertIsNotNone(ReaderSettings, 'Reader Settings service is not implemented')
        return ReaderSettings(self.store, self.auth, self.life, clock=lambda: self.now)

    def test_current_password_is_required_and_failed_attempt_does_not_write(self):
        service = self.service()
        with self.assertRaises(AuthError):
            service.change_password(1, 'wrong-password', 'a-new-passphrase', 'a-new-passphrase', 'test-ip')
        self.assertEqual(self.store.query('SELECT password FROM users WHERE id=1', one=True)[0], self.old_hash)
        self.assertEqual(self.life.version(1), 0)
        self.assertEqual(self.store.query('SELECT COUNT(*) FROM password_resets', one=True)[0], 1)

    def test_valid_change_revokes_sessions_and_reset_links(self):
        service = self.service()
        session_token = self.auth.new_session(1, self.auth.digest(self.old_hash))
        challenge = self.auth.issue(1, 'account_delete', 'binding', 'reader@example.test', 'ip')
        service.change_password(1, 'current-passphrase', 'a-new-passphrase', 'a-new-passphrase', 'test-ip')
        updated = self.store.query('SELECT password FROM users WHERE id=1', one=True)[0]
        self.assertTrue(check_password_hash(updated, 'a-new-passphrase'))
        self.assertFalse(check_password_hash(updated, 'current-passphrase'))
        self.assertFalse(self.life.active_session(1, 0))
        self.assertFalse(self.auth.valid_session(session_token, 1))
        self.assertEqual(self.store.query('SELECT COUNT(*) FROM password_resets', one=True)[0], 0)
        self.assertIsNotNone(self.store.query('SELECT consumed_at FROM security_otp WHERE challenge_id=%s', (challenge,), one=True)[0])

    def test_confirmation_length_and_reuse_are_rejected(self):
        service = self.service()
        for new, confirm in [('short', 'short'), ('x'*129, 'x'*129),
                             ('a-new-passphrase', 'different-password'),
                             ('current-passphrase', 'current-passphrase')]:
            with self.subTest(new_length=len(new)), self.assertRaises(AuthError):
                service.change_password(1, 'current-passphrase', new, confirm, 'test-ip')
        self.assertEqual(self.life.version(1), 0)

    def test_reset_is_single_use_and_revokes_existing_sessions(self):
        service = self.service()
        self.assertTrue(service.reset_available('reset-token'))
        service.reset_password('reset-token', 'recovered-password', 'recovered-password')
        self.assertFalse(service.reset_available('reset-token'))
        self.assertFalse(self.life.active_session(1, 0))
        with self.assertRaises(AuthError):
            service.reset_password('reset-token', 'another-password', 'another-password')

    def test_expired_reset_cannot_change_password(self):
        service = self.service()
        self.now += timedelta(hours=1)
        self.assertFalse(service.reset_available('reset-token'))
        with self.assertRaises(AuthError):
            service.reset_password('reset-token', 'recovered-password', 'recovered-password')
        self.assertEqual(self.life.version(1), 0)

    def test_login_started_before_password_change_cannot_accept_old_password_snapshot(self):
        # Simulate a password check that finished just before another request changed it.
        self.service().change_password(1, 'current-passphrase', 'a-new-passphrase', 'a-new-passphrase', 'ip')
        with self.assertRaises(AuthError):
            self.life.on_login(1, password_hash=self.old_hash)

    def test_recovery_code_get_renders_without_database_lookup(self):
        from flask import request, render_template, redirect, url_for
        from test_security_regressions import load_function
        app = Flask(__name__)
        app.add_url_rule('/forgot-password', 'forgot_password', lambda: 'forgot')
        view = load_function('verify_code', dict(request=request, mysql=object(),
                             render_template=lambda template, **context: 'code page for '+context.get('email',''),
                             redirect=redirect, url_for=url_for))
        app.add_url_rule('/verify-code', 'verify_code', view, methods=['GET'])
        response = app.test_client().get('/verify-code?email=reader@example.test')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'code page for reader@example.test', response.data)

    def test_recovery_verification_reports_delivery_failure_and_html_success(self):
        import secrets
        from flask import request, jsonify, url_for
        from test_security_regressions import load_function
        self.db.raw.execute('ALTER TABLE password_resets ADD COLUMN code TEXT')
        for delivered, ajax in [(True, False), (False, False), (True, True), (False, True)]:
            with self.subTest(delivered=delivered, ajax=ajax):
                self.db.raw.execute('UPDATE password_resets SET code=?,expires_at=?,token=NULL WHERE id=1',
                                    ('1234', datetime.now()+timedelta(minutes=10)))
                app = Flask(__name__)
                app.add_url_rule('/reset-password/<token>', 'reset_password', lambda token: 'reset')
                view = load_function('verify_code', dict(request=request,mysql=self.db,datetime=datetime,
                         timedelta=timedelta,secrets=secrets,url_for=url_for,jsonify=jsonify,
                         make_reset_link_email=lambda link: 'reset message',
                         send_email_notification=lambda *a, **kw: delivered,
                         render_template=lambda template, **context: template))
                app.add_url_rule('/verify-code', 'verify_code', view, methods=['POST'])
                response = app.test_client().post('/verify-code', data={'email':'reader@example.test','code':'1234'},
                            headers={'X-Requested-With':'XMLHttpRequest'} if ajax else {})
                self.assertEqual(response.status_code, 200 if delivered else 503)
                if delivered and not ajax:
                    self.assertIn(b'password_recovery_sent.html',response.data)

    def test_settings_requires_reader_login(self):
        from account_routes import register_accounts
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY='isolated')
        app.add_url_rule('/user/login', 'user_login', lambda: 'sign in')
        with patch('admin.security.has_role', lambda uid: False):
            register_accounts(app, dict(mysql=self.db, send_email_notification=lambda *a, **k: True))
        response = app.test_client().get('/user/settings')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/user/login'))

    def test_settings_csrf_and_successful_change(self):
        from pathlib import Path
        from flask import request, session, abort
        import secrets, hmac
        from test_security_regressions import load_function
        from account_routes import register_accounts
        root = Path(__file__).resolve().parents[1]
        app = Flask(__name__, template_folder=str(root/'templates'), static_folder=str(root/'static'))
        app.config.update(TESTING=True, SECRET_KEY='isolated')
        app.before_request(load_function('csrf_protect', dict(request=request, session=session, abort=abort, secrets=secrets, hmac=hmac)))
        app.add_url_rule('/', 'home', lambda: 'home')
        app.add_url_rule('/user/login', 'user_login', lambda: 'sign in')
        app.add_url_rule('/cookies', 'cookies_policy', lambda: 'cookies')
        app.add_url_rule('/privacy', 'privacy_policy', lambda: 'privacy')
        with patch('admin.security.has_role', lambda uid: False):
            register_accounts(app, dict(mysql=self.db, send_email_notification=lambda *a, **k: True))
        client = app.test_client()
        with client.session_transaction() as state:
            state.update(user_id=1, account_version=0, user_name='reader')
        page = client.get('/user/settings')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Current password', page.data)
        self.assertIn(b'/user/account-deletion', page.data)
        self.assertEqual(client.post('/user/settings', data={}).status_code, 403)
        with client.session_transaction() as state:
            token = state['_csrf_token']
        code = client.post('/user/account-deletion', data={'_csrf_token':token, 'action':'send', 'return_to':'settings'})
        self.assertEqual(code.status_code, 302)
        self.assertTrue(code.location.endswith('/user/settings#delete-account'))
        with client.session_transaction() as state:
            self.assertTrue(state.get('deletion_challenge'))
        result = client.post('/user/settings', data={'_csrf_token':token,
                             'current_password':'current-passphrase','password':'a-new-passphrase',
                             'confirm_password':'a-new-passphrase'})
        self.assertEqual(result.status_code, 302)
        with client.session_transaction() as state:
            self.assertNotIn('user_id', state)

    def test_monthly_count_excludes_guests_duplicates_deleted_and_old_activity(self):
        self.assertIsNotNone(monthly_active_members, 'Measured monthly users is not implemented')
        for uid in (2, 3):
            self.db.raw.execute('INSERT INTO users(id) VALUES(?)', (uid,))
        today = self.now.date()
        for days_ago, uid in [(0, 0), (0, 1), (1, 1), (29, 2), (30, 3), (0, 999), (-1, 3)]:
            self.db.raw.execute('INSERT INTO activity_daily(activity_day,user_id,page_views,reads,downloads,last_seen) VALUES(?,?,1,0,0,?)',
                                (today - timedelta(days=days_ago), uid, self.now))
        self.assertEqual(monthly_active_members(self.store, today), 2)


if __name__ == '__main__':
    unittest.main()
