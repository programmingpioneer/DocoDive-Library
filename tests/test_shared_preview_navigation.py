"""Preview navigation runs against synthetic DOM and responses, with no services."""
from pathlib import Path
from html.parser import HTMLParser
import json
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
  constructor(tag='div'){this.tagName=tag;this.dataset={};this.children=[];this._text='';this.value='';this.className='';this.handlers={};this.hidden=false;this.disabled=false;this.scrollTop=0;this.clientHeight=400;this.scrollHeight=400;this.attrs={};}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  get firstElementChild(){return this.children[0]||null;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=[...children];}
  setAttribute(name,value){this.attrs[name]=String(value);}
  addEventListener(name,handler,options={}){(this.handlers[name] ||= []).push({handler,once:options.once});}
  dispatch(name,event={}){const entries=this.handlers[name]||[];this.handlers[name]=entries.filter(entry=>!entry.once);entries.forEach(entry=>entry.handler(event));}
  scrollTo(options){this.lastScroll=options;this.scrollTop=options.top;this.dispatch('scroll');}
  focus(){this.focused=true;}
}
function fixture(reduced=false,createModal=false){
  const body=new Element(),modal=new Element(),controls=new Element(),up=new Element('button'),down=new Element('button');
  controls.hidden=true;modal.shown=false;up.disabled=true;down.disabled=true;
  const requests=[],events={},observers=[],windowEvents={};
  controls.querySelector=selector=>selector==='[data-preview-scroll="up"]'?up:down;
  modal.querySelector=selector=>selector==='.modal-body'?body:selector==='.shared-preview-scroll-controls'?controls:selector==='[data-preview-scroll="up"]'?up:selector==='[data-preview-scroll="down"]'?down:null;
  modal.classList={contains:name=>name==='show'&&modal.shown};
  const instance={show(){modal.shown=true;modal.dispatch('shown.bs.modal')},hide(){modal.shown=false;modal.dispatch('hidden.bs.modal')}};
  const bootstrap={Modal:{getOrCreateInstance:()=>instance,getInstance:()=>instance}};
  const window={bootstrap,addEventListener:(name,handler)=>windowEvents[name]=handler,matchMedia:()=>({matches:reduced}),
    requestAnimationFrame:handler=>handler(),ResizeObserver:class{constructor(handler){this.callback=handler;observers.push(this)}observe(){}unobserve(){}}};
  let mounted=!createModal;
  const document={addEventListener:(name,handler)=>{(events[name] ||= []).push(handler)},getElementById:()=>mounted?modal:null,
    createElement:tag=>!mounted&&tag==='div'?modal:new Element(tag),querySelector:()=>null,activeElement:null,
    body:{append(){mounted=true;}}};
  const location={href:'https://example.test/',origin:'https://example.test',pathname:'/',search:''};
  const fetch=(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
  vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window,document,bootstrap,fetch,console,URL,URLSearchParams,location,navigator:{}});
  const all=(element=body)=>[element,...element.children.flatMap(child=>all(child))];
  const find=className=>all().find(element=>element.className.split(' ').includes(className));
  async function open(id=12){const request=window.openBookModal(id);requests.at(-1).resolve({ok:true,json:async()=>({id,title:'Synthetic book '+id,author:'A Reader',is_logged_in:true})});await request;}
  return {window,document,body,modal,controls,up,down,requests,events,observers,windowEvents,find,open,instance};
}
async function arrowsOnlyScrollPreview(){
  const f=fixture();await f.open();assert.equal(f.controls.hidden,true,'Short content does not need navigation');
  assert.equal(typeof f.windowEvents.resize,'function','Preview navigation responds to changing content bounds');
  f.body.scrollHeight=1400;f.windowEvents.resize();
  assert.equal(f.controls.hidden,false);assert.equal(f.up.disabled,true);assert.equal(f.down.disabled,false);
  f.down.dispatch('click');assert.ok(f.body.scrollTop>0);assert.equal(f.body.lastScroll.behavior,'smooth');
  assert.equal(f.up.disabled,false);
  f.body.scrollTop=990;f.body.dispatch('scroll');f.down.dispatch('click');
  assert.equal(f.body.scrollTop,1000,'The downward step is clamped to the last content');assert.equal(f.down.disabled,true);
  f.body.scrollTop=10;f.body.dispatch('scroll');f.up.dispatch('click');
  assert.equal(f.body.scrollTop,0);assert.equal(f.up.disabled,true);
  f.body.scrollHeight=400;f.windowEvents.resize();assert.equal(f.controls.hidden,true);
  assert.equal(f.up.disabled,true);assert.equal(f.down.disabled,true);
}
async function reducedMotionAndFreshOpen(){
  const f=fixture(true);await f.open();assert.equal(typeof f.windowEvents.resize,'function','Preview navigation tracks resized content');f.body.scrollHeight=1400;f.windowEvents.resize();f.down.dispatch('click');
  assert.equal(f.body.lastScroll.behavior,'auto','Reduced-motion preferences avoid smooth movement');
  await f.open(13);assert.equal(f.body.scrollTop,0,'Each book starts at its title');
  assert.equal(f.up.disabled,true);
}
async function draftsSurviveReopen(){
  const f=fixture();await f.open(12);
  f.find('shared-preview-comment').value='Keep this review while checking another book';
  f.find('shared-preview-comment').dispatch('input');f.find('shared-preview-rating').value='3';f.find('shared-preview-rating').dispatch('change');
  f.instance.hide();await f.open(99);assert.equal(f.find('shared-preview-comment').value,'');
  await f.open(12);assert.equal(f.find('shared-preview-comment').value,'Keep this review while checking another book');
  assert.equal(f.find('shared-preview-rating').value,'3');
}
async function closeReturnsFocusToTrigger(){
  const f=fixture(),trigger=new Element('button');trigger.isConnected=true;
  const request=f.window.openBookModal(12,trigger);f.requests[0].resolve({ok:true,json:async()=>({title:'Sample book',is_logged_in:false})});await request;
  f.instance.hide();assert.equal(trigger.focused,true,'Closing the modal restores keyboard focus to its trigger');
}
async function submissionKeepsLaterEdits(){
  const f=fixture();await f.open(12);const comment=f.find('shared-preview-comment');
  comment.value='Review being submitted';comment.dispatch('input');
  const pending=f.find('shared-preview-review-form').onsubmit({preventDefault(){}});
  comment.value='A later edit while submitting';comment.dispatch('input');
  f.requests[1].resolve({ok:true,json:async()=>({success:true})});await pending;
  assert.equal(comment.value,'A later edit while submitting','An accepted review cannot erase text typed after submission');
  await f.open(12);assert.equal(f.find('shared-preview-comment').value,'A later edit while submitting');
}
async function reviewFormPrecedesExistingReviews(){
  const f=fixture(),pending=f.window.openBookModal(12);
  f.requests[0].resolve({ok:true,json:async()=>({id:12,title:'Sample book',is_logged_in:true,
    reviews:[{username:'Existing Reader',rating:4,comment:'A useful book'}]})});await pending;
  const section=f.find('shared-preview-reviews'),form=f.find('shared-preview-review-form'),card=f.find('shared-preview-review-card');
  const descendants=node=>[node,...node.children.flatMap(descendants)],nodes=descendants(section);
  assert.ok(nodes.indexOf(form)<nodes.indexOf(card),'The review entry form appears before existing reviews');
  assert.ok(card.textContent.includes('Existing Reader'),'Existing reader feedback remains available below the form');
}
async function createdModalMarkup(){const f=fixture(false,true);await f.open();console.log(JSON.stringify({markup:f.modal.innerHTML}));}
(async()=>{await ({arrowsOnlyScrollPreview,reducedMotionAndFreshOpen,draftsSurviveReopen,closeReturnsFocusToTrigger,submissionKeepsLaterEdits,reviewFormPrecedesExistingReviews,createdModalMarkup})[process.argv[2]]();console.log(process.argv[2]+' passed');})().catch(error=>{console.error(error);process.exitCode=1});
"""


class ModalMarkup(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.stack = []
        self.controls_in_header = False
        self.controls_in_content = False
        self.body_in_content = False
        self.controls = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'shared-preview-scroll-controls' in attrs.get('class', '').split():
            self.controls_in_header = any('modal-header' in parent.get('class', '').split()
                                          for _, parent in self.stack)
            self.controls_in_content = bool(self.stack and
                'modal-content' in self.stack[-1][1].get('class', '').split())
        if 'data-preview-scroll' in attrs:
            self.controls.append(attrs['data-preview-scroll'])
        if 'modal-body' in attrs.get('class', '').split():
            self.body_in_content = bool(self.stack and
                'modal-content' in self.stack[-1][1].get('class', '').split())
        if tag not in ('path',):
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()


class SharedPreviewNavigationTests(unittest.TestCase):
    def test_scroll_pair_overlays_the_full_width_content(self):
        result = subprocess.run([shutil.which('node'), '-e', CHECK,
                                 str(ROOT / 'static/js/user.js'), 'createdModalMarkup'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        markup = ModalMarkup(json.loads(result.stdout.splitlines()[0])['markup'])
        self.assertFalse(markup.controls_in_header, 'Scroll arrows no longer occupy the header')
        self.assertTrue(markup.controls_in_content, 'Scroll arrows overlay the modal rather than reserve a column')
        self.assertTrue(markup.body_in_content, 'Book content fills the modal without a side column')
        self.assertEqual(markup.controls, ['up', 'down'])

    def test_scroll_boundaries_motion_and_draft_retention(self):
        for scenario in ('arrowsOnlyScrollPreview', 'reducedMotionAndFreshOpen',
                         'draftsSurviveReopen', 'closeReturnsFocusToTrigger', 'submissionKeepsLaterEdits',
                         'reviewFormPrecedesExistingReviews'):
            with self.subTest(scenario=scenario):
                result = subprocess.run([shutil.which('node'), '-e', CHECK,
                                         str(ROOT / 'static/js/user.js'), scenario],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
