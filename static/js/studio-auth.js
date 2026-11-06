/* Presentation only. Authentication and verification remain server-side. */
(() => {
  'use strict';
  document.querySelectorAll('[data-password-toggle]').forEach(button => {
    button.addEventListener('click', () => {
      const field = document.getElementById(button.dataset.passwordToggle);
      const reveal = field.type === 'password';
      field.type = reveal ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(reveal));
      button.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
    });
  });
  document.querySelectorAll('.studio-auth-form').forEach(form => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('[type="submit"]');
      if (!button || button.disabled) return;
      button.disabled = true;
      button.querySelector('span').textContent = 'Please wait…';
      form.setAttribute('aria-busy', 'true');
    });
  });
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('.studio-auth-form').forEach(form => {
      form.removeAttribute('aria-busy');
      const button=form.querySelector('[type="submit"]');
      if(button){button.disabled=false;button.querySelector('span').textContent=document.getElementById('otp-code')?'Verify & enter Studio':'Continue to Studio';}
    });
  });
})();
