"""Synthetic lesson rendering and navigation; never imports the configured app."""
import ast
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import unittest

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader, TemplateNotFound
import learning_content

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def render_module(slug, module):
    base = """<title>{% block title %}{% endblock %}</title>
    <meta name="description" content="{% block meta_description %}{% endblock %}">
    {% block extra_css %}{% endblock %}{% block content %}{% endblock %}
    {% block scripts %}{% endblock %}"""
    env = Environment(loader=ChoiceLoader([
        DictLoader({'user/base.html': base}), FileSystemLoader(ROOT / 'templates')]),
        autoescape=True)
    env.globals.update(url_for=lambda endpoint, **kw: '/static/' + kw.get('filename', ''),
                       request=SimpleNamespace(base_url=f'https://example.test/learn/{slug}/{module}',
                                               host_url='https://example.test/'))
    scope = dict(vars(learning_content), mysql=SimpleNamespace(connection=SimpleNamespace(
        cursor=lambda: SimpleNamespace(close=lambda: None))),
        slug_to_category_name=lambda value, cur: value.replace('-', ' ').title(),
        category_to_slug=lambda value: slug, abort=lambda code: (_ for _ in ()).throw(ValueError(code)),
        TemplateNotFound=TemplateNotFound,
        render_template=lambda name, **context: env.get_template(name).render(**context))
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8-sig'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'category_module')
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'isolated-lesson', 'exec'), scope)
    return scope['category_module'](slug, module)


NAV_CHECK = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const events={};
const label={textContent:''};
const button={hidden:false,attrs:{},handlers:{},setAttribute(k,v){this.attrs[k]=String(v)},
  querySelector(){return label},addEventListener(k,v){this.handlers[k]=v}};
const link={handlers:{},addEventListener(k,v){this.handlers[k]=v}};
const nav={hidden:false,querySelectorAll(){return [link]}};
const root={classList:{add(){}},querySelector(s){return s==='.course-nav-toggle'?button:nav}};
const media={matches:false,addEventListener(k,v){this.change=v}};
const document={addEventListener(k,v){events[k]=v},querySelectorAll(){return [root]}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document,window:{matchMedia:()=>media}});
events.DOMContentLoaded();
assert.equal(nav.hidden,true);assert.equal(button.attrs['aria-expanded'],'false');
assert.equal(label.textContent,'Show Course Content');
button.handlers.click();assert.equal(nav.hidden,false);assert.equal(button.attrs['aria-expanded'],'true');
assert.equal(label.textContent,'Hide Course Content');
button.handlers.click();assert.equal(nav.hidden,true);assert.equal(label.textContent,'Show Course Content');
button.handlers.click();link.handlers.click();assert.equal(nav.hidden,true,'Following a lesson should close the mobile contents');
media.matches=true;media.change();assert.equal(nav.hidden,false);assert.equal(button.attrs['aria-expanded'],'true');
media.matches=false;media.change();assert.equal(nav.hidden,true);assert.equal(button.attrs['aria-expanded'],'false');
console.log('mobile toggle, link selection and breakpoint synchronization passed');
"""


class LearningExperienceTests(unittest.TestCase):
    def test_each_hub_book_has_its_own_preview_control(self):
        env = Environment(loader=ChoiceLoader([
            DictLoader({'user/base.html': '{% block content %}{% endblock %}'}),
            FileSystemLoader(ROOT / 'templates')]), autoescape=True)
        books = [dict(id=number, title='Synthetic book ' + str(number), slug='book-' + str(number),
                      author='Sample author', image_url=None, level='Python', avg_rating=0,
                      download_count=0, view_count=0) for number in (11, 22, 33)]
        html = env.get_template('user/learning_hub.html').render(
            category='Python', category_slug='python', hub_content={}, total_books=3,
            total_downloads=0, all_categories=[], category_modules=learning_content.GENERIC_MODULES,
            books=books, total_pages=1, page=1,
            request=SimpleNamespace(host_url='https://example.test/',
                                    base_url='https://example.test/learn/python'))
        buttons = [attrs for tag, attrs in Page(html).tags if tag == 'button'
                   and 'shared-preview-trigger' in attrs.get('class', '').split()]
        self.assertEqual([button['data-book-id'] for button in buttons], ['11', '22', '33'])
        self.assertEqual([button['aria-label'] for button in buttons],
                         ['Preview ' + book['title'] for book in books])

    def test_mobile_contents_state_matches_label_and_accessibility(self):
        result = subprocess.run([shutil.which('node'), '-e', NAV_CHECK,
                                 str(ROOT / 'static/js/learning.js')],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_lesson_page_has_metadata_breadcrumbs_and_current_track(self):
        subjects = ['python', 'javascript', 'java', 'c-c', 'web-development',
                    'data-science', 'machine-learning', 'algorithms', 'databases',
                    'cyber-security', 'mobile-apps', 'devops', 'others', 'mathematics']
        pages = [(subject, module) for subject in subjects
                 for module in ('beginner', 'intermediate', 'advanced', 'practice')]
        pages += [('ielts', module) for module in ('reading', 'writing', 'listening', 'speaking')]
        for slug, module in pages:
            with self.subTest(slug=slug, module=module):
                html = render_module(slug, module)
                tags = Page(html).tags
                self.assertEqual(sum(tag == 'h1' for tag, _ in tags), 1)
                self.assertTrue(next(attrs['content'] for tag, attrs in tags
                                     if tag == 'meta' and attrs.get('name') == 'description').strip())
                self.assertTrue(any(tag == 'nav' and attrs.get('aria-label') == 'Breadcrumb'
                                    for tag, attrs in tags))
                self.assertTrue(any(tag == 'a' and attrs.get('aria-current') == 'page'
                                    and attrs.get('href') == f'/learn/{slug}/{module}'
                                    for tag, attrs in tags))
                for tag, attrs in tags:
                    if 'course-nav-toggle' in attrs.get('class', '').split():
                        self.assertEqual(attrs.get('aria-controls'), 'courseNav')
                        self.assertNotIn('data-bs-toggle', attrs)

    def test_python_lessons_and_projects_survive_shared_layout(self):
        for module, lessons in [('beginner', learning_content.PYTHON_BEGINNER_LESSONS),
                                ('intermediate', learning_content.PYTHON_INTERMEDIATE_LESSONS),
                                ('advanced', learning_content.PYTHON_ADVANCED_LESSONS)]:
            html = render_module('python', module)
            tags = Page(html).tags
            ids = {attrs.get('id') for _, attrs in tags}
            links = {attrs.get('href') for tag, attrs in tags if tag == 'a'}
            for lesson in lessons:
                self.assertIn('lesson-' + str(lesson['id']), ids)
                self.assertIn(lesson['docs_url'], links)
            self.assertIn('projects-section', html)
            self.assertIn('data-learning-page', html)


if __name__ == '__main__':
    unittest.main()
