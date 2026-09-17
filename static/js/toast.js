/* DocoDive Toast System v1 — window.toast.* + auto alert() shim */
(function () {
  "use strict";
  if (window.toast && window.toast.__ready) return;

  var ICONS = {
    success: "bi-check-circle-fill",
    error: "bi-x-circle-fill",
    warning: "bi-exclamation-triangle-fill",
    info: "bi-info-circle-fill",
    loading: "bi-arrow-repeat"
  };
  var DUR = { success: 3500, error: 5000, warning: 4500, info: 3500, loading: 0 };
  var SEQ = 0;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getContainer(pos) {
    pos = pos || "top-right";
    var id = "toast-c-" + pos;
    var el = document.getElementById(id);
    if (!el) {
      el = document.createElement("div");
      el.id = id;
      el.className = "toast-container toast-" + pos;
      document.body.appendChild(el);
    }
    return el;
  }

  function spawn(opts) {
    var type = opts.type || "info";
    var msg = opts.message || "";
    var title = opts.title || "";
    var dur = opts.duration != null ? opts.duration : (DUR[type] != null ? DUR[type] : 3500);
    var container = getContainer(opts.position);
    var id = "toast-" + (++SEQ);

    var el = document.createElement("div");
    el.id = id;
    el.className = "toast-item toast-" + type;
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.setAttribute("aria-live", type === "error" ? "assertive" : "polite");

    var html = '<div class="toast-icon"><i class="bi ' + (ICONS[type] || ICONS.info) + '"></i></div>';
    html += '<div class="toast-body">';
    if (title) html += '<div class="toast-title">' + esc(title) + '</div>';
    if (msg) html += '<div class="toast-msg">' + esc(msg) + '</div>';
    html += '</div>';
    if (type !== "loading" && opts.dismissible !== false) {
      html += '<button type="button" class="toast-close" aria-label="Close">&times;</button>';
    }
    el.innerHTML = html;
    container.appendChild(el);
    requestAnimationFrame(function () { el.classList.add("toast-in"); });

    var timer = null;
    var closing = false;
    function dismiss() {
      if (closing) return;
      closing = true;
      if (timer) clearTimeout(timer);
      el.classList.remove("toast-in");
      el.classList.add("toast-out");
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 280);
    }
    if (dur > 0) timer = setTimeout(dismiss, dur);

    var cb = el.querySelector(".toast-close");
    if (cb) cb.addEventListener("click", dismiss);

    return { id: id, dismiss: dismiss };
  }

  function confirmDialog(message, opts) {
    opts = opts || {};
    var title = opts.title || "Confirm";
    var cText = opts.confirmText || "Confirm";
    var xText = opts.cancelText || "Cancel";
    var kind = opts.type || "default";
    var iconCls = kind === "danger"
      ? "bi-exclamation-triangle-fill"
      : kind === "warning"
      ? "bi-exclamation-circle-fill"
      : "bi-question-circle-fill";
    var iconBg = "toast-modal-" + (kind === "danger" ? "danger" : kind === "warning" ? "warning" : "default");

    return new Promise(function (resolve) {
      var bd = document.createElement("div");
      bd.className = "toast-modal-backdrop";
      var md = document.createElement("div");
      md.className = "toast-modal";
      md.setAttribute("role", "dialog");
      md.setAttribute("aria-modal", "true");
      md.innerHTML =
        '<div class="toast-modal-icon ' + iconBg + '"><i class="bi ' + iconCls + '"></i></div>' +
        '<div class="toast-modal-title">' + esc(title) + '</div>' +
        '<div class="toast-modal-msg">' + esc(message) + '</div>' +
        '<div class="toast-modal-actions">' +
          '<button type="button" class="toast-modal-cancel">' + esc(xText) + '</button>' +
          '<button type="button" class="toast-modal-confirm toast-modal-confirm-' + kind + '">' + esc(cText) + '</button>' +
        '</div>';
      bd.appendChild(md);
      document.body.appendChild(bd);
      setTimeout(function () { var b = md.querySelector(".toast-modal-confirm"); if (b) b.focus(); }, 40);
      requestAnimationFrame(function () { bd.classList.add("toast-modal-in"); });

      var done = false;
      function finish(v) {
        if (done) return;
        done = true;
        document.removeEventListener("keydown", onKey);
        bd.classList.remove("toast-modal-in");
        bd.classList.add("toast-modal-out");
        setTimeout(function () { if (bd.parentNode) bd.parentNode.removeChild(bd); }, 200);
        resolve(v);
      }
      function onKey(e) {
        if (e.key === "Escape") { e.preventDefault(); finish(false); }
        else if (e.key === "Enter") { e.preventDefault(); finish(true); }
      }
      md.querySelector(".toast-modal-confirm").addEventListener("click", function () { finish(true); });
      md.querySelector(".toast-modal-cancel").addEventListener("click", function () { finish(false); });
      bd.addEventListener("click", function (e) { if (e.target === bd) finish(false); });
      document.addEventListener("keydown", onKey);
    });
  }

  function autoType(msg) {
    var s = String(msg || "").toLowerCase();
    if (/✅|success|successful|posted|saved|uploaded|copied|done|complete/.test(s)) return "success";
    if (/❌|fail|error|invalid|cannot|unable|denied|wrong/.test(s)) return "error";
    if (/⚠|warn|attention|too large|too big|must be|less than|maximum|limit/.test(s)) return "warning";
    return "info";
  }

  var toast = {
    __ready: true,
    success: function (m, o) { return spawn(Object.assign({ type: "success", message: m }, o || {})); },
    error: function (m, o) { return spawn(Object.assign({ type: "error", message: m }, o || {})); },
    warning: function (m, o) { return spawn(Object.assign({ type: "warning", message: m }, o || {})); },
    info: function (m, o) { return spawn(Object.assign({ type: "info", message: m }, o || {})); },
    loading: function (m, o) { return spawn(Object.assign({ type: "loading", message: m, duration: 0 }, o || {})); },
    dismiss: function (id) {
      var el = document.getElementById(id);
      if (el && el.parentNode) {
        el.classList.remove("toast-in");
        el.classList.add("toast-out");
        setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 280);
      }
    },
    confirm: confirmDialog,
    auto: function (m, o) { var t = autoType(m); return toast[t](m, o); }
  };

  window.toast = toast;

  var _alert = window.alert;
  window.alert = function (msg) {
    try { return toast.auto(msg); }
    catch (e) { return _alert.call(window, msg); }
  };
})();