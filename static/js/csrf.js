/* Same-origin CSRF transport for existing fetch/XHR forms; no third-party tokens. */
(() => {
  'use strict';
  const token = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
  const mutates = method => !['GET','HEAD','OPTIONS'].includes((method || 'GET').toUpperCase());
  const sameOrigin = url => new URL(url, location.href).origin === location.origin;
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, options = {}) => {
    const method = options.method || (input instanceof Request ? input.method : 'GET');
    const url = input instanceof Request ? input.url : input;
    if (sameOrigin(url) && mutates(method)) {
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('X-CSRF-Token', token());
      options = {...options, headers};
    }
    return originalFetch(input, options);
  };
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method,url,...rest) { this._studioCsrf = mutates(method) && sameOrigin(url); return open.call(this,method,url,...rest); };
  XMLHttpRequest.prototype.send = function(body) { if(this._studioCsrf) this.setRequestHeader('X-CSRF-Token',token()); return send.call(this,body); };
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('form[method="post" i]').forEach(form => {
      if (sameOrigin(form.action) && !form.querySelector('[name="_csrf_token"]')) {
        const field = document.createElement('input'); field.type='hidden'; field.name='_csrf_token'; field.value=token(); form.append(field);
      }
    });
  });
})();
