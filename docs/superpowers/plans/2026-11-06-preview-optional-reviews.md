# Shared previews and optional linked reviews

**Goal:** Use one consistent Home/Hub quick preview, allow general DocoDive reviews or keyboard-searchable book reviews, and remove the accidental milestone header background.

**Constraints:** Existing Flask/Jinja and shared semantic colors. Preserve CSRF, authentication, native review ratings, escaped text and preview race protection. Work only on local source and isolated fixtures; no configured app, credentials, database, email, staging or production access. Deliver SQL for the owner to apply, without executing it.

- [x] Unify Home and Hub preview controllers, preserve existing actions, align content and add bounded top-center modal scroll arrows with reduced-motion support.
- [x] Make the book selector optional, add accessible keyboard search of approved books across the catalogue, and show a compact linked-book label in the review feed.
- [x] Persist general reviews with a real NULL book reference; provide a migration preserving existing column types and make moderation compatible with general reviews.
- [x] Remove the milestone header selector collision while retaining all filter/locked/unlocked behavior.
- [x] Run relevant isolated tests, full checks and dark/light browser fixtures at phone, desktop and 4K widths. Refresh delivery ZIP, hashes and instructions.

**Review focus:** Stale search responses; typed but unselected book text; no-books general feedback; empty/invalid/oversized submissions; unpublished books; optional review moderation/replies; keyboard focus; modal overflow and preview draft/race regressions.

## Latest user steering

- [x] Move all scroll arrows to the top center; remove the preview side rail and align every Quick Preview with Book Details.
- [x] Send one polished welcome email attempt per newly subscribed address, with durable duplicate protection and honest provider-status messaging; provide owner-run SQL if needed.
- [x] Create and verify a source backup before cleanup.
- [x] Audit duplicate/unused files, remove only confirmed disposable generated files after checks, and deliver a cleanup report.
