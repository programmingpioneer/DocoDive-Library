# Practice, readable text and page loading

Completed 6 November 2026. Changes are in the local project source. Restart the app and refresh with Ctrl+F5. No new package or database migration is required for this pass.

## What changed

The real `/learn/python/practice` entry point supplied no `info`, although the shared lesson layout requires it for navigation and resources. It now supplies the same Practice Resources descriptor as the generic route. A regression test reproduces the reported exception through that explicit route before checking the repaired render. The synthetic browser fixture now exercises that actual handler too; the previous fixture only exercised the generic handler.

All 14 practice entry pages now have a consistent workspace, inline icons and a local activity panel. The 11 existing quiz engines retain the supplied challenge banks, levels, topic filters, answer checking and session controls. The remaining three templates offer clearly labeled guided activities and a self-reported checklist instead of a fictitious construction progress bar. Quiz activity and guided checklist state are saved in this browser, with a clear notice that they are not account-synced. Duplicate submissions count once. Invalid saved JSON, wrong storage shapes and malformed counts are handled without crashing practice.

Python, JavaScript, Java and C/C++ explanations, hints and guided reviews now use the authored question content. They no longer depend on slow third-party text generation or its repeated requests. No API key is needed. Scroll helpers use a passive, frame-limited listener and respect reduced motion; animations also respect the reduced-motion preference.

The Home title keeps its accent in both themes. Menu footer links use a matching foreground and background. Additional verified text fixes cover small labels, account avatars, Favorites/History, Upload, catalogue actions and reader sign-in/recovery. Colors use the shared semantic tokens. About statistics, mission cards and value cards have equal heights within each group, including wrapped mobile copy. Home sections remain in their existing order.

Public pages use a bounded content width at 4K with a 20px root text size. Sign-in and recovery layouts also scale for large screens. Phone layout stays compact. Up/down buttons appear where scrolling is useful and stay below dialogs; the up control hides again at the top.

Each document retains its own server-rendered loading composition. Practice, Suggestions, Favorites and History skeletons now reflect their actual layouts more closely. A non-cached exit does not activate the outgoing page skeleton. Cached Back/Forward restores activate the returning document's own skeleton, preserve its theme, and release it with the existing short fade and bounded fallback. Native links, canceled forms, downloads and no-JavaScript visibility remain intact.

## Verification

- **149 isolated tests passed** in the final full run. This includes the explicit Python-route regression, local activity/guided progress, scroll controls, and 55 engine/saved-data combinations across the 11 quiz engines. No configured application startup or real external service is used by these tests.
- **97 synthetic renders passed.** Parsed 154 Jinja templates, 24 static scripts and 393 rendered inline scripts without execution errors.
- **27 public/account/help page types were checked in each theme** at desktop size. All 14 practice entry pages were checked in each theme. The latest scoped text measurements have no contrast flags; the final browser warning/error log is empty.
- Home and Python Practice were checked at **320, 430, 768, 1366 and 3840px**, including a 3840×2160 viewport. Guided practice and sign-in/recovery received additional phone/4K checks. No horizontal document overflow was found in the recorded measurements.
- Measured About card heights match within each group. The browser exercised a real quiz answer, observed the local Attempts count increase, and restored a 25% guided checklist after reload. The down arrow moved the page 720px; the up arrow returned it to zero.
- Real Home → Reviews navigation and Back/Forward recorded the correct `home` and `reviews` skeleton compositions with `loadTrigger=restore`. Saved skeleton screenshots are composition previews; the raw history observations record the actual restoration lifecycle.
- Six changed/new stylesheets parse without CSS errors. `app.py` parses, whitespace checks pass, and the lesson content bank is byte-identical to the previous handover. Relative to that handover, the only application-handler change is the added Practice Resources descriptor.

Browser checks used isolated sample fixtures on loopback port 5012. They did not access the user's port 5000 server, configuration secrets, TiDB, email, storage, OAuth, Sentry, staging or production. The text probe and visual checks are not a complete accessibility certification or a guarantee for every possible dynamic state. The evidence retains earlier findings and their corrected observations; two incomplete fixture-placeholder observations are excluded from final totals.

## Delivery

Evidence is under `deliverables/practice-reading-loading/`, including full test output, render audit, browser observations, source checks and screenshots. `deliverables/updated-source.zip` contains the current source and selected evidence. `deliverables/manifest.json` records file hashes; the package verification record is outside the ZIP to avoid self-referencing hashes.
