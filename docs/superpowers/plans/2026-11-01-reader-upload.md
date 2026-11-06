# Reader upload redesign implementation plan

**Goal:** Make Upload a Book clear, attractive and responsive using DocoDive's existing colours and SVG icons.
**Architecture:** One scoped Jinja page, upload CSS and a native JavaScript controller. Preserve POST /user/upload, GET /api/user/uploads, CSRF, PDF/category/optional-cover fields and the existing moderation workflow. No new dependency or migration.

## Decisions and constraints

- Continue under the user's standing instruction to make local changes autonomously. No approval gate, worktree, commit or deployment.
- Existing Mobbin connection is blocked by its paid-plan requirement; use the established DocoDive visual system.
- Desktop has a main form and a compact review/rights guide; phones stack them. Your Uploads remains below, with visible status and a manual Refresh action.
- A native PDF picker supports drag and drop, file name/size and removal. Cover preview stays local and uses the existing supported image formats. Match server limits: PDF 500 MB, cover 10 MB before server processing, total request 500 MB.
- Preserve auto category selection and explain automatic PDF metadata/cover behavior without new form requirements.
- Fix the current cover preview's missing coverThumb target while replacing its controller. Render API text safely, keep files on failed submissions, and show only real transfer progress and confirmed success.
- Synthetic loopback preview only: no configured app import, real upload/email/storage/database, staging/live or credentials.

## Tasks

- [x] Add failing tests for form contracts, optional cover, native fallback and controller states (validation, previews, safe list output, failure/retry, measured progress, confirmed success).
- [x] Build templates/user/user_upload.html, static/css/upload.css and static/js/upload.js. Keep global selectors scoped. Add file/image SVGs to the existing icon macro if needed.
- [x] Update synthetic upload-list fixtures. Check normal, selected-file, optional-cover, empty/error/unauthorized list and progress states without a real POST.
- [x] Run full tests, JS syntax/Jinja checks, five responsive browser widths and independent review. Save evidence/report and refresh source ZIP.

## Review focus

Long filenames/titles/category names at 320px; genuine zero and empty submissions; stale/failed refreshes; native keyboard file controls and cover preview cleanup; HTTP 413/401/HTML errors; duplicate submits; progress at 100% still waiting for server confirmation; no false success, unsafe HTML or lost selections after failure.

## Scope update — 4 November 2026

User additionally requests modest homepage layout polish and a more readable/responsive login popup. Preserve the homepage's existing hero, colours, illustration, section order, book cards and content. Add scoped spacing/width/type rules and improve the existing compact popup's type, labels, focus and keyboard tab behavior; keep its native field names, CSRF and authentication endpoints. Standalone login and Studio are outside this update.

- [x] Polish homepage layout and popup; verify phone/desktop, login/signup switching and field fit without authentication requests.

## Final verification — 4 November 2026

Completed with 128 isolated tests, 93 synthetic renders, 149 template parses, 396 static/rendered JavaScript parses and 132 browser observations. Final measurements have no horizontal overflow. Native browser file-selection was blocked by the extension permission; selected-file/cover/transfer states were verified in isolated controller tests instead of an actual upload. See docs/SITE_EXPERIENCE_REPORT.md for evidence and limits.
