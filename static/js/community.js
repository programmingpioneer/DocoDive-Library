(() => {
  'use strict';
  function init() {
    for (const panel of document.querySelectorAll('[data-achievements]')) {
      panel.addEventListener('click', event => {
        const button = event.target.closest('[data-achievement-filter]');
        if (!button) return;
        const filter = button.dataset.achievementFilter;
        let visible = 0;
        for (const card of panel.querySelectorAll('[data-achievement-state]')) {
          card.hidden = filter !== 'all' && card.dataset.achievementState !== filter;
          if (!card.hidden) visible++;
        }
        for (const tab of panel.querySelectorAll('[data-achievement-filter]')) {
          tab.setAttribute('aria-pressed', String(tab === button));
        }
        panel.querySelector('[data-achievement-empty]').hidden = visible !== 0;
      });
    }
    const dialog = document.getElementById('community-share-dialog');
    if (!dialog) return;
    let shareText = '';
    const status = dialog.querySelector('[data-share-status]');
    const summary = dialog.querySelector('[data-share-summary]');
    const nativeShare = dialog.querySelector('[data-share-native]');
    if (nativeShare) nativeShare.hidden = typeof navigator.share !== 'function';
    document.addEventListener('click', async event => {
      const share = event.target.closest('[data-community-share]');
      if (share) {
        const url = window.location.origin + '/';
        shareText = share.dataset.shareText + ' ' + url;
        summary.textContent = shareText;
        summary.value = shareText;
        status.textContent = '';
        const text = encodeURIComponent(share.dataset.shareText), link = encodeURIComponent(url);
        const links = {whatsapp:'https://wa.me/?text='+encodeURIComponent(shareText),
          twitter:'https://twitter.com/intent/tweet?text='+text+'&url='+link,
          facebook:'https://www.facebook.com/sharer/sharer.php?u='+link+'&quote='+text,
          telegram:'https://t.me/share/url?url='+link+'&text='+text};
        for (const anchor of dialog.querySelectorAll('[data-share-platform]')) anchor.href = links[anchor.dataset.sharePlatform];
        if (!dialog.open) dialog.showModal();
      }
      if (event.target.closest('[data-share-copy]')) {
        try {
          await navigator.clipboard.writeText(shareText);
          status.textContent = 'Stats and library link copied.';
        } catch (_) {
          status.textContent = 'Copy is unavailable. Select the text above and copy it manually.';
          summary.focus?.();
          summary.select?.();
        }
      }
      if (event.target.closest('[data-share-native]') && typeof navigator.share === 'function') {
        try {
          await navigator.share({title: 'My DocoDive progress', text: shareText});
          status.textContent = 'Share options opened.';
        } catch (error) {
          if (error.name !== 'AbortError') status.textContent = 'Sharing is unavailable here. Copy your stats or choose a platform above.';
        }
      }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
