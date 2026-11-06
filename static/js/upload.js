/* Native upload enhancement. Files remain local until the user submits. */
(() => {
  'use strict';
  const byId=id=>document.getElementById(id);
  const page=byId('readerUploadPage'),form=byId('uploadForm');
  if(!page || !form) return;
  const pdf=byId('pdf_file'),cover=byId('cover_image'),category=byId('categorySelect');
  const button=byId('uploadBtn'),buttonLabel=byId('uploadBtnLabel');
  const status=byId('statusMessage'),progress=byId('progressCard'),track=byId('uploadProgress');
  const history=byId('pending-uploads-list'),listStatus=byId('uploadsListStatus'),refresh=byId('refreshUploadsBtn');
  const MAX_TOTAL=500*1024*1024,MAX_COVER=10*1024*1024;
  let busy=false,coverUrl=null,listGeneration=0,listAbort=null,hasHistory=false;
  const bytes=value=>{
    if(!Number.isFinite(value)||value<0) return '—';
    if(value>=1024*1024) return (value/(1024*1024)).toFixed(1)+' MB';
    if(value>=1024) return (value/1024).toFixed(1)+' KB';
    return Math.round(value)+' B';
  };
  const remaining=seconds=>!Number.isFinite(seconds)||seconds<=0?'—':seconds<60?Math.ceil(seconds)+'s':Math.ceil(seconds/60)+' min';
  const report=(message,state='error')=>{status.textContent=message;status.dataset.state=state;status.hidden=false;};
  const icon=(target,id)=>{const template=byId(id);if(template?.content)target.append(template.content.cloneNode(true));};
  const element=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;};

  function updateSummary(){
    byId('uploadSummaryFile').textContent=pdf.files[0]?.name || 'No PDF selected';
    byId('uploadSummaryCategory').textContent=category.selectedOptions?.[0]?.textContent || 'Auto-detect from PDF';
    byId('uploadSummaryCover').textContent=cover.files[0]?.name || 'Create from first page';
  }
  function showPdf(){
    const file=pdf.files[0];
    byId('pdfSelection').hidden=!file;
    byId('pdfName').textContent=file?.name || '';
    byId('pdfSize').textContent=file?bytes(file.size):'';
    byId('choosePdfLabel').textContent=file?'Change PDF':'Choose PDF';
    updateSummary();
  }
  function validatePdf(file){
    if(!file || !/\.pdf$/i.test(file.name))return 'Choose a PDF (.pdf) file.';
    if(!file.size)return 'This PDF is empty. Choose a file with content.';
    if(file.size>MAX_TOTAL)return 'Keep your PDF and cover below the 500 MB total upload limit.';
    return '';
  }
  function validateCover(file){
    if(!file)return '';
    if(!/\.(jpe?g|png|gif|webp)$/i.test(file.name))return 'Choose a JPG, PNG, GIF or WebP cover image.';
    if(!file.size)return 'This cover image is empty. Choose another image.';
    if(file.size>MAX_COVER)return 'Choose a cover image of 10 MB or less.';
    return '';
  }
  function changePdf(){
    if(busy)return;
    const file=pdf.files[0];
    if(file){const error=validatePdf(file);if(error){pdf.value='';report(error);}else status.hidden=true;}
    showPdf();
  }
  function clearCover(){
    if(coverUrl){URL.revokeObjectURL(coverUrl);coverUrl=null;}
    cover.value='';byId('coverThumb').removeAttribute('src');byId('coverPreview').hidden=true;
    byId('coverName').textContent='';byId('coverSize').textContent='';updateSummary();
  }
  function changeCover(){
    if(busy)return;
    if(coverUrl){URL.revokeObjectURL(coverUrl);coverUrl=null;}
    const file=cover.files[0];
    const error=validateCover(file);
    if(!file || error){clearCover();if(error)report(error);return;}
    try{
      coverUrl=URL.createObjectURL(file);
      byId('coverThumb').src=coverUrl;
      byId('coverName').textContent=file.name;byId('coverSize').textContent=bytes(file.size);
      byId('coverPreview').hidden=false;status.hidden=true;updateSummary();
    }catch(error){clearCover();report('We could not preview that image. Choose another cover, or leave it empty.');}
  }
  function setBusy(value){
    busy=value;form.setAttribute('aria-busy',String(value));button.setAttribute('aria-busy',String(value));
    for(const id of ['pdf_file','cover_image','categorySelect','choosePdfBtn','clearPdfBtn','chooseCoverBtn','removeCoverBtn','uploadBtn'])byId(id).disabled=value;
    buttonLabel.textContent=value?'Submitting…':'Upload for Review';
  }
  function finish(message,success=false){
    progress.hidden=true;setBusy(false);
    if(success){form.reset();clearCover();showPdf();loadUploads();}
    report(message,success?'success':'error');
  }
  function emptyHistory(){
    const box=element('div','upload-history-empty'),symbol=element('span');icon(symbol,'uploadEmptyIcon');box.append(symbol,element('strong','','Your first submission starts here'),element('p','','You have no uploads yet. Share a PDF using the form above.'));history.replaceChildren(box);
  }
  function historyRow(book){
    const row=element('article','upload-history-row'),visual=element('span','upload-history-visual');icon(visual,'uploadRowIcon');
    const body=element('div','upload-history-body');body.append(element('strong','',typeof book.title==='string'&&book.title.trim()?book.title:'Untitled book'));
    const meta=element('div','upload-history-meta');meta.append(element('span','',typeof book.author==='string'&&book.author.trim()?'By '+book.author:'Author unknown'));
    if(typeof book.created_at==='string'){
      const date=new Date(book.created_at);
      if(!Number.isNaN(date.getTime()))meta.append(element('span','',new Intl.DateTimeFormat(undefined,{day:'numeric',month:'short',year:'numeric'}).format(date)));
    }
    body.append(meta);
    const statuses={pending:['Pending review','is-pending'],approved:['Approved','is-approved'],rejected:['Rejected','is-rejected']};
    const state=Object.prototype.hasOwnProperty.call(statuses,book.status)?statuses[book.status]:['Status unavailable',''];
    const badge=element('span','upload-history-badge '+state[1],state[0]);row.append(visual,body,badge);return row;
  }
  async function loadUploads(){
    const generation=++listGeneration;
    if(listAbort)listAbort.abort();listAbort=typeof AbortController==='function'?new AbortController():null;
    refresh.disabled=true;
    try{
      const response=await fetch('/api/user/uploads',{headers:{'X-Requested-With':'XMLHttpRequest'},...(listAbort?{signal:listAbort.signal}:{})});
      if(generation!==listGeneration)return;
      if(response.status===401||response.redirected){hasHistory=false;history.replaceChildren();byId('uploadsCount').textContent='';throw new Error('Please sign in again to view your uploads.');}
      if(!response.ok)throw new Error('Could not refresh your uploads. Please try Refresh again.');
      const data=await response.json();
      if(generation!==listGeneration)return;
      if(!Array.isArray(data)||data.some(book=>!book||typeof book!=='object'||Array.isArray(book)))throw new Error('Could not refresh your uploads. Please try Refresh again.');
      if(data.length)history.replaceChildren(...data.map(historyRow));else emptyHistory();
      byId('uploadsCount').textContent='('+data.length+')';listStatus.hidden=true;hasHistory=true;
    }catch(error){
      if(generation!==listGeneration||error.name==='AbortError')return;
      listStatus.textContent=error.message?.startsWith('Please sign in')||error.message?.startsWith('Could not refresh')?error.message:'Could not refresh your uploads. Check your connection and try again.';
      listStatus.hidden=false;listStatus.setAttribute('role','alert');
      if(!hasHistory)history.replaceChildren();
    }finally{if(generation===listGeneration)refresh.disabled=false;}
  }

  page.classList.add('is-enhanced');byId('uploadSummary').hidden=false;
  byId('choosePdfBtn').hidden=false;byId('chooseCoverBtn').hidden=false;
  byId('choosePdfBtn').addEventListener('click',()=>{if(!busy)pdf.click();});
  byId('chooseCoverBtn').addEventListener('click',()=>{if(!busy)cover.click();});
  byId('clearPdfBtn').addEventListener('click',()=>{if(!busy){pdf.value='';showPdf();byId('choosePdfBtn').focus();}});
  byId('removeCoverBtn').addEventListener('click',()=>{if(!busy){clearCover();byId('chooseCoverBtn').focus();}});
  byId('coverThumb').addEventListener('error',()=>{if(coverUrl){clearCover();report('That image could not be opened. Choose another cover, or leave it empty.');}});
  pdf.addEventListener('change',changePdf);cover.addEventListener('change',changeCover);category.addEventListener('change',updateSummary);
  refresh.addEventListener('click',()=>loadUploads());
  const drop=byId('uploadDropzone');
  drop.addEventListener('dragover',event=>{event.preventDefault();if(!busy)drop.classList.add('is-dragover');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('is-dragover'));
  drop.addEventListener('drop',event=>{
    event.preventDefault();drop.classList.remove('is-dragover');if(busy)return;
    const files=event.dataTransfer?.files;if(!files?.length)return;
    if(files.length!==1){report('Choose one PDF at a time.');return;}
    const error=validatePdf(files[0]);if(error){report(error);return;}
    try{const transfer=new DataTransfer();transfer.items.add(files[0]);pdf.files=transfer.files;changePdf();}
    catch(error){report('Use Choose PDF to select this file.');}
  });
  form.addEventListener('submit',event=>{
    event.preventDefault();if(busy)return;
    if(!form.reportValidity())return;
    const file=pdf.files[0],coverFile=cover.files[0];
    const error=validatePdf(file)||validateCover(coverFile);
    if(error){report(error);return;}
    if(file.size+(coverFile?.size||0)>MAX_TOTAL){report('Keep your PDF and cover below the 500 MB total upload limit.');return;}
    try{
      const data=new FormData(form),xhr=new XMLHttpRequest(),started=Date.now();
      status.hidden=true;setBusy(true);progress.hidden=false;
      track.classList.remove('is-indeterminate');track.setAttribute('aria-valuenow','0');byId('progressBar').style.width='0%';byId('progressPercent').textContent='0%';
      byId('progressStatus').textContent='Sending your files';byId('statSize').textContent=bytes(file.size+(coverFile?.size||0));byId('statSpeed').textContent='—';byId('statETA').textContent='—';
      xhr.open('POST','/user/upload',true);xhr.setRequestHeader('X-Requested-With','XMLHttpRequest');
      xhr.upload.onprogress=event=>{
        const elapsed=Math.max(0,(Date.now()-started)/1000),speed=elapsed>0?event.loaded/elapsed:0;
        byId('statSpeed').textContent=speed>0?bytes(speed)+'/s':'—';
        if(event.lengthComputable&&event.total>0){
          const percent=event.loaded>=event.total?100:Math.min(99,Math.max(0,Math.floor(event.loaded/event.total*100)));
          track.classList.remove('is-indeterminate');track.setAttribute('aria-valuenow',String(percent));byId('progressBar').style.width=percent+'%';byId('progressPercent').textContent=percent+'%';
          byId('statETA').textContent=percent===100?'—':remaining(speed>0?(event.total-event.loaded)/speed:0);
          if(percent===100)byId('progressStatus').textContent='Files sent · waiting for confirmation';
        }else{track.removeAttribute('aria-valuenow');track.classList.add('is-indeterminate');byId('progressPercent').textContent='…';byId('statETA').textContent='—';}
      };
      xhr.onload=()=>{
        let data=null;try{data=JSON.parse(xhr.responseText);}catch(error){}
        const path=xhr.responseURL?new URL(xhr.responseURL,window.location.href).pathname:'';
        if(xhr.status===401||path.startsWith('/user/login')){finish('Your session has ended. Please sign in again before submitting.');return;}
        if(xhr.status===413){finish('This upload is too large. Keep your PDF and cover below the 500 MB total upload limit.');return;}
        if(xhr.status>=200&&xhr.status<300&&data?.success===true){finish('Your book was received for review. It will appear after admin approval.',true);return;}
        finish(typeof data?.error==='string'&&data.error.trim()?data.error:'We could not confirm this submission. Refresh Your Uploads to check before trying again.');
      };
      xhr.onerror=()=>finish('Connection lost. Refresh Your Uploads to check whether it was received before trying again.');
      xhr.onabort=()=>finish('The transfer was interrupted. Refresh Your Uploads before trying again.');
      xhr.send(data);
    }catch(error){finish('The upload could not start. Check your connection and try again.');}
  });
  window.addEventListener('pagehide',()=>{if(coverUrl)URL.revokeObjectURL(coverUrl);if(listAbort)listAbort.abort();});
  showPdf();loadUploads();
})();
