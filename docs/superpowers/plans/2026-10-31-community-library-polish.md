# Community and library polish

Continue in the existing local Flask/Jinja project, preserving the approved indigo/slate styling and source-only workflow. The user delegated design choices and asked for implementation and browser testing.

1. Create a shared, measured achievement summary for the existing nine milestones; clamp progress, correct unlocked counts, surface the next goal, and keep existing stored badge values/POST validation compatible. Test zero, partial, complete and public/private profile states.
2. Redesign Leaderboard, My Library Stats and public profiles with the shared SVG icons, clear real metrics, visible milestone progress, useful links and empty states. Preserve badge selection and sharing. Avoid invented reading-time estimates or weekly growth.
3. Restyle Suggestions and its composer/replies, add a local search/status filter and accessible vote controls, preserve pagination/ownership/moderation/CSRF. Verify failures leave counts/content intact.
4. Add a shared book-card macro for Related Books, 404 recommendations and saved/history lists. Use the homepage's fixed cover/title/author/rating/action/count slots. Keep real destinations and preview controls, including blank/long titles and missing covers.
5. Refresh the 404 recovery screen and other error-page presentation through a shared layout where safe. Preserve status codes, noindex behavior, retry links and 503 retry information.
6. Run focused behavior/regression tests and local synthetic browser checks at 320, 390, 768, 1024 and 1366px. Review, save screenshots and refresh the source archive/report. No real posting, badge updates, account changes, email sends, staging or deployment actions are required.

Review focus: locked milestones must never be selectable; profile email stays owner-only; one/two-person leaderboards must not show empty podium people; paginated suggestion filters must clearly apply to this page; all book cards must reserve the same action slot regardless of metadata; error pages must retain their actual HTTP status and avoid caching private content.

Completed: shared presentation helpers/templates, local behavior tests, browser audit, fresh review and handover. Final full suite: 80 passing tests. A podium/count-animation attribute collision found in browser checks was fixed and rechecked. See docs/COMMUNITY_LIBRARY_REPORT.md for evidence and scope.
