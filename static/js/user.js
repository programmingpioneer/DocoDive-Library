/* Small shared helpers, independent of third-party animation libraries. */
window.escapeHTML = value => String(value == null ? '' : value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
window.safeURL = value => { try { const url=new URL(String(value||''),location.href); return ['https:','http:'].includes(url.protocol) ? escapeHTML(url.href) : ''; } catch (_) { return ''; } };
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('main img').forEach(image=>{image.decoding='async';if(!image.hasAttribute('loading')&&image.getBoundingClientRect().top>innerHeight)image.loading='lazy';});
  document.querySelectorAll('.ab-toolbar input[name=q]').forEach(e=>e.setAttribute('aria-label','Search books'));
  document.querySelectorAll('.ab-toolbar select[name=sort]').forEach(e=>e.setAttribute('aria-label','Sort books'));
});

// One preview for Home, the books catalogue and learning hubs.
let sharedPreviewRevision = 0;
const sharedPreviewDrafts = new Map();
const sharedPreviewScrollControllers = new WeakMap();
document.addEventListener('click',event=>{
  const button=event.target.closest('.shared-preview-trigger');
  if(button){event.preventDefault();window.openBookModal(button.dataset.bookId,button);}
});

function sharedPreviewScrollController(modal, body) {
  if (sharedPreviewScrollControllers.has(modal)) return sharedPreviewScrollControllers.get(modal);
  const controls = modal.querySelector('.shared-preview-scroll-controls');
  if (!controls) return null;
  const up = controls.querySelector('[data-preview-scroll="up"]');
  const down = controls.querySelector('[data-preview-scroll="down"]');
  const refresh = () => {
    const maximum = Math.max(0, body.scrollHeight - body.clientHeight);
    controls.hidden = maximum <= 1;
    up.disabled = maximum <= 1 || body.scrollTop <= 1;
    down.disabled = maximum <= 1 || body.scrollTop >= maximum - 1;
  };
  const step = direction => {
    const maximum = Math.max(0, body.scrollHeight - body.clientHeight);
    body.scrollTo({top:Math.max(0, Math.min(maximum, body.scrollTop + direction * Math.max(160, body.clientHeight * .7))),
      behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
  };
  up.addEventListener('click', () => step(-1));
  down.addEventListener('click', () => step(1));
  body.addEventListener('scroll', refresh, {passive:true});
  body.addEventListener('load', refresh, true);
  modal.addEventListener('shown.bs.modal', refresh);
  window.addEventListener('resize', refresh);
  const observer = window.ResizeObserver ? new window.ResizeObserver(refresh) : null;
  observer?.observe(body);
  let content;
  const controller = {opener:null, refresh() {
    if (content !== body.firstElementChild) {
      if (content) observer?.unobserve(content);
      content = body.firstElementChild;
      if (content) observer?.observe(content);
    }
    refresh();
  }};
  modal.addEventListener('hidden.bs.modal', () => {
    if (controller.opener?.isConnected) controller.opener.focus({preventScroll:true});
  });
  sharedPreviewScrollControllers.set(modal, controller);
  return controller;
}

function renderSharedBookPreview(body, book, id, requestRevision) {
  const make = (tag, className, text) => {
    const element = document.createElement(tag);
    element.className = className || '';
    if (text != null) element.textContent = text;
    return element;
  };
  // Only repository-owned SVG paths enter this markup; API text uses textContent.
  const glyph = name => {
    const paths = {
      download:'<path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4"/>',
      read:'<path d="M12 5v15M3 4.5C6 3.5 9 4 12 5c3-1 6-1.5 9-.5v15c-3-1-6-.5-9 .5-3-1-6-1.5-9-.5Z"/>',
      qr:'<path d="M3 3h6v6H3ZM15 3h6v6h-6ZM3 15h6v6H3ZM15 15h2v2h-2ZM19 15h2v6h-6v-2"/>',
      share:'<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m9 10 6-4m-6 8 6 4"/>',
      favorite:'<path d="M20.8 5.6a5.4 5.4 0 0 0-8.8 1 5.4 5.4 0 0 0-8.8 6.2L12 21l8.8-8.2a5.4 5.4 0 0 0 0-7.2Z"/>',
      star:'<path d="m12 3 2.8 5.7 6.3.9-4.6 4.5 1.1 6.3-5.6-3-5.6 3 1.1-6.3-4.6-4.5 6.3-.9Z"/>',
      lock:'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3"/>'
    };
    const icon = make('span','shared-preview-glyph');
    icon.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'+(paths[name]||paths.read)+'</svg>';
    return icon;
  };
  const labelAction = (element,name,label) => {element.replaceChildren(glyph(name),make('span','',label));return element;};
  const bookPath = '/book/' + encodeURIComponent(book.slug || id) + '/' + id;
  const current = () => requestRevision === sharedPreviewRevision;
  const csrfHeaders = () => ({'X-Requested-With':'XMLHttpRequest',
    'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]')?.content || ''});
  const gate = event => {
    if (!current()) { event.preventDefault(); return false; }
    if (book.is_logged_in) return true;
    event.preventDefault();
    if (window.showAuthModal) {
      const showAuth = () => { if (current()) window.showAuthModal(location.href); };
      const modal = document.getElementById('shared-book-preview');
      const preview = modal && window.bootstrap?.Modal.getInstance?.(modal);
      if (preview && modal.classList.contains('show')) {
        modal.addEventListener('hidden.bs.modal', showAuth, {once:true});
        preview.hide();
      } else showAuth();
    } else location.href = '/user/login?next=' + encodeURIComponent(location.pathname + location.search);
    return false;
  };
  const layout = make('div', 'shared-preview-layout');
  const cover = make('div', 'shared-preview-cover');
  let coverURL = '';
  try {
    if (book.image_url && book.image_url !== 'None') {
      const url = new URL(String(book.image_url), location.href);
      if (['http:', 'https:'].includes(url.protocol)) coverURL = url.href;
    }
  } catch (_) {}
  if (coverURL) {
    cover.className += ' shared-preview-cover-image';
    const image = make('img'); image.src = coverURL; image.alt = 'Cover of ' + (book.title || 'this book');
    image.decoding = 'async'; cover.append(image);
  } else {
    const placeholder=make('span','shared-preview-monogram',(book.title || 'Book').slice(0,2).toUpperCase());cover.append(placeholder);
    cover.append(make('span', 'shared-preview-cover-title', book.title || 'Book'));
  }
  const content = make('div', 'shared-preview-content');
  const metadata = make('div', 'shared-preview-meta');
  if (book.level) metadata.append(make('span', 'shared-preview-badge shared-preview-category', book.level));
  if (book.language) metadata.append(make('span', 'shared-preview-badge shared-preview-language', book.language));
  const author = make('p', 'shared-preview-author', 'by ');
  author.append(make('strong', '', book.author || 'Unknown author'));
  content.append(make('h3', 'shared-preview-book-title', book.title || 'Untitled book'), author, metadata,
    make('p', 'shared-preview-description', book.description || 'No description available.'));
  const actions = make('div', 'shared-preview-actions');
  const actionLink = (name, label, path, className) => {
    const link = make('a', 'btn rounded-pill shared-preview-' + name + ' ' + className, label);
    labelAction(link,name,label);
    link.href = path; link.onclick = event => gate(event); actions.append(link); return link;
  };
  actionLink('download', 'Download', '/book/' + id + '/download', 'btn-primary');
  const read = actionLink('read', 'Read Online', '/book/' + id + '/read', 'btn-outline-primary');
  read.target = '_blank'; read.rel = 'noopener';
  const qr = actionLink('qr', 'QR Code', '/book/' + id + '/qr', 'btn-outline-secondary');
  qr.target = '_blank'; qr.rel = 'noopener';
  const feedback = make('p', 'shared-preview-feedback'); feedback.role = 'status';
  const confirmedMutation = async (response, event, failureMessage) => {
    if (!current()) return false;
    let loginRedirect = false;
    try { loginRedirect = response.redirected && new URL(response.url, location.href).pathname === '/user/login'; } catch (_) {}
    if (response.status === 401 || loginRedirect) {
      book.is_logged_in = false;
      feedback.textContent = 'Your session expired. Sign in to try again.';
      gate(event); return false;
    }
    if (!response.ok || response.redirected) throw Error(failureMessage);
    let result;
    try { result = await response.json(); } catch (_) { throw Error(failureMessage); }
    if (!current()) return false;
    if (!result || result.success !== true) throw Error(failureMessage);
    return true;
  };
  const share = make('button', 'btn btn-outline-secondary rounded-pill shared-preview-share', 'Share');
  labelAction(share,'share','Share');
  share.type = 'button';
  share.onclick = async event => {
    if (!gate(event)) return;
    const url = new URL(bookPath, location.href).href;
    try {
      if (navigator.share) await navigator.share({title:book.title || 'Book', url});
      else if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        if (current()) feedback.textContent = 'Book link copied.';
      } else if (current()) feedback.textContent = 'Open book details to copy the link from your address bar.';
    } catch (error) {
      if (current() && error.name !== 'AbortError') feedback.textContent = 'Unable to share. Open book details to copy the link.';
    }
  };
  actions.append(share);
  if (book.is_logged_in) {
    let favorited = Boolean(book.is_favorite);
    const favorite = make('button', 'btn btn-outline-secondary rounded-pill shared-preview-favorite', favorited ? 'Favorited' : 'Favorite');
    labelAction(favorite,'favorite',favorited ? 'Favorited' : 'Favorite');
    favorite.type = 'button'; favorite.ariaPressed = String(favorited);
    favorite.onclick = async event => {
      event.preventDefault(); favorite.disabled = true;
      try {
        const response = await fetch('/user/favorite/' + id, {method:'POST', headers:csrfHeaders()});
        if (!await confirmedMutation(response, event, 'Unable to update your favorites. Please try again.')) return;
        favorited = !favorited; favorite.ariaPressed = String(favorited);
        labelAction(favorite,'favorite',favorited ? 'Favorited' : 'Favorite');
        feedback.textContent = favorited ? 'Saved to your favorites.' : 'Removed from your favorites.';
      } catch (error) { if (current()) feedback.textContent = error.message; }
      finally { if (current()) favorite.disabled = false; }
    };
    actions.append(favorite);
  }
  const details = make('a', 'shared-preview-details', 'View book details →'); details.href = bookPath;
  content.append(actions, details, feedback);
  const reviews = Array.isArray(book.reviews) ? book.reviews : [];
  const reviewSection = make('section', 'shared-preview-reviews');
  const reviewHeading = make('h4', 'shared-preview-review-heading');
  reviewHeading.append(glyph('star'),make('span','','Reviews' + (reviews.length ? ' (' + reviews.length + ')' : '')));
  reviewSection.append(reviewHeading);
  const reviewList = make('div', 'shared-preview-review-list');
  if (reviews.length) {
    const review = reviews[0], rating = Number(review.rating);
    const reviewCard = make('div', 'shared-preview-review-card');
    reviewCard.append(make('p', 'shared-preview-review-byline',
      (review.username || 'A reader') + (Number.isFinite(rating) && rating >= 1 && rating <= 5 ? ' · ' + rating + '/5' : '')),
      make('p', 'shared-preview-review-comment', review.comment || ''));
    reviewList.append(reviewCard);
    if (reviews.length > 1) {
      const allReviews = make('a', 'shared-preview-details', 'View all ' + reviews.length + ' reviews →');
      allReviews.href = bookPath + '#reviews'; reviewList.append(allReviews);
    }
  } else reviewList.append(make('p', 'shared-preview-review-comment', 'No reviews yet. Be the first to share your thoughts.'));
  if (book.is_logged_in) {
    const form = make('form', 'shared-preview-review-form');
    form.dataset.ajax = 'true';
    const ratingLabel = make('label', 'form-label small', 'Rating');
    const rating = make('select', 'form-select shared-preview-rating'); rating.name = 'rating'; rating.required = true;
    const ratingNames = ['Terrible','Poor','Average','Good','Excellent'];
    for (let score = 5; score >= 1; score--) { const option = make('option', '', score + ' - ' + ratingNames[score-1]); option.value = String(score); rating.append(option); }
    const draft = sharedPreviewDrafts.get(id);
    rating.value = draft?.rating || '5'; ratingLabel.append(rating);
    const commentLabel = make('label', 'form-label small', 'Comment');
    const comment = make('textarea', 'form-control shared-preview-comment'); comment.name = 'comment'; comment.rows = 2;
    comment.maxLength = 5000; comment.placeholder = 'What helped you, and who would you recommend this book to?';
    comment.value = draft?.comment || '';
    const saveDraft = () => sharedPreviewDrafts.set(id, {rating:rating.value, comment:comment.value});
    comment.addEventListener('input', saveDraft); rating.addEventListener('change', saveDraft);
    commentLabel.append(comment);
    const submit = make('button', 'btn btn-primary rounded-pill', 'Submit'); submit.type = 'submit';
    form.append(ratingLabel, commentLabel, submit);
    form.onsubmit = async event => {
      event.preventDefault(); if (!gate(event)) return; submit.disabled = true;
      const submittedRating = rating.value, submittedComment = comment.value || '';
      saveDraft();
      try {
        const response = await fetch('/book/' + id + '/review', {method:'POST', headers:csrfHeaders(),
          body:new URLSearchParams({rating:submittedRating, comment:submittedComment})});
        if (!await confirmedMutation(response, event, 'Unable to submit your review. Please try again.')) return;
        if (current()) {
          feedback.textContent = 'Review submitted. Open book details to see all reviews.';
          if (comment.value === submittedComment && rating.value === submittedRating) {
            comment.value = ''; sharedPreviewDrafts.delete(id);
          } else saveDraft();
        }
      } catch (error) { if (current()) feedback.textContent = error.message; }
      finally { if (current()) submit.disabled = false; }
    };
    reviewSection.append(form);
  } else {
    const signIn = make('button', 'btn btn-outline-primary rounded-pill btn-sm', 'Sign in to review or save this book');
    labelAction(signIn,'lock','Sign in to review or save this book');
    signIn.type = 'button'; signIn.onclick = gate; reviewSection.append(signIn);
  }
  reviewSection.append(reviewList);
  content.append(reviewSection); layout.append(cover, content); body.append(layout);
}
window.openBookModal = async function (id, opener) {
  if (!/^\d+$/.test(String(id))) return;
  if (!window.bootstrap) { location.href='/book/'+id; return; }
  let modal=document.getElementById('shared-book-preview');
  if (!modal) {
    modal=document.createElement('div'); modal.id='shared-book-preview';modal.className='modal fade';modal.tabIndex=-1;
    modal.setAttribute('aria-labelledby','shared-preview-title');
    modal.innerHTML=`<div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable"><div class="modal-content">
      <div class="modal-header"><h2 class="modal-title h5" id="shared-preview-title">Book Details</h2>
      <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close book preview"></button></div>
      <div class="modal-body" id="shared-preview-body" tabindex="0" role="region" aria-label="Book preview content"></div>
      <div class="shared-preview-scroll-controls" role="group" aria-label="Scroll book preview" hidden>
        <button type="button" class="shared-preview-scroll-button" data-preview-scroll="up" aria-controls="shared-preview-body" aria-label="Scroll preview up" title="Scroll preview up" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6"/></svg></button>
        <button type="button" class="shared-preview-scroll-button" data-preview-scroll="down" aria-controls="shared-preview-body" aria-label="Scroll preview down" title="Scroll preview down" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
      </div>
      </div></div>`;
    document.body.append(modal);
  }
  const requestRevision=++sharedPreviewRevision;
  const body=modal.querySelector('.modal-body');
  const scrollController=sharedPreviewScrollController(modal,body);
  if(scrollController)scrollController.opener=opener||document.activeElement;
  body.scrollTop=0; body.ariaBusy='true';
  const stopLoading=window.DocoDiveLoading?window.DocoDiveLoading.fill(body,{rows:3}):()=>{};
  if(!window.DocoDiveLoading)body.textContent='Loading book…';
  bootstrap.Modal.getOrCreateInstance(modal).show();
  modal.dataset.bookId=String(id);
  try {
    const response=await fetch('/api/book/'+id);
    if(!response.ok)throw Error('Unable to load this book.');
    const book=await response.json();
    if(requestRevision!==sharedPreviewRevision)return;
    body.replaceChildren();
    renderSharedBookPreview(body, book, String(id), requestRevision);
  } catch(error) { if(requestRevision===sharedPreviewRevision)body.textContent=error.message||'Unable to load this book.'; }
  finally{if(requestRevision===sharedPreviewRevision){stopLoading();body.ariaBusy='false';scrollController?.refresh();}}
};

document.addEventListener('DOMContentLoaded',()=>{
  if(!document.body.hasAttribute('data-public-site'))return;
  const banner=document.createElement('div');banner.className='connection-banner';banner.role='status';banner.hidden=navigator.onLine;banner.textContent='You are offline. Reconnect before submitting changes.';document.body.prepend(banner);
  window.addEventListener('online',()=>{banner.hidden=true;});window.addEventListener('offline',()=>{banner.hidden=false;});
  document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.matches('form[data-confirm]')||form.dataset.confirmed)return;
    event.preventDefault();
    if(!navigator.onLine){window.toast?.error('You are offline. Reconnect and retry.');return;}
    const approved=window.toast?await toast.confirm(form.dataset.confirm,{type:'danger'}):window.confirm(form.dataset.confirm);
    if(approved){form.dataset.confirmed='true';form.requestSubmit(event.submitter);}
  });
});
