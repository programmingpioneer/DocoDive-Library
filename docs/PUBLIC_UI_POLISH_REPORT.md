# Public interface polish — 31 October 2026

The four supplied screenshots identified visible inner scrollbars, oversized carousel dots, uneven book covers/actions and a blurred preview backdrop. The existing public design has been retained and these presentation issues corrected.

## Changes

- Public auth, book previews, Learning Hub menus, notification panels, suggestions and horizontal strips retain scrolling with no visible inner scrollbar. The website's normal outer page scrollbar remains available.
- Auth and preview panels use an opaque white surface and a dim, unblurred backdrop. Removed double scrollbar compensation that shifted dialogs sideways. Login labels and secondary text are more readable; narrow social buttons do not split provider names.
- Removed the generated grey carousel indicators. Autoplay and fade remain. At phone widths a carousel group can scroll sideways to its third card; native touch scrolling takes priority over Bootstrap's slide swipe handler.
- Home, catalogue, category, favorites and history cards share cover/title/author/action slots. Covers use containment inside a fixed 180px frame, or 160px on phones, so landscape covers do not move their buttons upward. Two-line titles, one-line authors and reserved rating space keep controls aligned. Action targets are 44px, with quieter borders and matching rounded corners.
- Search focus uses neutral grey styling with no blue outline/glow; keyboard focus remains identifiable. Added an accessible search label and auth-dialog heading association.
- Versioned the shared stylesheet URL so existing long-lived CSS caches load the update.

## Verification

Browser checks used the updated local Flask app on `127.0.0.1:5001`, through its existing configuration. No authentication credentials were entered and no forms, uploads, emails or admin actions were submitted. A separate isolated fixture preview was also used during initial auth inspection, then stopped.

| Check | Observed result |
|---|---|
| Desktop home/card grid | First six cards: 180px cover frames, 384px card height, actions start 302px from the card top |
| Catalogue at 320, 390, 768 and 1024 CSS pixels | No horizontal document overflow or clipped cards; 44px action targets confirmed at 320px |
| 390px catalogue and Python category | 160px cover frames, 364px card height, matching action offsets at 282px |
| Learning Hub menu | Scroll position changed from 0 to 323px, scrollbar width `none` |
| Phone Quick Details | Internal scroll moved 35px, scrollbar width `none`, backdrop filter `none`, no horizontal overflow |
| Login at 390×844 | Fully fits its panel; panel centered with 12px side margin inside the reserved page gutter |
| Signup at 320×740 | Scrolling reaches all legal links; Google/GitHub/Facebook buttons do not clip or wrap names |
| Search focus | Neutral RGB 148/163/184 outline, no box shadow |
| New Arrivals autoplay | Active group changed from books 1110021/1110020/1080021 to 1050345/1050344/1050343; zero indicator buttons |
| Automated checks | 45 existing isolated tests pass, including parsing all templates and rendered inline JavaScript |

Screenshots are in `deliverables/public-ui/`. The browser viewport override is reset after checks. The temporary test app is stopped after verification; the user's server is left running.

This verifies shared public components and representative pages, not every unique screen or every physical device. No database migration or package installation is required for this presentation pass. Restart the user's app once to clear any cached templates, then use Ctrl+F5.
