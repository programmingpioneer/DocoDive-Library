"""Reviews remain honest, selectable and safe when rendered without real services."""
import re
import unittest
import test_community_views


class ReviewsViewTests(unittest.TestCase):
    def setUp(self):
        self.view=test_community_views.CommunityViewTests()
        self.view.setUp()
        # The shared URL fixture registers only the first decorator per endpoint.
        # Include the real slug URL as well when checking linked book titles.
        self.view.app.add_url_rule('/book/<slug>/<int:book_id>', 'book_detail')

    def render(self,**extra):
        data=dict(reviews=[],books=[dict(id=4,title='A <safe> book')],avg_rating=0,total_reviews=0,breakdown={i:0 for i in range(1,6)})
        data.update(extra)
        return self.view.render('reviews',**data)

    def test_review_form_has_optional_searchable_book_and_native_star_choice(self):
        html=self.render()
        select=re.search(r'<select[^>]+id="reviewBookSelect"[^>]*>',html).group(0)
        self.assertNotIn('required',select)
        self.assertIn('Book <span',html)
        self.assertIn('optional',html)
        self.assertIn('role="combobox"',html)
        self.assertIn('aria-controls="reviewBookResults"',html)
        self.assertIn('A &lt;safe&gt; book',html)
        self.assertEqual(len(re.findall(r'type="radio" name="rating"',html)),5)
        self.assertIn('for="reviewComment"',html)
        self.assertNotIn('defaultBookId',html)

    def test_empty_reviews_and_no_books_do_not_invent_scores_or_post_to_book_one(self):
        html=self.render(books=[])
        self.assertIn('No written reviews yet',html)
        self.assertIn('id="reviewForm"',html)
        self.assertIn('general feedback',html)
        self.assertNotIn('rv-cat-num',html)
        self.assertNotIn('0 written reviews ·',html)

    def test_real_reviews_escape_content_and_keep_profile_and_pagination(self):
        html=self.render(avg_rating=4,total_reviews=25,page=2,total_pages=3,breakdown={5:0,4:25,3:0,2:0,1:0},reviews=[dict(username='reader',full_name='<A Reader>',avatar=None,rating=4,comment='<script>alert(1)</script>',created_at='Nov 1, 2026',book_id=4,book_title='A <safe> book',book_slug='safe-book')])
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',html)
        self.assertIn('&lt;A Reader&gt;',html)
        self.assertIn('/user/profile/reader',html)
        self.assertIn('Page 2 of 3',html)
        self.assertIn('page=1',html)
        self.assertIn('page=3',html)
        self.assertIn('reader-review-book',html)
        self.assertIn('A &lt;safe&gt; book',html)
        self.assertIn('/book/safe-book/4',html)


if __name__=='__main__':unittest.main()
