"""Reader upload contracts rendered without app configuration or external services."""
from bs4 import BeautifulSoup
import unittest
import test_community_views

class UploadViewTests(unittest.TestCase):
    def setUp(self):
        self.view=test_community_views.CommunityViewTests();self.view.setUp()

    def test_native_upload_contract_labels_and_optional_cover_are_preserved(self):
        html=self.view.render('user_upload',categories=['Python','A <long> category'])
        doc=BeautifulSoup(html,'html.parser');form=doc.select_one('#uploadForm')
        self.assertEqual(form.get('method'),'post')
        self.assertEqual(form.get('action'),'/user/upload')
        self.assertEqual(form.get('enctype'),'multipart/form-data')
        self.assertTrue(form.has_attr('data-ajax'))
        self.assertEqual(form.select_one('[name=_csrf_token]').get('value'),'test-csrf')
        self.assertTrue(form.select_one('[name=pdf_file]').has_attr('required'))
        self.assertFalse(form.select_one('[name=cover_image]').has_attr('required'))
        self.assertEqual(form.select_one('[name=category] option').get('value'),'')
        self.assertIsNotNone(doc.select_one('label[for=pdf_file]'))
        self.assertIsNotNone(doc.select_one('label[for=cover_image]'))
        self.assertIsNotNone(doc.select_one('#coverThumb'))
        self.assertIn('A &lt;long&gt; category',html)
        self.assertIsNotNone(doc.select_one('noscript'))

    def test_page_has_accessible_real_progress_status_and_inline_errors(self):
        doc=BeautifulSoup(self.view.render('user_upload',categories=[]),'html.parser')
        self.assertEqual(len(doc.select('h1')),1)
        self.assertIsNotNone(doc.select_one('#uploadProgress[role=progressbar]'))
        self.assertIsNotNone(doc.select_one('#statusMessage[role=alert]'))
        self.assertIsNotNone(doc.select_one('[data-refresh-uploads]'))
        self.assertIsNotNone(doc.select_one('a[href="/community-guidelines"]'))
        self.assertIsNotNone(doc.select_one('a[href="/contact"]'))
        self.assertIsNotNone(doc.select_one('[data-upload-summary]'))

if __name__=='__main__':unittest.main()
