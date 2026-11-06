# Studio visual refresh

User-approved direction: supplied Stitch ZIP, with email/password only on the first admin screen, compact original public auth styling, no blue hover/click lines around Learning Hub. Routine design choices delegated in the existing conversation. Mobbin search is unavailable; no Mobbin reference claims are made.

Preserve: Flask routes, CSRF, mandatory second-step OTP, real counts/charts, all existing management actions, public auth integrations, no main Users-table edit/delete actions. Source is the existing Flask/Jinja project. No live/staging/TiDB access or credentials.

Implement: split admin sign-in/verify shell; dark sidebar and compact header; cobalt and white Studio panels/tables/forms, overview metrics/actions/charts; original-width compact public modal and scoped Learning Hub focus treatment. Use Bootstrap/icons already installed. Avoid fake reference metrics, SSO/WebAuthn controls, uptime or compliance claims.

Verify: isolated Flask render/syntax tests and a loopback-only browser preview using synthetic data. Inspect sign-in, dashboard, representative management forms, public modal login/signup, Learning Hub, and narrow/desktop widths. No claim about real DB/email integration.

Completed: shared Studio/auth UI applied, public corrections applied, 38 tests and JS syntax checks passed; isolated Chrome layout checks recorded in docs/UI_REFRESH_REPORT.md.
