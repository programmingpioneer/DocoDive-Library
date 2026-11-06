"""Appearance and loading controls without account access or external requests."""
from pathlib import Path
import shutil,subprocess,unittest
from bs4 import BeautifulSoup
import test_community_views

ROOT=Path(__file__).resolve().parents[1]
CHECKS=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
assert.ok(fs.existsSync(process.argv[1]),'Theme initializer is missing');
class E{constructor(){this.dataset={};this.style={};this.attrs={};this.events={};this.hidden=false;this.children=[];this.textContent='';this.classList={add(){},remove(){}};}setAttribute(k,v){this.attrs[k]=String(v);}getAttribute(k){return this.attrs[k];}removeAttribute(k){delete this.attrs[k];}addEventListener(n,f){this.events[n]=f;}append(...e){this.children.push(...e);}replaceChildren(...e){this.children=[...e];}querySelectorAll(){return [];}}
function setup(saved=null,osDark=false,blocked=false){
 const root=new E(),body=new E(),toggle=new E(),loader=new E(),events={},writes=[],changes=[];
 const media={matches:osDark,addEventListener:(n,f)=>events.os=f};
 const document={documentElement:root,body,readyState:'complete',getElementById:id=>id==='page-loader'?loader:null,querySelectorAll:s=>s==='[data-theme-toggle]'?[toggle]:[],createElement:()=>new E(),addEventListener:(n,f)=>events[n]=f,dispatchEvent:e=>changes.push(e)};
 const window={location:{href:'http://local.test/user/settings'},localStorage:{getItem:()=>{if(blocked)throw Error('blocked');return saved;},setItem:(k,v)=>{if(blocked)throw Error('blocked');writes.push([k,v]);}},setTimeout:f=>{f();return 0;},clearTimeout(){},matchMedia:()=>media,addEventListener:(n,f)=>events[n]=f,requestAnimationFrame:f=>f()};
 class CE{constructor(type,options){this.type=type;this.detail=options?.detail;}}
 const ctx={document,window,CustomEvent:CE,URL,requestAnimationFrame:f=>f()};vm.createContext(ctx);
 vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),ctx);
 return {root,toggle,loader,events,writes,media,changes,window};
}
let x=setup(null,true);assert.equal(x.root.dataset.bsTheme,'dark');assert.equal(x.writes.length,0);assert.equal(x.toggle.getAttribute('aria-pressed'),'true');assert.match(x.toggle.getAttribute('aria-label'),/light/i);assert.equal(x.loader.hidden,true);
x.toggle.events.click();assert.equal(x.root.dataset.bsTheme,'light');assert.deepEqual(x.writes[0],['docodive_theme','light']);assert.match(x.toggle.getAttribute('aria-label'),/dark/i);x.media.matches=true;x.events.os({matches:true});assert.equal(x.root.dataset.bsTheme,'light');
x=setup('invalid',false);assert.equal(x.root.dataset.bsTheme,'light');x.media.matches=true;x.events.os({matches:true});assert.equal(x.root.dataset.bsTheme,'dark');
x=setup('light',true);assert.equal(x.root.dataset.bsTheme,'light');x.events.storage({key:'docodive_theme',newValue:'dark'});assert.equal(x.root.dataset.bsTheme,'dark');x.media.matches=false;x.events.storage({key:'docodive_theme',newValue:null});assert.equal(x.root.dataset.bsTheme,'light');
x=setup(null,false,true);x.toggle.events.click();assert.equal(x.root.dataset.bsTheme,'dark');assert.equal(x.writes.length,0);assert.equal(x.loader.hidden,true);
const box=new E(),done=x.window.DocoDiveLoading.fill(box,{rows:2});assert.equal(box.getAttribute('aria-busy'),'true');assert.equal(box.children[0].children.length,2);done();assert.equal(box.getAttribute('aria-busy'),undefined);
x=setup('light',false);const confirmForm={dataset:{},action:'http://local.test/user/account-deletion',target:'',hasAttribute:n=>n==='data-confirm'};
x.events.submit?.({target:confirmForm,defaultPrevented:false});assert.equal(x.loader.hidden,true,'Unconfirmed forms must not cover a canceled confirmation');confirmForm.dataset.confirmed='true';x.events.submit?.({target:confirmForm,defaultPrevented:false});assert.equal(x.loader.hidden,true,'Outgoing forms must not show the wrong page skeleton');x.events.pageshow({persisted:false});assert.equal(x.loader.hidden,true);
x.events.click?.({button:0,target:{closest:()=>({href:'http://local.test/book/a/1/download',target:'',hasAttribute:()=>false})}});assert.equal(x.loader.hidden,true,'Downloads must not leave a page overlay');
console.log('Appearance preference and safe outgoing navigation scenarios passed');
"""

class SiteExperienceTests(unittest.TestCase):
    def test_preference_system_manual_storage_and_loading(self):
        r=subprocess.run([shutil.which('node'),'-e',CHECKS,str(ROOT/'static/js/theme-init.js'),str(ROOT/'static/js/site-experience.js')],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_all_document_owners_load_shared_appearance_assets(self):
        owners=['user/base.html','user/auth.html','user/forgot_password.html','user/reset_password.html','user/verify_code.html','user/_error_base.html','admin/admin_base.html','admin/auth_base.html']
        for name in owners:
            with self.subTest(name=name):
                s=(ROOT/'templates'/name).read_text(encoding='utf-8')
                self.assertIn("shared/_experience_init.html",s)
                self.assertIn("shared/_experience_assets.html",s)
                self.assertIn("shared/_theme_toggle.html",s)
                self.assertIn("shared/_page_skeleton.html",s)

    def test_public_navigation_has_accessible_theme_button_and_skeleton(self):
        fixture=test_community_views.CommunityViewTests();fixture.setUp()
        doc=BeautifulSoup(fixture.render('books',pdfs=[]),'html.parser')
        toggle=doc.select_one('button[data-theme-toggle]')
        self.assertIsNotNone(toggle)
        self.assertEqual(toggle.get('type'),'button')
        self.assertIn('mode',toggle.get('aria-label',''))
        self.assertIsNotNone(doc.select_one('#page-loader[aria-hidden=true]'))
        self.assertIsNotNone(doc.select_one('script[src*="theme-init.js"]'))
        self.assertIsNotNone(doc.select_one('link[href*="theme.css"]'))

if __name__=='__main__':unittest.main()
