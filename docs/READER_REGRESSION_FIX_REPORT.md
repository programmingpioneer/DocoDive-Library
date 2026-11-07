# Reader, legacy downloads and preview refresh

7 November 2026. Local source, repository history and synthetic fixtures only.

## Corrected behavior

**Legacy downloads:** The original uploader in commit `2947225` stored keys such as `uploads/Book_Name_@DocoDive.pdf` and generic `application/octet-stream` metadata. Later uploads use `docodive/uploads/`. The previous delivery change rejected the older prefix, causing an application 404 before contacting storage. Both exact upload formats now work. Original cover keys are also recognized. The resolver retains configured-origin, bucket, traversal and key checks; it does not guess or rewrite object filenames or fetch arbitrary hosts. Explicit `NoSuchBucket` errors now indicate service unavailability (503), rather than a missing book (404).

**Reader content:** An iframe previously mounted its URL immediately, allowing an HTML/login/homepage response to appear inside the reader. The reader now checks the same-origin PDF endpoint with a body-free HEAD request before mounting it. Non-PDF responses, redirects, expired sessions, missing files and service failures produce an in-page retry/sign-in/support state. No error page is embedded as a PDF. The existing PDF stream still enforces login and approved-book checks, and HEAD requests do not count as downloads. Mobile toolbar controls and long titles now have separate rows; small preview action labels remain readable.

**Preview interruption:** Home previously called `location.reload()` immediately upon a catalogue update broadcast, including while Book Details was open. That interruption was reproduced in a regression test. Updates now wait until the open preview/dialog closes. An explicit opening flag covers the Bootstrap entrance transition as well. A rapid guest action also waits for that transition before handing off to sign-in, and queued updates remain blocked while sign-in opens. A local second-tab broadcast verified that the preview stays open and the queued refresh occurs after Close. The user's exact deployed first-click disappearance was not directly observed because staging access is outside scope; the local preview otherwise stayed open during repeated checks.

## Verification

- 219 isolated tests pass. The legacy route test runs the actual resolver and streaming helper against a synthetic SDK, checking the exact old key, PDF bytes, content type and resource closure.
- Reader-controller checks cover PDF success, HTML/XML responses, 401/404/503, redirects, network errors, retry and rejected external/non-reader URLs. Catalogue tests reproduce the old interruption and verify deferred refresh.
- 98 synthetic public/lesson renders pass; 155 templates, 27 static scripts and 393 rendered inline scripts parse successfully.
- Local Chrome checks cover the sample PDF, blocked HTML, expired session, missing file and retry, preview persistence during a second-tab catalogue update, and light/dark phone and desktop views. Evidence is in `deliverables/reader-regression-fix/`.
- The browser canceled the automated sample file-save check. Actual PDF response bytes and download headers pass isolated tests; successful saving of a real file remains an owner check.

## Local handover

Restart the app and refresh with Ctrl+F5. Open an older uploaded book, use Read Online and Download, then open a book preview and leave it open briefly. No new dependency or SQL migration is required.

No credentials, environment file, private database, email service, real storage object, staging or production was accessed. Actual object availability and R2 permissions remain unverified. If a stored reference is unsupported, the app now logs only its book ID and a safe category; URLs, signatures and object keys are not logged. The new reader check adds one metadata request before the native PDF viewer, without downloading a duplicate full PDF.
