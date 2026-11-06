"""Render real community templates without app config, credentials or services."""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from flask import render_template, session, abort
import test_admin_studio
from test_security_regressions import load_function
from seo import register_seo
from community_presentation import achievement_summary, rank_leaders

ROOT=Path(__file__).resolve().parents[1]


class CommunityViewTests(unittest.TestCase):
    def setUp(self):
        case=test_admin_studio.StudioTests();case.setUp()
        self.app=case.app
        register_seo(self.app,case.svc)
        self.app.jinja_env.filters['slugify']=lambda v:str(v).lower().replace(' ','-')
        tree=ast.parse((ROOT/'tests/test_admin_studio.py').read_text(encoding='utf-8'))
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='test_public_pages_render_metadata_and_javascript')
        values={}
        for n in method.body:
            if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('book','context'):
                exec(compile(ast.Module(body=[n],type_ignores=[]),'community-fixture','exec'),values)
        self.values=dict(values['context'],downloads=12,favorites=2,reviews=3,streak=4,longest=8,
            achievements=achievement_summary(12,2,3,8),unlocked_badges=[],current_badge=None,
            user=(1,'reader','private-reader@example.test',1,datetime(2026,1,1),None,'A bio',{},'A','Reader',None),
            total_uploads=1,total_reviews=3,total_favorites=2,total_points=20,total_downloads=12,
            social_links={},is_official=False,custom_badge=None)

    def render(self,name,owner=True,**extra):
        with self.app.test_request_context('/user/stats'):
            session.update(user_id=1 if owner else 2,user_name='reader',_csrf_token='test-csrf')
            return render_template('user/'+name+'.html',**dict(self.values,**extra))

    def test_public_profile_hides_email_and_owner_controls(self):
        public=self.render('user_profile',owner=False)
        self.assertNotIn('private-reader@example.test',public)
        self.assertNotIn('class="profile-actions"',public)
        own=self.render('user_profile')
        self.assertIn('private-reader@example.test',own)
        self.assertIn('class="profile-actions"',own)
        self.assertIn('4 / 9 unlocked',own)

    def test_stats_show_only_server_unlocked_badge_choices(self):
        badges=[dict(key='first_download',name='First Download',icon='stored-token',threshold=1)]
        html=self.render('user_stats',unlocked_badges=badges,current_badge='stored-token')
        self.assertIn('name="custom_badge" value="stored-token" checked',html)
        self.assertEqual(html.count('name="custom_badge"'),2)  # eligible choice and removal
        self.assertIn('name="_csrf_token" value="test-csrf"',html)
        self.assertNotIn('hrs reading',html)

    def test_profile_ignores_malformed_or_unsafe_stored_social_links(self):
        from bs4 import BeautifulSoup
        cases=[None,True,['https://example.test'], 'unexpected text',
               {'Website':'https://example.test','Bad':'javascript:alert(1)',
                'Number':42,'Object':{'url':'https://example.test'},'Empty':None}]
        for links in cases:
            with self.subTest(links=links):
                doc=BeautifulSoup(self.render('user_profile',social_links=links),'html.parser')
                actual=[a.get('href') for a in doc.select('.profile-social-links a')]
                self.assertEqual(actual,['https://example.test'] if isinstance(links,dict) else [])

    def test_small_leaderboards_do_not_create_placeholder_people(self):
        people=rank_leaders([dict(username='one',name='One',avatar_url=None,points=10,badge_count=1)])
        html=self.render('leaderboard',leaderboard=people)
        self.assertEqual(html.count('class="leader-top-card'),1)
        self.assertNotIn('Building weekly history',html)
        self.assertIn('Comparison history pending',html)
        self.assertIn('<dd>Unavailable</dd>',html)

    def test_404_recovers_even_when_recommendation_query_is_unavailable(self):
        def unavailable(*args,**kwargs):raise RuntimeError('fixture unavailable')
        common=load_function('inject_common',dict(session=session,app=self.app,is_official_user=unavailable,studio_content_setting=unavailable))
        self.app.context_processor(common)
        handler=load_function('not_found',dict(mysql=SimpleNamespace(connection=SimpleNamespace(cursor=unavailable)),app=self.app,render_template=render_template))
        self.app.register_error_handler(404,handler)
        response=self.app.test_client().get('/this-page-does-not-exist')
        self.assertEqual(response.status_code,404)
        self.assertIn(b'name="robots" content="noindex,follow"',response.data)
        self.assertIn(b'Search the library',response.data)

    def test_book_fallback_escapes_titles_and_handles_blank_titles(self):
        books=[dict(id=8,slug=None,title=' ',author=None,image_url=None),dict(id=9,slug=None,title='<script>alert(1)</script>',image_url=None)]
        html=self.render('404',trending_books=books)
        self.assertIn('Untitled book',html)
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertEqual(html.count('shared-preview-trigger'),2)

    def test_other_recovery_handlers_keep_their_http_status_and_noindex(self):
        handlers={400:'bad_request',401:'unauthorized',403:'forbidden',429:'too_many_requests',500:'internal_error',503:'service_unavailable'}
        for code,name in handlers.items():
            self.app.register_error_handler(code,load_function(name,dict(render_template=render_template)))
        self.app.add_url_rule('/fixture-error/<int:code>','fixture_error',lambda code:abort(code))
        for code in handlers:
            with self.subTest(code=code):
                response=self.app.test_client().get('/fixture-error/'+str(code))
                self.assertEqual(response.status_code,code)
                self.assertIn(b'noindex,follow',response.data)
                self.assertIn(b'Back to home',response.data)

    def badge_update(self, selected):
        tree=ast.parse((ROOT/'app.py').read_text(encoding='utf-8-sig'))
        definitions=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BADGE_DEFS' for t in n.targets)))
        calls=[]
        class Cursor:
            def execute(self,sql,args=()):self.sql=sql;calls.append((sql,args))
            def fetchone(self):
                if 'download_history' in self.sql:return (1,)
                if 'user_streaks' in self.sql:return (0,0)
                if 'custom_badge FROM' in self.sql:return (None,)
                return (0,)
            def close(self):pass
        mysql=SimpleNamespace(connection=SimpleNamespace(cursor=Cursor,commit=lambda:None))
        scope=dict(mysql=mysql,session={'user_id':1},request=SimpleNamespace(method='POST',form={'custom_badge':selected(definitions)}),BADGE_DEFS=definitions,render_template=lambda name,**context:context)
        result=load_function('user_stats',scope)()
        return calls,result

    def test_forged_locked_badge_cannot_be_saved(self):
        calls,_=self.badge_update(lambda defs:next(b['icon'] for b in defs if b['key']=='legend'))
        self.assertFalse(any(sql.startswith('UPDATE') for sql,_ in calls))

    def test_existing_unlocked_badge_token_is_still_accepted(self):
        calls,result=self.badge_update(lambda defs:defs[0]['icon'])
        updates=[args for sql,args in calls if sql.startswith('UPDATE')]
        self.assertEqual(len(updates),1)
        self.assertEqual(result['current_badge'],updates[0][0])
