/* Small, passive scroll helpers. Native keyboard and page navigation remain intact. */
(() => {
  'use strict';
  function init() {
    if (!document.body.hasAttribute('data-public-site')) return;
    const controls=document.createElement('div');
    controls.className='reading-scroll-controls';controls.setAttribute('role','group');controls.setAttribute('aria-label','Page scroll controls');
    function button(id,label,path) {
      const item=document.createElement('button');item.id=id;item.type='button';item.hidden=true;
      item.setAttribute('aria-label',label);item.title=label;
      item.innerHTML='<svg class="site-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="'+path+'"/></svg>';
      controls.append(item);return item;
    }
    const up=button('backToTop','Back to top','M12 20V4m-7 7 7-7 7 7');
    const down=button('scrollDown','Scroll down','M12 4v16m-7-7 7 7 7-7');
    document.body.append(controls);
    let queued=false;
    function sync() {
      queued=false;const top=window.scrollY||0;
      const remaining=document.documentElement.scrollHeight-window.innerHeight-top;
      up.hidden=top<300;down.hidden=remaining<100;
      controls.hidden=up.hidden&&down.hidden;
    }
    function schedule() { if(queued)return;queued=true;window.requestAnimationFrame(sync); }
    const behavior=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth';
    up.addEventListener('click',()=>window.scrollTo({top:0,behavior:behavior()}));
    down.addEventListener('click',()=>window.scrollBy({top:Math.max(240,window.innerHeight*.8),behavior:behavior()}));
    window.addEventListener('scroll',schedule,{passive:true});window.addEventListener('resize',schedule,{passive:true});
    window.addEventListener('pageshow',schedule);window.addEventListener('load',schedule);
    document.addEventListener('docodive:practice-answer',schedule);
    sync();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
