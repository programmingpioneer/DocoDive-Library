const suggestionsConfig = JSON.parse(document.getElementById('suggestions-config').textContent);
const userLoggedIn = suggestionsConfig.loggedIn;
const currentUserId = suggestionsConfig.userId;
const isModerator = suggestionsConfig.moderator;

async function sendSuggestionVote(url, element) {
  if (!userLoggedIn) { showAuthModal(window.location.href); return; }
  if (element.disabled) return;
  element.disabled = true;
  try {
    const response = await fetch(url, {method:'POST', headers:{'X-Requested-With':'XMLHttpRequest'}});
    if (!response.ok || response.redirected) throw Error('Could not save your vote. Please try again.');
    const data = await response.json();
    if (data.error || typeof data.liked !== 'boolean' || !Number.isFinite(data.count)) throw Error(data.error || 'Could not save your vote.');
    if (data.liked) element.classList.add('liked'); else element.classList.remove('liked');
    element.setAttribute('aria-pressed', String(data.liked));
    element.querySelector('.like-count').textContent = data.count;
  } catch (error) { alert(error.message || 'Connection error. Please try again.'); }
  finally { element.disabled = false; }
}
async function toggleLike(feedbackId, element) { return sendSuggestionVote(`/feedback/${feedbackId}/like`,element); }
  document.querySelectorAll('.reply-toggle').forEach(btn => btn.addEventListener('click', function() {
      document.getElementById('replyForm-' + this.dataset.id).classList.toggle('d-none');
  }));
  document.querySelectorAll('.official-reply-toggle').forEach(btn => btn.addEventListener('click', function() {
      document.getElementById('officialReplyForm-' + this.dataset.id).classList.toggle('d-none');
  }));

  document.querySelectorAll('.submit-reply').forEach(btn => btn.addEventListener('click', async function() {
      const btnEl = this;
      setButtonLoading(btnEl);
      const feedbackId = this.dataset.feedbackId;
      const textarea = document.querySelector(`#replyForm-${feedbackId} textarea`);
      const message = textarea.value.trim();
      if (!message) { resetButton(btnEl); return; }
      try {
          const res = await fetch(`/feedback/${feedbackId}/reply`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest' },
              body: new URLSearchParams({ message: message })
          });
          if (res.ok && !res.redirected) { textarea.value = ''; const container=document.getElementById('replies-'+feedbackId);container.hidden=false;loadReplies(feedbackId); }
          else { alert('Failed to post reply.'); }
      } catch(e) { alert('Network error.'); }
      resetButton(btnEl);
  }));

  document.querySelectorAll('.submit-official-reply').forEach(btn => btn.addEventListener('click', async function() {
      const btnEl = this;
      setButtonLoading(btnEl);
      const feedbackId = this.dataset.feedbackId;
      const textarea = document.querySelector(`#officialReplyForm-${feedbackId} textarea`);
      if (!textarea) { resetButton(btnEl); return; }
      const reply = textarea.value.trim();
      if (!reply) { resetButton(btnEl); return; }
      try {
          const res = await fetch(`/feedback/${feedbackId}/official-reply`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest' },
              body: new URLSearchParams({ reply: reply })
          });
          if (res.ok && !res.redirected) location.reload();
          else { alert('Failed to post reply.'); }
      } catch(e) { alert('Network error.'); }
      resetButton(btnEl);
  }));

  async function loadReplies(feedbackId) {
      const container = document.getElementById('replies-' + feedbackId);
      if (!container) return;
      container.hidden = false;
      document.querySelector(`[data-suggestion-discussion="${feedbackId}"]`)?.setAttribute('aria-expanded','true');
      try {
      const res = await fetch(`/api/feedback/${feedbackId}/replies`);
      if (!res.ok || res.redirected) throw Error('Replies are temporarily unavailable.');
      const replies = await res.json();
      let html = '';
      replies.forEach(r => {
          const likedClass = r.is_liked ? 'liked' : '';
          const avatarHtml = r.avatar_url
              ? `<a href="/user/profile/${encodeURIComponent(r.username)}" class="text-decoration-none flex-shrink-0"><img src="${safeURL(r.avatar_url)}" class="reply-avatar" alt="${escapeHTML(r.username)}"></a>`
              : `<a href="/user/profile/${encodeURIComponent(r.username)}" class="text-decoration-none flex-shrink-0"><div class="reply-avatar-fallback bg-secondary text-white">${escapeHTML((r.username || "?")[0].toUpperCase())}</div></a>`;
          const ownReply = (userLoggedIn && currentUserId == r.user_id) || isModerator;
          html += `
          <div class="reply-item d-flex gap-2 align-items-start" id="reply-${r.id}">
              ${avatarHtml}
              <div class="flex-grow-1 min-width-0">
                  <div class="d-flex justify-content-between gap-2">
                      <div class="min-width-0 reply-meta"><strong><a href="/user/profile/${encodeURIComponent(r.username)}" class="feedback-author-link">${escapeHTML(r.username)}</a></strong> <small class="text-muted">${escapeHTML(r.created_at)}</small></div>
                      ${ownReply ? `
                      <div class="three-dot-menu flex-shrink-0">
                          <button type="button" class="btn btn-sm btn-light rounded-circle" data-bs-toggle="dropdown" aria-label="Reply actions"><i class="bi bi-three-dots"></i></button>
                          <div class="dropdown-menu dropdown-menu-end">
                              <a class="dropdown-item" href="#" onclick="startEditReply(${r.id})"><i class="bi bi-pencil me-2"></i>Edit</a>
                              <a class="dropdown-item text-danger" href="#" onclick="deleteReply(${r.id})"><i class="bi bi-trash me-2"></i>Delete</a>
                          </div>
                      </div>` : ''}
                  </div>
                  <div class="reply-message-container" id="reply-message-container-${r.id}">
                      <span id="reply-message-${r.id}">${escapeHTML(r.message)}</span>
                      <div class="d-none" id="edit-reply-${r.id}">
                          <textarea class="form-control form-control-sm edit-textarea" rows="2" id="edit-reply-textarea-${r.id}">${escapeHTML(r.message)}</textarea>
                          <div class="inline-edit-btns mt-2">
                              <button class="btn btn-sm btn-primary" onclick="saveEditReply(event, ${r.id})"><span class="btn-text">Save</span><span class="book-spinner" style="font-size:0.8rem;"><i class="bi bi-book"></i></span></button>
                              <button class="btn btn-sm btn-outline-secondary" onclick="cancelEditReply(${r.id})">Cancel</button>
                          </div>
                      </div>
                  </div>
                  <button type="button" class="like-btn ${likedClass}" data-reply-id="${r.id}" aria-label="Support this reply" aria-pressed="${r.is_liked ? 'true' : 'false'}" onclick="toggleReplyLike(${r.id}, this)"><svg class="site-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20.8 5.6a5.4 5.4 0 0 0-8.8 1 5.4 5.4 0 0 0-8.8 6.2L12 21l8.8-8.2a5.4 5.4 0 0 0 0-7.2Z"/></svg> <span class="like-count">${r.like_count}</span></button>
              </div>
          </div>`;
      });
      container.innerHTML = html;
      } catch (_) {
        container.textContent = 'Replies are temporarily unavailable.';
        const retry = document.createElement('button'); retry.type='button'; retry.className='suggestion-retry'; retry.textContent='Try again';
        retry.addEventListener('click',()=>loadReplies(feedbackId)); container.append(retry);
      }
  }

async function toggleReplyLike(replyId, element) { return sendSuggestionVote(`/feedback/reply/${replyId}/like`,element); }

  function startEditFeedback(feedbackId) {
      document.getElementById('message-' + feedbackId).classList.add('d-none');
      document.getElementById('edit-message-' + feedbackId).classList.remove('d-none');
  }
  async function saveEditFeedback(event, feedbackId) {
      const btn = event.target.closest('button');
      setButtonLoading(btn);
      const newMsg = document.getElementById('edit-textarea-' + feedbackId).value.trim();
      if (!newMsg) { resetButton(btn); return; }
      try {
          const res = await fetch(`/feedback/${feedbackId}/edit`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest' },
              body: new URLSearchParams({ message: newMsg })
          });
          if (res.ok && !res.redirected) {
              document.getElementById('message-' + feedbackId).textContent = newMsg;
              cancelEditFeedback(feedbackId);
          } else alert('Failed to save.');
      } catch(e) { alert('Network error.'); }
      resetButton(btn);
  }
  function cancelEditFeedback(feedbackId) {
      document.getElementById('message-' + feedbackId).classList.remove('d-none');
      document.getElementById('edit-message-' + feedbackId).classList.add('d-none');
  }

  function startEditOfficialReply(feedbackId) {
      document.getElementById('official-reply-text-' + feedbackId).classList.add('d-none');
      document.getElementById('edit-official-reply-' + feedbackId).classList.remove('d-none');
  }
  async function saveEditOfficialReply(event, feedbackId) {
      const btn = event.target.closest('button');
      setButtonLoading(btn);
      const newReply = document.getElementById('edit-official-textarea-' + feedbackId).value.trim();
      if (!newReply) { resetButton(btn); return; }
      try {
          const res = await fetch(`/feedback/${feedbackId}/official-reply/edit`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest' },
              body: new URLSearchParams({ reply: newReply })
          });
          if (res.ok && !res.redirected) location.reload();
          else alert('Failed to save.');
      } catch(e) { alert('Network error.'); }
      resetButton(btn);
  }
  function cancelEditOfficialReply(feedbackId) {
      document.getElementById('official-reply-text-' + feedbackId).classList.remove('d-none');
      document.getElementById('edit-official-reply-' + feedbackId).classList.add('d-none');
  }

  function startEditReply(replyId) {
      document.getElementById('reply-message-' + replyId).classList.add('d-none');
      document.getElementById('edit-reply-' + replyId).classList.remove('d-none');
  }
  async function saveEditReply(event, replyId) {
      const btn = event.target.closest('button');
      setButtonLoading(btn);
      const newMsg = document.getElementById('edit-reply-textarea-' + replyId).value.trim();
      if (!newMsg) { resetButton(btn); return; }
      try {
          const res = await fetch(`/feedback/reply/${replyId}/edit`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest' },
              body: new URLSearchParams({ message: newMsg })
          });
          if (res.ok && !res.redirected) {
              document.getElementById('reply-message-' + replyId).textContent = newMsg;
              cancelEditReply(replyId);
          } else alert('Failed to save.');
      } catch(e) { alert('Network error.'); }
      resetButton(btn);
  }
  function cancelEditReply(replyId) {
      document.getElementById('reply-message-' + replyId).classList.remove('d-none');
      document.getElementById('edit-reply-' + replyId).classList.add('d-none');
  }

async function deleteSuggestionItem(url, question) {
  if (!await toast.confirm(question, {title:'Confirm deletion',confirmText:'Delete',type:'danger'})) return;
  try {
    const response=await fetch(url,{method:'POST',headers:{'X-Requested-With':'XMLHttpRequest'}});
    if (!response.ok || response.redirected) throw Error('Could not delete this item. Please try again.');
    location.reload();
  } catch (error) { alert(error.message || 'Connection error. Please try again.'); }
}
async function deleteFeedback(id) { return deleteSuggestionItem(`/feedback/${id}/delete`,'Delete this suggestion?'); }
async function deleteOfficialReply(id) { return deleteSuggestionItem(`/feedback/${id}/official-reply/delete`,'Remove official reply?'); }
async function deleteReply(id) { return deleteSuggestionItem(`/feedback/reply/${id}/delete`,'Delete this reply?'); }

  document.addEventListener('DOMContentLoaded', () => {
      const board = document.querySelector('[data-suggestion-board]');
      if (!board) return;
      const cards = [...board.querySelectorAll('[data-suggestion-card]')];
      const search = board.querySelector('[data-suggestion-search]');
      let filter = 'all';
      function filterIdeas() {
        const query = search.value.trim().toLowerCase(); let visible = 0;
        for (const card of cards) {
          card.hidden = !((filter === 'all' || card.dataset.answered === 'true') && card.textContent.toLowerCase().includes(query));
          if (!card.hidden) visible++;
        }
        board.querySelector('[data-suggestion-count]').textContent = `Showing ${visible} of ${cards.length} suggestions on this page`;
        board.querySelector('[data-suggestion-empty]').hidden = visible !== 0;
        for (const tab of board.querySelectorAll('[data-suggestion-filter]')) tab.setAttribute('aria-pressed',String(tab.dataset.suggestionFilter === filter));
      }
      search.addEventListener('input',filterIdeas);
      board.addEventListener('click', async event => {
        const tab = event.target.closest('[data-suggestion-filter]');
        if (tab) { filter = tab.dataset.suggestionFilter; filterIdeas(); }
        const discussion = event.target.closest('[data-suggestion-discussion]');
        if (discussion) {
          const container = document.getElementById('replies-'+discussion.dataset.suggestionDiscussion);
          const open = discussion.getAttribute('aria-expanded') !== 'true';
          discussion.setAttribute('aria-expanded',String(open)); container.hidden = !open;
          if (open && !container.dataset.loaded) { await loadReplies(discussion.dataset.suggestionDiscussion); container.dataset.loaded='true'; }
        }
      });
      filterIdeas();
  });
