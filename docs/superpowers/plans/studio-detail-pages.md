# Studio detail pages and integration checks

Use the supplied Stitch reference for Users, Pending Deletions, Tracking, Books, Approvals, Leaderboard, Analytics and Official Profile. Keep the accepted shell and sign-in design. No fake reference numbers, compliance claims, quotas or inactive controls. Preserve OTP, CSRF, deletion approval and 9-book pagination. Users main table has no edit/delete actions.

Add real directory summaries, status/time/search filters, bounded CSV export and member detail selection; improve deletion tabs/empty states; tracking filter/table; catalogue controls. Reorganize remaining reference pages around existing real controls.

Integration: user explicitly requests TiDB/email tests through the local application. No credential or .env disclosure, manual TiDB login, migrations or permanent deletion. Local server was not running at first check; startup request sent while implementation continues. Email recipient must be the user's own verified account; human enters credentials/OTP locally when needed.

Verification: isolated tests, synthetic preview with populated rows and browser layout checks; real application checks only when its server/session is available. Report each integration result independently and never count SMTP acceptance as mailbox receipt.

Completed: referenced detail pages applied; real authenticated TiDB views checked. User completed real OTP sign-in and confirmed CSV saving. 45 isolated tests passed. No real lifecycle deletion/role transfer/storage submissions were run. See docs/STUDIO_INTEGRATION_REPORT.md for evidence and limits.
