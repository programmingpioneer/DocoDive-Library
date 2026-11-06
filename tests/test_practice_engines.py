"""Run supplied practice engines with synthetic questions and no network."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const engines=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{for(const engine of engines){for(const saved of [null,'null','[]','broken','{"Test":{"correct":-1,"wrong":"oops"}}']){
 const events=[],requests=[];const elements=new Map(),data=new Map();
 const element=()=>({style:{},className:'',classList:{add(){},remove(){},contains(){return false}},textContent:'',innerHTML:'',insertAdjacentHTML(){},querySelectorAll(){return []},querySelector(){return null}});
 const document={getElementById:id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)},createElement:element,querySelectorAll:()=>[],addEventListener(){},dispatchEvent:e=>events.push(e)};
 const ctx={document,window:{scrollTo(){},matchMedia:()=>({matches:true})},localStorage:{getItem:k=>data.has(k)?data.get(k):saved,setItem:(k,v)=>data.set(k,v)},CustomEvent:class{constructor(type,o){this.type=type;this.detail=o.detail}},setInterval(){},clearInterval(){},setTimeout(){},clearTimeout(){},AbortController,fetch:async url=>{requests.push(url);return {ok:false}},console,Date,Math};
 vm.createContext(ctx);vm.runInContext(engine.source,ctx);
 vm.runInContext("session={total:0,correct:0,wrong:0,mode:'unlimited'};currentQ={id:'sample',title:'Example',topic:'Test',answer:'A',hint:'A hint',explanation:'The authored explanation.'};afterAnswer(true,currentQ,'A');afterAnswer(true,currentQ,'A');",ctx);
 assert.equal(vm.runInContext('session.total',ctx),1,engine.path+': repeated submissions must count once');
 assert.equal(events.filter(e=>e.type==='docodive:practice-answer').length,1,engine.path+': dashboard receives actual answer event');
 assert.equal(events[0].detail.stats.Test.correct,1,engine.path+': malformed saved activity must not break the engine');
 assert.equal(events[0].detail.stats.Test.wrong,0);
 if(typeof ctx.fetchDeepExplanation==='function'){
  const text=await vm.runInContext('fetchDeepExplanation(currentQ)',ctx);
  assert.equal(text,'The authored explanation.');
 }
 assert.equal(requests.length,0,engine.path+': practice explanations must not require an external service');
}}
console.log(engines.length+' engines: duplicate answers, progress event and local explanations passed.');})().catch(e=>{console.error(e);process.exitCode=1});
"""


class PracticeEngineTests(unittest.TestCase):
    def test_answer_accounting_and_local_explanations(self):
        engines=[]
        for path in sorted((ROOT/'templates/user').glob('*/practice.html')):
            source=path.read_text(encoding='utf8')
            for script in re.findall(r'<script\b[^>]*>(.*?)</script>',source,re.S):
                if 'const PRACTICE_DATA =' in script:
                    engines.append(dict(path=path.parent.name,source=re.sub(r'{{.*?}}','[]',script,flags=re.S)))
        self.assertEqual(len(engines),11)
        result=subprocess.run([shutil.which('node'),'-e',CHECK],input=json.dumps(engines),
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
