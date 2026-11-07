"""Keyboard selection and stale-result handling with a synthetic catalogue."""
from pathlib import Path
import shutil,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
CHECK=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class E{constructor(tag='div'){this.tagName=tag;this.value='';this.hidden=false;this.children=[];this.attrs={};this.events={};this.textContent='';this.classList={toggle(){}};}append(...es){this.children.push(...es);if(this.options)this.options.push(...es);}replaceChildren(...es){this.children=es;}addEventListener(n,f){this.events[n]=f;}setAttribute(n,v){this.attrs[n]=String(v);}removeAttribute(n){delete this.attrs[n];}focus(){this.focused=true;}scrollIntoView(){this.scrolled=true;}contains(e){return e===this||this.children.some(c=>c.contains(e));}}
function fixture(){
 const input=new E('input'),select=new E('select'),results=new E(),status=new E(),clear=new E('button'),native=new E(),enhanced=new E(),chip=new E(),title=new E(),modal=new E();
 results.hidden=true;enhanced.hidden=true;chip.hidden=true;clear.hidden=true;
 select.options=[{value:'',textContent:'General feedback'},{value:'4',textContent:'Alpha Primer'},{value:'5',textContent:'Beta Handbook'}];
 const nodes={reviewBookSearch:input,reviewBookSelect:select,reviewBookResults:results,reviewBookSearchStatus:status,reviewModal:modal};
 const queries={'[data-review-book-clear]':clear,'[data-review-book-native]':native,'[data-review-book-search]':enhanced,'[data-review-book-selection]':chip,'[data-review-book-title]':title};
 let n=0;const timers=new Map(),calls=[];
 const document={getElementById:id=>nodes[id],querySelector:s=>queries[s],createElement:t=>new E(t),addEventListener(){}};
 const window={setTimeout:f=>{timers.set(++n,f);return n},clearTimeout:k=>timers.delete(k)};
 const fetch=(url,options)=>new Promise((resolve,reject)=>calls.push({url,options,resolve,reject}));
 vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window,document,fetch,AbortController,URLSearchParams,Number,Array,String});
 const key=name=>{let e={key:name,preventDefault(){this.prevented=true},stopPropagation(){this.stopped=true}};input.events.keydown(e);return e};
 const type=value=>{input.value=value;input.events.input()};
 const flush=()=>{const jobs=[...timers.values()];timers.clear();jobs.forEach(f=>f())};
 const settle=async()=>{for(let i=0;i<8;i++)await Promise.resolve()};
 return{input,select,results,status,clear,native,enhanced,chip,title,modal,key,type,flush,settle,calls};
}
(async()=>{
 let f=fixture();assert.equal(f.native.hidden,true);assert.equal(f.enhanced.hidden,false);
 assert.equal(f.key('ArrowDown').prevented,true);assert.equal(f.input.attrs['aria-expanded'],'true');
 f.key('Enter');assert.equal(f.select.value,'4');assert.equal(f.input.value,'Alpha Primer');assert.equal(f.chip.hidden,false);
 f.clear.events.click();assert.equal(f.select.value,'');assert.equal(f.input.value,'');assert.equal(f.chip.hidden,true);
 f.type('rare title');f.flush();assert.match(f.calls[0].url,/q=rare\+title/);
 f.calls[0].resolve({ok:true,json:async()=>({books:[{id:250,title:'A <script> title',author:'Sample author'}]})});await f.settle();
 f.key('ArrowDown');f.key('Enter');assert.equal(f.select.value,'250');assert.equal(f.title.textContent,'A <script> title');
 assert.equal(f.select.options.some(o=>o.value==='250'),true,'Full-catalogue results can be selected beyond the initial list');
 f=fixture();f.type('older');f.flush();f.type('newer');f.flush();
 f.calls[1].resolve({ok:true,json:async()=>({books:[{id:20,title:'Newest result'}]})});await f.settle();
 f.calls[0].resolve({ok:true,json:async()=>({books:[{id:10,title:'Stale result'}]})});await f.settle();
 f.key('ArrowDown');f.key('Enter');assert.equal(f.select.value,'20','Stale search replies must not replace current results');
 f.type('closing');f.flush();f.modal.events['hidden.bs.modal']();f.calls[2].resolve({ok:true,json:async()=>({books:[{id:30,title:'Late result'}]})});await f.settle();assert.equal(f.results.hidden,true,'A late reply cannot reopen a closed modal');
 f=fixture();f.type('offline');f.flush();f.calls[0].reject(Error('offline'));await f.settle();assert.match(f.status.textContent,/unavailable|try again/i);assert.equal(f.input.value,'offline');assert.equal(f.select.value,'');
 f.key('Escape');assert.equal(f.input.attrs['aria-expanded'],'false');
 f=fixture();f.type('paused');f.key('Tab');assert.match(f.status.textContent,/paused/i);f.input.events.focus();f.flush();
 assert.equal(f.calls.length,1,'Returning to an interrupted query restarts search without retyping');
 const escape=f.key('Escape');assert.equal(escape.stopped,true,'Picker Escape must not bubble to dismiss the review modal');
 assert.equal(f.key('Escape').stopped,undefined,'A second Escape can dismiss the modal normally');
 f.input.events.click();f.flush();assert.equal(f.calls.length,2,'Clicking an unchanged paused query also resumes it');
 console.log('Book search: keyboard selection, clearing, full catalogue, escaped text, stale requests, modal closure and retry state passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
class ReviewBookSearchTests(unittest.TestCase):
 def test_keyboard_catalogue_and_request_lifecycle(self):
  r=subprocess.run([shutil.which('node'),'-e',CHECK,str(ROOT/'static/js/review-book-search.js')],capture_output=True,text=True,timeout=15)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
