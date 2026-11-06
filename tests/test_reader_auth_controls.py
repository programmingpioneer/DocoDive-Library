"""Offline tests for reader tabs, visibility and out-of-order availability replies."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKS = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
assert.ok(fs.existsSync(process.argv[1]),'Reader auth controller has not been implemented');
const source=fs.readFileSync(process.argv[1],'utf8');
class Element{
 constructor(dataset={}){this.dataset=dataset;this.events={};this.attrs={};this.hidden=false;this.value='';this.type='password';this.textContent='';}
 addEventListener(k,v){this.events[k]=v;}setAttribute(k,v){this.attrs[k]=String(v);}removeAttribute(k){delete this.attrs[k];}focus(){this.focused=true;}
}
const body=new Element({authMode:'login'}),title=new Element(),description=new Element(),password=new Element(),eye=new Element(),closedEye=new Element();
const tabs=['login','signup'].map(v=>new Element({authTab:v})),panels={login:new Element(),signup:new Element()};
const toggle=new Element({authPassword:'login-password'});toggle.querySelector=s=>s==='[data-eye-open]'?eye:closedEye;
const username=new Element({availability:'username'});username.id='username';const feedback=new Element();
const switches=['login','signup'].map(v=>new Element({authSwitch:v}));
const timers=new Map(),requests=[];let timer=0;
const document={title:'Sign in · DocoDive',querySelector:s=>s==='[data-reader-auth]'?body:null,
 querySelectorAll:s=>s==='[data-auth-tab]'?tabs:s==='[data-auth-switch]'?switches:s==='[data-auth-password]'?[toggle]:s==='[data-availability]'?[username]:[],
 getElementById:id=>id==='reader-auth-title'?title:id==='reader-auth-description'?description:id==='login-password'?password:id==='username-feedback'?feedback:panels[id.replace('-tab','')]};
vm.runInNewContext(source,{document,AbortController,encodeURIComponent,setTimeout:fn=>{timers.set(++timer,fn);return timer;},clearTimeout:id=>timers.delete(id),fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
const event=extra=>Object.assign({preventDefault(){this.prevented=true;}},extra);
const tick=()=>new Promise(r=>setImmediate(r));
const flush=()=>{for(const [id,fn]of [...timers]){timers.delete(id);fn();}};
(async()=>{
 assert.equal(requests.length,0,'Loading sign-in must not trigger availability calls');
 let e=event({key:'ArrowRight'});tabs[0].events.keydown(e);assert.equal(e.prevented,true);assert.equal(panels.login.hidden,true);assert.equal(panels.signup.hidden,false);assert.equal(tabs[1].attrs['aria-selected'],'true');assert.equal(tabs[1].focused,true);assert.match(title.textContent,/chapter/i);assert.match(document.title,/Create/);
 e=event({ctrlKey:true});tabs[0].events.click(e);assert.equal(e.prevented,undefined,'Modified link clicks retain normal navigation');
 switches[0].events.click(event());assert.equal(panels.signup.hidden,true);assert.match(document.title,/Sign in/);
 password.value='synthetic value only';toggle.events.click();assert.equal(password.type,'text');assert.equal(toggle.attrs['aria-pressed'],'true');assert.equal(eye.hidden,true);toggle.events.click();assert.equal(password.type,'password');assert.equal(password.value,'synthetic value only');assert.equal(closedEye.hidden,true);
 username.value='oldname';username.events.input();username.value='newname';username.events.input();flush();assert.equal(requests.length,1);assert.match(requests[0].url,/newname/);
 username.value='newername';username.events.input();assert.equal(requests[0].options.signal.aborted,true);assert.equal(feedback.textContent,'');flush();assert.equal(requests.length,2);
 requests[1].resolve({ok:true,redirected:false,json:async()=>({exists:false,message:'New name is available.'})});await tick();assert.equal(feedback.textContent,'New name is available.');
 requests[0].resolve({ok:true,redirected:false,json:async()=>({exists:true,message:'Old name is unavailable.'})});await tick();assert.equal(feedback.textContent,'New name is available.','Late responses must not overwrite the current input result');
 username.value='networkfail';username.events.input();flush();requests[2].reject(Error('offline'));await tick();assert.equal(feedback.textContent,'');assert.equal(feedback.attrs['aria-busy'],'false');
 username.value='123reader';username.events.input();flush();requests[3].resolve({ok:true,redirected:false,json:async()=>({exists:false,format_error:true,message:'Start with a letter.'})});await tick();assert.equal(feedback.dataset.state,'unavailable','Format errors must never be shown as available');
 username.value='simple';username.events.input();flush();requests[4].resolve({ok:true,redirected:false,json:async()=>({exists:false,simple:true,message:'Choose a stronger reader name.'})});await tick();assert.equal(feedback.dataset.state,'unavailable');
 username.value='bad name';username.events.input();flush();assert.equal(requests.length,5);assert.match(feedback.textContent,/letters and numbers/);
 console.log('9 reader auth control scenarios passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


class ReaderAuthControlTests(unittest.TestCase):
    def test_tabs_password_toggle_and_stale_availability_responses(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node is required to verify browser controls')
        result = subprocess.run([node, '-e', CHECKS, str(ROOT/'static/js/reader-auth.js')],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
