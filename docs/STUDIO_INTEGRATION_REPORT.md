# Studio detail pages and integration verification

This report supersedes the earlier synthetic-only UI pass for the checks listed below. The supplied Stitch ZIP remains the design reference. Mobbin refused reference search because this connection requires a paid plan; no Mobbin reference results were used.

## Delivered pages

| Page | Applied changes | Verification |
| --- | --- | --- |
| Users | Real summary cards, search/status/join-period/activity/sort filters, selected-member detail panel, numeric pagination and bounded CSV | Real TiDB data, matching/empty filters, member selection and user-confirmed CSV save; SQL regression tests |
| Pending Deletions | Request-status tabs, grace/retention summaries, request/reason cards, retention archive and illustrated empty states | TiDB-backed empty state and counts; lifecycle decisions tested with disposable SQL only |
| User Tracking | Search/day filters, actual download-link counts, paginated member table and CSV, linked charts | Real TiDB member rows and loaded chart data |
| Books | Catalogue summaries, category/status/sort controls, 9-item numeric pagination, reading/download counters and bounded CSV | Real TiDB catalogue, both 9-item pages and Python category results; filtered/pagination SQL tests |
| Approvals | Horizontal cover/detail review cards, summary strip, checklist and matching empty state | Actual empty queue; populated actions/render protected by existing routes and synthetic tests |
| Upload | Two-column form and publication checklist, styled file zone | Real page renders; upload submission/storage was not exercised |
| Leaderboard | Registered-member totals, podium, recorded score history and adjustment table | Real rows/history; corrected total verified as 48; orphan-record regression test |
| Analytics | Overview hero, scope indicators, linked record destinations and existing real charts | Real page and successful all-insights API response |
| Official Profile | Identity/stats layout, actual asynchronous stats with retry, guarded transfer controls | Actual stats loaded: 3 uploads, 0 comments, 32 points; ownership transfer was not submitted |

The Users main table/detail panel has no edit/delete actions. Standalone activity/profile-management routes retain their existing role checks. The ZIP's demo metrics, quotas, compliance badges, SSO claims and unsupported controls were not copied into the product.

## Real integration evidence

- The user started the local app at port 5000 and personally entered email/password/OTP. The user confirmed successful login. The browser then opened the authenticated Studio and received real TiDB-backed records. This verifies the actual admin email-OTP sign-in path without exposing credentials or codes in chat.
- Dashboard data showed 328 books and 2 registered users; the insights API completed successfully. Member filters returned 1 member with downloads and no unverified matches. The Python category filter returned 16 titles. Catalogue pages showed 1–9 and 10–18 of 328.
- The updated build was checked on loopback port 5001 using the existing runtime/configuration and authenticated session. No TiDB console login or manual database mutation was used. Flask CLI mode did not invoke the application's automatic account-maintenance worker.
- Member export endpoint returned HTTP 200. Browser automation canceled/timed out while trying to save the file, and its security policy blocked inspecting the browser Downloads page. The user then manually clicked Export CSV and explicitly confirmed the CSV saved successfully. File-save success is therefore human-confirmed; export content/formula escaping is covered by isolated tests.
- TiDB reads exposed a leaderboard discrepancy: raw point totals included orphaned user IDs. The displayed total now joins existing members, matching their visible scores and daily snapshots. No stored records were changed to correct this display issue.

## Automated checks and layout

Final source review identified a page-selection regression: selecting a member from page 2 reset the list to page 1. It was reproduced with a 35-member SQL fixture and corrected to preserve the browsing page; filters still reset to page 1. No other important regressions were reported in that source review.

45 isolated automated tests passed. The suite includes populated SQL directory filters, nine-book pagination, member selection, CSV formula escaping, authorization regressions and orphaned score handling. All 123 templates parse; static JavaScript and changed Python sources pass syntax checks; git diff --check passed.

Actual-data screenshots are in deliverables/studio-pages/. Desktop and 390px phone directory layouts were checked; the phone layout has no page-level horizontal overflow and keeps the wide table inside its scroll container. The earlier report documents the shared shell's wider synthetic breakpoint checks. Additional requested viewport overrides are not counted unless the browser reported the requested dimensions.

## Limits

Only the admin OTP email path was exercised against the real email service. Welcome/deletion/restoration/deleted mail templates and retry rules remain covered by isolated sender tests; those real lifecycle changes were not triggered on existing accounts. No actual permanent deletion, approval/rejection, upload, role transfer or points adjustment was performed during these integration checks. Actual concurrent MySQL transactions, assistive-technology behavior and rendering frame rate remain unverified.

This pass adds no package or migration. Restart an existing no-reload local server once to load the changed Python routes; then refresh the browser. The previous account migration must already exist for the application to run.
