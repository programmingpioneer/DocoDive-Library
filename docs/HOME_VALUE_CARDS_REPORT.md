# Home value cards follow-up

The four Home/About value cards now share equal heights, consistent icon/title/description alignment and the same hover treatment as neighbouring cards. The authors card's Report a concern link is a compact, rounded button with a readable foreground in light and dark mode.

## What changed

The older shared card rule explicitly disabled movement, while a dark-mode authors rule applied a warning background to the link. Those conflicting effects are now handled by the Home component's semantic surface/action tokens. All four cards lift by 8px, with an accent border and shared shadow on pointer hover. Reduced-motion users retain the static state. Narrow two-column layouts reserve equal title space; grid rows remain equal height. The report button remains inside its card and keeps a visible keyboard focus indicator.

The contact destination and page content remain unchanged. This is a scoped CSS fix, with cache tags updated to `20261105-cards-1` and service-worker cache `v1.0.13`.

## Fresh verification

- 7 targeted tests passed: 5 Home/auth presentation tests and 2 palette tests. The earlier 144-test full-suite result belongs to the broader preceding update; it was not rerun for this CSS-only change.
- Both modes checked at 320, 430, 768, 1366 and 3840px. All four cards have equal heights, aligned icons/headings/descriptions, and no document overflow.
- Report button stays inside its card with at least 44px height. Measured white-text contrast: 6.91:1 in light mode and 4.91:1 in dark mode.
- All four hover lifts, keyboard focus in both modes, and the `/contact` destination were checked in the browser. No console errors were captured.
- Both changed stylesheets parse; `git diff --check` passes.

Evidence: [measurements](../deliverables/home-value-cards/verification.json), [light screenshot](../deliverables/home-value-cards/light-desktop.png), [dark screenshot](../deliverables/home-value-cards/dark-desktop.png), and test logs in that folder. Browser work used only synthetic loopback fixtures on port 5012; no configured app, database, email or staging service was used.

Source is updated in place. Refresh with Ctrl+F5 after restarting the local app. The refreshed updated-source ZIP and SHA-256 manifest include this follow-up and all prior packaged source work.
