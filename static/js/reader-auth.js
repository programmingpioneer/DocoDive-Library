/* Standalone reader forms. Normal links and native POSTs also work without JS. */
(() => {
  'use strict';
  const root = document.querySelector('[data-reader-auth]');
  if (!root) return;
  const tabs = [...document.querySelectorAll('[data-auth-tab]')];
  const titles = {
    login: ['Welcome back.', 'Sign in to pick up where you left off.', 'Sign in · DocoDive'],
    signup: ['Your next chapter awaits.', 'Create your free account and start exploring.', 'Create an account · DocoDive']
  };
  function activate(mode, focus = false) {
    if (!titles[mode]) return;
    root.dataset.authMode = mode;
    tabs.forEach(tab => {
      const selected = tab.dataset.authTab === mode;
      tab.setAttribute('aria-selected', String(selected));
      tab.setAttribute('tabindex', selected ? '0' : '-1');
      document.getElementById(`${tab.dataset.authTab}-tab`).hidden = !selected;
      if (selected && focus) tab.focus();
    });
    document.getElementById('reader-auth-title').textContent = titles[mode][0];
    document.getElementById('reader-auth-description').textContent = titles[mode][1];
    document.title = titles[mode][2];
  }
  function ordinaryClick(event) {
    return !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && (!event.button || event.button === 0);
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', event => {
      if (!ordinaryClick(event)) return;
      event.preventDefault();
      activate(tab.dataset.authTab);
    });
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      activate(tabs[next].dataset.authTab, true);
    });
  });
  document.querySelectorAll('[data-auth-switch]').forEach(link => {
    link.addEventListener('click', event => {
      if (!ordinaryClick(event)) return;
      event.preventDefault();
      activate(link.dataset.authSwitch, true);
    });
  });
  document.querySelectorAll('[data-auth-password]').forEach(button => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.authPassword);
      const visible = input.type === 'password';
      input.type = visible ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(visible));
      button.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
      button.querySelector('[data-eye-open]').hidden = visible;
      button.querySelector('[data-eye-closed]').hidden = !visible;
    });
  });

  // Availability is advisory. Native validation and server checks decide acceptance.
  document.querySelectorAll('[data-availability]').forEach(input => {
    const feedback = document.getElementById(`${input.id}-feedback`);
    let timer, controller, revision = 0, lastChecked = '';
    function reset() {
      clearTimeout(timer);
      if (controller) controller.abort();
      revision += 1;
      lastChecked = '';
      feedback.textContent = '';
      feedback.dataset.state = '';
      feedback.setAttribute('aria-busy', 'false');
    }
    async function check() {
      const value = input.value.trim();
      const field = input.dataset.availability;
      if (!value || value === lastChecked) return;
      if (field === 'username' && !/^[a-zA-Z0-9]{3,20}$/.test(value)) {
        feedback.textContent = 'Use 3–20 letters and numbers, without spaces.';
        feedback.dataset.state = 'unavailable';
        return;
      }
      if (field === 'email' && !/^\S+@\S+\.\S+$/.test(value)) return;
      lastChecked = value;
      const current = revision;
      controller = new AbortController();
      feedback.setAttribute('aria-busy', 'true');
      try {
        const response = await fetch(`/api/check-availability?field=${field}&value=${encodeURIComponent(value)}`, {signal: controller.signal});
        if (!response.ok || response.redirected) throw new Error('Availability check unavailable');
        const data = await response.json();
        if (current !== revision || input.value.trim() !== value) return;
        if (data.error || typeof data.exists !== 'boolean') return;
        const taken = data.exists || data.reserved || data.format_error || data.simple;
        feedback.textContent = data.message || (taken ? 'Please choose another value.' : 'Available.');
        feedback.dataset.state = taken ? 'unavailable' : 'available';
      } catch (_) {
        if (current === revision) {
          feedback.textContent = '';
          feedback.dataset.state = '';
          lastChecked = '';
        }
      } finally {
        if (current === revision) feedback.setAttribute('aria-busy', 'false');
      }
    }
    input.addEventListener('input', () => {
      reset();
      timer = setTimeout(check, 350);
    });
    input.addEventListener('blur', () => {
      clearTimeout(timer);
      check();
    });
  });
})();
