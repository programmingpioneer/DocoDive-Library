"""Presentation defaults remain separate from actual account/review data."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from test_security_regressions import load_function

try:
    from public_presentation import community_display_count, homepage_review_cards
except ImportError:
    community_display_count = homepage_review_cards = None


class PresentationTests(unittest.TestCase):
    def test_counter_adds_only_the_requested_starting_value(self):
        self.assertIsNotNone(community_display_count, 'Display counter is not implemented')
        self.assertEqual(community_display_count(0), 273839)
        self.assertEqual(community_display_count(2), 273841)
        self.assertEqual(community_display_count(-1), 273839)

    def test_empty_reviews_have_explicit_sample_cards_without_mutating_input(self):
        self.assertIsNotNone(homepage_review_cards, 'Review fallback is not implemented')
        reviews = []
        cards = homepage_review_cards(reviews)
        self.assertGreaterEqual(len(cards), 3)
        self.assertTrue(all(card['sample'] for card in cards))
        self.assertTrue(all('Sample' in card['full_name'] for card in cards))
        cards[0]['comment'] = 'changed copy'
        self.assertNotEqual(homepage_review_cards([])[0]['comment'], 'changed copy')
        self.assertEqual(reviews, [])

    def test_actual_reviews_replace_samples(self):
        self.assertIsNotNone(homepage_review_cards, 'Review fallback is not implemented')
        review = dict(username='real_reader', full_name='A Reader', rating=4, comment='Useful book.', avatar='')
        cards = homepage_review_cards([review])
        self.assertEqual(len(cards), 1)
        self.assertFalse(cards[0].get('sample', False))
        self.assertEqual(cards[0]['comment'], 'Useful book.')

    def test_home_aggregates_keep_measured_counts_and_samples_separate(self):
        statements = []
        class Cursor:
            def execute(self, sql, args=()):
                statements.append(sql)
                self.sql = sql
            def fetchone(self):
                if 'SUM(download_count)' in self.sql:
                    return (12,)
                if 'FROM users' in self.sql:
                    return (2,)
                if 'FROM categories' in self.sql:
                    return (4,)
                if 'FROM reviews' in self.sql:
                    return (0,)
                return (8,)
            def fetchall(self):
                return []
            def close(self):
                pass
        scope = dict(datetime=datetime, _HOME_STATS_CACHE={'ts': None, 'data': None},
                     mysql=SimpleNamespace(connection=SimpleNamespace(cursor=Cursor)))
        with patch('public_metrics.monthly_active_members', return_value=2):
            result = load_function('get_home_stats', scope)()
        self.assertEqual(result['total_users'], 2)
        self.assertEqual(result['monthly_users'], 2)
        self.assertEqual(result['community_counter'], 273841)
        self.assertEqual(result['total_reviews'], 0)
        self.assertEqual(result['recent_reviews'], [])
        self.assertEqual(len(result['review_cards']), 3)
        self.assertTrue(all(sql.startswith('SELECT') for sql in statements))


if __name__ == '__main__':
    unittest.main()
