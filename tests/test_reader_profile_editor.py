"""Offline reader editor/share contracts, without importing application config."""
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from flask import Flask, render_template, session
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader
from community_presentation import achievement_summary

ROOT = Path(__file__).resolve().parents[1]


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def by_id(self, value):
        return next(attrs for _, attrs in self.tags if attrs.get('id') == value)


class ReaderProfileEditorTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask('isolated-reader-editor', static_folder=str(ROOT/'static'))
        self.app.secret_key = 'fixture-only'
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'user/base.html': '{% block extra_css %}{% endblock %}{% block content %}{% endblock %}{% block scripts %}{% endblock %}'}),
            FileSystemLoader(str(ROOT/'templates')),
        ])
        self.app.add_url_rule('/profile/<username>', 'user_profile', lambda username: '')

    def render_editor(self, social_links):
        with self.app.test_request_context('/'):
            session['_csrf_token'] = 'fixture-csrf'
            return render_template('user/edit_profile.html', profile=dict(
                username='reader123', first_name='Test', last_name='Reader',
                bio='A short bio', avatar_url=None, social_links=social_links))

    def test_editor_preserves_post_fields_csrf_and_native_limits(self):
        tags = Tags(self.render_editor({}))
        form = tags.by_id('editProfileForm')
        self.assertEqual((form['method'], form['action'], form['enctype']),
                         ('POST', '/user/profile/edit', 'multipart/form-data'))
        fields = {a.get('name'): a for _, a in tags.tags if a.get('name')}
        self.assertTrue({'_csrf_token', 'social_links', 'first_name', 'last_name', 'username', 'bio', 'avatar'} <= fields.keys())
        self.assertEqual(fields['_csrf_token']['value'], 'fixture-csrf')
        self.assertEqual(fields['first_name']['maxlength'], '50')
        self.assertEqual(fields['last_name']['maxlength'], '50')
        self.assertEqual(fields['bio']['maxlength'], '500')
        self.assertEqual(fields['username']['pattern'], '[A-Za-z0-9]{3,20}')
        self.assertNotIn('email', fields)

    def test_stored_social_json_is_escaped_and_hydrates_both_storage_shapes(self):
        links = {'Website': 'https://example.test/\"><img src=x onerror=alert(1)>'}
        for stored in (links, json.dumps(links)):
            with self.subTest(storage=type(stored).__name__):
                html = self.render_editor(stored)
                self.assertNotIn('<img src=x', html)
                self.assertEqual(json.loads(Tags(html).by_id('socialLinksInput')['value']), links)

    def test_share_preview_uses_canonical_milestones_and_leaves_unknown_count_unavailable(self):
        with self.app.test_request_context('/'):
            html = render_template('user/_share_stats.html', downloads=None, favorites=2,
                                   reviews=3, streak=4, achievements=achievement_summary(12, 2, 3, 8))
        self.assertIn('4 of 9 milestones unlocked', html)
        self.assertIn('<dt>Downloads</dt><dd>—</dd>', html)
        tags = Tags(html)
        self.assertIn('readonly', tags.by_id('community-share-summary'))
        links = [a for tag, a in tags.tags if tag == 'a']
        self.assertTrue(all(a['rel'] == 'noopener noreferrer' for a in links))

    def test_editor_dom_and_upload_contracts(self):
        result = subprocess.run([shutil.which('node') or 'node', '-e', EDITOR_CHECKS,
                                 str(ROOT/'static/js/edit-profile.js')], cwd=ROOT,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


EDITOR_CHECKS = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8');
class E {
 constructor(tag='div'){this.tag=tag;this.children=[];this.events={};this.attrs={};this.dataset={};this.value='';this.hidden=false;this.files=[];this.validityMessage='';this.textContent='';}
 append(...items){for(const item of items){item.parent=this;this.children.push(item);}}
 replaceChildren(...items){this.children=[];this.append(...items);}
 addEventListener(name,fn){this.events[name]=fn;}
 setAttribute(name,value){this.attrs[name]=value;}
 removeAttribute(name){delete this.attrs[name];}
 setCustomValidity(value){this.validityMessage=value;}
 checkValidity(){return !this.validityMessage;}
 reportValidity(){return this.querySelectorAll('input').every(e=>!e.validityMessage && (!e.required||e.value));}
 matches(selector){return selector[0]==='.'?(this.className||'').split(' ').includes(selector.slice(1)):this.tag===selector;}
 querySelectorAll(selector){return this.children.flatMap(e=>[...(e.matches(selector)?[e]:[]),...e.querySelectorAll(selector)]);}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 focus(){this.focused=true;}
 remove(){this.parent.children=this.parent.children.filter(e=>e!==this);}
}
function browser(stored){
 const ids={};for(const id of ['editProfileForm','socialLinksInput','socialLinksContainer','avatarInput','avatarPreview','avatarStatus','avatarProgressWrap','avatarProgressBar','saveProfileBtn','saveSpinner','usernameInput','usernameCheck','usernameError','addSocialLinkBtn','profileFlash','navbarAvatar'])ids[id]=new E();
 const form=ids.editProfileForm;form.action='/user/profile/edit';form.dataset.originalUsername='reader123';form.dataset.defaultAvatar='/default.jpg';
 ids.socialLinksInput.value=stored;ids.avatarPreview.src='/old.jpg';ids.usernameInput.value='reader123';
 const text=new E();text.className='btn-text';ids.saveProfileBtn.append(text);ids.saveProfileBtn.disabled=false;
 form.append(ids.socialLinksInput,ids.socialLinksContainer,ids.avatarInput,ids.usernameInput);
 const requests=[];let availabilityResolve;const delayed=[];
 class XHR {constructor(){this.upload={};requests.push(this);}open(method,url){this.method=method;this.url=url;}setRequestHeader(k,v){this.header=[k,v];}send(data){this.sent=data;}}
 class FD {constructor(form){this.form=form;}}
 class Reader {readAsDataURL(file){this.onload({target:{result:'data:image/png;base64,fixture'}});}}
 const scope={document:{getElementById:id=>ids[id]||null,createElement:tag=>new E(tag),querySelectorAll:()=>[]},window:{location:{origin:'https://fixture.test'}},URL,FileReader:Reader,FormData:FD,XMLHttpRequest:XHR,Date,SyntaxError,Error,clearTimeout(){},setTimeout:fn=>{delayed.push(fn);},fetch:()=>new Promise(resolve=>availabilityResolve=resolve)};
 vm.runInNewContext(source,scope);
 return{ids,form,requests,delayed,resolveAvailability:value=>availabilityResolve(value),submit:()=>form.events.submit({preventDefault(){}})};
}
(async()=>{
 const attack='https://example.test/\"><img src=x onerror=alert(1)>';
 let b=browser(JSON.stringify({Website:attack}));let rows=b.ids.socialLinksContainer.querySelectorAll('.social-link-row');assert.equal(rows.length,1);assert.equal(rows[0].querySelector('.link-input').value,attack);assert.equal(rows[0].querySelectorAll('img').length,0);
 b=browser(JSON.stringify(JSON.stringify({GitHub:'https://github.com/example'})));assert.equal(b.ids.socialLinksContainer.querySelectorAll('.social-link-row').length,1);
 b=browser('{}');b.ids.addSocialLinkBtn.events.click();let row=b.ids.socialLinksContainer.querySelector('.social-link-row');row.querySelector('.platform-select').value='Website';let input=row.querySelector('.link-input');input.value='javascript:alert(1)';input.events.input();b.submit();assert.equal(b.requests.length,0);assert.match(input.validityMessage,/https?/);
 input.value='https://example.test';input.events.input();b.submit();assert.equal(b.requests.length,1);let xhr=b.requests[0];assert.equal(xhr.method,'POST');assert.equal(xhr.url,'/user/profile/edit');assert.deepEqual(xhr.header,['X-Requested-With','XMLHttpRequest']);assert.equal(b.ids.saveProfileBtn.disabled,true);assert.equal(b.ids.socialLinksInput.value,JSON.stringify({Website:'https://example.test'}));xhr.status=200;xhr.responseText=JSON.stringify({success:true,message:'<img src=x onerror=alert(1)>',avatar_url:'javascript:alert(1)'});xhr.onload();assert.equal(b.ids.saveProfileBtn.disabled,false);assert.equal(b.ids.avatarPreview.src,'/old.jpg');assert.equal(b.ids.profileFlash.children[0].textContent,'<img src=x onerror=alert(1)>');
 b.ids.avatarInput.files=[{type:'image/png',size:100}];b.ids.avatarInput.events.change();assert.match(b.ids.avatarPreview.src,/^data:image/);b.submit();xhr=b.requests[1];xhr.upload.onprogress({lengthComputable:true,loaded:1,total:2});assert.equal(b.ids.avatarProgressBar.value,50);xhr.onerror();assert.equal(b.ids.saveProfileBtn.disabled,false);assert.match(b.ids.profileFlash.children[0].textContent,/Network/);
 b.ids.avatarInput.files=[{type:'image/png',size:11*1024*1024}];b.ids.avatarInput.events.change();assert.match(b.ids.avatarInput.validityMessage,/10 MB/);
 b=browser('{}');b.ids.usernameInput.value='taken123';b.ids.usernameInput.events.input();const pending=b.delayed.pop()();b.ids.usernameInput.value='reader123';b.ids.usernameInput.events.input();b.resolveAvailability({ok:true,json:async()=>({exists:true})});await pending;assert.equal(b.ids.usernameCheck.hidden,true);
 console.log('7 offline profile editor scenarios passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
