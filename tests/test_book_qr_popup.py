"""QR popup behavior against a synthetic DOM, without fetching images or services."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.handlers={};this.attrs={};this.dataset={};this.className='';this._text='';this.hidden=false;this.isConnected=true;this.open=false;}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  append(...children){for(const child of children){if(child.parentElement)child.parentElement.children=child.parentElement.children.filter(item=>item!==child);child.parentElement=this;this.children.push(child);}}
  replaceChildren(...children){this.children=[];this._text='';this.append(...children);}
  setAttribute(name,value){this.attrs[name]=String(value);}
  removeAttribute(name){delete this.attrs[name];}
  addEventListener(name,handler){(this.handlers[name] ||= []).push(handler);}
  dispatch(name,event={}){(this.handlers[name]||[]).forEach(handler=>handler(event));}
  showModal(){this.open=true;}
  close(){this.open=false;this.dispatch('close');}
  focus(){document.activeElement=this;this.focused=true;}
}
const body=new Element('body'),events={},requests=[];
const all=(element=body)=>[element,...element.children.flatMap(child=>all(child))];
const document={body,activeElement:null,addEventListener:(name,handler)=>{(events[name] ||= []).push(handler)},
  createElement:tag=>new Element(tag),getElementById:id=>all().find(item=>item.id===id)||null,querySelector:()=>null};
const location={href:'https://example.test/books',origin:'https://example.test',pathname:'/books',search:''};
const bootstrap={Modal:{getOrCreateInstance:element=>({show(){},hide(){element.dispatch('hidden.bs.modal')}}),getInstance:element=>({hide(){element.dispatch('hidden.bs.modal')}})}};
const window={bootstrap,addEventListener(){}};
const fetch=(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window,document,location,URL,URLSearchParams,bootstrap,navigator:{},fetch});
assert.equal(typeof window.openBookQr,'function','The QR action must open a popup on the current page');
const find=name=>all().find(item=>item.className.split(' ').includes(name));
const event=extra=>Object.assign({preventDefault(){this.prevented=true},stopPropagation(){this.stopped=true}},extra);
function open(id=7,options={}){window.openBookQr(id,{title:'A <safe> title',...options});return find('book-qr-dialog');}
function popupAndFocus(){
  const opener=new Element('button');body.append(opener);const dialog=open(7,{opener});
  assert.equal(dialog.tagName,'dialog');assert.equal(dialog.open,true);assert.equal(dialog.attrs['aria-labelledby'],'book-qr-heading');
  assert.equal(find('book-qr-image').src,'/book/7/qr','The image uses only the protected same-origin book QR route');
  assert.match(dialog.textContent,/A <safe> title/);assert.equal(requests.length,0,'QR display must not prefetch a PDF or submit tracking');
  const e=event({key:'Escape'});dialog.dispatch('keydown',e);assert.equal(e.prevented,true);assert.equal(e.stopped,true,'Escape must not close the enclosing book preview');assert.equal(dialog.open,false);assert.equal(opener.focused,true);
}
function latestImageOwnsFeedback(){
  const dialog=open(),old=find('book-qr-image');open(8,{title:'Another book'});const current=find('book-qr-image');
  assert.equal(all().filter(item=>item.tagName==='dialog').length,1,'All QR buttons reuse one popup');assert.equal(current.src,'/book/8/qr');
  old.dispatch('error');assert.doesNotMatch(find('book-qr-status').textContent,/unable/i,'A previous image cannot fail a newer book');
  current.dispatch('load');assert.equal(current.hidden,false);assert.equal(dialog.attrs['aria-busy'],'false');
  dialog.close();current.dispatch('error');assert.equal(dialog.open,false,'Late image replies cannot reopen a dismissed popup');
}
function failureAndRetry(){
  const dialog=open(),image=find('book-qr-image');image.dispatch('error');assert.match(find('book-qr-status').textContent,/unable/i);
  const retry=find('book-qr-retry');assert.equal(retry.hidden,false);retry.dispatch('click');const fresh=find('book-qr-image');assert.notEqual(fresh,image);assert.equal(fresh.src,'/book/7/qr');fresh.dispatch('load');assert.equal(retry.hidden,true);assert.equal(dialog.attrs['aria-busy'],'false');
}
function previewContainerAndBackdrop(){
  const preview=new Element(),opener=new Element('button');body.append(preview);preview.append(opener);const dialog=open(9,{container:preview,opener});
  assert.equal(dialog.parentElement,preview,'The native popup stays inside the Bootstrap focus trap');
  const draft=new Element('textarea');draft.value='Keep my unfinished review';preview.append(draft);
  dialog.dispatch('click',{target:find('book-qr-image')});assert.equal(dialog.open,true);
  dialog.dispatch('click',{target:dialog});assert.equal(dialog.open,false);assert.equal(draft.value,'Keep my unfinished review');
  open(9,{container:preview,opener});preview.dispatch('hide.bs.modal');assert.equal(dialog.open,false,'Closing the preview also dismisses its QR popup');
}
function invalidBookDoesNotOpen(){window.openBookQr('7/../../private?token=secret');assert.equal(find('book-qr-dialog'),undefined);assert.equal(requests.length,0);}
async function sharedActionUsesPopup(){
  const modal=new Element(),previewBody=new Element();modal.id='shared-book-preview';modal.classList={contains:()=>true};modal.querySelector=selector=>selector==='.modal-body'?previewBody:null;modal.append(previewBody);body.append(modal);
  const pending=window.openBookModal(12);requests[0].resolve({ok:true,json:async()=>({title:'A <safe> book',is_logged_in:true,link:'https://private.example.test/file?token=never-read-this'})});await pending;
  const comment=find('shared-preview-comment');comment.value='My unfinished review';comment.dispatch('input');
  const qr=find('shared-preview-qr'),click=event();qr.onclick(click);
  assert.equal(click.prevented,true);assert.equal(qr.tagName,'button');assert.equal(find('book-qr-dialog').open,true);
  assert.equal(find('book-qr-image').src,'/book/12/qr');assert.equal(location.href,'https://example.test/books');assert.equal(requests.length,1);
  find('book-qr-close').dispatch('click');assert.equal(comment.value,'My unfinished review');assert.equal(document.activeElement,qr);
  const oldAction=qr,next=window.openBookModal(99);requests[1].resolve({ok:true,json:async()=>({title:'New book',is_logged_in:true})});await next;oldAction.onclick(event());assert.equal(find('book-qr-dialog').open,false,'An old book action cannot reopen the QR popup');
}
(async()=>{await ({popupAndFocus,latestImageOwnsFeedback,failureAndRetry,previewContainerAndBackdrop,invalidBookDoesNotOpen,sharedActionUsesPopup})[process.argv[2]]();console.log(process.argv[2]+' passed');})().catch(error=>{console.error(error);process.exitCode=1});
"""


class BookQrPopupTests(unittest.TestCase):
    def test_same_page_popup_focus_races_and_recovery(self):
        for scenario in ('popupAndFocus', 'latestImageOwnsFeedback', 'failureAndRetry',
                         'previewContainerAndBackdrop', 'invalidBookDoesNotOpen', 'sharedActionUsesPopup'):
            with self.subTest(scenario=scenario):
                result = subprocess.run([shutil.which('node'), '-e', CHECK,
                                         str(ROOT/'static/js/user.js'), scenario],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
