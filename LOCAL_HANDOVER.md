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

Latest homepage, settings and notifications refinement: [31 October report](docs/HOME_NOTIFICATIONS_REPORT.md). Includes the disclosed starting counter and labeled sample reviews. No new dependency or migration is needed for this refinement.

Previous reader interface/settings update: [31 October report](docs/READER_INTERFACE_REPORT.md).

Latest public UI update (31 October 2026): [public interface polish report](docs/PUBLIC_UI_POLISH_REPORT.md).

# DocoDive — local handover

Latest detail-page and real integration checks: [Studio integration report](docs/STUDIO_INTEGRATION_REPORT.md). This later pass includes 45 automated tests and real TiDB/admin-OTP verification; older synthetic-only statements below are historical.

Updated: 29 October 2026

**Latest visual refresh:** Studio sign-in/dashboard and shared management styling now follow the supplied Stitch reference. Public auth returns to a compact original-style card, and Learning Hub blue borders are removed. Browser checks on an isolated synthetic preview are recorded in [docs/UI_REFRESH_REPORT.md](docs/UI_REFRESH_REPORT.md). Earlier statements about browser testing below describe the previous handover, not this later UI pass.

## Run karne ka tareeqa

Is version mein **naya package aur database migration required hain**. Existing local configuration use karein; credentials/environment files change ya read nahi ki gayin.

1. Active local virtual environment mein `python -m pip install -r requirements.txt` chalayein. Naya password package `argon2-cffi==25.1.0` hai.
2. Sirf apne **local test database** par `migrations/20261029_studio_accounts.sql` apply karein, apne existing local SQL tool se. Is mein security, deletion, mail, activity aur leaderboard tables banti hain; existing user records delete nahi hote. Agent ne migration execute nahi ki.
3. PowerShell mein `$env:FLASK_ENV="development"`, phir `python app.py`.
4. Browser mein **http**://127.0.0.1:5000 kholein. Cached HTTPS redirect ho to private window use karein.

Existing `scripts/run_all.py` bina arguments staging + production target karta hai, is liye local testing ke liye usay bare command se na chalayein. Nayi SQL `all_changes.sql` mein bhi included hai for your own later deployment workflow.

Detailed section status: [ACCEPTANCE_REPORT.md](ACCEPTANCE_REPORT.md).

User website: `http://127.0.0.1:5000/`

Admin Studio: `http://127.0.0.1:5000/admin-studio/login`

Studio mein existing verified official account ka email/password **aur mandatory 6-digit email OTP** use hoga. Email service ke baghair OTP bypass available nahi hai. Existing `site_settings.official_user_id` owner ko identify karta hai. Normal website login Studio access create nahi karta. Owner Studio ke Users section se doosre verified accounts ko admin bana sakta hai. Owner transfer ke baad purane owner ka access khatam ho sakta hai agar woh separately admin list mein nahi hai.

## Kya change hua

- Admin Blueprint aur independent Studio session; dedicated sidebar, dashboard, upload, approvals, books, users/roles, reviews/comments, suggestions, leaderboard adjustments, official account aur editable content pages.
- Public navigation se admin controls remove; public login/logout aur Studio login/logout alag identities preserve karte hain.
- User/admin templates alag folders mein. Scoped responsive styling, mobile form sizing, keyboard focus, readable leaderboard, shared catalogue previews, toast styles aur safe text rendering.
- Home/About aur Learning Hub titles, introductions aur module box text Studio se edit hota hai; blank values original content use karti hain.
- AJAX requests par CSRF bypass remove; same-origin CSRF transport, bounded review/comment text, parent-comment validation, Google callback state check, session-sensitive responses par no-store.
- Admin deletions mein dependent records handle hote hain. Book file cleanup successful database update/delete ke baad hoti hai. Storage failure server log mein record hota hai; database aur external storage ek atomic transaction nahi hain.
- Admin lists, public reviews aur suggestions paginated hain; feedback likes per-row queries se batch queries mein badle gaye. Default categories ek read se check hoti hain.

## Files ki structure

```text
app.py                 Flask setup, public routes, existing integrations
learning_content.py    68 original learning data collections
seo.py                 Metadata policy, canonical URLs, robots and split sitemaps
admin/
  admin_routes.py      Existing administrative workflows and legacy URL redirects
  security.py          Studio identity and role guards
  studio.py            Studio login, user editing and content/settings pages
templates/user/        Public pages and original lesson subfolders
templates/admin/       Studio-only pages and layout
static/css/            Existing styles plus user.css, admin.css, toast.css
static/js/             Existing scripts plus csrf.js, user.js, admin.js
tests/                 Isolated automated regression tests
```

`app.py` se learning data aur admin/account services separate modules mein nikal diye gaye hain; pehle file taqreeban 19,000 lines thi. Learning data ko separate karne ke baad tamam 68 collections ka original source se AST comparison pass hua. Python implementation aur test files format ki gayi hain.

## SEO

- Public book/catalogue titles, descriptions, canonical links and social previews updated.
- Paginated catalogue URLs apna page number preserve karte hain; search/filter variants aur private routes par noindex policy hai.
- Home WebSite/Organization data aur book structured data use hota hai; DocoDive ko har book ka publisher kehne wala inaccurate field remove hua.
- `/sitemap.xml` ab sitemap index hai; `/sitemaps/pages.xml` public/learning pages deta hai; books 5,000 URLs ke chunks mein hain. Sirf approved books include hoti hain. Old IELTS URLs canonical learning pages ko redirect karte hain.
- `robots.txt` assets ko crawl karne deta hai aur sitemap expose karta hai. Private access authentication se protected hai; noindex crawl access ko authorization ka badal nahi samajhta.
- Optional non-secret `PUBLIC_SITE_URL` preferred public origin set kar sakta hai, jaise `https://your-domain.example`. Iske baghair current request origin use hota hai. Local test mein localhost URLs expected hain. Is setting ki existing configuration mein koi tabdeeli nahi ki gayi.

Technical changes ranking guarantee nahi hain. Content quality, indexing aur competition bhi matter karte hain. Guidance: [Google SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide) aur [Google sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap).

## Mere local checks

- **38 automated tests passed** using isolated Flask clients, synthetic responses and in-memory SQLite transactions.
- Mandatory OTP, expiry/replay/binding/attempt caps, persistent rate limits, server session revocation, legacy-to-Argon2 password handling, deletion approval/deadline/restore/retention and mail retry covered.
- Welcome email deduplication, daily score snapshots and successful-only download tracking covered.
- 13 Studio pages and 7 public pages render with sample data; all HTML templates parse. Inline and static JavaScript syntax checked with Node. Python source syntax checked without importing the real application.
- Fresh review findings about deleted cookies, concurrent login and password bounds corrected; regression tests included.
- Real MySQL locks/concurrency/schema compatibility, browser visuals/FPS, actual app startup, external storage/OAuth and real email delivery **not run**. No live/staging access.

Repeat automated checks, existing dependencies installed hon to:

```text
python -m unittest discover -s tests -v
```

Node available ho to tests inline JavaScript syntax bhi check karte hain. Test code real database, secrets ya network use nahi karta.

## Aapki final local checklist

- [ ] `python app.py` starts; home, books, book detail, Learning Hubs/modules, reviews, suggestions, leaderboard, profile, uploads, history/favourites aur settings khulti hain.
- [ ] Guest, ordinary user aur official account ka normal login: public site par admin navigation nahi aati; direct Studio URL separate login mangta hai.
- [ ] Owner Studio login works; normal user reject hota hai. Dono logins saath use karein; ek taraf logout doosri identity ko remove nahi karta.
- [ ] Studio lists/search/next/previous; book upload/edit/cover/PDF replacement; approve/reject; delete; user edit and role grant/revoke. Destructive checks disposable local data par karein.
- [ ] Reviews/comments ke official replies aur delete; suggestion reply/edit/remove/delete; leaderboard adjustment; settings save karke public content verify karein.
- [ ] Public search/preview, review/comment/reply/like, favourites, newsletter, upload, download/read, auth/reset aur notification buttons check karein. Expired login/form token ka error bhi check karein.
- [ ] Widths **320, 360, 390, 768, 1024, 1440, 1920, 2560 px** par navigation, tables/cards, forms, modals aur long text check karein. Keyboard Tab/Escape aur reduced-motion setting bhi check karein.
- [ ] `/robots.txt`, `/sitemap.xml` aur child sitemaps kholein; canonical URL/description source mein dekhein; book JSON-LD valid ho aur private pages noindex hon.
- [ ] Existing external integrations ko apne local setup se verify karein. Error mile to exact traceback aur affected page/file share karein.

Source working folder mein directly updated hai. `deliverables/updated-source.zip` mein complete changed/new source files, moved templates, tests aur yeh guide hain; diff snippets nahi. Existing secrets, database contents, unchanged assets aur dependencies bundle mein nahi hain. Original root templates `templates/user/` ya `templates/admin/` mein relocate hui hain. User ki pehle se deleted `fly.toml` file ko restore/change nahi kiya gaya. Koi commit, push ya deployment nahi hua.

## Local LAN HTTPS fix (29 October)

Local LAN addresses no longer trigger production HTTPS redirects. HTTPS enforcement, HSTS and secure session cookies now use the explicit FLASK_ENV production setting. For local HTTP testing, set `$env:FLASK_ENV="development"` in PowerShell before `python app.py`. Open `http://192.168.1.9:5000` in a private window if a previous permanent redirect is cached. Eight targeted security tests, including LAN and production redirect cases, pass. Pip update and local in-memory rate-limit notices are not startup failures.

## Account deletion and maintenance

- User verifies registered email by OTP and supplies a reason; all their sessions are revoked immediately.
- Restore by login is allowed strictly before request time + 15 days. At/after the deadline, an unapproved request stays pending until an admin approves or cancels it. Approval never restarts the grace period.
- Only approved, elapsed requests are removed by server maintenance. Admin/owner accounts must transfer/remove their role first.
- Recently Deleted retains name/email for 30 days after deletion, then purges. Shared uploaded books remain with no uploader; personal records are removed.
- `python app.py` starts a local minute worker. A production WSGI process needs an externally scheduled `flask --app app account-maintenance` every minute; this scheduling is your deployment responsibility. The job can delete approved, elapsed local requests, so use disposable accounts for tests.
- Lifecycle emails use a leased retry queue. Delivery is at-least-once: a worker crash after provider acceptance can produce a duplicate. OTP delivery is immediate, codes are hashed and never queued as plaintext.
- Weekly score history starts with the update; no fabricated historical trends. Activity means page responses/reading opens/download links issued, not verified reading time or completed downloads. Suggestions have subjects, not a category field; topic charts group those subjects.
- The existing general Flask-Limiter in-memory development warning is separate from the new persisted Studio authentication limits. Production general limiter configuration remains part of your environment.
