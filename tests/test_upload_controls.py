"""Upload interaction contracts; no real browser POST, file storage or email."""
from pathlib import Path
import shutil,subprocess,unittest

CHECKS=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
assert.ok(fs.existsSync(process.argv[1]),'Upload controller is missing');
class E{
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.events={};this.children=[];this.hidden=false;this.disabled=false;this.files=[];this.dataset={};this.attrs={};this._value='';this._text='';this.style={};this.classes=new Set();this.classList={add:(...c)=>c.forEach(v=>this.classes.add(v)),remove:(...c)=>c.forEach(v=>this.classes.delete(v)),toggle:(c,on)=>on?this.classes.add(c):this.classes.delete(c)};}
 addEventListener(n,f){(this.events[n]??=[]).push(f);}fire(n,e={}){return (this.events[n]||[]).map(f=>f({preventDefault(){},...e}));}
 set value(v){this._value=v;if(v===''&&this.type==='file')this.files=[];}get value(){return this._value;}
 set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent??String(c)).join('');}
 set innerHTML(v){throw new Error('Dynamic innerHTML is forbidden');}append(...c){this.children.push(...c);}replaceChildren(...c){this._text='';this.children=[...c];}
 setAttribute(k,v){this.attrs[k]=String(v);}removeAttribute(k){delete this.attrs[k];}getAttribute(k){return this.attrs[k];}focus(){this.focused=true;}click(){this.clicked=true;}cloneNode(){return new E(this.tagName);}setCustomValidity(s){this.validation=s;}get options(){return [{value:'',textContent:'Auto-detect from PDF'},{value:'Python',textContent:'Python'}];}
}
const ids='readerUploadPage uploadForm pdf_file cover_image categorySelect choosePdfBtn choosePdfLabel clearPdfBtn chooseCoverBtn removeCoverBtn pdfSelection pdfName pdfSize coverPreview coverThumb coverName coverSize uploadDropzone uploadBtn uploadBtnLabel statusMessage progressCard uploadProgress progressBar progressPercent statSize statSpeed statETA progressStatus pending-uploads-list uploadsListStatus uploadsCount refreshUploadsBtn uploadSummary uploadSummaryFile uploadSummaryCover uploadSummaryCategory uploadRowIcon uploadEmptyIcon uploadErrorIcon'.split(' ');
const tick=()=>new Promise(r=>setImmediate(r));
async function fixture(){
 const n=Object.fromEntries(ids.map(id=>[id,new E()]));n.pdf_file.type=n.cover_image.type='file';n.categorySelect.selectedOptions=[{textContent:'Auto-detect from PDF'}];
 for(const id of ['uploadRowIcon','uploadEmptyIcon','uploadErrorIcon'])n[id].content={cloneNode:()=>new E('svg')};
 n.uploadForm.reportValidity=()=>n.pdf_file.files.length>0;n.uploadForm.reset=()=>{n.pdf_file.value='';n.cover_image.value='';n.categorySelect.value='';};
 let reply={ok:true,status:200,json:async()=>[{title:'<img src=x onerror=attack()>',author:'A <reader>',status:'approved',created_at:'2026-11-01 12:00:00'}]},fetchCalls=0;
 const requests=[],revoked=[],created=[];
 class XHR{constructor(){this.upload={};requests.push(this);}open(method,url){this.method=method;this.url=url;}setRequestHeader(k,v){(this.headers??={})[k]=v;}send(body){this.body=body;}}
 class FD{constructor(){this.pdf=n.pdf_file.files[0];this.cover=n.cover_image.files[0];this.category=n.categorySelect.value;}}
 class U extends URL{}U.createObjectURL=f=>{let u='blob:sample-'+created.length;created.push(u);return u;};U.revokeObjectURL=u=>revoked.push(u);
 const window={addEventListener(){},location:{href:'http://local.test/user/upload'}};
 const document={getElementById:id=>n[id]||null,createElement:tag=>new E(tag),createTextNode:s=>({textContent:String(s)})};
 class DT{constructor(){this.files=[];this.items={add:f=>this.files.push(f)};}}
 const context={window,document,XMLHttpRequest:XHR,FormData:FD,URL:U,DataTransfer:DT,AbortController,Date,Intl,fetch:async()=>{fetchCalls++;if(reply instanceof Error)throw reply;return reply;},console};
 vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);await tick();
 return {n,requests,created,revoked,setReply:r=>reply=r,refresh:async()=>{n.refreshUploadsBtn.fire('click');await tick();},selectPdf:(file)=>{n.pdf_file.files=[file];n.pdf_file.fire('change');},selectCover:file=>{n.cover_image.files=[file];n.cover_image.fire('change');},submit:()=>n.uploadForm.fire('submit'),fetchCalls:()=>fetchCalls};
}
const pdf=(name='A sample book.pdf',size=1024)=>({name,size,type:'application/pdf'});
(async()=>{
 let x=await fixture();assert.match(x.n['pending-uploads-list'].textContent,/<img src=x onerror=attack\(\)>/);assert.match(x.n['pending-uploads-list'].textContent,/Approved/);
 x.selectPdf(pdf('not-a-pdf.exe'));x.submit();assert.equal(x.requests.length,0);assert.match(x.n.statusMessage.textContent,/PDF/i);
 x.selectPdf(pdf('large.pdf',501*1024*1024));x.submit();assert.equal(x.requests.length,0);assert.match(x.n.statusMessage.textContent,/500/);
 x.selectPdf(pdf('Empty.pdf',0));x.submit();assert.equal(x.requests.length,0);
 x.selectPdf(pdf());assert.equal(x.n.pdfName.textContent,'A sample book.pdf');assert.equal(x.n.pdfSelection.hidden,false);
 x.selectCover({name:'cover.png',size:3*1024*1024,type:'image/png'});assert.equal(x.created.length,1);assert.equal(x.n.coverPreview.hidden,false);x.n.removeCoverBtn.fire('click');assert.equal(x.revoked.length,1);assert.equal(x.n.cover_image.files.length,0);assert.equal(x.n.chooseCoverBtn.focused,true);
 x.selectCover({name:'bad.svg',size:100,type:'image/svg+xml'});assert.equal(x.n.cover_image.files.length,0);assert.equal(x.n.pdf_file.files.length,1);
 x.selectCover({name:'big.jpg',size:11*1024*1024,type:'image/jpeg'});assert.equal(x.n.cover_image.files.length,0);assert.match(x.n.statusMessage.textContent,/10/);
 x.n.categorySelect.value='Python';x.n.categorySelect.selectedOptions=[{textContent:'Python'}];x.n.categorySelect.fire('change');x.submit();assert.equal(x.requests.length,1);assert.equal(x.requests[0].url,'/user/upload');assert.equal(x.requests[0].body.category,'Python');assert.equal(x.n.uploadBtn.disabled,true);x.submit();assert.equal(x.requests.length,1);
 let req=x.requests[0];req.upload.onprogress({lengthComputable:true,loaded:40,total:100});assert.equal(x.n.uploadProgress.getAttribute('aria-valuenow'),'40');req.upload.onprogress({lengthComputable:true,loaded:995,total:1000});assert.equal(x.n.uploadProgress.getAttribute('aria-valuenow'),'99');assert.doesNotMatch(x.n.progressStatus.textContent,/Files sent/);req.upload.onprogress({lengthComputable:true,loaded:100,total:100});assert.match(x.n.progressStatus.textContent,/confirmation/i);assert.equal(x.n.pdf_file.files.length,1);
 req.status=400;req.responseText=JSON.stringify({error:'<strong>Try again</strong>'});req.onload();assert.equal(x.n.uploadBtn.disabled,false);assert.equal(x.n.pdf_file.files.length,1);assert.equal(x.n.categorySelect.value,'Python');assert.match(x.n.statusMessage.textContent,/<strong>Try again<\/strong>/);
 x.submit();req=x.requests.at(-1);req.status=200;req.responseText='<html>Login</html>';req.responseURL='http://local.test/user/login';req.onload();assert.equal(x.n.pdf_file.files.length,1);assert.match(x.n.statusMessage.textContent,/sign in/i);
 x.submit();req=x.requests.at(-1);req.status=413;req.responseText='<html>Too large</html>';req.onload();assert.match(x.n.statusMessage.textContent,/500/);assert.equal(x.n.uploadBtn.disabled,false);
 x.submit();req=x.requests.at(-1);req.onerror();assert.equal(x.n.pdf_file.files.length,1);assert.match(x.n.statusMessage.textContent,/connection|network/i);
 x.submit();req=x.requests.at(-1);req.status=200;req.responseText=JSON.stringify({message:'not confirmed'});req.onload();assert.equal(x.n.pdf_file.files.length,1);assert.equal(x.n.uploadBtn.disabled,false);
 x.submit();req=x.requests.at(-1);req.status=200;req.responseText=JSON.stringify({success:true,message:'Legacy encoded prefix: Ã¢Å“â€¦'});req.onload();await tick();assert.equal(x.n.pdf_file.files.length,0);assert.equal(x.n.uploadBtn.disabled,false);assert.match(x.n.statusMessage.textContent,/received for review/i);assert.doesNotMatch(x.n.statusMessage.textContent,/Legacy encoded/);
 const rows=x.n['pending-uploads-list'].textContent;x.setReply({ok:false,status:503,json:async()=>({error:'unavailable'})});await x.refresh();assert.equal(x.n['pending-uploads-list'].textContent,rows);assert.equal(x.n.uploadsListStatus.hidden,false);
 x=await fixture();x.setReply({ok:true,status:200,json:async()=>[]});await x.refresh();assert.match(x.n['pending-uploads-list'].textContent,/no.*uploads|first submission|haven.t.*uploaded/i);
 x.setReply({ok:false,status:401});await x.refresh();assert.match(x.n.uploadsListStatus.textContent,/sign in/i);
 x=await fixture();x.selectPdf(pdf('large.pdf',499*1024*1024));x.selectCover({name:'cover.png',size:2*1024*1024,type:'image/png'});x.submit();assert.equal(x.requests.length,0);assert.match(x.n.statusMessage.textContent,/500/);
 let resolveSlow;x.setReply(new Promise(r=>{resolveSlow=r;}));await x.refresh();x.setReply({ok:true,status:200,json:async()=>[{title:'Newest response',status:'pending'}]});await x.refresh();resolveSlow({ok:true,status:200,json:async()=>[{title:'Stale response',status:'approved'}]});await tick();assert.match(x.n['pending-uploads-list'].textContent,/Newest response/);assert.doesNotMatch(x.n['pending-uploads-list'].textContent,/Stale response/);
 x.setReply({ok:false,status:401});await x.refresh();assert.equal(x.n['pending-uploads-list'].textContent,'');
 console.log('23 upload interaction scenarios passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
class UploadControlTests(unittest.TestCase):
    def test_selection_preview_progress_safe_history_and_retry(self):
        path=Path(__file__).resolve().parents[1]/'static/js/upload.js'
        r=subprocess.run([shutil.which('node'),'-e',CHECKS,str(path)],capture_output=True,text=True,timeout=25)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
