"""Local practice activity controller; fake browser storage, no services."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8');
function setup({kind='quiz',saved='{}',blocked=false}={}){
 const events={},storage=new Map([['sample',saved]]),fields={};
 const field=name=>fields[name] ||= {textContent:'',value:0,max:100};
 const checks=[1,2,3,4].map(id=>({dataset:{practiceStep:String(id)},checked:false,addEventListener(n,f){this[n]=f}}));
 const root={dataset:{practiceActivity:'',practiceKind:kind,practiceStatsKey:'sample'},querySelector:s=>field(s),querySelectorAll:()=>checks};
 const document={readyState:'complete',querySelectorAll:s=>s==='[data-practice-step]'?checks:[root],addEventListener:(n,f)=>events[n]=f};
 const window={localStorage:{getItem(k){if(blocked)throw Error('blocked');return storage.get(k)||null},setItem(k,v){if(blocked)throw Error('blocked');storage.set(k,v)}}};
 vm.runInNewContext(source,{window,document,Number,JSON,Object,Math});
 return {fields,checks,events,storage};
}
let f=setup({saved:JSON.stringify({Loops:{correct:3,wrong:1},Strings:{correct:1,wrong:0}})});
assert.equal(f.fields['[data-practice-attempts]'].textContent,'5');
assert.equal(f.fields['[data-practice-accuracy]'].textContent,'80%');
assert.equal(f.fields['[data-practice-topics]'].textContent,'2');
f.events['docodive:practice-answer']({detail:{key:'sample',stats:{Loops:{correct:4,wrong:1}},saved:true}});
assert.equal(f.fields['[data-practice-attempts]'].textContent,'5');assert.equal(f.fields['[data-practice-accuracy]'].textContent,'80%');
f.events['docodive:practice-answer']({detail:{key:'another-subject',stats:{Loops:{correct:999}},saved:true}});
assert.equal(f.fields['[data-practice-attempts]'].textContent,'5','Other subjects cannot overwrite this dashboard');
for(const saved of ['broken','null','[]','{"Bad":{"correct":-9,"wrong":"bad"}}']){
 f=setup({saved});assert.equal(f.fields['[data-practice-attempts]'].textContent,'0');
 assert.equal(f.fields['[data-practice-accuracy]'].textContent,'0%');
}
f=setup({blocked:true});assert.match(f.fields['[data-practice-storage]'].textContent,/not saved|session only/i);
f=setup({kind:'guided',saved:'["1","3"]'});assert.equal(f.checks[0].checked,true);assert.equal(f.checks[1].checked,false);
f.checks[1].checked=true;f.checks[1].change();assert.deepEqual(JSON.parse(f.storage.get('sample')),['1','2','3']);
assert.equal(f.fields['[data-practice-accuracy]'].textContent,'75%');
console.log('Practice activity: restored counts, live updates, subject isolation, malformed/blocked storage and guided progress passed.');
"""


class PracticeActivityTests(unittest.TestCase):
    def test_local_activity_and_guided_progress(self):
        result = subprocess.run([shutil.which('node'), '-e', CHECK,
                                 str(ROOT/'static/js/practice-activity.js')],
                                capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__ == '__main__': unittest.main()
