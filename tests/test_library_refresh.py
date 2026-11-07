"""Catalogue broadcasts must not dismiss an open book by reloading the page."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
CHECK=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const file=process.argv[1];let source;
if(fs.existsSync(file))source=fs.readFileSync(file,'utf8');
else{const html=fs.readFileSync(process.argv[2],'utf8'),start=html.indexOf('    const channel = new BroadcastChannel(');assert.ok(start>=0);source=html.slice(start,html.indexOf('    const navbar =',start));}
let reloads=0,blocked=true,channel;const events={};
class BroadcastChannel{constructor(name){this.name=name;channel=this;}close(){this.closed=true;}}
const document={querySelector:()=>blocked?{}:null,addEventListener:(name,fn)=>{(events[name]??=[]).push(fn);}};
const window={BroadcastChannel,location:{reload:()=>reloads++},addEventListener:(name,fn)=>{(events[name]??=[]).push(fn);}};
vm.runInNewContext(source,{window,document,BroadcastChannel,location:window.location});
channel.onmessage({data:'refresh'});channel.onmessage({data:'refresh'});
assert.equal(reloads,0,'An incoming catalogue refresh must not make an open popup disappear');
for(const fn of events['hidden.bs.modal']||[])fn();assert.equal(reloads,0,'Another open dialog still blocks refresh');
const preview={},auth={};for(const fn of events['show.bs.modal']||[])fn({target:auth});
blocked=false;for(const fn of events['hidden.bs.modal']||[])fn({target:preview});
assert.equal(reloads,0,'A sign-in dialog opening during the handoff still blocks refresh');
for(const fn of events['hidden.bs.modal']||[])fn({target:auth});assert.equal(reloads,1,'Apply one queued update only after the popup closes');
channel.onmessage({data:'unrelated'});assert.equal(reloads,1);
channel.onmessage({data:'refresh'});assert.equal(reloads,2,'An idle catalogue can update immediately');
console.log('Open-preview refresh guard passed');
"""


class LibraryRefreshTests(unittest.TestCase):
    def test_catalogue_refresh_waits_for_the_readers_open_popup(self):
        result=subprocess.run([shutil.which('node'),'-e',CHECK,str(ROOT/'static/js/library-refresh.js'),str(ROOT/'templates/user/index.html')],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
