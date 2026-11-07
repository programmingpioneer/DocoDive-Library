"""Rendered Home and Hub buttons open one controller, using synthetic responses."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
CHECK = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
  constructor(tag='div'){this.tagName=tag;this.id='';this.dataset={};this.children=[];this._text='';this.className='';this.style={};this.handlers={};this.classList={add(){},remove(){},toggle(){},contains(){return false}};}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=[...children];}
  addEventListener(name,handler){(this.handlers[name] ||= []).push(handler);}
  querySelector(){return null;}
  querySelectorAll(){return [];}
  contains(){return false;}
  hasAttribute(){return false;}
}
const fixture=JSON.parse(process.argv[2]),body=new Element(),modal=new Element(),requests=[],shows=[],elements={},events={};
modal.id='shared-book-preview';modal.querySelector=selector=>selector==='.modal-body'?body:null;
const bootstrap={Modal:class{
  constructor(element){this.element=element;}
  show(){shows.push(this.element.id);}
  static getOrCreateInstance(element){return new this(element);}
}};
const document={body:new Element(),addEventListener:(name,handler)=>{(events[name] ||= []).push(handler)},
  querySelector:()=>new Element(),querySelectorAll:()=>[],createElement:tag=>new Element(tag),
  getElementById:id=>id==='shared-book-preview'?modal:(elements[id] ||= Object.assign(new Element(),{id}))};
const window={bootstrap,addEventListener(){},DocoDiveLoading:{fill(target){target.textContent='Skeleton';return()=>{};}}};
const fetch=url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject}));
const scope={window,document,bootstrap,fetch,console,URL,URLSearchParams,navigator:{},location:{href:'https://example.test/',pathname:'/',search:''},setInterval(){},setTimeout(){},BroadcastChannel:class{}};
vm.createContext(scope);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),scope);
fixture.scripts.forEach(script=>vm.runInContext(script,scope));
(events.DOMContentLoaded||[]).forEach(handler=>handler());
(async()=>{
  for(const attrs of fixture.buttons){
    const button={dataset:{bookId:attrs['data-book-id']},className:attrs.class};
    button.closest=selector=>selector.startsWith('.')&&button.className.split(' ').includes(selector.slice(1))?button:null;
    const before=requests.length;
    (events.click||[]).forEach(handler=>handler({target:button,preventDefault(){}}));
    assert.equal(requests.length,before+1,'A preview click fetches exactly once');
    assert.equal(requests.at(-1).url,'/api/book/'+button.dataset.bookId);
    assert.equal(shows.at(-1),'shared-book-preview','Every page uses the same modal');
    assert.equal(body.textContent,'Skeleton');
    requests.at(-1).resolve({ok:true,json:async()=>({title:'Book '+button.dataset.bookId,author:'Sample author',is_logged_in:false})});
    await new Promise(resolve=>setImmediate(resolve));
    assert.ok(body.textContent.includes('Book '+button.dataset.bookId),'The clicked book owns its content');
    assert.ok(body.textContent.includes('Reviews'));
  }
  console.log(fixture.buttons.length+' rendered preview buttons opened the shared modal');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.buttons = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button' and any(name.endswith('preview-trigger')
                                   for name in attrs.get('class', '').split()):
            self.buttons.append(attrs)


class HomePreviewControlTests(unittest.TestCase):
    def test_home_and_hub_clicks_have_one_shared_preview(self):
        env = Environment(loader=ChoiceLoader([
            DictLoader({'user/base.html': '{% block content %}{% endblock %}{% block scripts %}{% endblock %}'}),
            FileSystemLoader(ROOT / 'templates')]), autoescape=True)
        env.globals['url_for'] = lambda endpoint, **kw: '/static/' + kw.get('filename', '')
        env.filters['slugify'] = lambda value: str(value).lower().replace(' ', '-')
        books = [dict(id=number, slug='example-' + str(number), title='Synthetic book ' + str(number),
                      author='Sample author', level='Python', description='Local fixture', language='English',
                      image_url=None, download_count=0, view_count=0, avg_rating=0, link='/example.pdf')
                 for number in (4, 8)]
        context = dict(site_content={}, hub_content={}, user_logged_in=False, pdfs=books, books=books,
                       search_query='', category='Python', category_name='Python', category_slug='python',
                       author_filter='', lang_filter='', categories=[], all_categories=[], category_modules=[],
                       page=1, total_pages=1, has_next=False, featured_book=None, streak=0, longest=0,
                       recommended_books=[], total_books=2, total_downloads=0, total_users=0,
                       total_categories=1, recent_reviews=[], user_downloads=0, user_favorites=0,
                       user_reviews=0, q='', sort='latest', books_jsonld={}, request=type('Request', (), {
                           'host_url':'https://example.test/', 'base_url':'https://example.test/learn/python'})())
        for page in ('index', 'learning_hub'):
            with self.subTest(page=page):
                html = env.get_template('user/' + page + '.html').render(**context)
                buttons = Page(html).buttons
                self.assertGreaterEqual(len(buttons), 2)
                self.assertEqual({button['data-book-id'] for button in buttons}, {'4', '8'})
                result = subprocess.run([shutil.which('node'), '-e', CHECK,
                                         str(ROOT / 'static/js/user.js'), json.dumps(dict(
                                             buttons=buttons, scripts=[script for attrs, script in re.findall(
                                                 r'<script([^>]*)>(.*?)</script>', html, re.S)
                                                 if 'application/ld+json' not in attrs and 'src=' not in attrs]))],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
