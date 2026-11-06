/* Optional services are created only after an explicit, valid cookie choice. */
(function () {
  'use strict';

  var preview = document.currentScript && document.currentScript.dataset.preview === 'true';
  var storageKey = 'docodive_cookie_preferences';
  var maxAge = 180 * 24 * 60 * 60 * 1000;
  var analyticsId = 'G-3GC4V3QX2W';

  function init() {
    if (window.__docodiveCookieControls) return;
    var banner = document.getElementById('cookie-banner');
    var dialog = document.getElementById('cookie-preferences');
    var form = document.getElementById('cookie-form');
    var analyticsInput = document.getElementById('cookie-analytics');
    var supportInput = document.getElementById('cookie-support');
    var status = document.getElementById('cookie-status');
    var statusMessage = document.getElementById('cookie-status-message');
    var dialogStatus = document.getElementById('cookie-dialog-status');
    if (!banner || !dialog || !form || !analyticsInput || !supportInput || !status || !statusMessage || !dialogStatus) return;
    window.__docodiveCookieControls = true;

    var choices = { analytics: false, support: false };
    var hasChoice = false;
    var storageAvailable = true;
    var analyticsLoaded = false;
    var supportLoaded = false;
    var opener = null;

    function valid(value) {
      var now = Date.now();
      return value !== null && typeof value === 'object' && !Array.isArray(value) &&
        value.version === 1 && typeof value.analytics === 'boolean' &&
        typeof value.support === 'boolean' && Number.isSafeInteger(value.savedAt) &&
        Number.isSafeInteger(value.expiresAt) && value.savedAt > 0 &&
        value.savedAt <= now && value.expiresAt > now &&
        value.expiresAt > value.savedAt && value.expiresAt - value.savedAt <= maxAge;
    }

    try {
      var stored = JSON.parse(window.localStorage.getItem(storageKey));
      if (valid(stored)) {
        choices = stored;
        hasChoice = true;
      }
    } catch (error) {
      // Invalid JSON is treated exactly like no choice; blocked storage is disclosed on save.
      try { window.localStorage.getItem(storageKey); } catch (storageError) { storageAvailable = false; }
    }

    function showStatus(message) {
      statusMessage.textContent = message;
      status.hidden = false;
    }

    function updateInputs() {
      analyticsInput.checked = choices.analytics;
      supportInput.checked = choices.support;
      dialogStatus.textContent = storageAvailable
        ? 'Your choice is saved in this browser for up to 180 days. You can change it at any time.'
        : 'This browser cannot save your choice. It will apply only during this visit.';
    }

    function appendScript(id, url) {
      if (document.getElementById(id)) return;
      var script = document.createElement('script');
      script.id = id;
      script.async = true;
      script.src = url;
      document.head.appendChild(script);
    }

    function loadSelectedServices() {
      if (preview || !hasChoice) return;
      window['ga-disable-' + analyticsId] = !choices.analytics;
      if (choices.analytics && !analyticsLoaded) {
        analyticsLoaded = true;
        window.dataLayer = window.dataLayer || [];
        window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
        window.gtag('js', new Date());
        window.gtag('config', analyticsId, { allow_google_signals: false, allow_ad_personalization_signals: false });
        appendScript('docodive-analytics', 'https://www.googletagmanager.com/gtag/js?id=' + analyticsId);
      }
      if (choices.support && !supportLoaded && document.body.dataset.pageHome === 'true') {
        supportLoaded = true;
        window.BrevoConversationsID = '6a551981edd95b5e7d08467b';
        window.BrevoConversations = window.BrevoConversations || function () {
          (window.BrevoConversations.q = window.BrevoConversations.q || []).push(arguments);
        };
        appendScript('docodive-support', 'https://conversations-widget.brevo.com/brevo-conversations.js');
      }
    }

    function clearAnalyticsCookies() {
      // Limit deletion to known analytics cookies readable on this origin.
      var names;
      try {
        names = document.cookie.split(';').map(function (cookie) { return cookie.split('=')[0].trim(); });
      } catch (error) {
        return;
      }
      var hostname = window.location.hostname;
      var domains = ['', hostname, '.' + hostname];
      var labels = hostname.split('.');
      while (labels.length > 2) {
        labels.shift();
        domains.push('.' + labels.join('.'));
      }
      var paths = ['/'];
      var segments = window.location.pathname.split('/').filter(Boolean);
      while (segments.length) {
        paths.push('/' + segments.join('/'));
        paths.push('/' + segments.join('/') + '/');
        segments.pop();
      }
      names.forEach(function (name) {
        if (!/^(_ga(?:_|$)|_gid$|_gat(?:_|$))/.test(name)) return;
        domains.forEach(function (domain) {
          paths.forEach(function (path) {
            try {
              document.cookie = name + '=; Max-Age=0; path=' + path + (domain ? '; domain=' + domain : '') + '; SameSite=Lax';
            } catch (error) {
              // Cookie cleanup is best effort and must never prevent saving a choice.
            }
          });
        });
      });
    }

    function closePreferences() {
      if (dialog.open) dialog.close();
    }

    function saveChoices(analytics, support) {
      var needsReload = (analyticsLoaded && !analytics) || (supportLoaded && !support);
      var now = Date.now();
      choices = { version: 1, analytics: analytics, support: support, savedAt: now, expiresAt: now + maxAge };
      hasChoice = true;
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(choices));
        storageAvailable = true;
      } catch (error) {
        storageAvailable = false;
      }
      if (!analytics) {
        window['ga-disable-' + analyticsId] = true;
        clearAnalyticsCookies();
      }
      updateInputs();
      banner.hidden = true;
      closePreferences();

      if (needsReload) {
        if (storageAvailable) {
          showStatus('Your choices are saved. Reloading this page to stop the optional tools you turned off.');
          // Save first: the next page must see the withdrawn permission.
          window.location.reload();
        } else {
          // Reloading with an old stored opt-in could turn providers on again.
          showStatus('Your choices apply only to this visit because this browser could not save them. A support tool already running may continue until you close this page. Please allow preference storage before reloading.');
        }
        return;
      }

      loadSelectedServices();
      showStatus(storageAvailable
        ? 'Your cookie choices are saved. You can change them using Cookie settings in the footer.'
        : 'Your choices apply only to this visit. This browser could not save them; you may be asked again on the next page.');
    }

    function openPreferences() {
      updateInputs();
      opener = document.activeElement;
      if (!dialog.open) dialog.showModal();
    }

    document.addEventListener('click', function (event) {
      if (!event.target || typeof event.target.closest !== 'function') return;
      if (event.target.closest('[data-cookie-settings]')) {
        event.preventDefault();
        openPreferences();
        return;
      }
      var button = event.target.closest('[data-cookie-action]');
      if (!button) return;
      var action = button.dataset.cookieAction;
      if (action === 'essential') saveChoices(false, false);
      if (action === 'accept') saveChoices(true, true);
      if (action === 'cancel') closePreferences();
      if (action === 'dismiss') status.hidden = true;
    });

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      saveChoices(analyticsInput.checked, supportInput.checked);
    });
    dialog.addEventListener('cancel', updateInputs);
    dialog.addEventListener('close', function () {
      updateInputs();
      if (opener && typeof opener.focus === 'function') opener.focus();
    });

    updateInputs();
    banner.hidden = hasChoice;
    loadSelectedServices();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
