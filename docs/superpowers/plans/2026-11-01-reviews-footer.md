# Reviews and footer implementation plan

> For agentic workers: use executing-plans and verify each task locally.

**Goal:** Improve the Reviews page, homepage footer and authors-rights tile within DocoDive's existing colours and SVG system.
**Architecture:** Scoped review assets, the existing shared footer, and a homepage-only feature row. Keep routes, server review data, pagination, newsletter consent/CSRF and cookie controls.
**Tech stack:** Flask/Jinja, Bootstrap 5, native JavaScript and existing SVG icons. No new dependency or migration.

## Constraints and decisions

- User has already requested autonomous edits in this working folder; no additional design approval, branch, commit or deployment.
- Synthetic loopback preview only; never import configured app.py, connect to TiDB, send email or submit real reviews/newsletter requests.
- Mobbin search refused the paid plan requirement; continue source-based design without claiming Mobbin evidence.
- Reviews currently silently submit against the first book. Make the existing book choice visible and required, preserving the existing POST endpoint.
- Existing category scores have no backing input. Preserve the five topic labels as review prompts without inventing topic ratings.
- Footer is shared; use the same treatment across public pages, preserving every existing destination and cookie action.

## Review focus

- Long names/comments/titles wrap at 320px without horizontal scrolling.
- Zero reviews and zero available books remain understandable and safe.
- Review submission errors/expired sessions retain the text and allow retry; success alone reloads.
- Rating uses native keyboard-accessible radios; reduced-motion settings are respected.
- Newsletter email field stays labelled, required and CSRF-protected; no automatic submission or changed subscription behavior.

## Tasks

- [x] 1. Reviews: test explicit book selection, empty states, escaping, star-radio semantics and submission failure handling. Rebuild templates/user/reviews.html with static/css/reviews.css and static/js/reviews.js. Run focused tests.
- [x] 2. Footer/rights: reshape templates/user/_site_footer.html and footer rules in static/css/site-shell.css; keep links and newsletter form. Update homepage feature row with SVGs, equal tiles and linked authors tile.
- [x] 3. Verify: full offline suite, JavaScript syntax, all Jinja templates; local browser at 320/390/768/1024/1366 widths, reviews modal and empty/guest states, homepage rights/footer. Save screenshots, report and refreshed source ZIP.

## Progress

Source read. Review flow and footer contracts identified. Plan proceeds under existing user authorization.

Completed: 94 tests pass; 17 JS syntax checks; 143 parsed templates; 18 browser observations across five widths and three extra states. Independent review has no actionable findings. Scoped overrides resolve legacy wide-dialog, font-size, focus and submit-button rules. No new migration/dependency or configured-service test.
