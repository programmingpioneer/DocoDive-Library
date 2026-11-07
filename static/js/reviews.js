/* Optional linked-book reviews. Shared CSRF transport protects both POST routes. */
(() => {
  'use strict';
  const modalEl=document.getElementById('reviewModal');
  if (!modalEl) return;
  const form=document.getElementById('reviewForm');
  const choices=Array.from(document.querySelectorAll('#reviewRatingStars input'));
  const description=document.querySelector('[data-rating-description]');
  const status=document.getElementById('reviewFormStatus');
  let busy=false;
  const signedIn=()=>document.body.dataset.userLoggedIn==='true';
  const showStatus=message=>{if(status){status.textContent=message;status.hidden=false;}};
  const updateRating=()=>{
    const selected=choices.find(input=>input.checked);
    const value=selected?Number(selected.value):5;
    choices.forEach(input=>input.closest('label').classList.toggle('is-active',Number(input.value)<=value));
    if(description) description.textContent=value+' out of 5 · '+['','Poor','Fair','Good','Very good','Excellent'][value];
  };
  const open=()=>{
    if(!signedIn()){
      if(typeof window.showAuthModal==='function') window.showAuthModal(window.location.href);
      else window.location.href='/user/login';
      return;
    }
    if(window.bootstrap) window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  };
  window.openReviewModal=open;
  document.querySelectorAll('[data-write-review]').forEach(button=>button.addEventListener('click',open));
  choices.forEach(input=>input.addEventListener('change',updateRating));
  updateRating();
  if(!form) return;
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(busy) return;
    if(!signedIn()){showStatus('Your session has ended. Sign in again to post your review.');return;}
    if(!form.reportValidity()) return;
    const book=document.getElementById('reviewBookSelect');
    const comment=document.getElementById('reviewComment');
    const search=document.getElementById('reviewBookSearch');
    const rating=choices.find(input=>input.checked);
    if(!book || (book.value && (!/^\d+$/.test(book.value) || Number(book.value)<1))){showStatus('Choose a valid book, or leave it empty for general feedback.');return;}
    if(search?.value.trim() && !book.value){showStatus('Choose a matching book, or clear the search to post general feedback.');search.focus();return;}
    if(!comment.value.trim()){showStatus('Please write a review.');comment.focus();return;}
    const button=document.getElementById('submitReviewBtn');
    const label=button.querySelector('[data-submit-label]');
    busy=true;button.disabled=true;button.setAttribute('aria-busy','true');label.textContent='Posting…';status.hidden=true;
    let success=false;
    try{
      const body=new URLSearchParams({rating:rating?rating.value:'5',comment:comment.value.trim()});
      const endpoint=book.value?'/book/'+encodeURIComponent(book.value)+'/review':'/api/reviews';
      const response=await fetch(endpoint,{
        method:'POST',headers:{'X-Requested-With':'XMLHttpRequest','Content-Type':'application/x-www-form-urlencoded'},body:body.toString()
      });
      if(response.redirected || response.status===401){showStatus('Your session has ended. Sign in again to post your review.');return;}
      const data=await response.json();
      if(!response.ok || data.success!==true){showStatus(data.error || 'Your review could not be posted. Please try again.');return;}
      success=true;showStatus('Your review has been posted. Refreshing reviews…');
      if(typeof window.showToast==='function') window.showToast('Review posted successfully!','success');
      window.setTimeout(()=>window.location.reload(),700);
    }catch(error){showStatus('Your review could not be posted. Check your connection and try again.');}
    finally{if(!success){busy=false;button.disabled=false;button.removeAttribute('aria-busy');label.textContent='Submit Review';}}
  });
})();
