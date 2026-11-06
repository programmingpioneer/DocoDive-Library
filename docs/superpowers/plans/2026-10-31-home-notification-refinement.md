# Homepage and notification refinement

User direction: restore default review cards, reduce stat-card text, use a 273,839 starting display counter plus real accounts, align the notification bell, compact the search box and improve Settings/Notifications with consistent icons.

- [x] Add a clearly disclosed display counter separate from measured account/activity totals, and sample review fallbacks that never enter the database or ratings aggregates.
- [x] Compact homepage search/stats, preserve review fading, replace the bell with a centered SVG button and extend the shared icon set.
- [x] Restyle Settings around icon headings/shortcuts without changing password, CSRF or deletion behavior.
- [x] Rebuild the notification inbox with filters, accessible controls, and success/failure handling that preserves unread state on failed requests.
- [x] Run isolated behavior tests and browser checks at phone/desktop widths; source bundle, screenshots and report are included in the handover.

Keep changes local. No real notification deletion, credential change, email send, account deletion, staging or deployment action is needed. Demo testimonials remain visibly labeled; the starting counter must not be described as measured monthly visitors.
