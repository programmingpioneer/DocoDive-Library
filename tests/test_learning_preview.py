"""Shared preview actions use fake responses; no HTTP requests or configured app."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
  constructor(tag='div'){this.tagName=tag;this.dataset={};this.children=[];this._text='';this.className='';this.handlers={};}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=[...children];}
  addEventListener(name,handler,options={}){(this.handlers[name] ||= []).push({handler,once:options.once});}
  dispatch(name){const handlers=this.handlers[name]||[];this.handlers[name]=handlers.filter(entry=>!entry.once);handlers.forEach(entry=>entry.handler());}
}
function fixture(){
  const body=new Element(),modal=new Element(),requests=[],auth=[],transitions=[];
  modal.querySelector=selector=>selector==='.modal-body'?body:null;
  modal.classList={contains:name=>name==='show'&&modal.shown};
  const instance={show(){modal.shown=true},hide(){transitions.push('hide preview');modal.shown=false;if(!modal.holdHide)modal.dispatch('hidden.bs.modal')}};
  const bootstrap={Modal:{getOrCreateInstance:()=>instance,getInstance:()=>instance}};
  const window={bootstrap,showAuthModal:url=>{auth.push(url);transitions.push('show auth')}};
  const document={addEventListener(){},getElementById:()=>modal,createElement:tag=>new Element(tag),
    querySelector:selector=>selector==='meta[name="csrf-token"]'?{content:'synthetic-csrf-token'}:null};
  const fetch=(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
  const location={href:'https://example.test/learn/python',origin:'https://example.test',pathname:'/learn/python',search:''};
  const navigator={clipboard:{writeText:async()=>{}}};
  vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window,document,bootstrap,fetch,console,URL,URLSearchParams,location,navigator});
  const all=(element=body)=>[element,...element.children.flatMap(child=>all(child))];
  const find=className=>all().find(element=>element.className.split(' ').includes(className));
  const open=async logged=>{
    const promise=window.openBookModal(12);
    requests[0].resolve({ok:true,json:async()=>({id:12,slug:'test-book',title:'A <script>synthetic</script> book',
      author:'Sample Author',description:'Sample description',level:'Python',language:'English',
      image_url:'javascript:alert(1)',is_logged_in:logged,is_favorite:false,
      reviews:[{username:'A Reader',rating:4,comment:'Useful exercises'}]})});
    await promise;
  };
  return {body,requests,auth,find,all,open,window,modal,transitions};
}
const event=()=>({preventDefault(){this.prevented=true}});
async function metadataAndGuestGate(){
  const f=fixture();await f.open(false);
  assert.equal(f.requests[0].url,'/api/book/12');
  for(const text of ['Sample Author','Sample description','Python','English','Reviews','A Reader','Useful exercises'])assert.ok(f.body.textContent.includes(text),text);
  assert.ok(f.body.textContent.includes('A <script>synthetic</script> book'),'Untrusted titles are rendered as text');
  assert.equal(f.all().filter(element=>element.tagName==='script').length,0);
  assert.equal(f.all().filter(element=>element.tagName==='img').length,0,'Unsafe cover schemes must be rejected');
  for(const name of ['download','read','qr']){
    const control=f.find('shared-preview-'+name);assert.ok(control,name+' action is present');
    if(name==='qr'){assert.equal(control.tagName,'button');assert.equal(control.ariaHasPopup,'dialog');}
    else assert.ok(control.href.startsWith('/book/12/'));
    const click=event();control.onclick(click);
    assert.equal(click.prevented,true);assert.equal(f.requests.length,1,'Guests must not invoke a protected action');
  }
  assert.equal(f.auth.length,3);assert.equal(f.find('shared-preview-review-form'),undefined);
}
async function favoriteAndReviewCsrf(){
  const f=fixture();await f.open(true);
  const favorite=f.find('shared-preview-favorite');assert.ok(favorite);
  const update=favorite.onclick(event());
  assert.equal(f.requests[1].url,'/user/favorite/12');assert.equal(f.requests[1].options.method,'POST');
  assert.equal(f.requests[1].options.headers['X-CSRF-Token'],'synthetic-csrf-token');
  f.requests[1].resolve({ok:true,json:async()=>({success:true})});await update;
  assert.equal(favorite.ariaPressed,'true');assert.ok(favorite.textContent.includes('Favorited'));
  const form=f.find('shared-preview-review-form');assert.ok(form);
  assert.equal(form.dataset.ajax,'true','The preview owns its loading state instead of the global form loader');
  f.find('shared-preview-comment').value='A synthetic review';f.find('shared-preview-rating').value='4';
  const review=form.onsubmit(event());
  assert.equal(f.requests[2].url,'/book/12/review');assert.equal(f.requests[2].options.method,'POST');
  assert.equal(f.requests[2].options.headers['X-CSRF-Token'],'synthetic-csrf-token');
  assert.equal(f.requests[2].options.body.get('rating'),'4');
  assert.equal(f.requests[2].options.body.get('comment'),'A synthetic review');
  f.requests[2].resolve({ok:true,json:async()=>({success:true})});await review;
  assert.ok(f.body.textContent.includes('Review submitted'));
}
async function invalidIdMakesNoRequest(){
  const f=fixture();await f.window.openBookModal('12/../../admin');assert.equal(f.requests.length,0);
}
async function reviewSessionRedirectKeepsDraft(){
  const f=fixture();await f.open(true);
  const comment=f.find('shared-preview-comment');comment.value='Keep this unsent draft';
  const send=f.find('shared-preview-review-form').onsubmit(event());
  f.requests[1].resolve({ok:true,status:200,redirected:true,url:'https://example.test/user/login',json:async()=>{throw Error('HTML login page')}});
  await send;
  assert.equal(comment.value,'Keep this unsent draft');
  assert.equal(f.body.textContent.includes('Review submitted'),false);
  assert.equal(f.auth.length,1,'A login redirect should request sign in instead of reporting success');
}
async function errorsAndUnconfirmedResultsKeepState(){
  for(const response of [{ok:false,status:403},{ok:false,status:500},
      {ok:true,status:200,json:async()=>({success:false})},
      {ok:true,status:200,json:async()=>({})},
      {ok:true,status:200,redirected:true,url:'https://example.test/unexpected',json:async()=>({success:true})},
      {ok:true,status:200,json:async()=>{throw Error('HTML error page')}}]){
    const f=fixture();await f.open(true);
    const favorite=f.find('shared-preview-favorite'),update=favorite.onclick(event());
    f.requests[1].resolve(response);await update;
    assert.equal(favorite.ariaPressed,'false','Only confirmed success can change favorite state');
    assert.equal(favorite.disabled,false);assert.equal(f.auth.length,0);
    const comment=f.find('shared-preview-comment');comment.value='Keep draft after an unsuccessful response';
    const form=f.find('shared-preview-review-form'),send=form.onsubmit(event());
    f.requests[2].resolve(response);await send;
    assert.equal(comment.value,'Keep draft after an unsuccessful response');
    assert.equal(form.children.at(-1).disabled,false);
    assert.equal(f.body.textContent.includes('Review submitted'),false);
    assert.equal(f.auth.length,0);
  }
}
async function staleActionCannotInterruptCurrentPreview(){
  for(const action of ['favorite','review']){
    for(const expired of [{ok:false,status:401},{ok:false,status:403},
        {ok:true,status:200,json:async()=>({success:true})},
        {ok:true,status:200,redirected:true,url:'https://example.test/user/login',json:async()=>({success:true})}]){
      const f=fixture();await f.open(true);
      const pending=action==='favorite'?f.find('shared-preview-favorite').onclick(event()):f.find('shared-preview-review-form').onsubmit(event());
      const next=f.window.openBookModal(99);
      f.requests[2].resolve({ok:true,json:async()=>({id:99,title:'Current preview',author:'Another author',is_logged_in:true})});await next;
      const shown=f.body.textContent;
      f.requests[1].resolve(expired);await pending;
      assert.equal(f.body.textContent,shown);assert.equal(f.auth.length,0);
      assert.deepEqual(f.transitions,[],'A superseded action must not hide the current preview');
    }
  }
}
async function authWaitsForPreviewToClose(){
  const f=fixture();await f.open(false);f.modal.holdHide=true;
  f.find('shared-preview-download').onclick(event());
  assert.deepEqual(f.transitions,['hide preview']);assert.equal(f.auth.length,0);
  f.modal.dispatch('hidden.bs.modal');
  assert.deepEqual(f.transitions,['hide preview','show auth']);assert.equal(f.auth.length,1);
}
async function supersededAuthHandoffStaysQuiet(){
  const f=fixture();await f.open(false);f.modal.holdHide=true;
  f.find('shared-preview-download').onclick(event());
  const next=f.window.openBookModal(99);
  f.requests[1].resolve({ok:true,json:async()=>({id:99,title:'Another current preview',is_logged_in:true})});await next;
  f.modal.dispatch('hidden.bs.modal');
  assert.equal(f.auth.length,0);assert.ok(f.body.textContent.includes('Another current preview'));
}
(async()=>{
  await ({metadataAndGuestGate,favoriteAndReviewCsrf,invalidIdMakesNoRequest,
    reviewSessionRedirectKeepsDraft,errorsAndUnconfirmedResultsKeepState,
    staleActionCannotInterruptCurrentPreview,authWaitsForPreviewToClose,
    supersededAuthHandoffStaysQuiet})[process.argv[2]]();
  console.log(process.argv[2]+' passed');
})().catch(error=>{console.error(error);process.exitCode=1});
"""


class LearningPreviewTests(unittest.TestCase):
    def test_metadata_protected_actions_and_csrf(self):
        for scenario in ('metadataAndGuestGate', 'favoriteAndReviewCsrf', 'invalidIdMakesNoRequest',
                         'reviewSessionRedirectKeepsDraft', 'errorsAndUnconfirmedResultsKeepState',
                         'staleActionCannotInterruptCurrentPreview', 'authWaitsForPreviewToClose',
                         'supersededAuthHandoffStaysQuiet'):
            with self.subTest(scenario=scenario):
                result = subprocess.run([shutil.which('node'), '-e', CHECK,
                                         str(ROOT / 'static/js/user.js'), scenario],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
