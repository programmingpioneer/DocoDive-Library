# Practice, text and navigation implementation plan

**Goal:** Restore real practice routes, make Home and shared text readable in both themes, and show the destination's own skeleton on initial and history navigation.

**Architecture:** Retain Flask/Jinja, the supplied challenge banks and their existing engines. Use semantic tokens for all new presentation, one small local progress controller, and the document's server-rendered skeleton. No new network service or dependency.

**User decisions:** Proceed autonomously in the existing local source. Preserve the Home layout; match About card sizing. Test synthetic local fixtures only. Do not access configuration secrets, configured integrations, staging or production.

- [x] Reproduce the explicit `python_practice` route with an isolated regression test. Supply the same module information as the generic route; ensure both real entry paths render.
- [x] Add a shared practice workspace with readable icons, progress and responsive controls. Keep existing answers, filters and challenge engines intact. Track actual attempts locally with clear storage scope; test repeat answers, reset and unavailable storage.
- [x] Correct the Home heading foreground and pale menu actions at their component selectors; equalize About card groups and preserve readable type at phone/tablet/desktop/4K widths.
- [x] Replace the single hardcoded scroll control with theme-aware up/down controls, respecting boundaries, dialogs, reduced motion and a small-screen safe area.
- [x] Refine per-page skeleton mapping/compositions and early loading/history paint. Preserve native navigation, canceled submissions, downloads, bounded fallback and no-JS visibility.
- [x] Run route/controller/render tests and real browser checks on isolated sample fixtures in both themes. Review diffs and source boundaries, save screenshots, refresh source ZIP/manifest and final handover.

**Review focus:** Explicit routes shadowing generic routes; repeated answer events inflating tracking; corrupted/blocked browser storage; cached Back/Forward at a nonzero scroll position; overlays hiding page controls or delaying usable content; equal cards with long/custom content; reduced-motion and 4K readability.
