"""Reader library/preferences render against isolated fixtures only."""
from bs4 import BeautifulSoup
import test_community_views
import unittest


class ReaderPageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_community_views.CommunityViewTests()
        self.fixture.setUp()

    def test_saved_and_history_cards_keep_destinations_and_escape_content(self):
        books=[dict(id=8,title='<script>unsafe</script>',author='A long author',level='Python',slug=None,image_url=None,downloaded_at='2026-11-01 12:00'),
               dict(id=9,title=' ',author=None,level='Other',slug='other-book',image_url=None,downloaded_at='2026-10-31 12:00')]
        for name in ('user_favorites','user_history'):
            html=self.fixture.render(name,pdfs=books)
            doc=BeautifulSoup(html,'html.parser')
            self.assertIsNotNone(doc.select_one('[data-reader-library] input[type=search]'))
            self.assertEqual(len(doc.select('.shelf-card')),2)
            self.assertNotIn('<script>unsafe</script>',html)
            self.assertIn('Untitled book',html)
            if name=='user_history':self.assertIsNotNone(doc.select_one('a[href="/book/8/8/download"]'))
            else:self.assertEqual(len(doc.select('button.shared-preview-trigger')),2)

    def test_empty_library_provides_real_browse_route(self):
        for name in ('user_favorites','user_history'):
            doc=BeautifulSoup(self.fixture.render(name,pdfs=[]),'html.parser')
            self.assertIsNotNone(doc.select_one('.reader-library-empty a[href="/books"]'))
            self.assertEqual(len(doc.select('.shelf-card')),0)

    def test_menu_links_participate_in_bootstrap_arrow_navigation(self):
        doc=BeautifulSoup(self.fixture.render('user_favorites',pdfs=[]),'html.parser')
        for selector,minimum in [('.reader-learning-menu a.mega-item',20),('.reader-community-menu a.mega-item',4)]:
            links=doc.select(selector)
            self.assertGreaterEqual(len(links),minimum)
            self.assertTrue(all('dropdown-item' in link.get('class',[]) for link in links))

    def test_paused_preferences_preserve_native_categories_and_frequency(self):
        html=self.fixture.render('preferences',pref=dict(notify_new_books=False,favorite_categories=['Long <topic>'],email_frequency='off'),categories=['Python','Long <topic>'])
        doc=BeautifulSoup(html,'html.parser')
        form=doc.select_one('form[action="/user/preferences"]')
        self.assertEqual(form.select_one('input[name=_csrf_token]')['value'],'test-csrf')
        self.assertFalse(form.select_one('[name=notify_new_books]').has_attr('checked'))
        selected=form.select('[name=favorite_categories][checked]')
        self.assertEqual([e['value'] for e in selected],['Long <topic>'])
        self.assertFalse(any(e.has_attr('disabled') for e in form.select('input')))
        selected_frequency=form.select_one('input[name=email_frequency][checked]')
        self.assertIsNotNone(selected_frequency)
        self.assertEqual(selected_frequency['value'],'off')
        self.assertEqual({e['value'] for e in form.select('input[name=email_frequency]')},{'daily','weekly','off'})
        self.assertIn('all categories',html.lower())
