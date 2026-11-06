/* One source of truth for responsive course contents, without a second collapse controller. */
(() => {
  'use strict';
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-learning-page]').forEach(root => {
      const button = root.querySelector('.course-nav-toggle');
      const nav = root.querySelector('#courseNav');
      if (!button || !nav) return;
      const desktop = window.matchMedia('(min-width: 992px)');
      const label = button.querySelector('[data-course-toggle-label]');
      let mobileOpen = false;
      function sync() {
        const expanded = desktop.matches || mobileOpen;
        nav.hidden = !expanded;
        button.setAttribute('aria-expanded', String(expanded));
        button.setAttribute('aria-label', expanded ? 'Hide Course Content' : 'Show Course Content');
        if (label) label.textContent = expanded ? 'Hide Course Content' : 'Show Course Content';
      }
      root.classList.add('learning-nav-ready');
      button.addEventListener('click', () => { mobileOpen = !mobileOpen; sync(); });
      nav.querySelectorAll('a[href^="#"]').forEach(link => {
        link.addEventListener('click', () => { if (!desktop.matches) { mobileOpen = false; sync(); } });
      });
      desktop.addEventListener('change', sync);
      sync();
    });
  });
})();
