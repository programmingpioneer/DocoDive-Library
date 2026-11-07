# Reader login and community colour refinement

The standalone `/user/login` and `/user/signup` now use a Studio-style split layout: an indigo/teal library story with book artwork on desktop, and a compact form with a small brand header on phones. The home-page sign-in modal and Studio login remain separate.

## Delivered

- Inline SVG email, password, visibility and provider icons; readable 16px inputs; password visibility button; native email/required-field validation; password autocomplete; proper label associations.
- Link-based sign-in/signup tabs work without JavaScript. Enhanced tabs support Arrow Left/Right and Home/End, with synchronized selection, focus, headings and hidden panels. Normal modified link clicks retain their browser behavior.
- Signup retains existing POST names, CSRF and server rules. Names, username and email can be retained after a failed POST; passwords are never echoed into HTML. Desktop uses a compact two-column field arrangement; phones keep full-width username/email inputs.
- Password-reset, verification and expired-session flashes are now visible on this standalone page. They were previously omitted. Errors and flashes remain escaped and appear once.
- Availability checks are debounced, abort superseded requests, ignore late results and fail quietly when unavailable. Server `format_error`, `simple`, reserved and existing-name responses are advisory warnings rather than green success.
- Suggestions now use lilac composer surfaces, warm idea icons, rose support controls and green team-response markers. Leaderboard adds actual-rank gold/silver/bronze accents. Stats/profile metrics have coloured SVG tiles; profiles have an indigo/teal cover; milestones have blue, rose, amber and orange icons with teal earned-progress states.
- Related/saved/history/recovery book cards retain the completed shared geometry, with a richer fallback cover palette. Recovery screens receive matching indigo controls and helpful coloured icons. The existing nine milestone thresholds, measured metrics, privacy guards, card destinations and error status codes are preserved.

## When the login page appears

Existing protected routes redirect here when there is no signed-in reader session: for example Favorites, History, Stats, Settings, uploads, downloads and online reading. It also appears for direct visits, after signup verification instructions or password-reset/change redirects, and after authentication errors. A missing, expired or revoked session can lead here through those protected routes. Explicit reader logout currently returns home. This refinement does not change session expiry or diagnose a specific automatic logout.

## Verification

- **83 automated tests passed**, including all existing security, settings, consent, SEO, lifecycle and Studio checks. All templates parse; all 13 JavaScript files, including the service worker, pass syntax checks.
- New coverage verifies escaped/once-only feedback, initial signup state, native links/CSRF/password non-retention and **nine offline auth-control scenarios**. Regressions were observed failing before their fixes.
- **63 saved local browser observations** cover the eight primary page families at 320, 390, 768, 1024 and 1366px, plus errors, visitor privacy, repeated proof views and a 1366×600 short window. No horizontal document overflow was found. Three podium members remain present at all five widths.
- Login and signup fit 1024×768 and 1366×768. Phone login fits 390×844; at 320×640 it uses 144px of natural document scrolling. Five-field signup and short windows retain natural scrolling so fields and legal links remain reachable. Phone tab, recovery and legal targets measure at least 44px.
- Browser interactions verified keyboard tabs, password visibility, four earned sample achievements, session feedback and visitor email privacy. A preview-only comment endpoint was corrected to return JSON; all five detail widths were rechecked without new console errors.
- Fresh read-only review found no outstanding actionable issues. Its phone touch-target observation was corrected and browser-verified.

These browser checks used synthetic data on loopback port 5012. No configured application startup, credentials, TiDB, real email, provider authentication, real signup/posting, staging or deployment was used in this pass. No new package or database migration is required.

Evidence is in `deliverables/reader-login-colour/`; `browser-audit.json` records dimensions and `interaction-checks.json` records the interaction scope. The refreshed `deliverables/updated-source.zip` includes the earlier completed community/library work and this refinement. Restart the local app and refresh with Ctrl+F5 to load changed assets.
