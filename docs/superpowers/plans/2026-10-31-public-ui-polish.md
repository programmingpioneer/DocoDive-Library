# Public UI polish implementation plan

User direction: keep the existing public design and carousel animation. Hide visible scrollbars while preserving scrolling, remove carousel dots, align book covers/text/actions, remove modal background blur, and replace blue search focus rails with a neutral focus treatment. Apply the shared changes across public pages and verify desktop and narrow viewports.

- [x] Give the existing book cards semantic layout slots and fixed cover space, with two-line titles and one-line authors.
- [x] Remove only the generated carousel indicator controls; retain autoplay and swipe.
- [x] Scope invisible scrollbars to public dialogs, menus, suggestions and horizontal strips; retain overflow and keyboard access.
- [x] Use opaque modal surfaces, a dim unblurred backdrop, readable auth type and neutral search focus.
- [x] Verify actual browser layout and scrolling at desktop/mobile widths, parse templates/JavaScript, run existing isolated checks, update the handover archive.

Use the existing Flask/Jinja/Bootstrap stack. No database, credentials, dependency or deployment changes are needed. Short windows and zoom must retain access to every form control.
