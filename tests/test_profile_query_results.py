"""Reproduce the Sentry profile crash without app config or an external database."""
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from flask import abort,render_template,session
import test_community_views
from test_security_regressions import load_function


class ProfileQueryResultTests(unittest.TestCase):
    def setUp(self):
        self.view=test_community_views.CommunityViewTests()
        self.view.setUp()

    def route(self,missing=(),no_user=False,fail=None,counts=None):
        calls=[]
        class Cursor:
            closed=False
            def execute(inner,sql,args=()):
                inner.sql=sql
                calls.append((sql,args))
                if fail and fail in sql:raise RuntimeError('synthetic query failure')
            def fetchone(inner):
                sql=inner.sql
                if 'FROM users WHERE username' in sql:
                    return None if no_user else (7,'reader','private-reader@example.test',1,datetime(2026,1,1),None,'A reader.',None,'A','Reader',None)
                for table in missing:
                    if 'FROM '+table+' ' in sql:return None
                for table,value in (counts or {}).items():
                    if 'FROM '+table+' ' in sql:return (value,)
                if 'FROM user_streaks' in sql:return None
                if 'SUM(points)' in sql:return (None,)
                return (0,)
            def close(inner):inner.closed=True
        cursor=Cursor()
        self.last_cursor=cursor
        cursor.settings_reads=[]
        def setting(key):
            # The profile must finish its result stream before a helper opens a cursor.
            cursor.settings_reads.append(cursor.closed)
            return None
        logger=Mock()
        def render(name,**context):
            self.last_context=context
            return render_template(name,**context)
        scope=dict(mysql=SimpleNamespace(connection=SimpleNamespace(cursor=lambda:cursor)),
                   get_site_setting=setting,json=__import__('json'),abort=abort,
                   BADGE_DEFS=[],render_template=render,app=SimpleNamespace(logger=logger))
        handler=load_function('user_profile',scope)
        with self.view.app.test_request_context('/user/profile/reader'):
            session['user_id']=7
            html=handler('reader')
        return html,cursor,calls,logger

    def test_missing_aggregate_row_renders_unavailable_instead_of_crashing_or_fake_zero(self):
        for table in ['documents','reviews','favorites','user_points','download_history']:
            with self.subTest(table=table):
                html,cursor,calls,logger=self.route(missing=(table,))
                self.assertIn('Some activity totals are temporarily unavailable',html)
                self.assertIn('—',html)
                self.assertTrue(cursor.closed)
                logger.warning.assert_called()
                self.assertTrue(self.last_context['profile_stats_unavailable'])
                if table in ('reviews','favorites','download_history'):
                    self.assertIsNone(self.last_context['achievements'])
                    self.assertIn('Achievements temporarily unavailable',html)

    def test_valid_counts_and_achievements_are_not_replaced_by_fallbacks(self):
        html,cursor,calls,logger=self.route(counts=dict(documents=2,reviews=3,favorites=5,user_points=1234,download_history=12))
        self.assertEqual([self.last_context[key] for key in ('total_uploads','total_reviews','total_favorites','total_points','total_downloads')],[2,3,5,1234,12])
        self.assertEqual(self.last_context['achievements']['unlocked_count'],4)
        self.assertIn('1,234',html)
        self.assertNotIn('Some activity totals are temporarily unavailable',html)
        logger.warning.assert_not_called()

    def test_empty_account_and_null_points_are_real_zero_without_an_error_notice(self):
        html,cursor,calls,logger=self.route()
        self.assertIn('A Reader',html)
        self.assertNotIn('Some activity totals are temporarily unavailable',html)
        self.assertIn('0 / 9 unlocked',html)
        self.assertTrue(cursor.closed)
        self.assertTrue(all(cursor.settings_reads),'Site settings read overlaps the profile cursor')
        self.assertTrue(all(sql.lstrip().startswith('SELECT') and args for sql,args in calls))
        logger.warning.assert_not_called()

    def test_missing_profile_is_still_404_and_closes_its_cursor(self):
        with self.assertRaises(Exception) as error:self.route(no_user=True)
        self.assertEqual(getattr(error.exception,'code',None),404)
        self.assertTrue(self.last_cursor.closed)

    def test_query_failure_closes_cursor_without_hiding_database_errors(self):
        # A failed SQL query must remain an error, never become a fabricated zero.
        with self.assertRaisesRegex(RuntimeError,'synthetic query failure'):
            self.route(fail='FROM reviews')
        self.assertTrue(self.last_cursor.closed)


if __name__=='__main__':unittest.main()
