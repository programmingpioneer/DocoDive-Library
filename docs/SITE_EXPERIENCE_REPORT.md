# DocoDive local update — 4 November 2026

Upload a Book has a new responsive form and submission history. The homepage retains its sections, collections, counter disclosure, reviews and animated illustration. Its spacing and compact login popup are refined. Public, reader, recovery, learning and Studio layouts now share a light/dark appearance control and loading skeletons.

## Interface changes

- **Upload a Book:** PDF chooser/drop zone, selected-file details/removal, optional cover with local preview/removal, category selection, a submission summary, review guidance and authors' rights links. Desktop uses a form and guide column; phones stack the content. Long filenames/titles wrap. The native multipart form remains available without JavaScript.
- **Upload feedback:** real transfer progress, with 100% reserved for transferred bytes rather than completed server processing. Success appears only after a confirmed successful response. Failed requests retain the files/category; duplicate submits are blocked. History supports Refresh, empty/error/expired-session states and safe text rendering.
- **Homepage:** existing layout and content retained, with small width/spacing/type adjustments. The search remains compact; the heading, illustration, categories, book collections and About/footer remain in place.
- **Login popup:** compact single column, readable labels and 16px fields, consistent SVG icons, login/signup switching, password visibility and a close control outside the scrolling content. Scrolling remains usable while its scrollbar is hidden. Small-phone signup necessarily scrolls to keep every field and link reachable.
- **Appearance:** a sun/moon control in the top navigation, Studio header and standalone pages. The OS preference is used until the reader chooses light/dark. Explicit preference is saved locally and follows navigation/reload; storage failures have a usable fallback. Open tabs can follow preference changes. Cookie policy now discloses this local setting. It does not enable optional analytics or support widgets.
- **Dark surfaces:** page backgrounds, forms, cards, dropdowns, account/settings pages, books, legal/recovery pages, learning lessons/code, Studio tables and chart labels/grids. Covers, photos, logos and PDF contents are preserved. Browser checks found and corrected white Quick Preview/Studio panels, the homepage's white fade/About background, and low-contrast learning statistics.
- **Skeletons:** one shared page shell in all eight document-owning templates; actual async skeletons for notifications, upload history and both homepage/shared book previews. Pending cover images get a placeholder. Artificial minimum loader delays were removed. Reduced-motion, error, cancelled-confirmation, download, back-navigation and no-JavaScript handling are included.
- **Responsive correction found during checks:** Upload's flex heading no longer collapses into a narrow text column at 320px. Mobile Apps' advanced lesson no longer expands its grid to a long code example's intrinsic width; examples remain readable within the page.

Existing native field names, CSRF, upload/auth endpoints and moderation remain. Account deletion still requires admin approval and the 15-day grace period; recently deleted identity retention remains 30 days. No new dependency or database migration is required for this update.

## Security changes

The local source audit inventories 153 explicit Flask route registrations, including 30 API paths. Four concrete boundaries were fixed and independently reviewed:

1. New PDF/cover storage keys include a random suffix, preventing same-title uploads from overwriting an existing object before moderation. Duplicate checks now handle borrowed cursors correctly and stop on database errors.
2. The public book API returns the authenticated local download route instead of a raw PDF storage address.
3. Brevo's webhook rejects requests when authentication is not configured and checks configured authentication in constant time.
4. New email-based Google/GitHub account linking requires a verified provider assertion, rejects replacing a different existing provider binding, and checks conditional-update races. First-time Facebook identities cannot automatically attach to an existing same-email account; existing bound provider identities still sign in.

See [the source security report](SECURITY_SOURCE_REVIEW_2026-11-04.md) and [route inventory](../deliverables/site-experience/security-route-inventory.json) for classifications, regression evidence and limits. This is source review and isolated regression testing, not a live penetration test or a claim that every possible vulnerability is absent.

External storage policy and historical public PDF URLs were not verified or revoked. The existing Facebook deletion callback is still an acknowledgement stub, not deletion processing. The report also records the limits of third-party verified-email assertions and the existing account-availability enumeration behavior. No credential values or cloud permissions were inspected or changed.

## Verification evidence

| Check | Result |
|---|---|
| Full isolated Python/Node regression suite | **128 tests passed**, 93.747 seconds |
| Synthetic public/lesson rendering | **93 successful renders**, zero failures |
| Jinja source parsing | **149 templates parsed** |
| JavaScript syntax, without execution | **20 static scripts + 376 rendered inline scripts parsed** |
| Browser | **132 observations**, 108 latest URL/width/theme measurements; no final horizontal overflow |
| Current browser tab console | **0 errors** captured |
| Upload widths | **320, 390, 768, 1024, 1366px**; final heading width at 320px is 214px |
| Other browser coverage | 36 reader/public page states at phone and desktop sizes; six lesson families; 14 Studio sections on phone; Studio overview/analytics/verification desktop; popup login/signup in both appearances |
| Diff whitespace | `git diff --check` passed |

Upload-controller tests exercise 23 synthetic scenarios, including local previews, validation, duplicate submits, progress at 99.5%, 401/413/network/malformed responses, retries and stale history. Shared/home preview regression tests cover stale successes and failures, including reopening the same book. Appearance tests cover OS/manual/cross-tab/blocked-storage behavior and loader recovery. Security suites include five storage and eleven callback tests.

Browser evidence is in [site-experience](../deliverables/site-experience/): screenshots, [observations](../deliverables/site-experience/browser-checks.json), [render/source audit](../deliverables/site-experience/render-audit.json) and [test log](../deliverables/site-experience/unit-tests.log). Early observations and their actual theme/URL fields are retained; the JSON's latest measurements reflect corrected layouts. A global width check does not replace checking every individual control, assistive technology or device.

### Testing limits

The browser used a disposable synthetic server at `127.0.0.1:5012`. It did not import configured `app.py`, read `.env`/credentials, access the user's server on port 5000, or contact real TiDB, email, OAuth, object storage, Sentry, staging or production. Preview cookies use a distinct name. All people, records and responses in this pass's screenshots are sample fixtures.

Chrome extension file selection was blocked by its **Allow access to file URLs** requirement. That permission was not changed. No real PDF upload or end-to-end storage transfer was performed. File-selection, preview, validation and transfer/error behavior were checked with isolated synthetic tests. The ordinary native picker and actual upload remain part of the owner's local final run.

## Local handover

The source files are updated in place. Restart the app and refresh the browser to load the new shared assets; the public static-cache version is also incremented. Open Upload a Book and try a permitted PDF, optional cover, approval status and a failed/retried request against your own configuration. Check the top sun/moon button and account/login popup on your phone. Staging and deployment remain the owner's final gate.

The refreshed `deliverables/updated-source.zip` includes prior source work, these changes, tests and reports, with a SHA-256 manifest. It excludes environment files, credentials, private keys, database backups and member exports. No commit, push or deployment was performed.
