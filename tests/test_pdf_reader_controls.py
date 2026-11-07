"""Reader response guards with synthetic fetches; no app config or network."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
CHECK=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
assert.ok(fs.existsSync(process.argv[1]),'Reader response controller is missing');
class Element{
 constructor(){this.dataset={};this.attrs={};this.events={};this.hidden=false;this.disabled=false;this.textContent='';}
 addEventListener(n,f){(this.events[n]??=[]).push(f);}fire(n){return Promise.all((this.events[n]||[]).map(f=>f({preventDefault(){}})));}
 setAttribute(n,v){this.attrs[n]=String(v);}getAttribute(n){return this.attrs[n]??null;}removeAttribute(n){delete this.attrs[n];}
}
const tick=()=>new Promise(r=>setImmediate(r));
const reply=(status=200,type='application/pdf',more={})=>({status,ok:status>=200&&status<300,headers:{get:n=>n.toLowerCase()==='content-type'?type:null},...more});
async function fixture(initial=reply(),path='/book/4/pdf'){
 const ids='pdfIframe readerStatus readerMessage readerRetry readerSignin readerContainer readerDirect'.split(' '),n=Object.fromEntries(ids.map(id=>[id,new Element()]));
 n.pdfIframe.dataset.pdfUrl=path;n.pdfIframe.hidden=true;n.readerRetry.hidden=n.readerSignin.hidden=true;
 let result=initial;const calls=[];
 const document={getElementById:id=>n[id]||null};
 const location={href:'https://local.test/book/4/read',origin:'https://local.test',pathname:'/book/4/read',search:''};
 const window={setTimeout:()=>1,clearTimeout(){},addEventListener(){}};
 vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document,location,window,URL,AbortController,console,fetch:async(url,options)=>{calls.push({url,options});if(result instanceof Error)throw result;return result;}});await tick();
 return {n,calls,setReply:r=>result=r,retry:async()=>{await n.readerRetry.fire('click');await tick();}};
}
(async()=>{
 if(process.argv[2]==='acceptPdf'){
  let f=await fixture();assert.equal(f.calls.length,1);assert.equal(f.calls[0].options.method,'HEAD');assert.equal(f.calls[0].options.cache,'no-store');assert.equal(f.calls[0].options.credentials,'same-origin');assert.equal(f.calls[0].options.redirect,'error');
  assert.equal(f.n.pdfIframe.getAttribute('src'),'/book/4/pdf');assert.equal(f.n.pdfIframe.hidden,false);assert.equal(f.n.readerStatus.hidden,true);
 }else if(process.argv[2]==='rejectHtmlAndFailures'){
  for(const response of [reply(200,'text/html'),reply(200,'application/xml'),reply(404,'text/html'),reply(503,'text/html'),reply(200,'application/pdf',{redirected:true}),reply(200,'application/pdf',{type:'opaqueredirect'}),new Error('network')]){
   let f=await fixture(response);assert.equal(f.n.pdfIframe.getAttribute('src'),null,'No homepage/login/XML is embedded');assert.equal(f.n.pdfIframe.hidden,true);assert.equal(f.n.readerStatus.hidden,false);assert.equal(f.n.readerRetry.hidden,false);assert.notEqual(f.n.readerMessage.textContent,'');
  }
 }else if(process.argv[2]==='sessionRetryAndOrigins'){
  let f=await fixture(reply(401,'application/json'));assert.equal(f.n.readerSignin.hidden,false);assert.match(f.n.readerSignin.href,/^\/user\/login\?next=/);assert.equal(f.n.pdfIframe.getAttribute('src'),null);
  f.setReply(reply());await f.retry();assert.equal(f.n.pdfIframe.hidden,false);assert.equal(f.n.readerSignin.hidden,true);
  for(const path of ['https://untrusted.test/file.pdf','/','/user/login','//elsewhere.test/book/4/pdf','javascript:alert(1)']){
   f=await fixture(reply(),path);assert.equal(f.calls.length,0);assert.equal(f.n.pdfIframe.getAttribute('src'),null);
  }
 }else if(process.argv[2]==='retryDropsAnEarlierPdf'){
  let f=await fixture();f.setReply(reply(200,'text/html'));await f.retry();assert.equal(f.n.pdfIframe.getAttribute('src'),null);assert.equal(f.n.pdfIframe.hidden,true);
 }
 console.log(process.argv[2]+' passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class PDFReaderControlTests(unittest.TestCase):
    def test_reader_rejects_non_pdf_responses_and_recovers_without_embedding_html(self):
        for scenario in ('acceptPdf','rejectHtmlAndFailures','sessionRetryAndOrigins','retryDropsAnEarlierPdf'):
            with self.subTest(scenario=scenario):
                result=subprocess.run([shutil.which('node'),'-e',CHECK,str(ROOT/'static/js/pdf-reader.js'),scenario],capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
