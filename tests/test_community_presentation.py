import unittest
import sqlite3
from types import SimpleNamespace
from test_security_regressions import load_function

try:
    from community_presentation import achievement_summary, rank_leaders
except ImportError:
    achievement_summary = rank_leaders = None


class AchievementTests(unittest.TestCase):
    def test_new_reader_has_nine_locked_goals(self):
        self.assertIsNotNone(achievement_summary, 'Achievement summary is not implemented')
        result = achievement_summary(0, 0, 0, 0)
        self.assertEqual(len(result['items']), 9)
        self.assertEqual(result['unlocked_count'], 0)
        self.assertEqual(result['next']['key'], 'first_download')
        self.assertTrue(all(b['progress'] == 0 and b['remaining'] > 0 for b in result['items']))

    def test_progress_and_unlocked_count_are_shared_and_bounded(self):
        self.assertIsNotNone(achievement_summary, 'Achievement summary is not implemented')
        result = achievement_summary(12, 2, 3, 8)
        self.assertEqual(result['unlocked_count'], 4)
        collector = next(b for b in result['items'] if b['key'] == 'book_collector')
        self.assertEqual((collector['progress'], collector['remaining']), (100, 0))
        favorites = next(b for b in result['items'] if b['key'] == 'favoriter')
        self.assertEqual((favorites['progress'], favorites['remaining']), (40, 3))
        self.assertTrue(all(0 <= b['progress'] <= 100 for b in result['items']))

    def test_all_complete_has_no_fake_next_goal(self):
        self.assertIsNotNone(achievement_summary, 'Achievement summary is not implemented')
        result = achievement_summary(500, 50, 30, 150)
        self.assertEqual(result['unlocked_count'], 9)
        self.assertIsNone(result['next'])
        self.assertEqual(result['completion'], 100)

    def test_negative_and_missing_counts_start_at_zero(self):
        self.assertIsNotNone(achievement_summary, 'Achievement summary is not implemented')
        result = achievement_summary(-2, None, -4, 0)
        self.assertTrue(all(b['current'] == 0 for b in result['items']))

    def test_tied_leaders_have_the_same_rank_without_mutating_records(self):
        self.assertIsNotNone(rank_leaders)
        people = [dict(points=20), dict(points=20), dict(points=5)]
        result = rank_leaders(people)
        self.assertEqual([p['rank'] for p in result], [1, 1, 3])
        self.assertNotIn('rank', people[0])

    def test_current_rank_uses_the_same_existing_members_as_the_podium(self):
        for official in (None,2):
            with self.subTest(official=official):
                db=sqlite3.connect(':memory:')
                db.executescript('''CREATE TABLE users(id INTEGER,username TEXT,first_name TEXT,last_name TEXT,avatar_url TEXT);
                    CREATE TABLE user_points(user_id INTEGER,points INTEGER);
                    CREATE TABLE download_history(user_id INTEGER);CREATE TABLE favorites(user_id INTEGER);
                    CREATE TABLE reviews(user_id INTEGER);CREATE TABLE user_streaks(user_id INTEGER,longest_streak INTEGER);
                    INSERT INTO users VALUES(1,'reader','A','Reader',NULL);
                    INSERT INTO user_points VALUES(1,10),(999,500);''')
                if official:
                    db.execute("INSERT INTO users VALUES(2,'official','Official','Account',NULL)")
                    db.execute('INSERT INTO user_points VALUES(2,300)')
                class Cursor:
                    def execute(self,sql,args=()):
                        self.raw=None if 'leaderboard_snapshots' in sql else db.execute(sql.replace('%s','?'),args)
                    def fetchall(self):return self.raw.fetchall() if self.raw else []
                    def fetchone(self):return self.raw.fetchone()
                    def close(self):pass
                scope=dict(mysql=SimpleNamespace(connection=SimpleNamespace(cursor=Cursor)),session={'user_id':1},
                    get_site_setting=lambda key:official,is_official_user=lambda uid:uid==official,
                    render_template=lambda name,**context:context)
                result=load_function('leaderboard',scope)()
                self.assertEqual(result['current_user_rank'],1)
                self.assertEqual(result['leaderboard'][0]['rank'],1)
                db.close()
