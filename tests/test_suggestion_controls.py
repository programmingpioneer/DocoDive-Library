"""Regression checks for voting failures and explicit-event inline edits."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
NODE=shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
CHECKS=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
assert.ok(fs.existsSync(process.argv[1]),'Suggestion controller is not implemented');
const source=fs.readFileSync(process.argv[1],'utf8');
function browser(ok=true){
 const records={},messages=[],calls=[];let resets=0;
 const button={disabled:false,attrs:{},classes:new Set(),setAttribute(k,v){this.attrs[k]=v;},querySelector(s){return s==='.like-count'?{set textContent(v){records.count=v;}}:null;}};
 button.classList={add:c=>button.classes.add(c),remove:c=>button.classes.delete(c),contains:c=>button.classes.has(c)};
 const field={value:'A revised suggestion'},message={textContent:'Original suggestion',classList:{remove(){},add(){}}};
 const document={querySelectorAll:()=>[],addEventListener(){},getElementById:id=>id==='suggestions-config'?{textContent:JSON.stringify({loggedIn:true,userId:1,moderator:false,ids:[]})}:id==='edit-textarea-7'?field:id==='message-7'?message:{classList:{add(){},remove(){}}}};
 const scope={document,window:{location:{href:'http://127.0.0.1/feedback'}},console,URLSearchParams,encodeURIComponent,alert:m=>messages.push(m),setButtonLoading(){},resetButton(){resets++;},showAuthModal(){},fetch:async(url,options)=>{calls.push({url,options});return {ok,redirected:false,json:async()=>({liked:true,count:8})};}};
 vm.createContext(scope);vm.runInContext(source,scope);
 return{scope,button,records,messages,calls,message,get resets(){return resets;}};
}
(async()=>{
 let b=browser(false);await b.scope.toggleLike(7,b.button);assert.equal(b.records.count,undefined);assert.equal(b.button.classes.has('liked'),false);assert.ok(b.messages.length);assert.equal(b.button.disabled,false);
 b=browser();await b.scope.toggleLike(7,b.button);assert.equal(b.records.count,8);assert.equal(b.button.attrs['aria-pressed'],'true');
 b=browser();await b.scope.saveEditFeedback({target:{closest:()=>b.button}},7);assert.equal(b.calls[0].url,'/feedback/7/edit');assert.equal(b.message.textContent,'A revised suggestion');assert.equal(b.resets,1);
 b=browser(false);await b.scope.saveEditFeedback({target:{closest:()=>b.button}},7);assert.equal(b.message.textContent,'Original suggestion');assert.equal(b.resets,1);
 console.log('4 suggestion vote/edit scenarios passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


class SuggestionControlsTests(unittest.TestCase):
    def test_vote_failure_and_explicit_edit_event(self):
        result=subprocess.run([NODE,'-e',CHECKS,str(ROOT/'static/js/suggestions.js')],cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
