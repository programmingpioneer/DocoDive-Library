"""Submission contract with no database, browser POST or outgoing request."""
from pathlib import Path
import shutil,subprocess,unittest

CHECKS=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class E{constructor(){this.events={};this.value='';this.checked=false;this.hidden=true;this.textContent='';this.disabled=false;this.classes=new Set();this.classList={toggle:(s,on)=>on?this.classes.add(s):this.classes.delete(s)};}addEventListener(n,f){this.events[n]=f;}closest(){return this;}setAttribute(n,v){this[n]=v;}removeAttribute(n){delete this[n];}focus(){this.focused=true;}}
async function fixture(){
 const modal=new E(),form=new E(),status=new E(),comment=new E(),book=new E(),search=new E(),button=new E(),label=new E(),desc=new E(),trigger=new E();
 const choices=[1,2,3,4,5].map(n=>{let e=new E();e.value=String(n);e.checked=n===5;return e;});
 form.reportValidity=()=>true;button.querySelector=()=>label;
 const nodes={reviewModal:modal,reviewForm:form,reviewFormStatus:status,reviewComment:comment,reviewBookSelect:book,reviewBookSearch:search,submitReviewBtn:button};
 const body={dataset:{userLoggedIn:'true'}},calls=[];let response={ok:false,status:400,json:async()=>({error:'Please try again'})},reloaded=false,shown=false,auth=false;
 const window={location:{href:'http://localhost/reviews',reload:()=>{reloaded=true;}},bootstrap:{Modal:{getOrCreateInstance:()=>({show:()=>{shown=true;}})}},showAuthModal:()=>{auth=true;},setTimeout:f=>f()};
 const context={window,document:{body,getElementById:id=>nodes[id],querySelector:()=>desc,querySelectorAll:s=>s.includes('input')?choices:[trigger]},URLSearchParams,fetch:async(url,options)=>{calls.push({url,options});if(response instanceof Error)throw response;return response;}};
 vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
 const submit=()=>form.events.submit({preventDefault(){}});
 return {book,search,comment,choices,button,label,status,desc,calls,body,trigger,submit,setResponse:r=>response=r,state:()=>({reloaded,shown,auth})};
}
(async()=>{
 let x=await fixture();assert.match(x.desc.textContent,/5 out of 5/);x.choices.forEach(c=>c.checked=c.value==='2');x.choices[1].events.change();assert.match(x.desc.textContent,/2 out of 5/);assert.equal(x.choices.filter(c=>c.classes.has('is-active')).length,2);
 x.trigger.events.click();assert.equal(x.state().shown,true);x.body.dataset.userLoggedIn='false';x.trigger.events.click();assert.equal(x.state().auth,true);
 x=await fixture();x.comment.value='Keep this draft';x.book.value='invalid';await x.submit();assert.equal(x.calls.length,0);assert.match(x.status.textContent,/valid book/);
 x.book.value='';x.search.value='An unselected title';await x.submit();assert.equal(x.calls.length,0);assert.match(x.status.textContent,/Choose a matching book/);assert.equal(x.search.focused,true);
 x.search.value='';await x.submit();assert.equal(x.calls[0].url,'/api/reviews');assert.equal(x.comment.value,'Keep this draft');assert.equal(x.button.disabled,false);
 x=await fixture();x.comment.value='Keep this draft';
 x.book.value='6';await x.submit();assert.equal(x.calls[0].url,'/book/6/review');assert.equal(new URLSearchParams(x.calls[0].options.body).get('comment'),'Keep this draft');assert.equal(x.comment.value,'Keep this draft');assert.equal(x.button.disabled,false);assert.equal(x.state().reloaded,false);assert.equal(x.status.textContent,'Please try again');
 x.setResponse({ok:true,status:200,json:async()=>({})});await x.submit();assert.equal(x.state().reloaded,false);assert.equal(x.button.disabled,false);
 x.setResponse({redirected:true,status:200});await x.submit();assert.match(x.status.textContent,/session has ended/);assert.equal(x.comment.value,'Keep this draft');assert.equal(x.button.disabled,false);
 x.setResponse(new Error('network'));await x.submit();assert.match(x.status.textContent,/connection/);assert.equal(x.button.disabled,false);
 x.setResponse({ok:true,status:200,json:async()=>({success:true})});await x.submit();assert.equal(x.state().reloaded,true);assert.equal(x.button.disabled,true);
 console.log('Review controls: optional book, unselected search, validated book, guest/session, errors, drafts and success passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""

class ReviewControlTests(unittest.TestCase):
    def test_rating_and_submission_errors_preserve_the_draft(self):
        path=Path(__file__).resolve().parents[1]/'static/js/reviews.js'
        run=subprocess.run([shutil.which('node'),'-e',CHECKS,str(path)],capture_output=True,text=True,timeout=20)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

if __name__=='__main__':unittest.main()
