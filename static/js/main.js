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

  // ================== AOS INIT (Modern, Smooth & Responsive) ==================
  try {
    if (typeof AOS !== 'undefined') {
      AOS.init({
        duration: 600,
        once: true,
        mirror: false,
        offset: 80,
        easing: 'ease-out-cubic',
        throttleDelay: 50,
        anchorPlacement: 'top-bottom',
        disable: () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        startEvent: 'DOMContentLoaded',
        disableMutationObserver: true
      });
    }
  } catch (e) { console.warn('AOS init failed:', e); }

  // ================== AUTH MODAL ==================
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
    try { btn.classList.add('btn-loading'); btn.disabled = true; } catch (e) { }
  };

  window.resetButton = function (btn) {
    if (!btn) return;
    try { btn.classList.remove('btn-loading'); btn.disabled = false; } catch (e) { }
  };

  function showModalFlash(msg, type) {
    try {
      var flash = document.getElementById('modalFlash');
      if (!flash) return;
      flash.innerHTML = '<div class="alert alert-' + type + ' alert-dismissible fade show py-2 small" role="alert">' + window.escapeHTML(msg) + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>';
    } catch (e) { }
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

      // ================== LOGIN ==================
      var loginForm = document.getElementById('modalLoginForm');
      if (loginForm) {
        loginForm.addEventListener('submit', async function (e) {
          e.preventDefault();
          var btn = this.querySelector('button[type="submit"]');
          window.setButtonLoading(btn);
          var fd = new FormData(this);
          try {
            var res = await fetch('/user/login', {
              method: 'POST',
              body: fd,
              headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            var data = await res.json();

            if (data.success) {
              window.authModal.hide();
              window.location.href = window.pendingRedirectUrl || data.redirect || '/';
            } else {
              showModalFlash(data.error || 'Login failed. Please check your email and password.', 'danger');
              window.resetButton(btn);
            }
          } catch (err) {
            showModalFlash('Server error. Please try again in a moment.', 'danger');
            window.resetButton(btn);
            console.error('Login error:', err);
          }
        });
      }

      // ================== SIGNUP ==================
      var signupForm = document.getElementById('modalSignupForm');
      if (signupForm) {
        signupForm.addEventListener('submit', async function (e) {
          e.preventDefault();
          var btn = this.querySelector('button[type="submit"]');
          window.setButtonLoading(btn);
          var fd = new FormData(this);

          try {
            var res = await fetch('/user/signup', {
              method: 'POST',
              body: fd,
              headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            var data = await res.json();

            if (data.success) {
              window.resetButton(btn);
              var msg = data.message || 'Account created! Please check your email to verify.';
              showModalFlash(msg, 'success');
              // Modal hide mat karo — user ko success dikhe
            } else {
              showModalFlash(data.error || 'Signup failed. Please try again.', 'danger');
              window.resetButton(btn);
            }
          } catch (err) {
            showModalFlash('Server error. Please try again in a moment.', 'danger');
            window.resetButton(btn);
            console.error('Signup error:', err);
          }
        });
      }
      
      var modalUsername = document.getElementById('modalUsername');
      if (modalUsername) {
        var modalFirstName = document.getElementById('modalFirstName');
        var modalLastName = document.getElementById('modalLastName');

        var usernameFeedback = modalUsername.closest('.mb-3')
          ? modalUsername.closest('.mb-3').querySelector('.feedback')
          : null;

        var usernameSuggestions = modalUsername.closest('.mb-3')
          ? modalUsername.closest('.mb-3').querySelector('.username-suggestions')
          : null;

        var usernameTimer;
        var lastAutoProposed = '';

        function clearUsernameFeedback() {
          if (usernameFeedback) usernameFeedback.textContent = '';
          if (usernameSuggestions) usernameSuggestions.innerHTML = '';
          modalUsername.classList.remove('is-valid', 'is-invalid');
        }

        function renderUsernameSuggestions(list) {
          if (!usernameSuggestions) return;
          usernameSuggestions.innerHTML = '';
          (list || []).forEach(function (suggestion) {
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'btn btn-sm btn-outline-primary rounded-pill px-2 py-1';
            chip.textContent = suggestion;
            chip.addEventListener('click', function () {
              lastAutoProposed = suggestion;
              modalUsername.value = suggestion;
              modalUsername.dispatchEvent(new Event('input', { bubbles: true }));
            });
            usernameSuggestions.appendChild(chip);
          });
        }

        function proposeUsernameFromName() {
          var fn = modalFirstName ? modalFirstName.value.trim() : '';
          var ln = modalLastName ? modalLastName.value.trim() : '';
          if (!fn && !ln) return;

          var current = modalUsername.value.trim();
          if (current && current !== lastAutoProposed) return;

          var candidate = (fn + ln).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 20);
          if (!candidate || candidate.length < 3) return;

          fetch('/api/check-availability?field=username&value=' + encodeURIComponent(candidate) +
                '&first_name=' + encodeURIComponent(fn) +
                '&last_name=' + encodeURIComponent(ln))
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (data.error) return;

              var chosen = candidate;
              if (data.exists || data.reserved) {
                chosen = (data.suggestions && data.suggestions.length)
                  ? data.suggestions[0]
                  : candidate + Math.floor(100 + Math.random() * 900);
              }

              lastAutoProposed = chosen;
              modalUsername.value = chosen;
              modalUsername.dispatchEvent(new Event('input', { bubbles: true }));
            })
            .catch(function () {});
        }

        [modalFirstName, modalLastName].forEach(function (el) {
          if (!el) return;
          el.addEventListener('input', proposeUsernameFromName);
        });

        modalUsername.addEventListener('input', function () {
          clearTimeout(usernameTimer);
          var val = this.value.trim();

          if (val.length < 3) {
            clearUsernameFeedback();
            return;
          }

          usernameTimer = setTimeout(function () {
            var fn = modalFirstName ? modalFirstName.value.trim() : '';
            var ln = modalLastName ? modalLastName.value.trim() : '';

            fetch(
              '/api/check-availability?field=username&value=' +
              encodeURIComponent(val) +
              '&first_name=' + encodeURIComponent(fn) +
              '&last_name=' + encodeURIComponent(ln)
            )
              .then(function (r) { return r.json(); })
              .then(function (data) {
                if (data.error) {
                  clearUsernameFeedback();
                  return;
                }

                modalUsername.classList.remove('is-valid', 'is-invalid');
                if (usernameFeedback) usernameFeedback.textContent = '';
                if (usernameSuggestions) usernameSuggestions.innerHTML = '';

                if (data.format_error) {
                  modalUsername.classList.add('is-invalid');
                  if (usernameFeedback) {
                    usernameFeedback.textContent = data.message || 'Invalid username format.';
                    usernameFeedback.className = 'feedback small mt-1 text-danger';
                  }
                  return;
                }

                if (data.simple) {
                  modalUsername.classList.add('is-invalid');
                  if (usernameFeedback) {
                    usernameFeedback.textContent = data.message || 'Username is too simple.';
                    usernameFeedback.className = 'feedback small mt-1 text-danger';
                  }
                  renderUsernameSuggestions(data.suggestions);
                  return;
                }

                if (data.reserved || data.exists) {
                  modalUsername.classList.add('is-invalid');
                  if (usernameFeedback) {
                    usernameFeedback.textContent = data.message || 'Username is not available.';
                    usernameFeedback.className = 'feedback small mt-1 text-danger';
                  }
                  renderUsernameSuggestions(data.suggestions);
                  return;
                }

                modalUsername.classList.add('is-valid');
                if (usernameFeedback) {
                  usernameFeedback.textContent = '✓ Username is available!';
                  usernameFeedback.className = 'feedback small mt-1 text-success';
                }
              })
              .catch(function () {
                clearUsernameFeedback();
              });
          }, 100);
        });

        // First/last name badalne par bhi recheck ho
        [modalFirstName, modalLastName].forEach(function (el) {
          if (!el) return;
          el.addEventListener('input', function () {
            if (modalUsername.value.trim().length >= 3) {
              modalUsername.dispatchEvent(new Event('input'));
            }
          });
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
  } catch (e) { }

  // ================== SERVICE WORKER ==================
  try {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', function () {
        navigator.serviceWorker.register('/static/sw.js').catch(function () { });
      });
    }
  } catch (e) { }

  // ================== PREVIEW MODAL + DOWNLOAD ==================
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
              imgContainer.innerHTML = '<img src="' + window.safeURL(img) + '" class="img-fluid shadow-sm w-100" style="object-fit:cover;max-height:400px;border-radius:15px;">';
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

    // ================== SCROLL REVEAL (once + safe fallback) ==================
  try {
    var revealCards = document.querySelectorAll('.anim-card');

    function revealAllCards() {
      revealCards.forEach(function (card) {
        card.classList.add('revealed');
      });
    }

    if (revealCards.length && typeof IntersectionObserver !== 'undefined') {
      var observer = new IntersectionObserver(function (entries, obs) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('revealed');
            obs.unobserve(entry.target);
          }
        });
      }, { threshold: 0.1, rootMargin: '0px 0px -30px 0px' });

      revealCards.forEach(function (card) {
        observer.observe(card);
      });

      // SAFETY NET: jo cards miss ho jayen, 2 second baad sab force-reveal
      setTimeout(revealAllCards, 2000);
    } else {
      revealAllCards();
    }
  } catch (e) {
    document.querySelectorAll('.anim-card').forEach(function (c) {
      c.classList.add('revealed');
    });
    console.warn('Scroll reveal failed:', e);
  }

  // Scroll controls are managed by reading-controls.js.

  // ================== COUNT-UP ANIMATION ==================
  try {
    var countEls = document.querySelectorAll('[data-count]');
    if (countEls.length) {
      var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      function animateCount(el) {
        var target = parseInt(el.getAttribute('data-count'), 10) || 0;
        if (reduceMotion) {
          el.textContent = target.toLocaleString();
          return;
        }
        var start = null, duration = 1400;
        function step(ts) {
          if (!start) start = ts;
          var progress = Math.min((ts - start) / duration, 1);
          var eased = 1 - Math.pow(1 - progress, 3);
          el.textContent = Math.floor(eased * target).toLocaleString();
          if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
      }
      if ('IntersectionObserver' in window) {
        var io = new IntersectionObserver(function (entries, obs) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              animateCount(entry.target);
              obs.unobserve(entry.target);
            }
          });
        }, { threshold: 0.3 });
        countEls.forEach(function (el) { io.observe(el); });
      } else {
        countEls.forEach(animateCount);
      }
    }
  } catch (e) { console.warn('Count-up failed:', e); }

  // ================== ACTIVE NAV LINK ==================
  try {
    var path = window.location.pathname;
    document.querySelectorAll('.navbar .nav-link').forEach(function (link) {
      var href = link.getAttribute('href');
      if (!href || href === '#') return;
      if (path === href) link.classList.add('active');
    });
  } catch (e) { console.warn('Active nav failed:', e); }

  // ================== IMAGE ERROR FALLBACK ==================
  try {
    document.addEventListener('error', function (e) {
      var img = e.target;
      if (!img || img.tagName !== 'IMG') return;
      var isCover = img.classList.contains('flat-book-cover') ||
        img.classList.contains('book-cover') ||
        img.alt === 'Cover';
      if (!isCover || img.dataset.fallbackHandled) return;
      img.dataset.fallbackHandled = '1';
      img.style.display = 'none';
      var wrapper = img.parentElement;
      if (wrapper) {
        var initials = (img.alt || 'Book').trim().substring(0, 2).toUpperCase() || '📚';
        var ph = document.createElement('div');
        ph.className = 'd-flex align-items-center justify-content-center';
        ph.style.cssText = 'width:100%;height:100%;min-height:120px;background:linear-gradient(135deg,#a5b4fc,#818cf8);color:#fff;border-radius:8px;font-weight:700;';
        ph.textContent = initials;
        wrapper.appendChild(ph);
      }
    }, true);
  } catch (e) { console.warn('Image fallback failed:', e); }

  // ================== TOAST HELPER ==================
  window.showToast = function (message, type) {
    try {
      type = type || 'success';
      var existing = document.getElementById('globalToast');
      if (existing) existing.remove();
      var toast = document.createElement('div');
      toast.id = 'globalToast';
      toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:' +
        (type === 'error' || type === 'danger' ? '#dc3545' : '#198754') +
        ';color:#fff;padding:12px 20px;border-radius:50px;z-index:99999;font-weight:600;box-shadow:0 8px 24px rgba(0,0,0,.2);transition:opacity .3s;';
      toast.textContent = message;
      document.body.appendChild(toast);
      setTimeout(function () {
        toast.style.opacity = '0';
        setTimeout(function () { toast.remove(); }, 300);
      }, 3500);
    } catch (e) { console.warn('Toast failed:', e); }
  };

});
