"""Exercise the actual inbox controller with offline DOM/network boundaries."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node') or str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
CHECKS = r"""
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
assert.ok(fs.existsSync(process.argv[1]), 'Inbox controller is not implemented');
const source=fs.readFileSync(process.argv[1],'utf8');
function browser({ok=true,redirected=false,network=false,confirm=true}={}) {
  class Element {
    constructor(dataset={}) {this.dataset=dataset;this.hidden=false;this.disabled=false;this.textContent='';this.attrs={};this.events={};this.connected=true;this.classes=new Set();this.classList={contains:c=>this.classes.has(c),remove:c=>this.classes.delete(c)};}
    setAttribute(k,v){this.attrs[k]=v;} addEventListener(k,fn){this.events[k]=fn;}
    querySelector(s){return this.children?.[s]||null;} remove(){this.connected=false;}
    closest(s){if(s==='[data-notification-action]')return this.dataset.notificationAction?this:null;if(s==='[data-notification-filter]')return this.dataset.notificationFilter?this:null;if(s==='[data-notification-row]')return this.row||null;return null;}
  }
  const root=new Element(), status=new Element(), empty=new Element(), unread=new Element(), total=new Element(), all=new Element({notificationAction:'read-all'});
  const rows=['library','community'].map((category,i)=>{const r=new Element({notificationRow:'',id:String(i+1),category});r.classes.add('is-unread');r.children={'[data-read-button]':new Element(), '[data-unread-label]':new Element()};return r;});
  const filters=['all','unread','library','community'].map(f=>new Element({notificationFilter:f}));
  const nodes={'[data-inbox-status]':status,'[data-inbox-empty]':empty,'[data-inbox-unread]':unread,'[data-inbox-total]':total,'[data-notification-action="read-all"]':all};
  root.querySelector=s=>nodes[s]||null;
  root.querySelectorAll=s=>s==='[data-notification-row]'?rows.filter(r=>r.connected):s==='[data-notification-filter]'?filters:[];
  const calls=[];let refreshes=0;
  const externalEvents={};const document={readyState:'complete',addEventListener:(k,fn)=>externalEvents[k]=fn,querySelector:s=>s==='[data-notification-inbox]'?root:s==='meta[name="csrf-token"]'?{content:'test-csrf'}:null};
  const window={toast:{confirm:async()=>confirm},updateNotifications:()=>{refreshes++;}};
  vm.runInNewContext(source,{document,window,fetch:async(url,options)=>{calls.push({url,options});if(network)throw Error('offline');return {ok,redirected,json:async()=>({success:true})};},console});
  async function click(action,index=0) {const b=action==='read-all'?all:new Element({notificationAction:action});if(action!=='read-all')b.row=rows[index];await root.events.click({target:b,preventDefault(){}});}
  async function filter(value){await root.events.click({target:filters.find(f=>f.dataset.notificationFilter===value),preventDefault(){}});}
  return {rows,calls,status,unread,total,empty,all,filters,click,filter,externalReadAll:()=>{assert.equal(typeof externalEvents['docodive:notifications-read-all'],'function');externalEvents['docodive:notifications-read-all']();},get refreshes(){return refreshes;}};
}
(async()=>{
let count=0;async function test(name,fn){await fn();count++;console.log('PASS '+name);}
await test('failed bulk request preserves unread rows and count',async()=>{const b=browser({ok:false});await b.click('read-all');assert.ok(b.rows.every(r=>r.classList.contains('is-unread')));assert.equal(b.unread.textContent,'2');assert.match(b.status.textContent,/try again/i);assert.equal(b.all.disabled,false);});
await test('redirect to login is not treated as success',async()=>{const b=browser({redirected:true});await b.click('read');assert.ok(b.rows[0].classList.contains('is-unread'));});
await test('network failure keeps the row and restores controls',async()=>{const b=browser({network:true});await b.click('delete');assert.equal(b.rows[0].connected,true);assert.match(b.status.textContent,/try again/i);});
await test('successful individual read includes CSRF and updates count',async()=>{const b=browser();await b.click('read');assert.equal(b.rows[0].classList.contains('is-unread'),false);assert.equal(b.unread.textContent,'1');assert.equal(b.calls[0].options.headers['X-CSRF-Token'],'test-csrf');assert.equal(b.refreshes,1);});
await test('bulk read uses the ownership-protected bulk endpoint',async()=>{const b=browser();await b.click('read-all');assert.equal(b.calls.length,1);assert.equal(b.calls[0].url,'/api/notifications/read-all');assert.equal(b.unread.textContent,'0');assert.equal(b.all.disabled,true);});
await test('cancelled deletion makes no request',async()=>{const b=browser({confirm:false});await b.click('delete');assert.equal(b.calls.length,0);assert.equal(b.rows[0].connected,true);});
await test('successful deletion removes only its row',async()=>{const b=browser();await b.click('delete');assert.equal(b.rows[0].connected,false);assert.equal(b.rows[1].connected,true);assert.equal(b.total.textContent,'1');});
await test('filters do not send requests and empty unread filter is clear',async()=>{const b=browser();await b.filter('library');assert.equal(b.rows[0].hidden,false);assert.equal(b.rows[1].hidden,true);assert.equal(b.calls.length,0);await b.click('read-all');await b.filter('unread');assert.ok(b.rows.every(r=>r.hidden));assert.equal(b.empty.hidden,false);assert.equal(b.filters[1].attrs['aria-pressed'],'true');});
console.log(count+' inbox behavior checks passed');
await test('confirmed bell bulk-read synchronizes the visible inbox without another POST',async()=>{const b=browser();await b.filter('unread');b.externalReadAll();assert.equal(b.unread.textContent,'0');assert.equal(b.all.disabled,true);assert.equal(b.empty.hidden,false);assert.equal(b.rows.every(r=>r.hidden),true);assert.equal(b.calls.length,0);});
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class InboxTests(unittest.TestCase):
    def test_offline_inbox_behaviors(self):
        result = subprocess.run([NODE, '-e', CHECKS, str(ROOT / 'static/js/notifications.js')],
                                cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
