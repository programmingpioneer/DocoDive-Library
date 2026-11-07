(() => {
  'use strict';
  const toggle=document.getElementById('studio-menu');
  const sidebar=document.getElementById('studio-sidebar');
  const narrow=matchMedia('(max-width:1000px)');
  const syncNavigation=()=>{if(sidebar)sidebar.inert=narrow.matches&&!document.body.classList.contains('studio-menu-open');};
  const closeNavigation=()=>{document.body.classList.remove('studio-menu-open');toggle?.setAttribute('aria-expanded','false');syncNavigation();};
  toggle?.addEventListener('click',()=>{const open=document.body.classList.toggle('studio-menu-open');toggle.setAttribute('aria-expanded',String(open));syncNavigation();});
  document.querySelector('.studio-menu-scrim')?.addEventListener('click',()=>{closeNavigation();toggle?.focus();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('studio-menu-open')){closeNavigation();toggle?.focus();}});
  narrow.addEventListener('change',()=>{closeNavigation();});
  syncNavigation();
  document.querySelectorAll('table').forEach(table=>{const headings=[...table.querySelectorAll('thead th')].map(e=>e.textContent.trim());table.querySelectorAll('tbody tr').forEach(row=>[...row.cells].forEach((cell,i)=>cell.dataset.label=headings[i]||''));});
  document.addEventListener('submit',async event=>{
    const form=event.target;
    if(!form.matches('[data-confirm],.studio-json') || form.dataset.confirmed==='true') return;
    event.preventDefault();
    if(form.dataset.confirm && !await toast.confirm(form.dataset.confirm,{title:'Confirm action',confirmText:'Confirm',type:'danger'})) return;
    if(!form.matches('.studio-json')){form.dataset.confirmed='true';form.requestSubmit(event.submitter);return;}
    const button=event.submitter; const original=button?.textContent;if(button){button.disabled=true;button.textContent='Saving…';}form.setAttribute('aria-busy','true');
    try {if(!navigator.onLine)throw new Error('You are offline. Reconnect and retry.');const fields=new FormData(form);const options=form.dataset.json==='true'?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(fields))}:{method:'POST',body:fields};const response=await fetch(form.action,options);if(response.redirected){location.href=response.url;return;}const data=await response.json();if(!response.ok||data.error)throw new Error(data.error||'Unable to save.');toast.success(data.message||'Saved.');location.reload();}
    catch(error){toast.error(error.message||'Unable to save. Please try again.');}
    finally{form.removeAttribute('aria-busy');if(button){button.disabled=false;button.textContent=original;}}
  });
})();
