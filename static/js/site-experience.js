/* Local appearance and honest loading states. No network requests or account writes. */
(() => {
  'use strict';
  function init(){
    const root=document.documentElement;
    let choice=['light','dark'].includes(root.dataset.themeChoice)?root.dataset.themeChoice:'light';
    const controls=Array.from(document.querySelectorAll('[data-theme-toggle]'));
    const feedback=document.createElement('span');feedback.className='experience-sr-only';feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');document.body.append(feedback);
    function apply(theme,persist=false){
      root.dataset.bsTheme=theme;root.style.colorScheme=theme;
      controls.forEach(button=>{const label='Switch to '+(theme==='dark'?'light':'dark')+' mode';button.setAttribute('aria-label',label);button.setAttribute('title',label);button.setAttribute('aria-pressed',String(theme==='dark'));});
      if(persist){choice=theme;root.dataset.themeChoice=theme;try{window.localStorage.setItem('docodive_theme',theme);feedback.textContent=(theme==='dark'?'Dark':'Light')+' mode is on.';}catch(error){feedback.textContent=(theme==='dark'?'Dark':'Light')+' mode is on for this page. Your browser could not save this preference.';}}
      document.dispatchEvent(new CustomEvent('docodive:themechange',{detail:{theme}}));
    }
    apply(choice);
    controls.forEach(button=>button.addEventListener('click',()=>apply(root.dataset.bsTheme==='dark'?'light':'dark',true)));
    window.addEventListener('storage',event=>{if(event.key!=='docodive_theme')return;choice=['light','dark'].includes(event.newValue)?event.newValue:'light';root.dataset.themeChoice=choice;apply(choice);});

    const frame=callback=>typeof window.requestAnimationFrame==='function'?window.requestAnimationFrame(callback):callback();
    const loader=document.getElementById('page-loader');
    const motion=typeof window.matchMedia==='function'?window.matchMedia('(prefers-reduced-motion: reduce)'):null;
    const now=()=>window.performance?.now?.()??Date.now();
    let visit=0,readyTimer,hideTimer,failsafe;
    const clearTimers=()=>{[readyTimer,hideTimer,failsafe].forEach(id=>window.clearTimeout(id));};
    function hidePage(token){
      if(token!==visit)return;
      clearTimers();visit++;
      if(loader){loader.hidden=true;loader.classList.add('hidden');loader.classList.remove('is-active','is-leaving');}
      root.dataset.siteReady='true';
    }
    function showOwnPage(reason,settle=true){
      clearTimers();const token=++visit,started=now();
      if(!loader){root.dataset.siteReady='true';return;}
      loader.hidden=false;loader.classList.remove('hidden','is-leaving');loader.classList.add('is-active');
      loader.dataset.loadTrigger=reason;root.dataset.siteReady='false';
      // Every document keeps its server-rendered composition, including its cached snapshot.
      failsafe=window.setTimeout(()=>hidePage(token),4000);
      if(!settle)return;
      frame(()=>frame(()=>{
        if(token!==visit)return;
        readyTimer=window.setTimeout(()=>{
          if(token!==visit)return;
          if(motion?.matches){hidePage(token);return;}
          loader.classList.add('is-leaving');root.dataset.siteReady='true';
          hideTimer=window.setTimeout(()=>hidePage(token),160);
        },Math.max(0,(motion?.matches?0:120)-(now()-started)));
      }));
    }
    showOwnPage('initial');
    // Do not put the outgoing page's skeleton over links, downloads or canceled forms.
    window.addEventListener('pagehide',event=>{
      if(event?.persisted)showOwnPage('leave',false);
      else hidePage(visit);
    });
    window.addEventListener('pageshow',event=>{
      if(!event?.persisted)return;
      showOwnPage('restore');
      try{
        const saved=window.localStorage.getItem('docodive_theme');
        choice=['light','dark'].includes(saved)?saved:'light';root.dataset.themeChoice=choice;
        apply(choice);
      }catch(error){/* Keep this page's current choice when storage is unavailable. */}
    });

    // Only cover art gets an image placeholder; photos, logos and PDF pages stay intact.
    document.querySelectorAll('.shelf-card img,.book-card img,.pdf-card img,.book-cover img').forEach(image=>{
      if(image.complete)return;
      const parent=image.parentElement;if(!parent)return;
      parent.classList.add('experience-image-loading');
      const done=()=>parent.classList.remove('experience-image-loading');
      image.addEventListener('load',done,{once:true});image.addEventListener('error',done,{once:true});
    });
  }
  window.DocoDiveLoading={
    fill(container,options={}){
      if(!container)return ()=>{};
      const shell=document.createElement('div');shell.className='skeleton-fragment';shell.setAttribute('aria-hidden','true');
      const count=Math.min(6,Math.max(1,Number(options.rows)||3));
      for(let i=0;i<count;i++){
        const row=document.createElement('div');row.className='skeleton-row';
        const visual=document.createElement('span');visual.className='skeleton-block skeleton-row-icon';
        const lines=document.createElement('span');lines.className='skeleton-row-lines';
        for(let j=0;j<2;j++){const line=document.createElement('span');line.className='skeleton-block skeleton-line';lines.append(line);}
        row.append(visual,lines);shell.append(row);
      }
      container.replaceChildren(shell);container.setAttribute('aria-busy','true');
      return ()=>container.removeAttribute('aria-busy');
    }
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
