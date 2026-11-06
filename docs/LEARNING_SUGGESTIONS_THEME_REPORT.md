# Learning Hub and Community Suggestions theme correction

Updated 5 November 2026. Local source changes only. Restart the local app and refresh with Ctrl+F5. This pass needs no new dependency or database migration.

## Result

Learning Hub cards, book actions, counters and FREE labels now use the shared surface, foreground and state tokens. The legacy dark stylesheet had overridden those components with a separate purple palette and pale action backgrounds. Its existing selectors now use the same semantic roles as current components; card sizing and action alignment are preserved.

All 60 subject/level templates and the shared hub template now use readable accent text on neutral surfaces. Filled diagram cells, table headings and practice actions use the foreground intended for a filled primary background. Inline code and hint actions also have readable light/dark colors. Course content, controls, scripts and the lesson content bank were preserved.

Community Suggestions now uses the shared tokens for the composer, search, filters, cards, avatars, liked state, team replies and menus. Guidelines remains a secondary action; Delete keeps its danger color. The component scope prevents older global dark rules from changing its search background or state colors. No suggestion was posted, edited, deleted or voted on during this browser pass.

## Verification

- 21 targeted isolated tests passed, including learning routes/previews, community views, suggestion controls, design tokens and loading/navigation behavior. The prior full-suite results elsewhere in this project are historical; this pass reran these 21 relevant tests.
- 97 synthetic page renders passed. Parsed 152 Jinja templates, 22 static scripts and 393 rendered inline scripts without execution errors.
- Browser measurements cover all 60 learning tracks in each mode at 1366px. Corrected findings were revisited; the latest observations have no text contrast flags from the scoped check and no horizontal document overflow.
- Learning Hub and Suggestions were measured in both modes at 320, 430, 768, 1366 and 3840px: 20 page/theme/width combinations with no horizontal document overflow. Saved screenshots include phone and desktop appearances.
- Suggestions search, team-replied filtering, the composer, discussion/reply controls and action-menu colors were inspected. A Hub book preview opened the selected book and its matching details/read/download links.
- Six changed stylesheets parse without CSS errors. The 61 learning templates retain the same lesson text, markup and scripts after excluding CSS and asset-version changes. `learning_content.py` is byte-identical to the previous delivered ZIP. Whitespace checks passed.
- The final captured browser error/warning log is empty.

The browser used an isolated local fixture on port 5012 with synthetic records. It did not import the configured application or contact TiDB, email, storage, OAuth, Sentry, staging or production. Real integration behavior is outside these results. The color probe inspects rendered direct text and resolved backgrounds; it is not a complete WCAG or every-interaction certification. It resolves solid-color gradients; the light Suggestions submit button's two-color gradient was separately inspected because the simple probe reports its ancestor background. Its white text is readable against both gradient stops.

## Files and evidence

Main changes: `static/css/style.css`, `user.css`, `responsive.css`, `theme.css`, `learning.css`, `suggestions.css`, the learning templates, and the Suggestions component identifier. CSS asset references and the service-worker cache version were updated. The synthetic preview now includes Hub module cards and category chips so these states can be checked.

Evidence: `deliverables/learning-suggestions-theme/`. Raw browser observations retain earlier findings and their later corrected measurements. The one fixture URL typo with no theme/layout is excluded from verification totals. `browser-summary.json` records the latest result summary. `deliverables/updated-source.zip` contains the current local source and selected evidence; the accompanying manifest records each file hash.
