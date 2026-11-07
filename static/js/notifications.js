/* Scoped inbox state: failed requests must never clear an unread indicator. */
(() => {
  'use strict';
  function init() {
    const inbox = document.querySelector('[data-notification-inbox]');
    if (!inbox) return;
    const status = inbox.querySelector('[data-inbox-status]');
    const empty = inbox.querySelector('[data-inbox-empty]');
    const bulk = inbox.querySelector('[data-notification-action="read-all"]');
    let filter = 'all';
    let pending = false;
    const rows = () => [...inbox.querySelectorAll('[data-notification-row]')];
    function refresh() {
      const list = rows();
      const unread = list.filter(row => row.classList.contains('is-unread')).length;
      inbox.querySelector('[data-inbox-unread]').textContent = String(unread);
      inbox.querySelector('[data-inbox-total]').textContent = String(list.length);
      bulk.disabled = pending || !unread;
      let visible = 0;
      for (const row of list) {
        row.hidden = !(filter === 'all' || (filter === 'unread' ? row.classList.contains('is-unread') : row.dataset.category === filter));
        if (!row.hidden) visible++;
      }
      empty.hidden = visible !== 0;
      for (const button of inbox.querySelectorAll('[data-notification-filter]')) {
        button.setAttribute('aria-pressed', String(button.dataset.notificationFilter === filter));
      }
    }
    function markRead(row) {
      row.classList.remove('is-unread');
      row.querySelector('[data-unread-label]').hidden = true;
      row.querySelector('[data-read-button]').hidden = true;
    }
    async function request(path) {
      const response = await fetch(path, {
        method: 'POST', credentials: 'same-origin',
        headers: {'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || ''}
      });
      if (!response.ok || response.redirected) throw new Error('Request failed');
      const result = await response.json();
      if (result.success !== true) throw new Error('Update was not confirmed');
    }
    inbox.addEventListener('click', async event => {
      const tab = event.target.closest('[data-notification-filter]');
      if (tab) {filter = tab.dataset.notificationFilter; refresh(); return;}
      const button = event.target.closest('[data-notification-action]');
      if (!button || button.disabled || pending) return;
      event.preventDefault();
      const action = button.dataset.notificationAction;
      if (!['read-all', 'read', 'delete'].includes(action)) return;
      const row = button.closest('[data-notification-row]');
      if (action !== 'read-all' && (!row || !/^\d+$/.test(row.dataset.id))) return;
      pending = true; button.disabled = true; refresh(); status.hidden = true;
      inbox.setAttribute('aria-busy', 'true');
      try {
        if (action === 'delete') {
          const confirmed = window.toast?.confirm
            ? await window.toast.confirm('Delete this notification?', {title: 'Delete notification', confirmText: 'Delete', type: 'danger'})
            : window.confirm('Delete this notification?');
          if (!confirmed) return;
        }
        const path = action === 'read-all' ? '/api/notifications/read-all' : `/api/notifications/${row.dataset.id}/${action === 'delete' ? 'delete' : 'read'}`;
        await request(path);
        if (action === 'delete') row.remove();
        else if (action === 'read-all') rows().forEach(markRead);
        else markRead(row);
        status.textContent = action === 'delete' ? 'Notification deleted.' : 'Notifications marked read.';
        status.dataset.tone = 'success';
        status.hidden = false;
        window.updateNotifications?.();
      } catch (_) {
        status.textContent = 'Could not update notifications. Check your connection and try again.';
        status.dataset.tone = 'error';
        status.hidden = false;
      } finally {
        pending = false; button.disabled = false; refresh();
        inbox.setAttribute('aria-busy', 'false');
      }
    });
    document.addEventListener('docodive:notifications-read-all',()=>{
      rows().forEach(markRead);
      status.textContent='Notifications marked read.';
      status.dataset.tone='success';status.hidden=false;
      refresh();
    });
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
