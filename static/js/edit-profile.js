/* Profile editing keeps the server form, CSRF and upload-progress contracts. */
(() => {
  'use strict';
  const form = document.getElementById('editProfileForm');
  if (!form) return;
  const linksInput = document.getElementById('socialLinksInput');
  const container = document.getElementById('socialLinksContainer');
  const avatarInput = document.getElementById('avatarInput');
  const avatarPreview = document.getElementById('avatarPreview');
  const avatarStatus = document.getElementById('avatarStatus');
  const progressWrap = document.getElementById('avatarProgressWrap');
  const progress = document.getElementById('avatarProgressBar');
  const save = document.getElementById('saveProfileBtn');
  const saveText = save.querySelector('.btn-text');
  const spinner = document.getElementById('saveSpinner');
  const username = document.getElementById('usernameInput');
  const usernameCheck = document.getElementById('usernameCheck');
  const usernameError = document.getElementById('usernameError');
  const platforms = ['Facebook', 'Twitter', 'LinkedIn', 'GitHub', 'Instagram', 'YouTube', 'Website'];
  let rowCount = 0;
  let availabilityRevision = 0;
  let debounceTimer;
  let savedAvatar = avatarPreview.src;

  function validWebURL(value) {
    try { return ['http:', 'https:'].includes(new URL(value).protocol); }
    catch (_) { return false; }
  }
  function field(labelText, control, id) {
    const wrapper = document.createElement('div');
    wrapper.className = 'social-link-field';
    const label = document.createElement('label');
    control.id = id;
    label.htmlFor = id;
    label.textContent = labelText;
    wrapper.append(label, control);
    return wrapper;
  }
  function validateLink(input) {
    const value = input.value.trim();
    input.setCustomValidity(value && !validWebURL(value) ? 'Use a full http:// or https:// address.' : '');
  }
  function addLink(platform = '', value = '', focus = false) {
    const row = document.createElement('div');
    row.className = 'social-link-row';
    const select = document.createElement('select');
    select.className = 'form-select platform-select';
    for (const name of ['', ...platforms]) {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name === 'Twitter' ? 'X (Twitter)' : name || 'Choose platform';
      select.append(option);
    }
    select.value = platforms.includes(platform) ? platform : '';
    const input = document.createElement('input');
    input.type = 'url';
    input.className = 'form-control link-input';
    input.placeholder = 'https://...';
    input.autocomplete = 'url';
    input.value = typeof value === 'string' ? value : '';
    input.addEventListener('input', () => validateLink(input));
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'link-remove-btn';
    remove.setAttribute('aria-label', 'Remove social link');
    remove.title = 'Remove link';
    remove.textContent = '×';
    remove.addEventListener('click', () => { row.remove(); document.getElementById('addSocialLinkBtn').focus(); });
    const id = ++rowCount;
    row.append(field('Platform', select, 'social-platform-' + id), field('Profile or website URL', input, 'social-url-' + id), remove);
    container.append(row);
    validateLink(input);
    if (focus) select.focus();
  }
  let existing = {};
  try {
    existing = JSON.parse(linksInput.value || '{}');
    if (typeof existing === 'string') existing = JSON.parse(existing || '{}');
    if (!existing || typeof existing !== 'object' || Array.isArray(existing)) existing = {};
  } catch (_) { existing = {}; }
  for (const [platform, value] of Object.entries(existing)) addLink(platform, value);
  document.getElementById('addSocialLinkBtn').addEventListener('click', () => addLink('', '', true));

  function showFlash(message, success = false) {
    const flash = document.getElementById('profileFlash');
    const alert = document.createElement('div');
    alert.className = 'edit-profile-flash' + (success ? ' is-success' : '');
    alert.textContent = message;
    flash.replaceChildren(alert);
    if (window.showToast) window.showToast(message, success ? 'success' : 'error');
  }
  avatarInput.addEventListener('change', () => {
    const file = avatarInput.files?.[0];
    avatarInput.setCustomValidity('');
    avatarStatus.textContent = '';
    if (!file) { avatarPreview.src = savedAvatar; return; }
    const error = file.size > 10 * 1024 * 1024 ? 'Choose a photo under 10 MB.' :
      file.type && !['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type) ? 'Choose a JPG, PNG, GIF or WebP photo.' : '';
    avatarInput.setCustomValidity(error);
    if (error) { avatarStatus.textContent = error; return; }
    const reader = new FileReader();
    reader.onload = event => { avatarPreview.src = event.target.result; };
    reader.readAsDataURL(file);
  });

  username.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const revision = ++availabilityRevision;
    const value = username.value.trim();
    usernameCheck.hidden = true;
    usernameError.hidden = true;
    username.removeAttribute('aria-invalid');
    if (!value || value === form.dataset.originalUsername || !username.checkValidity()) return;
    debounceTimer = setTimeout(async () => {
      try {
        const response = await fetch('/api/check-availability?field=username&value=' + encodeURIComponent(value));
        if (!response.ok) throw new Error('unavailable');
        const data = await response.json();
        if (revision !== availabilityRevision) return;
        const taken = data.exists || data.reserved;
        usernameCheck.hidden = false;
        usernameCheck.textContent = taken ? 'Unavailable' : 'Available';
        usernameCheck.dataset.tone = taken ? 'error' : 'success';
        usernameError.hidden = !taken;
        usernameError.textContent = data.message || 'This username is unavailable. Please choose another.';
        if (taken) username.setAttribute('aria-invalid', 'true');
      } catch (_) {
        if (revision !== availabilityRevision) return;
        usernameCheck.hidden = false;
        usernameCheck.textContent = 'Check on save';
        usernameCheck.dataset.tone = '';
      }
    }, 500);
  });

  function setSaving(active) {
    save.disabled = active;
    saveText.textContent = active ? 'Saving…' : 'Save changes';
    spinner.hidden = !active;
    form.setAttribute('aria-busy', String(active));
  }
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (save.disabled) return;
    const links = {};
    for (const row of container.querySelectorAll('.social-link-row')) {
      const platform = row.querySelector('.platform-select');
      const input = row.querySelector('.link-input');
      const value = input.value.trim();
      platform.required = !!value;
      input.required = !!platform.value;
      validateLink(input);
      if (platform.value && value && validWebURL(value)) links[platform.value] = value;
    }
    linksInput.value = JSON.stringify(links);
    if (!form.reportValidity()) return;
    if (linksInput.value.length > 500) { showFlash('Your social links must total 500 characters or fewer. Please shorten or remove a link.'); return; }
    setSaving(true);
    progressWrap.hidden = !avatarInput.files?.length;
    progress.value = 0;
    avatarStatus.textContent = '';
    const xhr = new XMLHttpRequest();
    xhr.open('POST', form.action);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) {
        progress.value = Math.round(event.loaded / event.total * 100);
        progress.textContent = progress.value + '%';
      }
    };
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status !== 200 || !data.success) throw new Error(data.error || 'We could not save your profile. Please try again.');
        if (data.avatar_url) {
          const url = new URL(data.avatar_url, window.location.origin);
          if (['http:', 'https:'].includes(url.protocol)) {
            url.searchParams.set('t', Date.now());
            savedAvatar = url.href;
            avatarPreview.src = savedAvatar;
            const navAvatar = document.getElementById('navbarAvatar');
            if (navAvatar) navAvatar.src = savedAvatar;
          }
        }
        form.dataset.originalUsername = username.value.trim() || form.dataset.originalUsername;
        for (const link of document.querySelectorAll('[data-profile-return]')) {
          link.href = '/user/profile/' + encodeURIComponent(form.dataset.originalUsername);
        }
        showFlash(data.message || 'Profile updated successfully!', true);
        avatarStatus.textContent = 'Profile saved.';
      } catch (error) { showFlash(error instanceof SyntaxError ? 'We could not read the server response. Please refresh and try again.' : error.message); }
      finally { progressWrap.hidden = true; setSaving(false); }
    };
    xhr.onerror = () => { progressWrap.hidden = true; setSaving(false); showFlash('Network error. Please check your connection and try again.'); };
    xhr.send(new FormData(form));
  });
})();
