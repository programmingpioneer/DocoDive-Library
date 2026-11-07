"""Page-owned loading lifecycle, with a deterministic clock and no browser/services."""
from pathlib import Path
import shutil,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
CHECKS=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
function setup({layout='reviews',reduced=false,raf=true}={}){
 let now=0,id=0;const timers=new Map(),frames=[],events={},classes=new Set(),storage=new Map();
 class E{constructor(){this.dataset={};this.style={};this.attrs={};this.hidden=false;this.children=[];this.classList={add:(...xs)=>xs.forEach(x=>classes.add(x)),remove:(...xs)=>xs.forEach(x=>classes.delete(x)),contains:x=>classes.has(x)};}setAttribute(k,v){this.attrs[k]=String(v);}removeAttribute(k){delete this.attrs[k];}append(...xs){this.children.push(...xs);}replaceChildren(...xs){this.children=xs;}querySelectorAll(){return [];}}
 const root=new E(),loader=new E(),body=new E();loader.dataset.skeletonLayout=layout;
 const document={readyState:'complete',documentElement:root,body,getElementById:x=>x==='page-loader'?loader:null,querySelectorAll:()=>[],createElement:()=>new E(),addEventListener:(n,f)=>events[n]=f,dispatchEvent(){}};
 const window={location:{href:'http://local.test/reviews'},performance:{now:()=>now},localStorage:{getItem:k=>storage.get(k)||null},matchMedia:q=>({matches:q.includes('reduced-motion')?reduced:false,addEventListener(){}}),addEventListener:(n,f)=>events[n]=f,setTimeout:(fn,delay=0)=>{const key=++id;timers.set(key,{at:now+delay,fn});return key;},clearTimeout:key=>timers.delete(key)};
 if(raf)window.requestAnimationFrame=f=>frames.push(f);
 const ctx={window,document,URL,CustomEvent:class {constructor(type,options){this.type=type;this.detail=options?.detail;}},Date};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
 const tick=ms=>{const end=now+ms;for(;;){let next=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;now=next[1].at;timers.delete(next[0]);next[1].fn();}now=end;};
 const frame=()=>{now+=16;frames.splice(0).forEach(f=>f(now));};const ready=()=>{frame();frame();tick(300);};
 return{root,loader,events,classes,storage,window,timers,frame,tick,ready};
}
let x=setup();assert.equal(x.loader.hidden,false,'Own skeleton should be visible until the next paint');x.frame();x.frame();x.tick(87);assert.equal(x.loader.hidden,false);x.tick(1);assert.ok(x.classes.has('is-leaving'),'Ready content fades in rather than popping');x.tick(160);assert.equal(x.loader.hidden,true);assert.equal(x.root.dataset.siteReady,'true');
x.events.pagehide({persisted:true});assert.equal(x.loader.hidden,false,'Cached document must be stored with its own skeleton ready');assert.equal(x.loader.dataset.skeletonLayout,'reviews');x.events.pageshow({persisted:true});assert.equal(x.loader.dataset.loadTrigger,'restore');assert.equal(x.loader.hidden,false);x.ready();assert.equal(x.loader.hidden,true);
x.events.pageshow({persisted:false});assert.equal(x.loader.hidden,true,'Ordinary load must not flash the skeleton a second time');
x.events.pagehide({persisted:false});assert.equal(x.loader.hidden,true,'An uncached exit must not paint an outgoing skeleton');
x=setup();x.frame();x.frame();x.tick(120);const stale=[...x.timers.values()].find(t=>t.at<4000)?.fn;assert.ok(stale);x.events.pagehide({persisted:true});x.events.pageshow({persisted:true});stale();assert.equal(x.loader.hidden,false,'A previous visit cannot hide the restored page loader');x.ready();assert.equal(x.loader.hidden,true);
x=setup();x.tick(4000);assert.equal(x.loader.hidden,true,'Fail-safe releases the page if animation frames stall');x.frame();x.frame();x.tick(500);assert.equal(x.loader.hidden,true,'Stale frames cannot revive a released loader');
x=setup({reduced:true});x.frame();x.frame();x.tick(0);assert.equal(x.loader.hidden,true,'Reduced motion skips the fade and artificial minimum');
x=setup({raf:false});x.tick(300);assert.equal(x.loader.hidden,true,'A browser without requestAnimationFrame must still release the page');
x=setup({layout:'inbox'});x.ready();x.events.pagehide({persisted:true});x.events.pageshow({persisted:true});assert.equal(x.loader.dataset.skeletonLayout,'inbox','Restoration uses this page composition, not the outgoing page');x.ready();
x.storage.set('docodive_theme','dark');x.events.pagehide({persisted:true});x.events.pageshow({persisted:true});assert.equal(x.root.dataset.bsTheme,'dark','Restore resynchronizes a theme changed on another page');x.ready();
for(const href of ['http://local.test/books','http://local.test/book/a/1/download','http://local.test/reviews#details','https://external.test/']){x.events.click?.({button:0,defaultPrevented:false,target:{closest:()=>({href,target:'',hasAttribute:()=>false})}});assert.equal(x.loader.hidden,true,'Outgoing navigation must not display the old page skeleton');}
x.events.submit?.({defaultPrevented:false,target:{action:'http://local.test/books',target:'',hasAttribute:()=>false,dataset:{}}});assert.equal(x.loader.hidden,true,'Pending forms keep their current page instead of the wrong skeleton');
console.log('10 loading lifecycle groups passed: initial, restore, first pageshow, stale timers, fail-safe, reduced motion, missing RAF, page identity, theme restore, outgoing navigation.');
"""
class NavigationLoadingTests(unittest.TestCase):
    def test_page_owned_initial_and_history_loading(self):
        r=subprocess.run([shutil.which('node'),'-e',CHECKS,str(ROOT/'static/js/site-experience.js')],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
