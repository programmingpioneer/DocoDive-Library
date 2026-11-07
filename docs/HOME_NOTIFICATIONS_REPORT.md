# Homepage, settings and notifications refinement — 31 October 2026

Later UI pass: [Community and library report](COMMUNITY_LIBRARY_REPORT.md).

This pass addresses the latest screenshots: oversized search and statistic cards, missing default reviews, an elevated notification bell and inconsistent account controls.

## Changes

- Homepage search is 54px high with a 44px submit button. Desktop has a single-line Search label; phones use the labeled SVG search button. Focus is indicated around the form, without the inner rectangular outline. Clear/search suggestions retain their existing behavior.
- Statistic cards have equal height and short labels. The requested display counter is **273,839 plus the current registered account count**; two accounts therefore display **273,841**. Its label is **Users counter**. An accessible information disclosure explains the starting value and that it is not measured monthly traffic. Actual registered-account and 30-day activity metrics remain separate and unchanged. The existing five-minute aggregate cache still applies.
- When there are no submitted reviews, three visibly labeled **Sample review** cards appear in the existing fading carousel. They have generic Sample reader names and no fabricated customer identities, photos or rating stars. Real reviews replace them as soon as available through the existing homepage cache. Samples never enter the database or review/rating totals.
- The bell is a real 44px button with an inline SVG, centered with the profile control. Its badge stays within the button. The seven profile-menu icons now use the same SVG system, as do catalogue/search/filter controls, Settings and notification preferences. Existing book Details/Preview controls keep their shared SVGs.
- Settings uses icon headings, a clear section menu and preference shortcuts. Password change, email recovery, CSRF protection and the existing verified deletion workflow are preserved. The deletion deadline and administrator approval requirements remain visible before submission.
- Notifications now has unread/total counts, All/Unread/Library/Community filters, matching type icons, explicit Mark read and Delete controls, an empty state and feedback for updates. Phones use a two-column filter layout and place row actions below the message. Read/delete requests change the screen only after a successful, non-redirected JSON confirmation. Errors preserve unread indicators and messages. Deletion still requires confirmation. CSRF and account ownership checks remain in place.

## Verification

- **64 isolated automated tests pass.** New checks cover the counter/sample separation, read-only homepage aggregates, review replacement and the production notification controller. The latter runs **8 offline JavaScript behavior scenarios**: failed bulk requests, sign-in redirects, network failure, successful read with CSRF, bulk endpoint behavior, canceled deletion, successful deletion and local filters. Existing consent, account-security, lifecycle, template and metadata checks also pass.
- **26 browser observations across 8 page families** using the local sample-data preview. Home, Settings and Notifications were checked at **320, 390, 768, 1024 and 1366 CSS pixels**. Catalogue, book detail, profile, notification preferences and Privacy were additionally checked at phone/desktop widths. No document overflow was observed. Bell/profile center difference was 0px throughout; notification filter targets and password fields were at least 44px high.
- Actual browser clicks verified Unread and Community filters, the counter disclosure, the profile menu and search focus. The restored carousel was observed showing multiple samples. The profile menu contains seven SVG icons and fits the 390px viewport.
- Evidence: `deliverables/ui-refinement/browser-audit.json` and the phone/desktop PNGs in the same directory. Screenshots use synthetic reader/notification records. Password changes, notification writes/deletion, email delivery and account deletion were exercised only by isolated tests, not against real accounts. No staging/live site, deployment, credentials or environment-file contents were accessed during this pass.

## Run locally

Changes are already in the workspace and included in `deliverables/updated-source.zip` with SHA-256 hashes in `deliverables/manifest.json`. No new package or database migration is required for this refinement. Restart the app and use Ctrl+F5. The disposable sample preview is stopped after verification; the user's existing server is left alone.

This report supersedes the previous reader-interface report only for the homepage counter, empty-review presentation and the UI changes described above. Earlier integration results remain historical; no fresh TiDB/email delivery test is claimed here.
