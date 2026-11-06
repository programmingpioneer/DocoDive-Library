# Side-center transparent scroll arrows

6 November 2026. This corrects the earlier top-center placement to the user's latest request.

Page arrows now float at the right side, vertically centered in the viewport. Quick Preview arrows use the same vertical pair, absolutely positioned at the right center of the popup. Both wrappers and buttons have transparent backgrounds and no box shadow or visible button border. Only the icon, hover color and keyboard focus outline remain; touch targets stay 44px. A subtle icon-only shadow helps readability across underlying content.

The page controls are fixed and the popup controls are absolute, so they reserve no column or row and do not resize the page. Pointer events pass through the gap between the buttons. Popup arrows scroll only the popup; page arrows scroll the document. Existing boundary hiding/disabled states, reduced motion and focus return are retained. Short previews hide the pair when no scrolling is needed.

Changed application files: `static/css/reading-controls.css`, `static/css/preview.css`, `static/js/user.js`, asset versions in `templates/user/base.html`, and service-worker cache version v1.0.20. The existing preview markup regression now checks the overlay sibling instead of header placement. No backend or database change was made in this correction.

Verification: eight focused tests pass (five preview, one page-scroll, two design-token tests), both CSS files parse, and shared JavaScript syntax passes. Isolated browser fixtures checked page controls at 320/390/768/1366/3840 pixels in both modes, popup controls at 320/390/768/1366 in both modes, and the 4K fit/visibility case. Visible controls measured within one pixel of vertical center, with transparent computed backgrounds and no shadows. The modal body remains a direct full-width sibling; no side frame exists. Clicks in the overlay gap reach the underlying content. Both page and popup scrolling were exercised. Evidence is under `deliverables/scroll-overlay/`.

Only synthetic loopback fixtures were used; the user's configured app, database, email, staging and production were not accessed. Temporary viewport settings were reset and the fixture server stopped. Restart and Ctrl+F5. There is no new SQL for this UI correction; earlier optional-review/newsletter migration instructions still apply to those earlier features.

## Latest Book Details reference alignment

The shared Quick Preview now matches the supplied Book Details reference: a wider desktop dialog (up to 84rem), cover/details in a 1:2 grid, five distinct token-based pill actions on one row at wide desktop widths, a star Reviews heading and a horizontal Rating/Comment/Submit form. Existing feedback follows the form. Phones stack the content, actions and form. Transparent right-side vertically centered arrows remain overlays with no reserved column. Public Book Details itself remains unchanged.

Final pre-publication verification: 182 isolated tests pass (146.277s). Browser fixtures cover 320/390/768/1366/3840 pixels in each theme; final stable observations fit the viewport without horizontal overflow. Desktop actions share a row and the form precedes existing feedback. Earlier resize/entry-transition samples are retained in local evidence; final settled observations replace them for acceptance. All checks used synthetic local data, not the configured application or real services.

The 15 empty legacy Learning Hub folders were removed without deleting any files. Active templates are under `templates/user/`, `templates/admin/` and `templates/shared/`. Tests remain separate in `tests/`. Source and tests are prepared for develop review; generated deliverables, backups, environment files and the legacy local migration runner are excluded. The pre-existing `fly.toml` deletion is deliberately left uncommitted. Approved account/review/newsletter SQL migrations remain in `migrations/` for the owner's manual application; none was executed here.
