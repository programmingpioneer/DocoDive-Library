"""Scroll-helper boundaries and reduced motion without a real browser."""
from pathlib import Path
import shutil,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
CHECK=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const events={},calls=[],children=[];
const element=()=>({attrs:{},hidden:false,children:[],setAttribute(k,v){this.attrs[k]=v},append(e){this.children.push(e)},addEventListener(n,f){this[n]=f}});
const body=element();body.hasAttribute=()=>true;body.append=e=>children.push(e);
const document={readyState:'complete',body,documentElement:{scrollHeight:2000},createElement:element,addEventListener(n,f){events[n]=f}};
const window={innerHeight:800,scrollY:0,requestAnimationFrame:f=>f(),matchMedia:()=>({matches:true}),addEventListener(n,f){events[n]=f},scrollTo:o=>calls.push(o),scrollBy:o=>calls.push(o)};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window,document,Math});
const group=children[0],[up,down]=group.children;
assert.equal(up.hidden,true);assert.equal(down.hidden,false);assert.equal(group.attrs['aria-label'],'Page scroll controls');
window.scrollY=500;events.scroll();assert.equal(up.hidden,false);assert.equal(down.hidden,false);
up.click();assert.equal(calls[0].top,0);assert.equal(calls[0].behavior,'auto');
down.click();assert.equal(calls[1].top,640);assert.equal(calls[1].behavior,'auto');
window.scrollY=1200;events.scroll();assert.equal(down.hidden,true);assert.equal(up.hidden,false);
document.documentElement.scrollHeight=500;window.scrollY=0;events.resize();assert.equal(group.hidden,true,'Short pages need no floating controls');
console.log('Scroll controls: top/middle/end, short page, labels and reduced motion passed.');
"""
class ReadingControlsTests(unittest.TestCase):
 def test_scroll_boundaries_and_reduced_motion(self):
  r=subprocess.run([shutil.which('node'),'-e',CHECK,str(ROOT/'static/js/reading-controls.js')],capture_output=True,text=True,timeout=15)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
