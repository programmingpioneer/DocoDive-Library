/* Read actual practice results and guided self-checks. No network or account writes. */
(() => {
  'use strict';
  function init() {
    document.querySelectorAll('[data-practice-activity]').forEach(root => {
      const key = root.dataset.practiceStatsKey;
      const guided = root.dataset.practiceKind === 'guided';
      const field = name => root.querySelector('[data-practice-' + name + ']');
      const storageNote = field('storage');
      let saved = true, value;
      try { value = JSON.parse(window.localStorage.getItem(key) || (guided ? '[]' : '{}')); }
      catch (error) { value = guided ? [] : {}; saved = false; }
      const checks = guided ? Array.from(document.querySelectorAll('[data-practice-step]')) : [];
      const safeCount = n => typeof n === 'number' && Number.isFinite(n) && n > 0 ? Math.min(1000000, Math.floor(n)) : 0;
      function paint(stats) {
        let attempts = 0, correct = 0, topics = 0;
        if (guided) {
          attempts = checks.filter(check => check.checked).length;
          correct = attempts; topics = checks.length;
        } else if (stats && typeof stats === 'object' && !Array.isArray(stats)) {
          Object.values(stats).slice(0, 500).forEach(stat => {
            if (!stat || typeof stat !== 'object') return;
            const yes = safeCount(stat.correct), no = safeCount(stat.wrong);
            correct += yes; attempts += yes + no;
            if (yes + no) topics++;
          });
        }
        const percent = Math.round(100 * correct / (guided ? (checks.length || 1) : (attempts || 1)));
        field('attempts').textContent = String(attempts);
        field('accuracy').textContent = percent + '%';
        field('topics').textContent = String(topics);
        const progress = field('progress');
        if (progress) { progress.max = 100; progress.value = percent; progress.textContent = percent + '%'; }
        if (storageNote) storageNote.textContent = saved ?
          (guided ? 'Self-reported progress · saved in this browser.' : 'Practice activity · saved in this browser. Not synced to your account.') :
          'Session only · browser storage is unavailable; this progress is not saved.';
      }
      if (guided) {
        const ids = Array.isArray(value) ? value : [];
        checks.forEach(check => {
          check.checked = ids.includes(check.dataset.practiceStep);
          check.addEventListener('change', () => {
            try { window.localStorage.setItem(key, JSON.stringify(checks.filter(c => c.checked).map(c => c.dataset.practiceStep))); saved = true; }
            catch (error) { saved = false; }
            paint();
          });
        });
      }
      document.addEventListener('docodive:practice-answer', event => {
        if (guided || event.detail?.key !== key) return;
        saved = event.detail.saved !== false;
        paint(event.detail.stats);
      });
      paint(value);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
  else init();
})();
