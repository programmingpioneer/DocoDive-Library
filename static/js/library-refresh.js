/* Keep incoming catalogue updates from interrupting an open reader dialog. */
(() => {
  'use strict';
  if(!window.BroadcastChannel)return;
  const channel=new window.BroadcastChannel('docodive_upload');
  const opening=new Set();
  let pending=false;
  const busy=()=>opening.size||document.querySelector('.modal.show,.modal[aria-modal="true"],#shared-book-preview[data-preview-open="true"],dialog[open]');
  const apply=()=>{if(pending&&!busy()){pending=false;window.location.reload();}};
  channel.onmessage=event=>{if(event.data==='refresh'){pending=true;apply();}};
  document.addEventListener('show.bs.modal',event=>{if(!event.defaultPrevented)opening.add(event.target);});
  document.addEventListener('shown.bs.modal',event=>opening.delete(event.target));
  document.addEventListener('hidden.bs.modal',event=>{opening.delete(event?.target);apply();});
  document.addEventListener('close',apply,true);
})();
