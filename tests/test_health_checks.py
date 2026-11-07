"""Render health probes use an isolated Flask app, never configured services."""
import ast
import hmac
from pathlib import Path
import secrets
import unittest

from flask import Flask, Response, abort, redirect, request, session
from flask_limiter import Limiter
from flask_talisman import Talisman

from test_security_regressions import load_function

ROOT=Path(__file__).resolve().parents[1]
PATHS=('/healthhz','/healthz')


class HealthCheckTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.app.config.update(TESTING=True,SECRET_KEY='isolated-health-fixture-only')
        scope=dict(request=request,Response=Response,IS_PRODUCTION=True,redirect=redirect,
                   session=session,abort=abort,secrets=secrets,hmac=hmac)
        try:
            health=load_function('serve_healthcheck',scope)
        except StopIteration:
            self.fail('The configured Render health probe has no early response handler')
        self.app.before_request(health)
        Talisman(self.app,force_https=True,content_security_policy=None)
        self.limiter=Limiter(app=self.app,key_func=lambda:'health-fixture',
                             default_limits=['1 per minute'],storage_uri='memory://')
        for name in ('enforce_canonical_host','csrf_protect','redirect_legacy_resources'):
            self.app.before_request(load_function(name,scope))
        self.app.after_request(load_function('add_cache_headers',scope))
        self.later_calls=[]

        @self.app.before_request
        def database_guard():
            if request.path in PATHS:
                self.fail('Health probes must not reach session/database/application hooks')
            self.later_calls.append(request.path)

        self.app.add_url_rule('/normal','normal',lambda:Response('normal',mimetype='text/plain'))
        self.app.add_url_rule('/change','change',lambda:'changed',methods=['POST'])
        self.client=self.app.test_client()

    def test_configured_path_and_canonical_alias_return_plain_get_and_head(self):
        for path in PATHS:
            for method in ('GET','HEAD'):
                with self.subTest(path=path,method=method):
                    response=self.client.open(path,method=method,base_url='http://www.library.example')
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.mimetype,'text/plain')
                    self.assertEqual(response.data,b'ok\n' if method=='GET' else b'')
                    self.assertNotIn('Location',response.headers)
                    self.assertNotIn('Set-Cookie',response.headers)
                    self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(self.later_calls,[])

    def test_probes_do_not_consume_the_normal_request_quota(self):
        for _ in range(6):
            self.assertEqual(self.client.get('/healthhz').status_code,200)
        self.assertEqual(self.client.get('/normal',base_url='https://library.example').status_code,200)
        self.assertEqual(self.client.get('/normal',base_url='https://library.example').status_code,429)

    def test_reader_cookie_cannot_turn_a_probe_into_a_database_check(self):
        with self.client.session_transaction() as state:
            state['user_id']=123
        response=self.client.get('/healthhz')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('Set-Cookie',response.headers)
        self.assertEqual(self.later_calls,[])

    def test_normal_requests_keep_https_and_csrf_protection(self):
        response=self.client.get('/normal',base_url='http://library.example')
        self.assertIn(response.status_code,(301,302,307,308))
        self.assertTrue(response.headers['Location'].startswith('https://'))
        self.assertEqual(self.client.post('/change',base_url='https://library.example').status_code,403)
        self.assertEqual(self.client.post('/healthhz',base_url='https://library.example').status_code,403)
        self.assertNotEqual(self.client.get('/healthhz/extra',base_url='https://library.example').status_code,200)

    def test_actual_registration_precedes_https_and_rate_limit_hooks(self):
        tree=ast.parse((ROOT/'app.py').read_text(encoding='utf-8'))
        index=next(i for i,node in enumerate(tree.body) if isinstance(node,ast.FunctionDef) and node.name=='serve_healthcheck')
        for name in ('Talisman','Limiter'):
            setup=next(i for i,node in enumerate(tree.body) if any(
                isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id==name
                for call in ast.walk(node)))
            self.assertLess(index,setup)
        decorators=tree.body[index].decorator_list
        self.assertTrue(any(isinstance(d,ast.Attribute) and d.attr=='before_request' for d in decorators))


if __name__=='__main__':unittest.main()
