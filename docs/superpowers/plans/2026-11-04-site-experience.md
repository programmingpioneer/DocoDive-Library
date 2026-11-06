# Site appearance, loading and security continuation

**Goal:** Complete Upload a Book, lightly polish homepage and popup authentication, add consistent dark mode and genuine loading skeletons throughout public/Studio pages, and review local API/key boundaries.
**Architecture:** Shared appearance/bootstrap assets in the eight document-owning templates; a header theme control; scoped theme CSS covering page families; shared skeleton markup/helpers. Keep homepage structure and existing routes/forms. Browser checks use only synthetic loopback fixtures.

## Tasks and ownership

- [x] Finish upload interactions, accessibility/contrast review fixes and responsive checks (parent; static/css/upload.css, static/js/upload.js, user_upload.html/tests).
- [x] Minor homepage and compact auth popup polish (home_popup_polish agent; new CSS/partial/test only; parent integrates base include).
- [x] Shared theme initialization/toggle, system default, local preference, cross-tab changes, blocked-storage handling and dark surfaces/text/forms throughout public/Studio/standalone layouts (parent).
- [x] Replace competing artificial-delay page loaders with a shared skeleton; add honest async list/preview and image loading states; reduced-motion and failure/no-JS recovery (parent).
- [x] Local source route/key inventory and concrete security fixes (api_security_audit agent owns app.py and focused storage tests; parent coordinates other exposure edits).
- [x] Full isolated checks, theme/controller tests, representative page families and all learning templates, responsive browser checks, screenshots, report and refreshed source ZIP.

## Decisions and constraints

- User authorizes autonomous local work; no approval gate, commits/worktree/deploy, credential access or configured database/email/storage/staging/live requests.
- Homepage hero, book collections, About structure, disclosed counter and sample-review labeling remain intact.
- Appearance follows the OS until a user chooses light/dark. Store only that explicit preference in this browser; no new network endpoint or optional analytics activation.
- Dark styling preserves actual cover images, logos and PDF contents. Theme the surrounding controls/surfaces.
- Skeletons represent real navigation/data/image loading, disappear when content is ready, recover on errors and have reduced-motion/no-JS fallbacks. No artificial minimum display interval.
- Source review is not a live penetration or bucket-policy test. Fix verified local weaknesses; record external policy limits honestly.

## Review focus

320px signed-in/signed-out headers; OS/manual/cross-tab/blocked-storage theme transitions; pre-paint initialization; dark forms/dropdowns/legal/learning/code/Studio states; auth native/AJAX contracts; skeleton error exits; upload progress below100%; image/cover keyboard focus; untrusted API text and route authorization; collisions/duplicate errors before storage.

## Final verification — 4 November 2026

Completed with 128 isolated tests, 93 synthetic renders, 149 template parses, 396 static/rendered JavaScript parses and 132 browser observations. Final measurements have no horizontal overflow. Native browser file-selection was blocked by the extension permission; selected-file/cover/transfer states were verified in isolated controller tests instead of an actual upload. See docs/SITE_EXPERIENCE_REPORT.md for evidence and limits.
