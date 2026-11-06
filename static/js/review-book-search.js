/* Optional book association. Native select remains the no-script fallback. */
(() => {
  'use strict';
  const input=document.getElementById('reviewBookSearch'),select=document.getElementById('reviewBookSelect');
  const results=document.getElementById('reviewBookResults'),status=document.getElementById('reviewBookSearchStatus');
  const native=document.querySelector('[data-review-book-native]'),enhanced=document.querySelector('[data-review-book-search]');
  const clear=document.querySelector('[data-review-book-clear]'),chip=document.querySelector('[data-review-book-selection]'),title=document.querySelector('[data-review-book-title]');
  if(!input||!select||!results||!status||!native||!enhanced||!clear||!chip||!title)return;
  let items=[],active=-1,revision=0,timer,controller;
  const seed=Array.from(select.options).filter(o=>o.value).map(o=>({id:o.value,title:o.textContent,author:''}));
  const valid=b=>b&&/^[1-9]\d{0,18}$/.test(String(b.id))&&typeof b.title==='string'&&b.title.trim();
  function close(invalidate=true){
    results.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');active=-1;
    if(invalidate){
      revision++;window.clearTimeout(timer);controller?.abort();
      if(status.textContent==='Searching books…')status.textContent='Search paused. Return to the field to search again.';
    }
  }
  function highlight(index){
    active=index;
    Array.from(results.children).forEach((option,i)=>option.setAttribute('aria-selected',String(i===index)));
    if(index>=0&&results.children[index]){input.setAttribute('aria-activedescendant',results.children[index].id);results.children[index].scrollIntoView({block:'nearest'});}
  }
  function choose(book){
    const id=String(book.id);
    if(!Array.from(select.options).some(o=>o.value===id)){
      const option=document.createElement('option');option.value=id;option.textContent=book.title;select.append(option);
    }
    select.value=id;input.value=book.title;title.textContent=book.title;chip.hidden=false;clear.hidden=false;
    status.textContent='Book selected. Your review will link to this title.';close();
  }
  function paint(books,hasMore=false){
    items=books.filter(valid).slice(0,20);active=-1;results.replaceChildren();input.removeAttribute('aria-activedescendant');
    items.forEach((book,i)=>{
      const option=document.createElement('button');option.type='button';option.id='review-book-option-'+i;option.className='review-book-option';option.tabIndex=-1;
      option.setAttribute('role','option');option.setAttribute('aria-selected','false');
      const name=document.createElement('strong');name.textContent=book.title;option.append(name);
      if(book.author){const author=document.createElement('small');author.textContent=String(book.author);option.append(author);}
      option.addEventListener('pointerdown',event=>event.preventDefault());
      option.addEventListener('click',()=>choose(book));option.addEventListener('pointermove',()=>highlight(i));
      results.append(option);
    });
    results.hidden=items.length===0;input.setAttribute('aria-expanded',String(items.length>0));
    status.textContent=items.length?items.length+' matching '+(items.length===1?'book':'books')+'. Use the arrow keys and Enter to choose.':'No matching books. Clear the search to leave the book optional.';
    if(hasMore&&items.length)status.textContent+=' More books match; refine the title or author.';
  }
  async function lookup(query,token){
    controller=typeof AbortController==='function'?new AbortController():null;
    try{
      const response=await fetch('/api/review-books?'+new URLSearchParams({q:query}),{headers:{Accept:'application/json'},...(controller?{signal:controller.signal}:{})});
      if(!response.ok||response.redirected)throw Error('Unavailable');
      const data=await response.json();if(token!==revision)return;
      if(!Array.isArray(data.books))throw Error('Invalid results');paint(data.books,data.has_more===true);
    }catch(error){
      if(token!==revision)return;close(false);status.textContent='Book search is unavailable. Try again, or clear the search to post general feedback.';
    }
  }
  function search(){
    const token=++revision;window.clearTimeout(timer);controller?.abort();
    select.value='';chip.hidden=true;clear.hidden=!input.value;const query=input.value.trim().slice(0,100);
    if(!query){paint(seed);return;}
    items=[];active=-1;results.replaceChildren();results.hidden=false;input.setAttribute('aria-expanded','true');input.removeAttribute('aria-activedescendant');status.textContent='Searching books…';
    timer=window.setTimeout(()=>lookup(query,token),180);
  }
  function resume(){
    if(!results.hidden||select.value)return;
    if(items.length)paint(items);else search();
  }
  input.addEventListener('input',search);
  input.addEventListener('click',()=>{if(!input.value.trim())paint(seed);else resume();});
  input.addEventListener('focus',()=>{if(input.value.trim())resume();});
  input.addEventListener('keydown',event=>{
    if(event.key==='Escape'){
      // First Escape closes the picker; another Escape can close the modal.
      if(!results.hidden){event.preventDefault();event.stopPropagation();}
      close();return;
    }
    if(event.key==='Tab'){close();return;}
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();if(results.hidden){if(items.length)paint(items);else if(!input.value.trim())paint(seed);else resume();}
      if(items.length)highlight(event.key==='ArrowDown'?(active+1)%items.length:(active<0?items.length-1:(active+items.length-1)%items.length));
      return;
    }
    if(event.key==='Enter'&&!results.hidden){event.preventDefault();if(active>=0)choose(items[active]);else if(items.length===1)choose(items[0]);}
  });
  clear.addEventListener('click',()=>{select.value='';input.value='';chip.hidden=true;clear.hidden=true;status.textContent='No book selected. Your review will be general DocoDive feedback.';close();input.focus();});
  document.addEventListener('pointerdown',event=>{if(!enhanced.contains(event.target))close();});
  document.getElementById('reviewModal')?.addEventListener('hidden.bs.modal',()=>close());
  native.hidden=true;enhanced.hidden=false;clear.hidden=!input.value;chip.hidden=!select.value;
  const selected=seed.find(book=>book.id===select.value);if(selected)choose(selected);
})();
