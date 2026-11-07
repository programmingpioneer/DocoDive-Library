# Reviews dark mode and page loading

5 November 2026. Reviews now uses the shared semantic palette in its rating summary, cards, stars, invitation, topic tiles, empty state and review form. The shared dark-mode rule no longer paints a rectangle behind every element whose class happens to end in “hero”. Existing painted Home, library, profile and Studio panels keep their explicit surfaces; structural page headings keep their own layout.

## Loading and browser history

Each document continues to render its own skeleton on the server. Navigation no longer covers an outgoing page with that outgoing page's skeleton. The destination displays its own composition when it arrives. Before a document enters the browser's history cache, its own skeleton is prepared in that cached document. On Back/Forward restoration, the skeleton is shown again and then fades into the prepared page. No page HTML or account information is added to application storage.

Initial and restored pages receive two paint frames and a short 120ms minimum display, followed by a 160ms fade. Reduced-motion preferences skip the minimum and fade. A four-second fail-safe releases the page if rendering stalls. Visit tokens cancel stale callbacks so an earlier visit cannot hide a later restoration. Restored pages also reread the local light/dark preference, including a preference changed on another page. Native history and scroll restoration remain with the browser.

Downloads, same-page anchors, canceled forms and ordinary links do not trigger the wrong outgoing composition. Existing asynchronous component placeholders and form controllers remain. No backend route, dependency or database migration was added.

## Fresh verification

- **145 isolated tests passed**, 89.060 seconds. The new deterministic loading test covers initial loading, cached restoration, stale timers/frames, first pageshow, fail-safe release, reduced motion, missing animation-frame support, page identity, restored theme choice and outgoing navigation. The new requirement failed before implementation and passed afterward.
- **97 synthetic page/lesson renders**, zero failures; **152 Jinja templates**, **22 static scripts and 393 rendered inline scripts** parsed.
- **48 browser observations, 42 latest URL/width/theme measurements**. Final measurements have no horizontal overflow or stuck loader.
- Reviews checked in both appearances at **320, 430, 768, 1366 and 3840px**; review form checked in both modes; empty Reviews checked in dark mode.
- Fourteen shared reader/help/community page fixtures checked in both modes at phone width. Browser history testing verified cached Reviews/Home restoration, including a theme change between pages. Studio Overview/Analytics Back/Forward also selected the correct document composition; those Studio visits used fresh document loads in this browser.
- Captured browser console: **zero warnings/errors**. Updated CSS parses; Reviews has no remaining hardcoded colour values. `git diff --check` passes.

Evidence is in [deliverables/reviews-navigation](../deliverables/reviews-navigation/): [verification summary](../deliverables/reviews-navigation/verification.json), [browser records](../deliverables/reviews-navigation/browser-checks.json), [test log](../deliverables/reviews-navigation/unit-tests.log), [dark Reviews](../deliverables/reviews-navigation/reviews-dark-desktop.png), [light Reviews](../deliverables/reviews-navigation/reviews-light-desktop.png) and [phone view](../deliverables/reviews-navigation/reviews-dark-phone.png). An early record captures the normal forward-navigation fade while still visible; its later settled measurement confirms the loader finished.

All browser work used synthetic loopback fixtures on port 5012. It did not import configured app.py, use the owner's port-5000 server, read credentials/environment files or contact real database, email, OAuth, storage, Sentry, staging or production. Screenshots contain sample records. Checks cover representative pages, widths and history paths, not every physical device or every account workflow.

## Local handover

Source files are updated in place. Restart the app and refresh with Ctrl+F5 to replace cached assets. Changed loading/theme/Reviews assets use `20261105-navigation-1`; service-worker cache is `v1.0.14`. Try Reviews, another page, Back and Forward with your local app. The refreshed source ZIP and SHA-256 manifest include this update and prior packaged work. No commit, push or deployment was performed.
