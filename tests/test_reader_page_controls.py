"""Local library sorting and preference summaries without network or account writes."""
from pathlib import Path
import shutil,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
CHECKS=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
assert.ok(fs.existsSync(process.argv[1]),'Reader page controls are missing');
class E{constructor(dataset={}){this.dataset=dataset;this.events={};this.hidden=false;this.value='';this.checked=false;this.textContent='';}addEventListener(n,f){this.events[n]=f;}focus(){this.focused=true;}}
const query=new E(),sort=new E(),result=new E(),empty=new E(),clear=new E(),grid=new E();sort.value='original';
const cards=['Zulu','alpha','Middle'].map(t=>new E({bookTitle:t,bookSearch:t+' Reader'}));grid.nodes=[...cards];grid.append=(...nodes)=>{grid.nodes=[...nodes];};
const library=new E({libraryLabel:'saved books'});library.querySelectorAll=()=>cards;library.querySelector=s=>({'[data-library-search]':query,'[data-library-sort]':sort,'[data-library-result]':result,'[data-library-empty]':empty,'[data-library-clear]':clear,'[data-library-grid]':grid}[s]);
const notify=new E(),summary=new E(),unsaved=new E(),all=new E();notify.checked=true;const cats=[new E(),new E()],radios=['daily','weekly','off'].map(v=>{let e=new E();e.value=v;e.checked=v==='weekly';return e;});
unsaved.hidden=true;const prefs=new E();prefs.querySelectorAll=s=>s.includes('favorite_categories')?cats:radios;prefs.querySelector=s=>({'[name=notify_new_books]':notify,'[data-preference-summary]':summary,'[data-preference-unsaved]':unsaved,'[data-categories-clear]':all}[s])||(s.includes('email_frequency')?radios.find(r=>r.checked):null);
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document:{querySelectorAll:()=>[library],querySelector:()=>prefs}});
query.value='reader';query.events.input();assert.equal(cards.filter(c=>!c.hidden).length,3);query.value='nothing';query.events.input();assert.equal(empty.hidden,false);assert.equal(cards.every(c=>c.hidden),true);clear.events.click();assert.equal(cards.every(c=>!c.hidden),true);assert.equal(query.focused,true);
sort.value='az';sort.events.change();assert.equal(grid.nodes.map(e=>e.dataset.bookTitle).join(','),'alpha,Middle,Zulu');sort.value='za';sort.events.change();assert.equal(grid.nodes[0],cards[0]);sort.value='original';sort.events.change();assert.equal(grid.nodes.map(e=>e.dataset.bookTitle).join(','),'Zulu,alpha,Middle');
assert.match(summary.textContent,/all categories/i);assert.equal(unsaved.hidden,true);cats[0].checked=true;prefs.events.change();assert.match(summary.textContent,/1 topic/);assert.equal(unsaved.hidden,false);all.events.click();assert.equal(cats.every(c=>!c.checked),true);assert.match(summary.textContent,/all categories/i);
notify.checked=false;radios.forEach(r=>r.checked=r.value==='off');prefs.events.change();assert.match(summary.textContent,/paused/i);assert.match(summary.textContent,/digests off/i);assert.ok(cats.every(c=>!c.disabled));console.log('7 reader page control scenarios passed');
"""
class ReaderPageControlTests(unittest.TestCase):
    def test_search_sort_and_native_preference_summary(self):
        run=subprocess.run([shutil.which('node'),'-e',CHECKS,str(ROOT/'static/js/reader-pages.js')],capture_output=True,text=True,timeout=20)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
