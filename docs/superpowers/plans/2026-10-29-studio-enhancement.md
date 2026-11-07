# Studio enhancement implementation plan

Goal: Implement the supplied comprehensive UI/UX and authentication/deletion spec on local files only.
Architecture: Existing Flask/Jinja + Bootstrap + Chart.js. Dedicated security/account lifecycle modules with explicit transactions because current MySQL pool uses autocommit. Additive SQL migrations are supplied, never executed by the agent. Existing password hashes remain usable; new/rehashed passwords use Argon2. No live/staging/browser or credentials access.
Spec: attachment eedf36f4-02b4-4b89-9491-cccfda39ef4f/Pasted text.txt.

Confirmed decisions: unapproved deletion remains pending beyond 15 days; approved, elapsed requests are deleted by server job. Recently deleted name/email retained for 30 days then purged. Existing local HTTP exception remains for development cookies; production HTTPS/Secure enforced. No authenticated admin session before OTP verification; anonymous CSRF/challenge cookie is permitted. OTP expires in 5 minutes, maximum 3 attempts, 60-second resend cooldown, 5 sends/account/hour, bounded per-IP sends. Deletion login restore only before deadline; pending accounts after deadline require admin cancellation.

- [x] Add schema and transactional repositories for hashed OTPs, server-side admin sessions, persistent rate limits, deletion requests, activity and email outbox. Never log OTP/password. Test expiry/replay/binding/attempt caps and rate limits.
- [x] Integrate mandatory OTP, Argon2-compatible password verification, bounded admin sessions/revocation, generic auth responses and security audit events. Keep local HTTP workflow.
- [x] Implement user deletion verification+reason, immediate logout/revocation, admin approval/rejection, 15-day restore and scheduled deletion, 30-day retention, retryable lifecycle emails. Include idempotency and session-race regression tests; real MySQL concurrency remains unverified.
- [x] Rebuild Studio overview/users/books/approvals/tracking/reviews/suggestions/analysis/settings with reusable charts+cards; 9-item book/approval pagination; no main-table edit/delete actions. Include accessible chart drill-down tables.
- [x] Improve public modals, Learning Hub preview, notification cards, leaderboard and responsive design from 320 to 2560+. Use reduced motion and explicit loading/error/offline/unauthorized states.
- [x] Run isolated local tests, syntax/template/JS/metadata checks and one fresh-context final review under executing-plans workflow. Report per-section implemented/verified/not verified and update full-file archive. Browser layouts/FPS, real DB and email are not falsely claimed.

No commits, push, deployment or real deletion. User already delegated routine design choices, so no redundant design approval cycle.

Verification: 38 isolated tests passed. See ACCEPTANCE_REPORT.md for per-section implementation and integration limits.
