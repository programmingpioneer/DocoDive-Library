// ================== DOCODIVE MAIN.JS ==================
document.addEventListener('DOMContentLoaded', function () {

  // ================== PASSIVE EVENT LISTENERS ==================
  try {
    (function () {
      var supportsPassive = false;
      try {
        var opts = Object.defineProperty({}, 'passive', {
          get: function () { supportsPassive = true; }
        });
        window.addEventListener('testPassive', null, opts);
        window.removeEventListener('testPassive', null, opts);
      } catch (e) { }
      if (supportsPassive) {
        var originalAddEventListener = EventTarget.prototype.addEventListener;
        EventTarget.prototype.addEventListener = function (type, listener, options) {
          var passiveEvents = ['scroll', 'touchstart', 'touchend', 'touchmove', 'wheel'];
          if (passiveEvents.indexOf(type) !== -1 && typeof options !== 'object') {
            options = { passive: true };
          } else if (passiveEvents.indexOf(type) !== -1 && typeof options === 'object' && options.passive === undefined) {
            options.passive = true;
          }
          originalAddEventListener.call(this, type, listener, options);
        };
      }
    })();
  } catch (e) { console.warn('Passive listeners setup failed:', e); }

  // ================== AOS INIT ==================
  try {
    if (typeof AOS !== 'undefined') {
      AOS.init({
        duration: 350,
        once: true,       // ✅ Optimized
        mirror: false,     // ✅ Optimized
        offset: 100,
        easing: 'ease-out',
        throttleDelay: 99,
        anchorPlacement: 'top-bottom',
        disable: 'mobile'
      });
    }
  } catch (e) { console.warn('AOS init failed:', e); }

  // ================== AUTH MODAL (only if modal exists) ==================
  window.authModal = null;
  window.pendingRedirectUrl = null;

  window.switchTab = function (tab) {
    try {
      document.querySelectorAll('.auth-tab').forEach(function (t) { t.classList.remove('active'); });
      document.querySelectorAll('.auth-form').forEach(function (f) { f.classList.add('d-none'); });
      document.querySelector('.auth-tab[data-tab="' + tab + '"]').classList.add('active');
      document.getElementById(tab === 'login' ? 'modalLoginForm' : 'modalSignupForm').classList.remove('d-none');
    } catch (e) { console.warn('switchTab failed:', e); }
  };

  window.togglePassword = function (inputId, iconSpan) {
    try {
      var input = document.getElementById(inputId);
      if (!input) return;
      var icon = iconSpan.querySelector('i');
      if (input.type === 'password') {
        input.type = 'text';
        if (icon) { icon.classList.remove('bi-eye-slash'); icon.classList.add('bi-eye'); }
        var checkbox = document.getElementById(inputId === 'modalLoginPassword' ? 'modalLoginShowCheckbox' : 'modalSignupShowCheckbox');
        if (checkbox) checkbox.checked = true;
      } else {
        input.type = 'password';
        if (icon) { icon.classList.remove('bi-eye'); icon.classList.add('bi-eye-slash'); }
        var checkbox2 = document.getElementById(inputId === 'modalLoginPassword' ? 'modalLoginShowCheckbox' : 'modalSignupShowCheckbox');
        if (checkbox2) checkbox2.checked = false;
      }
    } catch (e) { console.warn('togglePassword failed:', e); }
  };

  window.togglePasswordCheckbox = function (inputId, eyeIconId, checkbox) {
    try {
      var input = document.getElementById(inputId);
      if (!input) return;
      var icon = document.getElementById(eyeIconId);
      if (!icon) return;
      if (checkbox.checked) {
        input.type = 'text';
        icon.classList.remove('bi-eye-slash');
        icon.classList.add('bi-eye');
      } else {
        input.type = 'password';
        icon.classList.remove('bi-eye');
        icon.classList.add('bi-eye-slash');
      }
    } catch (e) { console.warn('togglePasswordCheckbox failed:', e); }
  };

  window.setButtonLoading = function (btn) {
    if (!btn) return;
    try { btn.classList.add('btn-loading'); btn.disabled = true; } catch (e) {}
  };

  window.resetButton = function (btn) {
    if (!btn) return;
    try { btn.classList.remove('btn-loading'); btn.disabled = false; } catch (e) {}
  };

  function showModalFlash(msg, type) {
    try {
      var flash = document.getElementById('modalFlash');
      if (!flash) return;
      flash.innerHTML = '<div class="alert alert-' + type + ' alert-dismissible fade show py-2 small" role="alert">' + msg + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>';
    } catch (e) {}
  }

  // Init auth modal (safely)
  try {
    var authModalEl = document.getElementById('authModal');
    if (authModalEl && typeof bootstrap !== 'undefined') {
      window.authModal = new bootstrap.Modal(authModalEl);

      document.querySelectorAll('.auth-tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
          window.switchTab(this.dataset.tab);
        });
      });

      var loginForm = document.getElementById('modalLoginForm');
      if (loginForm) {
        loginForm.addEventListener('submit', async function (e) {
          e.preventDefault();
          var btn = this.querySelector('button[type="submit"]');
          window.setButtonLoading(btn);
          var fd = new FormData(this);
          try {
            var res = await fetch('/user/login', {
              method: 'POST', body: fd,
              headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            var data = await res.json();
            if (data.success) {
              window.authModal.hide();
              window.location.href = window.pendingRedirectUrl || data.redirect || '/';
            } else {
              showModalFlash(data.error || 'Login failed', 'danger');
              window.resetButton(btn);
            }
          } catch (err) {
            showModalFlash('Something went wrong', 'danger');
            window.resetButton(btn);
          }
        });
      }

      var signupForm = document.getElementById('modalSignupForm');
      if (signupForm) {
        signupForm.addEventListener('submit', async function (e) {
          e.preventDefault();
          var btn = this.querySelector('button[type="submit"]');
          window.setButtonLoading(btn);
          var fd = new FormData(this);
          try {
            var res = await fetch('/user/signup', {
              method: 'POST', body: fd,
              headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            var data = await res.json();
            if (data.success) {
              window.authModal.hide();
              window.location.href = window.pendingRedirectUrl || data.redirect || '/';
            } else {
              showModalFlash(data.error || 'Signup failed', 'danger');
              window.resetButton(btn);
            }
          } catch (err) {
            showModalFlash('Something went wrong', 'danger');
            window.resetButton(btn);
          }
        });
      }
    }
  } catch (e) { console.warn('Auth modal init failed:', e); }

  window.showAuthModal = function (redirectUrl) {
    window.pendingRedirectUrl = redirectUrl || window.location.href;
    if (window.authModal) window.authModal.show();
  };

  // ================== GLOBAL FORM LOADING ==================
  try {
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (form.hasAttribute('data-ajax')) return;
      var btn = form.querySelector('button[type="submit"], input[type="submit"]');
      if (btn) window.setButtonLoading(btn);
    });
  } catch (e) {}

  // ================== NOTIFICATIONS ==================
  window.updateNotifications = function () { /* will be defined below */ };
  window.markAllRead = function () { /* will be defined below */ };

  try {
    window.timeAgo = function (dateString) {
      try {
        var dbDate = dateString.replace(' ', 'T') + 'Z';
        var now = new Date();
        var past = new Date(dbDate);
        if (isNaN(past.getTime())) return dateString;
        var diffMs = now - past;
        var diffSec = Math.floor(diffMs / 1000);
        var diffMin = Math.floor(diffSec / 60);
        var diffHr = Math.floor(diffMin / 60);
        var diffDay = Math.floor(diffHr / 24);
        if (diffDay > 0) return diffDay + 'd ago';
        if (diffHr > 0) return diffHr + 'h ago';
        if (diffMin > 0) return diffMin + 'm ago';
        return 'Just now';
      } catch (e) { return dateString; }
    };

    window.goToNotif = function (url) { window.location = url; };

    window.markNotifRead = async function (id, el) { /* placeholder */ };
    window.deleteNotif = async function (id, el) { /* placeholder */ };

    window.updateNotifications = function () {
      try {
        fetch('/api/notifications/unread-count')
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var badge = document.getElementById('notifBadge');
            if (badge) {
              if (d.count > 0) { badge.style.display = 'inline'; badge.textContent = d.count; }
              else { badge.style.display = 'none'; }
            }
          }).catch(function () {});

        fetch('/api/notifications')
          .then(function (r) { return r.json(); })
          .then(function (list) {
            var container = document.getElementById('notifList');
            if (!container) return;
            if (!list || list.length === 0) {
              container.innerHTML = '<div class="text-center text-muted py-4"><i class="bi bi-bell-slash fs-2 d-block mb-2"></i><small>No notifications yet</small></div>';
              return;
            }
            var html = '';
            list.forEach(function (n) {
              var ago = window.timeAgo(n.created_at);
              var avatarUrl = n.image_url || n.actor_avatar || '/static/default-avatar.png';
              var heading = 'Notification', snippet = n.message || '';
              if (n.type === 'approval') heading = '📗 Book Approved';
              else if (n.type === 'rejection') heading = '📕 Book Rejected';
              else if (n.type === 'general_comment') heading = '💬 Comment';
              else if (n.type === 'reply') heading = '↩️ Reply';
              snippet = snippet.replace(/<[^>]*>/g, '');
              var targetUrl = n.link || '/user/notifications';
              html += '<div class="d-flex align-items-center p-2 border-bottom notif-card-item ' + (!n.is_read ? 'bg-purple-light' : '') + '">' +
                '<div class="flex-grow-1" onclick="window.goToNotif(\'' + targetUrl + '\')" style="cursor:pointer;">' +
                '<strong class="small">' + heading + '</strong>' +
                '<small class="text-muted ms-2">' + ago + '</small>' +
                '<div class="text-muted small text-truncate">' + snippet + '</div></div></div>';
            });
            container.innerHTML = html;
          }).catch(function () {});
      } catch (e) {}
    };

    window.markAllRead = function () {
      fetch('/api/notifications').then(function (r) { return r.json(); }).then(function (list) {
        var unread = list.filter(function (n) { return !n.is_read; });
        Promise.all(unread.map(function (n) {
          return fetch('/api/notifications/' + n.id + '/read', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        })).then(function () { window.updateNotifications(); });
      }).catch(function () {});
    };

    window.updateNotifications();
    setInterval(window.updateNotifications, 30000);
  } catch (e) { console.warn('Notifications init failed:', e); }

  // ================== QR CODE POPUP ==================
  try {
    var qrPopup = document.getElementById('qrPopup');
    if (qrPopup) {
      var qrCloseBtn = qrPopup.querySelector('button');
      if (qrCloseBtn) {
        qrCloseBtn.addEventListener('click', function () { qrPopup.style.display = 'none'; });
      }
    }
  } catch (e) {}

  // ================== HIDE LOADER (robust) ==================
  (function () {
    var loader = document.getElementById('page-loader');
    if (!loader) return;
    var MIN_DISPLAY_TIME = 2000;
    var pageLoaded = false, timerDone = false;
    function doHide() {
      if (!loader) return;
      loader.classList.add('hidden');
      setTimeout(function () {
        if (loader && loader.parentNode) loader.parentNode.removeChild(loader);
      }, 500);
    }
    function tryHide() { if (pageLoaded && timerDone) doHide(); }
    window.addEventListener('load', function () { pageLoaded = true; tryHide(); });
    setTimeout(function () { timerDone = true; tryHide(); }, MIN_DISPLAY_TIME);
    // Failsafe: hide after 8 seconds no matter what
    setTimeout(function () {
      if (loader && !loader.classList.contains('hidden')) doHide();
    }, 8000);
  })();

  // ================== SERVICE WORKER ==================
  try {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', function () {
        navigator.serviceWorker.register('/static/sw.js').catch(function () {});
      });
    }
  } catch (e) {}

  // ================== PREVIEW MODAL + DOWNLOAD (safe) ==================
  try {
    var previewBtns = document.querySelectorAll('.preview-btn');
    previewBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        try {
          var title = this.getAttribute('data-title');
          var link = this.getAttribute('data-link');
          var author = this.getAttribute('data-author');
          var desc = this.getAttribute('data-desc');
          var img = this.getAttribute('data-img');
          var lang = this.getAttribute('data-lang');
          var modalTitle = document.getElementById('modalTitle');
          if (modalTitle) modalTitle.textContent = title;
          var modalAuthor = document.getElementById('modalAuthor');
          if (modalAuthor) modalAuthor.textContent = (author && author !== 'None') ? author : 'Admin';
          var modalDesc = document.getElementById('modalDesc');
          if (modalDesc) modalDesc.textContent = (desc && desc !== 'None') ? desc : 'No description available.';
          var modalDownloadBtn = document.getElementById('modalDownloadBtn');
          if (modalDownloadBtn) modalDownloadBtn.setAttribute('data-file-url', link);
          var imgContainer = document.getElementById('modalImageContainer');
          if (imgContainer) {
            if (img && img !== 'None' && img.trim() !== '') {
              imgContainer.innerHTML = '<img src="' + img + '" class="img-fluid shadow-sm w-100" style="object-fit:cover;max-height:400px;border-radius:15px;">';
            } else {
              imgContainer.innerHTML = '<div class="bg-light d-flex justify-content-center align-items-center" style="height:350px;"><i class="bi bi-journal-code text-primary" style="font-size:6rem;"></i></div>';
            }
          }
          var pdfModalEl = document.getElementById('pdfPreviewModal');
          if (pdfModalEl && typeof bootstrap !== 'undefined') {
            new bootstrap.Modal(pdfModalEl).show();
          }
        } catch (e) { console.warn('Preview modal error:', e); }
      });
    });
  } catch (e) { console.warn('Preview buttons setup failed:', e); }

  // ================== SCROLL REVEAL ==================
  try {
    var revealCards = document.querySelectorAll('.anim-card');
    if (revealCards.length && typeof IntersectionObserver !== 'undefined') {
      var observer = new IntersectionObserver(function (entries, obs) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('revealed');
            obs.unobserve(entry.target);
          }
        });
      }, { threshold: 0.15 });
      revealCards.forEach(function (card) { observer.observe(card); });
    }
  } catch (e) { console.warn('Scroll reveal failed:', e); }

});