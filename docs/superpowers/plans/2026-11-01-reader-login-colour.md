# Reader login and community colour implementation plan

> Use superpowers:executing-plans for inline implementation. User has delegated design, local edits and verification in this existing checkout; do not create a worktree, commit or deploy.

Goal: replace the tall standalone reader login/signup with the requested Studio-style split layout, and give the recently completed community screens stronger, coherent colour.

Architecture: retain Flask routes, POST names, CSRF and server validation. Replace only user/auth.html presentation with scoped reader-auth.css and reader-auth.js; leave the homepage modal and Studio authentication separate. Reuse inline SVG icons. Keep recovery CSS independent.

Constraints: local source only; no app.py import, .env, TiDB, email, actual account submission or staging browser access. Synthetic preview on loopback only. Natural document scroll on short screens; never clip a form to achieve a no-scroll screenshot. Desktop login should fit 1366x768; phone login should fit or need only short natural scrolling, with at least 44px controls and 16px inputs.

- [x] 1. Reproduce missing standalone flash feedback with an isolated render test. Cover escaped errors, correct initial signup panel, CSRF and password non-retention. Implement a split brand/story and compact form, useful links, inline password toggle, native validation, and accessible link-based tabs with no-JS fallback.
- [x] 2. Extract standalone controls into reader-auth.js. Test keyboard tabs/password visibility and debounced availability responses, especially stale replies and failures. Existing API remains authoritative; availability is advisory.
- [x] 3. Restyle community.css and suggestions.css with indigo/teal/amber accents, readable dark headings, meaningful metric and achievement icon colours, gold/silver/bronze podiums, and a richer profile cover. Preserve geometry, measured metrics, privacy and links. Bump only touched asset versions.
- [x] 4. Run focused tests, all existing tests and JS syntax checks. Browser-check synthetic login/signup/errors and four community screens at 320,390,768,1024,1366px, plus 1366x600. Exercise tab keyboard navigation and password toggle using synthetic fields only. Save real screenshots and an audit.
- [x] 5. Obtain one fresh read-only review (executing-plans final review). Address significant findings, refresh report and source ZIP with verified hashes, stop only the owned preview server.

Review focus: flash feedback appears once and is escaped; inactive forms are hidden without stranding no-JS users; tab keys and click paths keep ARIA/title in sync; late availability responses never overwrite a new value; all fields/actions remain reachable at small heights; social sign-in/real authentication are not exercised in the preview.

Pre-flight: template data attributes/IDs are consumed by the new controller; tests and browser fixtures must use that same contract. Colour changes consume existing community class names without changing the calculation helpers.

Verification: 83 tests passed (48.349s), including escaped/once-only flashed feedback, correct initial signup state, password non-retention and nine offline auth-control scenarios. Three initial regression failures were observed before implementation; API format_error/simple flags were separately reproduced RED then corrected. A fresh read-only reviewer found no Critical/Important issues; the 44px phone target observation was fixed and verified in the browser. No outstanding findings.

Scope ruling: real authentication, account creation, providers, database and email remain unchanged and outside this synthetic preview pass; their final integration test is user-owned. This is a UI refinement in the authorized existing checkout, with no dependency, schema, commit, deployment or session-lifetime change.
