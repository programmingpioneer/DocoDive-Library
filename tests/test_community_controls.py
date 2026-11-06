"""Run community filters/sharing against offline browser boundaries."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
CHECKS = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
assert.ok(fs.existsSync(process.argv[1]),'Community controller is not implemented');
const source=fs.readFileSync(process.argv[1],'utf8');
function browser(failCopy=false,nativeMode='absent'){
 class E {constructor(dataset={}){this.dataset=dataset;this.attrs={};this.hidden=false;this.textContent='';this.events={};}setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,fn){this.events[k]=fn;}closest(s){return s==='[data-community-share]'&&this.dataset.communityShare!==undefined?this:s==='[data-share-copy]'&&this.dataset.shareCopy!==undefined?this:s==='[data-share-native]'&&this.dataset.shareNative!==undefined?this:s==='[data-achievement-filter]'&&this.dataset.achievementFilter?this:null;}showModal(){this.open=true;this.openCount=(this.openCount||0)+1;}focus(){this.focused=true;}select(){this.selected=true;}}
 const events={},panel=new E(),empty=new E(),dialog=new E(),summary=new E(),status=new E(),copy=new E({shareCopy:''}),native=new E({shareNative:''}),share=new E({communityShare:'',shareText:'3 downloads, 2 favorites'}),filters=['all','unlocked','locked'].map(v=>new E({achievementFilter:v})),cards=['unlocked','locked'].map(v=>new E({achievementState:v}));
 const links=['whatsapp','twitter','facebook','telegram'].map(v=>new E({sharePlatform:v}));
 panel.querySelectorAll=s=>s==='[data-achievement-filter]'?filters:cards;
 panel.querySelector=s=>empty;
 dialog.querySelector=s=>s==='[data-share-summary]'?summary:s==='[data-share-native]'?native:status;
 dialog.querySelectorAll=()=>links;
 const document={readyState:'complete',getElementById:()=>dialog,querySelectorAll:s=>s==='[data-achievements]'?[panel]:[],addEventListener:(k,fn)=>events[k]=fn};
 let copied='',shared=null;
 const navigator={clipboard:{writeText:async t=>{if(failCopy)throw Error('denied');copied=t;}}};
 if(nativeMode!=='absent')navigator.share=async data=>{if(nativeMode==='error')throw Error('blocked');if(nativeMode==='cancel')throw {name:'AbortError'};shared=data;};
 vm.runInNewContext(source,{document,window:{location:{origin:'http://127.0.0.1:5012'}},navigator,encodeURIComponent,console});
 return{cards,filters,dialog,summary,status,links,native,get copied(){return copied;},get shared(){return shared;},async filter(v){await panel.events.click({target:filters.find(f=>f.dataset.achievementFilter===v)});},async open(){await events.click({target:share});},async copy(){await events.click({target:copy});},async nativeShare(){await events.click({target:native});}};
}
(async()=>{
 let b=browser();await b.filter('unlocked');assert.equal(b.cards[0].hidden,false);assert.equal(b.cards[1].hidden,true);assert.equal(b.filters[1].attrs['aria-pressed'],'true');
 await b.filter('locked');assert.equal(b.cards[0].hidden,true);assert.equal(b.cards[1].hidden,false);
 await b.open();assert.equal(b.dialog.open,true);assert.match(b.summary.textContent,/3 downloads/);assert.ok(b.links.every(l=>/^https:\/\//.test(l.href)));
 assert.equal(b.summary.value,b.summary.textContent);assert.equal(b.native.hidden,true);await b.open();assert.equal(b.dialog.openCount,1);
 await b.copy();assert.match(b.copied,/http:\/\/127.0.0.1:5012/);assert.match(b.status.textContent,/copied/i);
 b=browser(true);await b.open();await b.copy();assert.equal(b.dialog.open,true);assert.match(b.status.textContent,/copy.*text|select.*text/i);assert.equal(b.summary.selected,true);
 b=browser(false,'available');await b.open();assert.equal(b.native.hidden,false);await b.nativeShare();assert.match(b.shared.text,/3 downloads/);
 b=browser(false,'error');await b.open();await b.nativeShare();assert.match(b.status.textContent,/copy.*stats/i);
 b=browser(false,'cancel');await b.open();await b.nativeShare();assert.equal(b.status.textContent,'');
 console.log('9 community control scenarios passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


class CommunityControlsTests(unittest.TestCase):
    def test_filters_share_dialog_and_clipboard_failure(self):
        result=subprocess.run([NODE,'-e',CHECKS,str(ROOT/'static/js/community.js')],cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
