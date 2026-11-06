# Reader settings and responsive public pages

User-approved direction: improve the whole public interface on phones, use clear book icons, show only measured monthly active members, expand professional privacy/deletion/cookie information, and put password change, password reset and deletion access together in Settings.

Existing Flask/Jinja/Bootstrap stack and account security tables will be reused. No deployment, credentials, database migration or external account mutation is required.

- [x] Add isolated failing tests for password change/current-password checks, session revocation, reset-token invalidation, Settings access/CSRF and rolling 30-day member counts.
- [x] Implement a reader settings service and route; reuse existing verified deletion workflow within the Settings page. Invalidate reader/Studio sessions and outstanding reset tokens after password changes or resets.
- [x] Add the measured monthly counter, without baselines or fabricated visitors.
- [x] Integrate responsive typography, navigation, SVG card controls and plaintext footer links. Check actual viewport width, overflow and touch targets.
- [x] Add restrained legal/help pages and functional opt-in controls that prevent optional analytics/chat loading before consent.
- [x] Verify representative public/account/learning pages across phone/tablet/desktop sizes, crawl local route/template links, run all isolated tests and refresh the source bundle/report.

Independent work is split by owned files: legal templates/style; cookie controls/style/tests; responsive layer/card templates. Parent owns services/routes/settings/header/footer/integration and final verification.

Boundaries: no real password/deletion/email submissions in the browser; use disposable local fixtures for those workflows. Legal text describes implemented behavior and existing contact details without inventing registration data or certification. No claim that every physical device or jurisdiction has been certified.
