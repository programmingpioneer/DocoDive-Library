Later reader-login and colour refinement: [current report](READER_LOGIN_COLOUR_REPORT.md). Includes 83 passing tests and 63 current synthetic-browser observations. The completed library/community behavior below is retained.

# Community and library interface — 31 October 2026

Suggestions, Leaderboard, My Library Stats and reader profiles now share indigo/slate styling, SVG icons, responsive cards and useful empty states. Book recommendations and recovery pages follow the same library presentation.

## Delivered

- **Suggestions:** collapsible idea composer, labeled fields with the existing 200/5,000-character bounds, search and All ideas/Team replied filters, response markers, support buttons and expandable discussions. Filters apply to the current pagination page. Discussions load on demand, avoiding a request per suggestion at page load. Existing reply/edit/delete/ownership/moderation endpoints are preserved. Failed votes leave counts unchanged; edit handlers receive the click event explicitly. Failed or redirected updates report errors. Discussion visibility and expanded state stay in sync.
- **Leaderboard:** contributor cards, current standing, contribution details, milestone counts and a points guide. Tied scores share a rank. Current-user ranking excludes orphan points and the configured official account consistently with the public list. One/two-person states do not create empty podium people. Comparison changes identify the recorded snapshot; missing history is not fabricated.
- **My Library Stats:** recorded downloads, favorites, reviews and streaks; current activity mix; next milestone; shortcuts; share dialog; and a native radio selector for eligible display badges. Removed the unsupported reading-hours estimate. Badge choices save only on submission.
- **Profiles:** cover/identity layout, contribution metrics, account facts, social links and the shared achievement panel. Owners receive Edit profile, Settings and their private email. Other visitors do not receive that email or owner controls in the rendered HTML. Official profiles have a separate community state. Stored badge values remain compatible and use matching SVG milestone icons.
- **Achievements:** the same nine existing thresholds drive Stats, profiles and leaderboard milestone counts. Correct unlocked totals, bounded progress, remaining targets, next goal and All/Unlocked/In progress filters replace duplicated calculations. The server continues validating badge selection against eligible legacy tokens.
- **Books:** Related Books, 404 recommendations, Favorites and History use `user/_book_card.html`. Covers retain 180px desktop/160px phone frames; titles, authors, metadata, rating/date, actions and counts have fixed slots. Blank titles and missing covers have safe fallbacks. History retains Download; the other lists have Details/Preview. Missing count data is unavailable rather than an invented zero.
- **Recovery:** 400/401/403/404/429/500/503 and connection screens share readable recovery actions and help/legal links. Only 404 queries recommendations. Presentation settings fall back safely during an outage; route authorization helpers are unchanged. Status codes and noindex behavior are retained.

## Verification

| Check | Result |
|---|---|
| Full isolated suite | **80 tests pass**; final focused discussion/controller checks also pass |
| Offline UI controllers | 35 scenarios across consent, notifications, community sharing/filters and suggestion voting/editing, included through the suite |
| Templates / syntax | All **138 templates** parse; **12 JavaScript files including the service worker** pass syntax checks; changed Python sources parse |
| Profile / badges | Owner/visitor privacy, forged locked-badge rejection and acceptance of eligible existing tokens verified |
| Rankings | Isolated real route with disposable SQLite verifies ties, orphan points and official exclusion |
| Recovery responses | Isolated HTTP 400/401/403/404/429/500/503 retain status/noindex. The 404 test includes the real common presentation processor with failing settings accessors |
| Browser | **65 observations over 18 page families**. Six principal screen families at 320/390/768/1024/1366px; additional catalogue/learning/saved/history comparisons and empty/visitor/official states |
| Card geometry | Home/catalogue/learning: covers 160/180px, action offsets 287/308px. Related/404/Favorites/History: covers 160/180px, offsets 288/309px due to the card border. Cards within each row align |
| Actual UI actions | Achievement filters, share-dialog opening/closing, suggestion search/empty search, Team replied filter, loaded discussion and 404 Preview/Close verified |
| Review | Independent read-only review findings on rank population, error context and loading styles were fixed and rechecked |

Browser testing caught a layout attribute colliding with the existing count-up animation, which could replace podium cards with a number. The attribute was renamed and all five widths rechecked. Two superseded observations remain marked in the raw audit. Final settled views have no document overflow. Other recovery screens were checked both with optional supplied books and with their normal book-free context.

Screenshots and `browser-audit.json` are in `deliverables/community-polish/`. Browser records are synthetic fixtures served on loopback. Source behavior was tested against disposable data. No real suggestion/reply posting, votes, badge saves, downloads, deletions, email sends, credential access, staging/live access or deployment occurred. Earlier TiDB/email results remain historical.

## Local handover

The workspace is updated. `deliverables/updated-source.zip` includes updated source and evidence; hashes are in `deliverables/manifest.json`. No new package or migration is needed for this UI pass. Restart the app and use Ctrl+F5. Check `/feedback`, `/leaderboard`, `/user/stats`, a reader profile, Related Books and an unknown URL for 404. The disposable preview is stopped after verification; the user's server is left untouched.
