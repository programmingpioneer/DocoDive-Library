from pathlib import Path
import unittest
from flask import Flask,render_template
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]

class PageSkeletonTests(unittest.TestCase):
    def test_placeholder_composition_matches_page_family(self):
        app=Flask(__name__,template_folder=str(ROOT/'templates'))
        cases={'home':'home','books':'catalog','detail':'detail','upload':'upload',
               'login':'auth','signup':'auth','forgot':'recovery','profile':'profile',
               'edit-profile':'form','settings':'settings','stats':'stats',
               'notifications':'inbox','preferences':'preferences','leaderboard':'leaderboard',
               'reviews':'reviews','feedback':'suggestions','contact':'legal','privacy':'legal'}
        rendered=[]
        for page,layout in cases.items():
            with self.subTest(page=page),app.test_request_context('/preview/page/'+page):
                doc=BeautifulSoup(render_template('shared/_page_skeleton.html'),'html.parser')
                loader=doc.select_one('#page-loader')
                self.assertEqual(loader.get('data-skeleton-layout'),layout)
                self.assertEqual(loader.get('data-skeleton-page'),page)
                self.assertEqual(loader.get('aria-hidden'),'true')
                self.assertTrue(loader.select('.skeleton-block'))
                rendered.append(str(loader))
        self.assertEqual(len(set(rendered)),len(cases))

    def test_lesson_skeleton_only_includes_a_tip_rail_where_the_course_has_one(self):
        app=Flask(__name__,template_folder=str(ROOT/'templates'))
        for subject,has_tips in [('python',False),('javascript',False),('mobile-apps',True),('ielts',True)]:
            with self.subTest(subject=subject),app.test_request_context('/preview/lesson/'+subject+'/beginner'):
                doc=BeautifulSoup(render_template('shared/_page_skeleton.html'),'html.parser')
                self.assertEqual(bool(doc.select('.sk-course-tips')),has_tips)

    def test_lesson_and_studio_use_course_and_workspace_shapes(self):
        app=Flask(__name__,template_folder=str(ROOT/'templates'))
        for path,layout in [('/preview/lesson/python/beginner','lesson'),
                            ('/preview/lesson/python/practice','practice'),
                            ('/admin-studio/users','studio-table'),
                            ('/admin-studio/dashboard','studio-dashboard')]:
            with self.subTest(path=path),app.test_request_context(path):
                doc=BeautifulSoup(render_template('shared/_page_skeleton.html'),'html.parser')
                self.assertEqual(doc.select_one('#page-loader').get('data-skeleton-layout'),layout)

if __name__=='__main__':unittest.main()
