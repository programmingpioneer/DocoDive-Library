"""Navigation timing and notification rendering at isolated browser boundaries."""
from pathlib import Path
import shutil,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
HOVER=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');assert.ok(fs.existsSync(process.argv[1]),'Navigation controller missing');
class E{constructor(){this.events={};this.attrs={};}addEventListener(k,f){this.events[k]=f;}contains(e){return e===this.inside||e===this.trigger;}closest(){return this.parent;}getAttribute(k){return this.attrs[k];}focus(){document.activeElement=this;}}
const parent=new E(),trigger=new E(),second=new E();trigger.parent=parent;parent.trigger=trigger;second.parent=new E();const docEvents={},timers=new Map();let id=0,shown=0,hidden=0,toggled=0;
const dropdown={show(){shown++;trigger.attrs['aria-expanded']='true';document.activeElement=trigger;},hide(){hidden++;trigger.attrs['aria-expanded']='false';},toggle(){toggled++;}};
const document={readyState:'interactive',activeElement:null,getElementById:k=>k==='learningDropdown'?trigger:k==='communityDropdown'?second:null,querySelectorAll:()=>[trigger,second],addEventListener:(k,f)=>docEvents[k]=f};
const window={addEventListener(){}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document,window,matchMedia:()=>({matches:true}),setTimeout:f=>{timers.set(++id,f);return id;},clearTimeout:i=>timers.delete(i)});
assert.equal(typeof docEvents.DOMContentLoaded,'function','Deferred controller must wait for later Bootstrap before initialization');window.bootstrap={Dropdown:{getOrCreateInstance:()=>dropdown}};docEvents.DOMContentLoaded();
const flush=()=>{for(const [i,f]of [...timers]){timers.delete(i);f();}};
parent.events.mouseenter();assert.equal(shown,0);parent.events.mouseleave();flush();assert.equal(shown,0,'Passing over a menu must not flash it');
parent.events.mouseenter();flush();assert.equal(shown,1);parent.events.mouseleave();flush();assert.equal(trigger.attrs['aria-expanded'],'false','Bootstrap focuses the trigger on hover; pointer exit must still close it');
parent.events.mouseenter();flush();parent.inside={};document.activeElement=parent.inside;parent.events.mouseleave();flush();assert.equal(trigger.attrs['aria-expanded'],'true','Keyboard-focused menu content stays open');document.activeElement=null;parent.events.mouseleave();flush();assert.equal(trigger.attrs['aria-expanded'],'false');
let prevented=false;trigger.events.keydown({key:'Enter',preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.equal(toggled,1);console.log('7 menu timing/keyboard scenarios passed');
"""
NOTIFICATIONS=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');assert.ok(fs.existsSync(process.argv[1]),'Notification preview controller missing');
class E{constructor(){this.children=[];this.dataset={};this.style={};this.attrs={};this.hidden=false;this.textContent='';}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=[...x];}setAttribute(k,v){this.attrs[k]=String(v);}addEventListener(k,f){this[k]=f;}cloneNode(){return new E();}}
const list=new E(),status=new E(),badge=new E(),button=new E(),events={},requests=[];const template={content:{cloneNode:()=>new E()}};
const document={readyState:'complete',hidden:false,getElementById:id=>id==='notifList'?list:id==='notifStatus'?status:id==='notifBadge'?badge:id==='notifMarkAll'?button:template,createElement:()=>new E(),addEventListener:(k,f)=>events[k]=f,dispatchEvent:e=>{events[e.type]?.(e);events.lastDispatched=e.type;}};
let failures=0;const window={toast:{error(){failures++;},success(){}}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document,window,navigator:{onLine:true},location:{href:'http://127.0.0.1:5012/',origin:'http://127.0.0.1:5012'},URL,Date,Number,String,Array,CustomEvent:class{constructor(type){this.type=type;}},setInterval(){},fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
const tick=()=>new Promise(r=>setImmediate(r));const ok=data=>({ok:true,redirected:false,json:async()=>data});
(async()=>{
 requests[0].resolve(ok([{type:'reply',actor_name:'<script>unsafe</script>',message:'<img src=x onerror=bad()>',link:'https://evil.test/',created_at:'2026-11-01T12:00:00Z'}]));await tick();requests[1].resolve(ok({count:1}));await tick();assert.equal(list.children.length,1);assert.match(list.children[0].className,/dropdown-item/,'Notification links participate in Bootstrap arrow navigation');assert.equal(list.children[0].href,'/user/notifications');assert.equal(list.children[0].children[1].children[0].children[0].textContent,'<script>unsafe</script>');assert.equal(badge.textContent,'1');
 const old=window.updateNotifications();const current=window.updateNotifications();requests[3].resolve(ok([]));await tick();requests[4].resolve(ok({count:0}));await current;assert.equal(badge.style.display,'none');assert.equal(button.disabled,true);requests[2].resolve(ok([{actor_name:'old'}]));await old;assert.equal(badge.style.display,'none');
 const failed=window.markAllRead();requests[5].resolve({ok:false,redirected:false,status:500});await failed;assert.equal(failures,1);assert.equal(badge.style.display,'none');assert.equal(list.children.length,1);
 const read=window.markAllRead();requests[6].resolve(ok({success:true}));await tick();assert.equal(events.lastDispatched,'docodive:notifications-read-all','Confirmed bell action must synchronize the main inbox');requests[7].resolve(ok([]));await tick();requests[8].resolve(ok({count:0}));await read;
 console.log('6 notification safety/state scenarios passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
class ReaderNavigationTests(unittest.TestCase):
    def run_check(self,code,name):
        result=subprocess.run([shutil.which('node'),'-e',code,str(ROOT/'static/js'/name)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_hover_keyboard_coordination(self):self.run_check(HOVER,'navigation.js')
    def test_notification_safe_rendering_empty_and_stale_counts(self):self.run_check(NOTIFICATIONS,'notification-menu.js')
