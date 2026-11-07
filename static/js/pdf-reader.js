/* Mount only the authenticated PDF endpoint, never a returned HTML page. */
(() => {
  'use strict';
  const frame=document.getElementById('pdfIframe');
  if(!frame)return;
  const panel=document.getElementById('readerStatus'),message=document.getElementById('readerMessage');
  const retry=document.getElementById('readerRetry'),signin=document.getElementById('readerSignin');
  const container=document.getElementById('readerContainer'),direct=document.getElementById('readerDirect');
  let revision=0,controller;
  function fail(text,needsLogin=false){
    frame.hidden=true;frame.removeAttribute('src');panel.hidden=false;direct.hidden=true;
    message.textContent=text;retry.hidden=false;signin.hidden=!needsLogin;
    signin.href='/user/login?next='+encodeURIComponent(location.pathname+location.search);
  }
  async function load(){
    const current=++revision;controller?.abort();const active=new AbortController();controller=active;
    frame.hidden=true;frame.removeAttribute('src');panel.hidden=false;direct.hidden=true;
    retry.hidden=true;retry.disabled=true;signin.hidden=true;
    container.setAttribute('aria-busy','true');
    message.textContent='Checking that your book is ready to read…';
    let timer;
    try{
      const url=new URL(frame.dataset.pdfUrl,location.href);
      if(url.origin!==location.origin||url.search||url.hash||!/^\/book\/(?:[^/]+\/)?\d+\/pdf$/.test(url.pathname))
        throw new Error('invalid PDF endpoint');
      timer=window.setTimeout(()=>active.abort(),40000);
      const response=await fetch(url.href,{method:'HEAD',credentials:'same-origin',cache:'no-store',redirect:'error',
        headers:{'X-Requested-With':'XMLHttpRequest'},signal:active.signal});
      if(current!==revision)return;
      const type=(response.headers.get('Content-Type')||'').split(';')[0].trim().toLowerCase();
      if(response.status===401||response.status===403){fail('Please sign in again to read this book.',true);return;}
      if(response.status===404){fail('This PDF file is not available. Try another book or contact support.');return;}
      if(response.status===503){fail('Book storage is temporarily unavailable. Please retry in a moment.');return;}
      if(!response.ok||response.redirected||response.type==='opaqueredirect'||type!=='application/pdf'){
        fail('The server did not return a PDF. Please retry or contact support.');return;
      }
      frame.setAttribute('src',url.pathname);frame.hidden=false;panel.hidden=true;direct.hidden=false;
    }catch(error){
      if(current===revision)fail('We could not open this PDF. Check your connection and try again.');
    }finally{
      window.clearTimeout(timer);
      if(current===revision){retry.disabled=false;container.setAttribute('aria-busy','false');}
    }
  }
  retry.addEventListener('click',load);
  frame.addEventListener('error',()=>fail('The PDF viewer could not load. Please retry or open the PDF in a new tab.'));
  load();
})();
