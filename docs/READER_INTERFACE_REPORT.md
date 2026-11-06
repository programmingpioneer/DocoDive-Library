# Public interface and account settings — 31 October 2026

Later refinement: [Homepage, Settings and Notifications](HOME_NOTIFICATIONS_REPORT.md). Its disclosed display counter and labeled sample-review fallback supersede the homepage presentation described below; measured metrics are still retained separately.

The public interface now has a compact mobile header, readable text, labeled SVG book controls, a restrained company footer, extended policy/help documents and an Account settings page. The supplied screenshot's cramped icons and small About text were addressed in the shared responsive layer.

## Delivered behavior

- Mobile navigation keeps the brand, account control and menu within the screen. The GitHub badge is hidden below desktop widths. Account settings is reachable from the profile menu and profile page.
- Book cards use inline SVG icons and visible Details/Preview labels. Covers, two-line titles, author text and actions keep consistent positions across landscape, portrait and missing covers. Favorites and history share the same layout. Forms use readable text and bounded fields; code/tables can scroll within their containers.
- The footer and About social links use text links. Privacy, Terms, Cookies, Data deletion, Contact, Community guidelines and Accessibility are linked together and from the footer. Standalone sign-in/recovery screens include legal/help links as well.
- Monthly active users is a measured count of distinct existing signed-in members with recorded page/read/download activity in the last 30 UTC calendar days, including today. Guest activity is not presented as unique visitors. Counts are cached with the existing five-minute homepage cache. An unavailable measurement displays an unavailable state; there is no added baseline. The local configured database returned 2 during verification.
- Homepage review cards now come from submitted reviews. Removed the unsourced 5M collection/uptime claims.
- `/user/settings` puts password change, email recovery, notification/cookie preferences and verified account deletion in one place. Current password is required for changes. New passwords have the existing 8–128 character bounds and must match confirmation and differ from the current password. Changes/reset revoke reader and Studio sessions, consume outstanding verification codes and invalidate other password reset links. An in-progress login cannot use a password snapshot from before a change.
- Email-code recovery has a GET page for its normal HTML fallback, readable validation/confirmation pages, and reports delivery failure. Existing asynchronous recovery remains supported.
- Settings reuses the existing deletion service and policy: verified email, immediate session revocation, administrator approval, 15-day restoration deadline, approved scheduled deletion and 30-day name/email archive retention. Sending a deletion code from Settings returns to that section.
- Cookie controls default Analytics and Support chat off, save a choice for up to 180 days, support changing it from the footer, and handle denied browser storage. Optional provider scripts load only after the relevant choice. Removed older standalone sign-in/maintenance chat loaders that bypassed the choice. Essential account functions and first-party activity records remain separate from optional integrations.

## Verification evidence

| Check | Result |
|---|---|
| Isolated automated suite | 59 tests pass; disposable SQLite fixtures, no real credential changes or email sends |
| Cookie controller | 18 offline JavaScript behavior checks, included through the automated suite |
| Templates and JavaScript | All 134 templates parse; rendered inline scripts and 8 shared static JS files plus the service worker pass syntax checks |
| Local GET route audit | 124/124 pass, covering 20 published Learning Hubs and all 80 lesson routes; 9 private routes correctly lead to sign-in |
| Browser viewport checks | 61 observations over 34 URLs at 320, 390, 768, 1024 and 1366 CSS pixels; settled pages have no document overflow or error pages. One recovery measurement during initial CSS/font loading was rechecked after loading and passed. Raw records are in `deliverables/reader-responsive/browser-audit.json` |
| Desktop card positions | First six catalogue cards: 180px cover frames, 389px card height, actions at the same 308px offset |
| Phone card controls | 17px SVG icons with labels; approximately 47px high action targets and consistent offsets at 390px |
| Account menu | At 390px, menu measured 280px wide within the viewport; Account settings link opened `/user/settings` |
| Cookie controls | Actual local browser starts with zero optional provider scripts; Essential only keeps them absent; preferences reopen with both optional choices off |

Public browser checks used the configured local Flask app on port 5001. Private account screen layouts used the isolated sample-data preview on port 5012. Password, reset-token, session, CSRF and deletion-return behavior were tested through the real local service/route code against disposable databases. No real password changes, deletion submissions, uploads or new emails were performed. Earlier human-confirmed admin OTP/CSV checks remain documented in the Studio report.

The route audit checks successful page delivery and expected sign-in redirects; it does not authenticate every private route. The browser audit covers representative screen families and widths, not every lesson at every physical device size. Existing historic download/view totals were not rewritten. The source's privacy/support contact addresses are retained; their inbox delivery has not been verified.

The credential checks follow the current-password/session guidance in the [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html). Policy wording and optional storage controls were checked against the [ICO privacy notices and cookies guidance](https://ico.org.uk/for-organisations/advice-for-small-organisations/privacy-notices-and-cookies/cookies-and-privacy-notices-in-detail/), while describing this application's actual practices.

## Local handover

Source is edited in the existing workspace and included in `deliverables/updated-source.zip`, with hashes in `deliverables/manifest.json`. No new dependency or database migration is needed for this pass. Restart the user's app once, then use Ctrl+F5 to clear cached templates/styles. Open `/user/settings` after signing in. The temporary test servers are stopped after verification; the user's existing server is left running. No staging or production website was accessed or deployed.
