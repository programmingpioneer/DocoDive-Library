/* Personal library filters and an advisory, unsaved preferences summary. */
(() => {
  'use strict';
  document.querySelectorAll('[data-reader-library]').forEach(root => {
    const search=root.querySelector('[data-library-search]');
    if (!search) return;
    const order=root.querySelector('[data-library-sort]'),grid=root.querySelector('[data-library-grid]');
    const cards=[...root.querySelectorAll('[data-library-entry]')];
    const result=root.querySelector('[data-library-result]'),empty=root.querySelector('[data-library-empty]');
    function refresh() {
      const term=search.value.trim().toLocaleLowerCase();
      const sorted=[...cards];
      if (order.value==='az'||order.value==='za') sorted.sort((a,b)=>a.dataset.bookTitle.localeCompare(b.dataset.bookTitle,undefined,{sensitivity:'base'})*(order.value==='za'?-1:1));
      grid.append(...sorted);
      let shown=0;
      cards.forEach(card=>{card.hidden=!card.dataset.bookSearch.toLocaleLowerCase().includes(term);if(!card.hidden)shown++;});
      result.textContent=`Showing ${shown} of ${cards.length} ${root.dataset.libraryLabel}`;
      empty.hidden=shown!==0;
    }
    search.addEventListener('input',refresh);
    order.addEventListener('change',refresh);
    root.querySelector('[data-library-clear]').addEventListener('click',()=>{search.value='';refresh();search.focus();});
    refresh();
  });
  const prefs=document.querySelector('[data-reader-preferences]');
  if (!prefs) return;
  const summary=prefs.querySelector('[data-preference-summary]'),unsaved=prefs.querySelector('[data-preference-unsaved]');
  const categories=[...prefs.querySelectorAll('[name=favorite_categories]')];
  const notify=prefs.querySelector('[name=notify_new_books]');
  function refreshSummary(changed=false) {
    const selected=categories.filter(c=>c.checked).length;
    const frequency=prefs.querySelector('[name=email_frequency]:checked')?.value||'weekly';
    const rhythm={daily:'Daily digest',weekly:'Weekly digest',off:'Digests off'}[frequency];
    summary.textContent=`${notify.checked?'New-book updates on':'New-book updates paused'} · ${rhythm} · ${selected?selected+' topic'+(selected===1?'':'s')+' selected':'All categories'}`;
    if(changed)unsaved.hidden=false;
  }
  prefs.addEventListener('change',()=>refreshSummary(true));
  prefs.querySelector('[data-categories-clear]')?.addEventListener('click',()=>{categories.forEach(c=>{c.checked=false;});refreshSummary(true);});
  refreshSummary();
})();
