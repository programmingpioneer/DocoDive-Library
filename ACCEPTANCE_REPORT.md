Latest reader regression fix (7 November 2026): [report](docs/READER_REGRESSION_FIX_REPORT.md). Restored original uploads/ PDF keys, prevented HTML/homepage responses from embedding inside the reader, and deferred catalogue-triggered reloads while a preview is open. Mobile toolbar/action alignment corrected. 219 isolated tests pass; local browser checks use sample data only. Browser file-save confirmation remains outstanding. No new dependency or migration. Restart and Ctrl+F5. Earlier entries below are historical.

Latest PDF/QR update (6 November 2026): [report](docs/PDF_QR_FIX_REPORT.md). Exact stored PDF keys, authenticated same-origin streaming/ranges, friendly storage failures and single download tracking; animated in-page QR shared by Book Details, Home and Learning Hubs. 214 isolated tests pass; local browser evidence uses synthetic PDF/QR only. No new dependency or migration. Restart and Ctrl+F5. Actual R2 authorization remains an owner check; no real storage, database or email accessed. Earlier entries below are historical.

Latest preview/reference and source organization update (6 November 2026): [report](docs/SCROLL_OVERLAY_REPORT.md). Wide Book Details style Quick Preview, desktop action row and horizontal review form, stacked phone layout, transparent side-center scroll arrows. Active learning templates live only under templates/user; 15 empty legacy folders removed, zero files deleted. 182 tests pass and ten stable light/dark responsive browser cases pass. Prepared for develop review; generated local artifacts/private backups excluded. Earlier migration instructions remain applicable.

Latest scroll-arrow correction (6 November 2026): [report](docs/SCROLL_OVERLAY_REPORT.md). Page and Quick Preview arrows now float at the right side, vertically centered, with transparent backgrounds and no reserved row/column. Eight focused checks and isolated light/dark responsive browser checks pass. Restart and Ctrl+F5; no new migration for this UI correction. Earlier entries below are historical.

Latest preview/reviews/newsletter/cleanup update (6 November 2026): [report](docs/PREVIEW_REVIEWS_NEWSLETTER_REPORT.md). Shared Book Details preview with top-center arrows, optional keyboard-searchable review books, compact book labels, milestone theme fix, and one automatic newsletter welcome attempt per normalized address. Apply the two owner-run SQL files in the report before using optional general reviews/newsletter welcomes, then restart and Ctrl+F5. Verified source backup precedes generated-cache cleanup; uncertain source/assets retained. No real database/email/staging/production accessed. Earlier entries below are historical.

Latest practice/text/loading update (6 November 2026): [report](docs/PRACTICE_READING_LOADING_REPORT.md). Fixed the real Python practice route crash; all practice pages have a shared responsive workspace and honest local activity/checklists. Home/menu/text contrast, equal About cards, phone-to-4K type, scroll arrows and page-owned history skeletons refined. Final 149 isolated tests and 97 synthetic renders pass; browser checks cover 27 page types and 14 practice entries in both themes. Restart and Ctrl+F5; no new dependency or migration. No configured integrations accessed in this pass.

Latest Learning Hub/Suggestions dark-mode fix: [report](docs/LEARNING_SUGGESTIONS_THEME_REPORT.md). Shared card/action colors, readable lesson labels and Suggestions state colors. 21 targeted tests and 97 synthetic renders pass; 60 learning tracks checked in each mode and both pages checked at five widths. Restart and Ctrl+F5. No new dependency or migration; no configured integration access in this pass.

Latest Reviews/history-loading fix: [report](docs/REVIEWS_NAVIGATION_REPORT.md). Readable Reviews in both modes, corrected shared heading backgrounds and each document’s own skeleton on initial loading and Back/Forward restoration. 145 isolated tests pass; 97 synthetic renders and responsive/history browser checks. Refresh with Ctrl+F5; no dependency or migration.

Latest Home card fix: [report](docs/HOME_VALUE_CARDS_REPORT.md). Equal card alignment, shared hover effects and a readable Report a concern button in both modes; 7 targeted tests and five-width browser checks passed. Refresh with Ctrl+F5.

Latest UI/theme/learning refinement (5 November 2026): [report](docs/UI_TOKEN_REFINEMENT_REPORT.md). Shared semantic colours, responsive Home/auth/legal/account pages, 60 learning templates, per-book previews and page-specific skeletons. 144 isolated tests pass; 97 synthetic renders and phone-to-4K browser checks. Restart and Ctrl+F5. No new dependency or migration for this pass. Real integrations and actual uploads remain owner checks. Earlier entries below are historical.

Latest upload/appearance/security update (4 November 2026): [report](docs/SITE_EXPERIENCE_REPORT.md). Responsive Upload a Book, modest homepage/popup polish, shared dark mode/skeletons and four source security fixes; 128 isolated tests pass. Browser evidence uses synthetic fixtures only. Restart and refresh; no new dependency/migration. Actual PDF/storage, TiDB/email/OAuth and staging were not tested in this pass.

Latest profile crash fix: [report](docs/PROFILE_QUERY_FIX_REPORT.md). Missing aggregate results no longer crash profiles or become fake zeros; 99 isolated tests pass. Restart the app; no new migration/dependency.

Latest Reviews/footer update: [report](docs/REVIEWS_FOOTER_REPORT.md). Redesigned Reviews, shared public footer and linked authors tile; 94 isolated tests pass and five responsive widths checked. No new dependency or migration.

Latest personal library/navigation update: [report](docs/READER_LIBRARY_NAVIGATION_REPORT.md). Modern Favorites, History, Preferences, social icons and smoother reader menus; 90 tests pass. No new dependency or migration.

Latest reader login and community colour refinement: [report](docs/READER_LOGIN_COLOUR_REPORT.md). Split reader login/signup, visible session feedback, stronger community colours and 83 passing tests. No new dependency or migration.

Latest community/library UI update: [31 October report](docs/COMMUNITY_LIBRARY_REPORT.md). Suggestions, Leaderboard, Stats, profiles, achievements, recommendation cards and recovery screens; 80 automated tests pass. No new dependency or migration for this pass.

Latest homepage, settings and notifications refinement: [31 October report](docs/HOME_NOTIFICATIONS_REPORT.md): 64 automated tests and five-width local sample-data browser checks.

Previous reader interface/settings update: [31 October report](docs/READER_INTERFACE_REPORT.md).

Latest public UI update (31 October 2026): [public interface polish report](docs/PUBLIC_UI_POLISH_REPORT.md).

# Local enhancement acceptance report

Latest detail-page and real integration checks: [Studio integration report](docs/STUDIO_INTEGRATION_REPORT.md). This later pass includes 45 automated tests and real TiDB/admin-OTP verification; older synthetic-only statements below are historical.

Latest UI pass: see [docs/UI_REFRESH_REPORT.md](docs/UI_REFRESH_REPORT.md) for browser-verified synthetic layouts, screenshots and limitations. The original report below is retained as the earlier implementation baseline.

29 October 2026. Implementation status and verification limits are separate below. No live/staging, credentials, real application startup or browser was accessed.

| Section | Implemented | Verified locally | Still needs your local integration check |
| --- | --- | --- | --- |
| Admin authentication | Password + mandatory hashed 6-digit OTP, 5-minute TTL, 3 attempts, 60-second cooldown, hourly/account/IP limits; Argon2 and legacy support; server sessions and role/password revocation | Service transactions, expiry, replay, limits, session checks and Flask login flow | Real email, MySQL locks, cookies behind your actual HTTPS proxy |
| Account deletion | Email OTP + reason, immediate session revocation, admin approval/cancel, 15-day restore, approved scheduled deletion, 30-day identity retention | Approval/deadline, restore, repeat-job safety, retention, missing/deleted-cookie rejection | Actual schema relationships and parallel MySQL transactions; destructive tests only on disposable local data |
| Emails | Styled signup welcome, deletion summary, restored and deleted emails; retryable lifecycle queue | Deduplication and retry with a synthetic sender | Real mailbox delivery and rendering; social welcome uses existing mail path |
| Dashboard / analytics | Real aggregate charts, clickable chart/table links, summary cards below charts, empty/error/retry states | Template render and JavaScript syntax | Chart library load, populated SQL results, chart click-through in browser |
| Users / tracking | User details, join/status/activity, detail pages, no main-list edit/delete controls; activity graphs and successful download-link tracking | Rendering and successful/failed download tracking regression | Real user data and query performance |
| Books / approvals | 9 per page, numeric pagination/counts, category-title-date order, cover/author, confirmation actions | Render and syntax; source query review | Populated pagination and approval/file workflows |
| Reviews / suggestions | All reviews with filters, inline official replies, reply display; suggestion volume/topics/status charts | Render, malformed reply validation and source review | Populated threads and all actions |
| Learning / settings / leaderboard | Shared Studio forms and save controls; public learning preview; rank/avatar/points and recorded weekly score change | Templates, daily snapshot behavior | Keyboard/hover behavior and visual layout |
| Public UI | Centered bounded auth and book modals, richer notifications, offline/error/unauthorized states, touch/focus/reduced-motion styles | Templates, JSON-LD and JavaScript syntax | 320/768/1024/1440/1920/2560+ widths, accessibility and actual frame rate |
| SEO / local HTTP | Canonical/social metadata, index policies, structured data and split sitemaps; explicit production HTTPS policy | SEO tests and local-LAN redirect regression | Search-engine indexing/ranking and browser redirect cache |

## Evidence and boundaries

38 automated tests pass. Tests use isolated Flask apps, in-memory SQLite with a MySQL syntax adapter, and synthetic data. SQLite strips FOR UPDATE; this does not prove concurrent MySQL locking. The real application is not imported by the suite. Static review issues were addressed before handover.

No browser layout, 60fps, actual network integration, production readiness or ranking guarantee is claimed. Activity starts on installation. Weekly change needs seven days of score history. Suggestion topics use submitted subjects because the existing data model has no category column. The details page uses real pending/deleted status; a pending request past its deadline cannot restore through login unless an admin cancels it.

## Required before running

Install updated requirements and apply migrations/20261029_studio_accounts.sql to your local database. See LOCAL_HANDOVER.md for exact order, local HTTP settings, the minute worker and the existing migration runner's multi-environment default. The agent did not run SQL against any database except the in-memory test fixture.
