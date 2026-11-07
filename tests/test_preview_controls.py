"""Preview request races are checked locally, without browser or network traffic."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKS = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
  constructor(tag='div'){this.tagName=tag;this.dataset={};this.children=[];this._text='';}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=[...children];}
  addEventListener(name,callback){((this.handlers??={})[name]??=[]).push(callback);}
}
function fixture(){
  const body=new Element(),modal=new Element(),requests=[],loading=[];
  modal.querySelector=selector=>selector==='.modal-body'?body:null;
  const bootstrap={Modal:{getOrCreateInstance:()=>({show(){}})}};
  const window={bootstrap,DocoDiveLoading:{fill(target){
    const load={stops:0};loading.push(load);target.textContent='Skeleton '+loading.length;
    return ()=>{load.stops++;};
  }}};
  const document={addEventListener(){},getElementById:()=>modal,createElement:tag=>new Element(tag)};
  const fetch=url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject}));
  vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window,document,bootstrap,fetch,console});
  return {window,body,requests,loading};
}
const response=title=>({ok:true,json:async()=>({title,author:'A Reader',description:'A local test book'})});
async function lateFailureAfterNewSuccess(){
  const f=fixture(),first=f.window.openBookModal(1),second=f.window.openBookModal(2);
  f.requests[1].resolve(response('Newer book'));await second;
  const shown=f.body.textContent;
  f.requests[0].reject(new Error('Old request failed'));await first;
  assert.equal(f.body.textContent,shown,'A late failure must not replace the newer book');
  assert.equal(f.loading[0].stops,0,'The old request must not stop loading after replacement');
  assert.equal(f.loading[1].stops,1,'The current request must finish its own loading state');
}
async function lateFailureWhileNewPending(){
  const f=fixture(),first=f.window.openBookModal(1),second=f.window.openBookModal(2);
  f.requests[0].reject(new Error('Old request failed'));await first;
  assert.equal(f.body.textContent,'Skeleton 2','A late failure must leave the current skeleton visible');
  assert.equal(f.loading[0].stops,0);
  assert.equal(f.loading[1].stops,0,'The current skeleton stays active until its own response');
  f.requests[1].resolve(response('Current book'));await second;
  assert.match(f.body.textContent,/Current book/);assert.equal(f.loading[1].stops,1);
}
async function sameBookResponsesBackwards(){
  const f=fixture(),first=f.window.openBookModal(7),second=f.window.openBookModal(7);
  f.requests[1].resolve(response('Fresh same-book response'));await second;
  const shown=f.body.textContent;
  f.requests[0].resolve(response('Stale same-book response'));await first;
  assert.equal(f.body.textContent,shown,'Reopening the same book must still supersede its earlier request');
  assert.equal(f.loading[0].stops,0,'The old same-book request cannot finish the new loading state');
  assert.equal(f.loading[1].stops,1);
}
async function sameBookOldSuccessWhileNewPending(){
  const f=fixture(),first=f.window.openBookModal(7),second=f.window.openBookModal(7);
  f.requests[0].resolve(response('Old same-book response'));await first;
  assert.equal(f.body.textContent,'Skeleton 2','An earlier same-book response must leave the newer skeleton alone');
  assert.equal(f.loading[0].stops,0);assert.equal(f.loading[1].stops,0);
  f.requests[1].resolve(response('Latest book'));await second;
  assert.match(f.body.textContent,/Latest book/);assert.equal(f.loading[1].stops,1);
}
async function sameBookLateFailure(){
  const f=fixture(),first=f.window.openBookModal(7),second=f.window.openBookModal(7);
  f.requests[1].resolve(response('Latest same-book success'));await second;
  const shown=f.body.textContent;
  f.requests[0].reject(new Error('Old same-book failure'));await first;
  assert.equal(f.body.textContent,shown,'An old failure must not replace a newer request for the same book');
  assert.equal(f.loading[0].stops,0);assert.equal(f.loading[1].stops,1);
}
async function currentFailureStillVisible(){
  const f=fixture(),request=f.window.openBookModal(9);
  f.requests[0].reject(new Error('Current request failed'));await request;
  assert.equal(f.body.textContent,'Current request failed');assert.equal(f.loading[0].stops,1);
}
const scenarios={lateFailureAfterNewSuccess,lateFailureWhileNewPending,sameBookResponsesBackwards,
  sameBookOldSuccessWhileNewPending,sameBookLateFailure,currentFailureStillVisible};
(async()=>{
  await scenarios[process.argv[2]]();
  console.log(process.argv[2]+' passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class PreviewControlTests(unittest.TestCase):
    def test_latest_open_owns_preview_content_and_loading(self):
        for scenario in ("lateFailureAfterNewSuccess", "lateFailureWhileNewPending",
                         "sameBookResponsesBackwards", "sameBookOldSuccessWhileNewPending",
                         "sameBookLateFailure", "currentFailureStillVisible"):
            with self.subTest(scenario=scenario):
                result = subprocess.run(
                    [shutil.which("node"), "-e", CHECKS,
                     str(ROOT / "static/js/user.js"), scenario],
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
