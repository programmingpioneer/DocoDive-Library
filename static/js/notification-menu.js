/* Safe, steady notification preview shared by the reader navigation and inbox. */
(() => {
  'use strict';
  function setup(){
    const list=document.getElementById('notifList');if(!list)return;
    const status=document.getElementById('notifStatus'),badge=document.getElementById('notifBadge'),mark=document.getElementById('notifMarkAll');
    let revision=0,readBusy=false,unread=0;
    const kinds={approval:['Book approved','Your book has been approved.'],rejection:['Book update','Your book has been rejected.'],reply:['New reply','Someone replied to your comment.'],general_comment:['New comment','There is a new comment on your book.'],new_book:['New in the library','A new book is ready to explore.']};
    function make(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
    function symbol(kind){const e=make('span','notif-dd-fallback notif-symbol-'+kind);const template=document.getElementById('notif-symbol-'+kind)||document.getElementById('notif-symbol-default');if(template)e.append(template.content.cloneNode(true));return e;}
    function count(value){unread=Number.isFinite(Number(value))?Math.max(0,Number(value)):0;if(badge){badge.textContent=String(unread);badge.style.display=unread?'inline-flex':'none';}if(mark)mark.disabled=readBusy||unread===0;}
    function showStatus(message,retry=false){if(!status)return;status.replaceChildren(make('span','',message));status.hidden=false;if(retry){const button=make('button','notif-retry','Retry');button.type='button';button.addEventListener('click',()=>window.updateNotifications());status.append(button);}}
    window.timeAgo=function(value){let raw=String(value||'').trim();if(/^\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?$/.test(raw))raw=raw.replace(' ','T')+'Z';const date=new Date(raw);if(!Number.isFinite(date.getTime()))return 'Recently';const minutes=Math.max(0,Math.floor((Date.now()-date.getTime())/60000));return minutes>=1440?Math.floor(minutes/1440)+'d ago':minutes>=60?Math.floor(minutes/60)+'h ago':minutes?minutes+'m ago':'Just now';};
    window.goToNotif=url=>{window.location=url;};
    window.updateNotifications=async function(){
      const current=++revision;list.setAttribute('aria-busy','true');
      if(!list.dataset.loaded){if(window.DocoDiveLoading)window.DocoDiveLoading.fill(list,{rows:3});else list.replaceChildren(make('p','notif-empty','Loading your updates…'));}
      try{
        if(!navigator.onLine)throw Error('You are offline. Reconnect to load updates.');
        const response=await fetch('/api/notifications');
        if(current!==revision)return;
        if(response.status===401||response.redirected){const link=make('a','notif-sign-in','Sign in to view notifications');link.href='/user/login';list.replaceChildren(link);count(0);return;}
        if(!response.ok)throw Error('Your updates could not be refreshed.');
        const notifications=await response.json();if(current!==revision)return;
        if(!Array.isArray(notifications))throw Error('Your updates could not be refreshed.');
        const rows=[];
        for(const n of notifications){
          if(!n||typeof n!=='object')continue;
          const kind=Object.hasOwn(kinds,n.type)?n.type:'default';
          const link=make('a','notif-dd-row dropdown-item '+(!n.is_read?'is-unread':''));
          try{const url=new URL(n.link||'/user/notifications',location.href);link.href=url.origin===location.origin?url.href:'/user/notifications';}catch(_){link.href='/user/notifications';}
          const visual=make('div','notif-dd-visual');const fallback=()=>visual.replaceChildren(symbol(kind));
          try{if(!n.book_cover)throw Error('No cover');const url=new URL(n.book_cover,location.href);if(!['https:','http:'].includes(url.protocol))throw Error('Invalid cover');const image=make('img','notif-dd-cover');image.src=url.href;image.alt='';image.width=40;image.height=54;image.loading='lazy';image.addEventListener('error',fallback);visual.append(image);}catch(_){fallback();}
          const body=make('div','notif-dd-body'),head=make('div','notif-dd-head');
          head.append(make('span','notif-dd-name',n.actor_name||'DocoDive'),make('span','notif-dd-time',window.timeAgo(n.created_at)));
          body.append(head,make('div','notif-dd-title',n.book_title||kinds[kind]?.[0]||'Library update'),make('div','notif-dd-status',n.message||kinds[kind]?.[1]||'You have a new update.'));
          link.append(visual,body);if(!n.is_read){const dot=make('span','notif-dd-dot');dot.setAttribute('aria-label','Unread');link.append(dot);}rows.push(link);
        }
        list.replaceChildren(...(rows.length?rows:[make('p','notif-empty','All quiet here. New updates will appear when there is something to share.')]));list.dataset.loaded='true';if(status)status.hidden=true;
        const counts=await fetch('/api/notifications/unread-count');
        if(!counts.ok||counts.redirected)return;const data=await counts.json();if(current===revision)count(data.count);
      }catch(error){if(current===revision){if(!list.dataset.loaded)list.replaceChildren(make('p','notif-empty','Your updates are unavailable right now.'));showStatus(error.message||'Unable to load notifications.',true);}}
      finally{if(current===revision)list.setAttribute('aria-busy','false');}
    };
    window.markAllRead=async function(){
      if(readBusy)return;readBusy=true;if(mark)mark.disabled=true;
      try{
        if(!navigator.onLine)throw Error('Reconnect before marking updates read.');
        const response=await fetch('/api/notifications/read-all',{method:'POST'});
        if(!response.ok||response.redirected)throw Error('Unable to mark updates read. Please try again.');
        const result=await response.json();if(result.success!==true)throw Error('The update was not confirmed. Please try again.');
        count(0);document.dispatchEvent(new CustomEvent('docodive:notifications-read-all'));
        await window.updateNotifications();window.toast?.success('Notifications marked read.');
      }
      catch(error){showStatus(error.message);window.toast?.error(error.message);}
      finally{readBusy=false;if(mark)mark.disabled=unread===0;}
    };
    window.updateNotifications();
    setInterval(()=>{if(!document.hidden)window.updateNotifications();},30000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
