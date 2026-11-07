"""PDF gates and metrics use synthetic SQL/storage, never configured app startup."""
import unittest
from types import SimpleNamespace
from urllib.parse import quote

from flask import Flask, Response, abort, flash, g, jsonify, redirect, request, session, url_for
from werkzeug.utils import secure_filename

from test_security_regressions import load_function


class DeliveryError(Exception):
    def __init__(self, status_code=503, category='authorization'):
        super().__init__('private provider XML or credentials must not be reflected')
        self.status_code, self.category, self.headers = status_code, category, {}


class Resource:
    def __init__(self, status=200):
        self.status_code = status
        self.headers = {'Content-Length': '8', 'Accept-Ranges': 'bytes'}
        if status == 206:
            self.headers['Content-Range'] = 'bytes 0-7/100'
        self.closed = False
        self.iterated = False

    def iter_chunks(self):
        self.iterated = True
        yield b'%PDF-1.4'

    def close(self):
        self.closed = True


class PDFRouteTests(unittest.TestCase):
    def setUp(self):
        import re
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='pdf-isolated-fixture-only')
        self.row = ('https://assets.example.test/docodive/uploads/real_unique.pdf', 'A useful book', 'useful-book')
        self.sql, self.calls = [], []
        self.error = None
        self.resource = Resource()
        owner = self

        class Cursor:
            def execute(self, sql, args=()): owner.sql.append((sql, args))
            def fetchone(self): return owner.row
            def close(self): pass

        def open_object(*args, **kwargs):
            self.calls.append((args, kwargs))
            if self.error: raise self.error
            return self.resource

        def render(name, **context):
            if name == 'user/pdf_unavailable.html':
                return '<h1>PDF temporarily unavailable</h1>'
            return str(context['pdf_url'])

        self.connection = SimpleNamespace(cursor=Cursor, commit=lambda:None)
        scope = dict(app=self.app, request=request, session=session, g=g, jsonify=jsonify,
                     redirect=redirect, url_for=url_for, abort=abort, flash=flash, Response=Response,
                     render_template=render, re=re, quote=quote, secure_filename=secure_filename,
                     mysql=SimpleNamespace(connection=self.connection),
                     r2_client=SimpleNamespace(meta=SimpleNamespace(endpoint_url='https://account.r2.cloudflarestorage.com')),
                     R2_BUCKET='fixture-bucket', R2_PUBLIC_BASE='https://assets.example.test',
                     extract_r2_key=lambda value:'docodive/uploads/real_unique.pdf' if value.startswith('https://assets.example.test/') else None,
                     trusted_public_pdf_url=lambda *args:None, open_pdf_object=open_object,
                     PDFDeliveryError=DeliveryError)
        self.scope = scope
        for name in ('_pdf_error_response', '_pdf_filename', '_serve_book_pdf', 'download_book', 'book_pdf', 'read_book'):
            load_function(name, scope)
        self.app.add_url_rule('/', 'home', lambda:'home')
        self.app.add_url_rule('/user/login', 'user_login', lambda:'login')
        for name, path in [('download_book','/book/<int:book_id>/download'), ('book_pdf','/book/<int:book_id>/pdf'), ('read_book','/book/<int:book_id>/read')]:
            self.app.add_url_rule(path, name, scope[name], methods=['GET','HEAD'])
        self.client = self.app.test_client()
        with self.client.session_transaction() as state: state['user_id'] = 1

    def writes(self):
        return [sql for sql,args in self.sql if sql.lstrip().startswith(('UPDATE','INSERT'))]

    def test_inline_pdf_streams_without_download_metrics(self):
        response = self.client.get('/book/4/pdf', buffered=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'%PDF-1.4')
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertTrue(response.headers['Content-Disposition'].startswith('inline;'))
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(self.writes(), [])
        response.close()
        self.assertTrue(self.resource.closed)

    def test_download_records_one_initiation_after_opening_storage(self):
        response = self.client.get('/book/4/download', buffered=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(len(self.writes()), 2)
        self.assertEqual(len(self.calls), 1)
        response.close()

    def test_head_and_range_do_not_create_extra_downloads(self):
        response = self.client.head('/book/4/download')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'')
        self.assertTrue(self.calls[-1][1]['head'])
        self.assertFalse(self.resource.iterated)
        self.assertTrue(self.resource.closed)
        self.assertEqual(self.writes(), [])
        self.resource = Resource(206)
        response = self.client.get('/book/4/download', headers={'Range':'bytes=0-7'}, buffered=True)
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers['Content-Range'], 'bytes 0-7/100')
        self.assertEqual(self.calls[-1][1]['range_header'], 'bytes=0-7')
        self.assertEqual(self.writes(), [])
        response.close()

    def test_provider_denial_is_friendly_and_not_counted(self):
        self.error = DeliveryError()
        for path in ('/book/4/pdf','/book/4/download'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 503)
            self.assertIn(b'PDF temporarily unavailable', response.data)
            self.assertNotIn(b'credentials', response.data)
            self.assertNotIn(b'<Error>', response.data)
        self.assertEqual(self.writes(), [])

    def test_unknown_storage_url_does_not_guess_a_slug_filename(self):
        self.row = ('https://untrusted.example.test/book.pdf','Book','some-slug')
        response = self.client.get('/book/4/download')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.writes(), [])

    def test_legacy_uploader_pdf_reaches_storage_without_a_prefix_rewrite(self):
        from pdf_delivery import resolve_r2_key, open_pdf_object, PDFDeliveryError
        from test_pdf_delivery import SDK, PDF
        key='uploads/Book_Name_@DocoDive.pdf'
        self.scope['extract_r2_key']=lambda value:resolve_r2_key(value,public_base='https://assets.example.test')
        self.scope['open_pdf_object']=open_pdf_object
        self.scope['PDFDeliveryError']=PDFDeliveryError
        self.row=('https://assets.example.test/'+key,'Original upload','original-upload')
        for endpoint in ('pdf','download'):
            with self.subTest(endpoint=endpoint):
                sdk=SDK(ContentType='application/octet-stream')
                self.scope['r2_client']=sdk
                response=self.client.get('/book/4/'+endpoint,buffered=True)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.mimetype,'application/pdf')
                self.assertEqual(response.data,PDF)
                self.assertEqual(sdk.calls[0][1]['Key'],key)
                response.close()
                self.assertEqual(sdk.body.close_count,1)

    def test_metrics_cursor_failure_cannot_abort_pdf_delivery(self):
        original = self.connection.cursor
        calls = []
        def factory():
            calls.append(True)
            if len(calls) > 1: raise RuntimeError('metrics unavailable')
            return original()
        self.connection.cursor = factory
        response = self.client.get('/book/4/download', buffered=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'%PDF-1.4')
        response.close()
        self.assertTrue(self.resource.closed)

    def test_metrics_cursor_close_failure_cannot_abort_pdf_delivery(self):
        original = self.connection.cursor
        calls = []
        def factory():
            cursor = original()
            calls.append(True)
            if len(calls) > 1:
                def fail_close(): raise RuntimeError('cursor close unavailable')
                cursor.close = fail_close
            return cursor
        self.connection.cursor = factory
        response = self.client.get('/book/4/download', buffered=True)
        self.assertEqual(response.status_code, 200)
        response.close()
        self.assertTrue(self.resource.closed)

    def test_if_range_falls_back_to_a_complete_current_object(self):
        response = self.client.get('/book/4/download', headers={'Range':'bytes=0-7','If-Range':'"old-version"'}, buffered=True)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.calls[-1][1]['range_header'])
        self.assertNotIn('Content-Range', response.headers)
        self.assertEqual(self.writes(), [])
        response.close()

    def test_guest_and_unapproved_book_cannot_reach_storage(self):
        self.row = None
        self.assertEqual(self.client.get('/book/4/pdf').status_code, 404)
        with self.client.session_transaction() as state: state.clear()
        self.assertEqual(self.client.get('/book/4/download').status_code, 302)
        self.assertEqual(self.client.get('/book/4/pdf').status_code, 401)
        self.assertEqual(self.calls, [])

    def test_reader_uses_stable_same_origin_content_url(self):
        response = self.client.get('/book/4/read')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'/book/4/pdf')
        self.assertEqual(self.calls, [])

    def test_filename_cannot_inject_response_headers(self):
        self.row = (self.row[0], 'A title\r\nX-Injected: yes/..', 'book')
        response = self.client.get('/book/4/download')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('X-Injected', response.headers)
        self.assertNotIn('\r', response.headers['Content-Disposition'])
        response.close()

    def test_real_reader_template_has_one_server_gated_download_and_stable_iframe(self):
        from test_community_views import CommunityViewTests
        from bs4 import BeautifulSoup
        fixture = CommunityViewTests(); fixture.setUp()
        html = fixture.render('read_online', book_id=4, book_title='A <safe> book', book_slug='book', pdf_url='/book/4/pdf')
        document = BeautifulSoup(html, 'html.parser')
        self.assertIsNone(document.select_one('#pdfIframe').get('src'),'Never embed an unchecked HTML response')
        self.assertEqual(document.select_one('#pdfIframe')['data-pdf-url'], '/book/4/pdf')
        self.assertIsNotNone(document.select_one('script[src*="js/pdf-reader.js"]'))
        self.assertIn('PDF reader:', document.select_one('#pdfIframe')['title'])
        self.assertEqual(len(document.select('a[href="/book/4/download"]')), 1)
        self.assertNotIn('/api/download/', html)


if __name__ == '__main__': unittest.main()
