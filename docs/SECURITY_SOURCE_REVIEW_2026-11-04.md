# Local security source review — 2026-11-04

This review found and fixed four concrete source boundaries: upload object collisions, public raw-PDF URL disclosure, optional webhook authentication, and unchecked social-account email linking. The work used source inspection, AST extraction and isolated local tests. It was not penetration testing or a deployed-service assessment.

## Coverage and handling

- Inventoried **153 explicit Flask route registrations**, including **30 API-path registrations**, from `app.py`, `account_routes.py`, `seo.py`, and the admin modules. The complete route, method, source location, authorization and CSRF classification is in `deliverables/site-experience/security-route-inventory.json`.
- Reviewed reader/session ownership checks, studio authentication and roles, CSRF exceptions, uploads and object storage paths, OAuth callbacks, webhook/internal-token handling, notification ownership, public API response fields, SQL input boundaries, and browser credential exposure.
- Examined 21 root/admin Python source files for credential input locations and literal credential patterns, and 184 HTML/JavaScript/CSS browser source files. Counts reflect the local working tree during parallel UI work.
- Did **not** read environment/credential/config secret files, backups, or member exports. No configured `app.py` import occurred. No live application, database, email, OAuth, R2, Sentry, staging or browser requests were made. Provider documentation was read separately; tests substituted local data and in-memory storage/databases.
- No credential values are included in this report or the inventory. No credentials or cloud policies were changed.

## Route protection scope

| Source boundary | Registrations | Source evidence |
|---|---:|---|
| Studio session plus server-side role | 38 | `admin/studio.py:74` blueprint guard; `admin/security.py:32` identity validates the persistent studio session, current role and verified user |
| Protected legacy admin redirects | 25 | `admin/admin_routes.py:1066` authorizes before forwarding |
| Public studio sign-in/code flow | 3 | Password check, persistent throttling, session-bound OTP, three OTP attempts, five-minute expiry |
| Reader session and account-version revocation | 33 | Route-local reader checks and `account_routes.py:52` session revocation hook |
| Public content/authentication entry points | 44 | Public pages, catalogue/learning APIs, signup/login/recovery and their declared input boundaries |
| Public feedback read; signed-in write | 1 | Reader check inside POST branch |
| Optional-reader unread count | 1 | Anonymous response is zero; signed-in query uses session user ID |
| OAuth callbacks | 3 | Google explicit state check; GitHub/Facebook use Authlib authorization-code/state processing |
| Token-based account recovery/verification | 2 | Token lookup; recovery also rechecks expiry and consumes/reset-invalidates tokens transactionally |
| Authenticated external/internal callbacks | 3 | Brevo shared secret, Facebook HMAC request, cron constant-time shared-secret check |

All declared unsafe browser methods pass the global session-token CSRF guard (`app.py:268`). The three external/internal callback paths are exempt from browser CSRF and use their own authentication. The JSON inventory states the actual classification per registration; it does not imply every public route requires a user session. Flask's implicit static route and automatic HEAD/OPTIONS methods are not expanded.

Notification updates include both notification ID and session user ID in SQL. Feedback/reply edits and deletion verify ownership; administrative moderation is restricted to the studio identity. Reviewed search/filter queries parameterize user data, with allowlisted dynamic sort columns. Directory CSV exports escape formula-leading cells and remain behind studio authorization.

## Fixed findings and local evidence

### 1. Uploads could replace an approved document before moderation — important

Previously `generate_r2_key` derived object identity solely from the cleaned title. A signed-in reader could upload a PDF with the same title as an approved book and replace its storage object before the new database row was moderated. Covers shared the same collision pattern. The duplicate helper also received a cursor but tried to create another cursor, then returned “not duplicate” after swallowing the error.

**Fix:** `app.py:432` adds a cryptographically random 128-bit suffix to every new object key. `app.py:614` accepts either a borrowed cursor or a connection, closes only its own cursor, and propagates database errors so uploads stop on failed duplicate checks. Existing stored keys are unchanged.

**Proof:** The new storage tests first failed because two same-title uploads left one object, then passed with two independently preserved objects. Separate tests cover borrowed/owned cursor lifetime and database-error rejection. No R2 requests were made.

### 2. Anonymous book API disclosed the raw PDF location — important

The API returned `telegram_link` directly although the read/download routes required a signed-in reader.

**Fix:** `app.py:3580` retains the existing `link` response field but fills it with the same-origin `download_book` route. Its consumer in `templates/user/index.html` continues using that field. The real download route checks sign-in and approved status before generating a signed storage URL.

**Proof:** A Flask test of the isolated API function failed on the storage URL and now returns `/book/shared-title/7/download` without the storage hostname. Template inspection found raw PDF addresses only in the authenticated reader view and protected admin editor. This does **not** establish private-bucket enforcement; see the open storage boundary below.

### 3. Brevo webhook accepted requests when authentication was not configured — important

The previous code checked the header only if the configured webhook secret existed, so a missing setting silently accepted unauthenticated JSON and logged it.

**Fix:** `app.py:2201` returns 503 when authentication is unavailable, returns 403 for missing/wrong headers, and compares configured headers in constant time.

**Proof:** A local test first received 200 without a configured secret and now receives 503 without logging an event. Valid and invalid authentication tests pass. Configuration values were never read.

### 4. Social-account email linking did not verify its trust boundary — important

The provider-ID lookup already ran first, but fallback email matching could bind an unchecked email assertion or overwrite a different existing provider identity.

**Fix:** `app.py:835` preserves provider-ID-first sign-in. New email-based bindings require an explicit verified Google/GitHub assertion and an empty same-provider binding. The conditional update and affected-row check reject concurrent replacement. Google callback normalization is at `app.py:2226`; GitHub at `app.py:2300` selects only a primary, verified email from the authenticated email endpoint, including when the public profile has an email.

The current Facebook response has no usable verified-email assertion. A new Facebook identity therefore cannot automatically attach to an existing same-email account. **Already-bound Facebook identities still sign in.** No new linking flow was added.

**Proof:** Tests first demonstrated unchecked bindings for all three providers, public-profile GitHub email preference, and replacement of an existing binding. All now pass. A real in-memory SQLite test injects a competing binding immediately before update and confirms the competing identity is preserved and no sign-in is granted.

## Open boundaries and required follow-up

1. **Private PDF access is not established by these changes.** `app.py:412` still uploads through a helper that returns a configured public-base URL, and existing URLs may remain known. Unique object names and removing a public API disclosure do not enforce sign-in on a storage host. If PDFs require private access, verify the deployed bucket/domain policy and move PDF delivery to private objects with authenticated signed access. No bucket ACL, object policy, historical URL revocation or live storage access was inspected or changed.

2. **Facebook's deletion callback is an acknowledgement stub.** `app.py:2389` checks the request HMAC, parses the provider user ID, then returns a fixed confirmation code and informational URL without queuing or performing account deletion. A valid callback therefore does not demonstrate deletion processing. Connect it to the application's deletion lifecycle with provider-ID lookup and a real request-specific status record before relying on it for deletion fulfillment. No deletion behavior was changed in this review.

3. **Verified email is a limited linking policy.** Google's documentation warns that verified third-party email can outlive mailbox ownership. The narrow change checks the provider assertion but does not add a fresh mailbox/account challenge or restrict Google linking to authoritative Gmail/Workspace identities. Brand-new social-account creation also retains the existing provider-profile trust behavior. This review did not establish a live provider-side takeover. A broader account-linking policy should address current mailbox ownership if that assurance is required.

4. **Account enumeration remains intentional current behavior.** `/api/check-availability?field=email`, signup, login and recovery distinguish registered email addresses. This reveals registration status, not passwords or profile records. Decide whether that UX is required; otherwise use generic responses and account-scoped abuse controls. No enumeration responses were redesigned here.

## Credential and external-service review

| Integration/input | Classification and source result |
|---|---|
| Flask/session secret, database password, mail password | Server environment inputs; no literal credential value found in reviewed source |
| R2 access-key pair, Brevo API/webhook keys, Gemini key, cron secret, OAuth client secrets | Server credential inputs; no credential values found in reviewed browser templates/static files |
| OAuth client IDs | Public application identifiers; not client secrets |
| Google Analytics measurement ID | Public browser identifier, loaded through cookie choices in `static/js/privacy.js` |
| Brevo conversations widget identifier | Public browser widget identifier; not the private Brevo mail API key |
| Sentry DSN | Telemetry-ingestion configuration; not a Sentry administrative API token; values and live permissions were not inspected |

Pattern candidates in auth markup were password-control attributes, not passwords. The JavaScript teaching example contained an explicit API-key placeholder. No confirmed hardcoded private credential was found in the reviewed source. This result does not verify the scopes, validity, rotation history or deployed values of any configured credential.

## Verification

- Red-to-green runs demonstrated each fixed boundary before implementation.
- New focused suites: **5 storage tests and 11 callback tests passed**.
- Existing isolated security/admin/account/settings set: **44 tests passed** before the fixes.
- Full local command: `python -B -m unittest discover -s tests` using the existing external project interpreter: **126 tests passed in 69.447 seconds**.
- The full run emitted existing datetime/SQLite deprecation notices and expected injected-failure logs. It reported no test failures or errors.
- Final combined focused security rerun: **60 tests passed in 21.196 seconds**, zero failures, errors or skips.

Changed code is limited to `app.py`, `tests/test_storage_boundaries.py`, and `tests/test_callback_boundaries.py`. Review artifacts are this report and the route inventory. No commits, deployment, configured service startup or secret access occurred.

Final combined UI/security suite after integration: **128 tests passed in 93.747 seconds**. The combined source/render audit and synthetic browser checks are documented separately in [SITE_EXPERIENCE_REPORT.md](SITE_EXPERIENCE_REPORT.md).

## Primary provider references

- [Google OAuth userinfo response](https://developers.google.com/resources/api-libraries/documentation/oauth2/v2/python/latest/oauth2_v2.userinfo.html): documents the verified-email response flag.
- [GitHub authenticated email endpoints](https://docs.github.com/en/rest/users/emails): documents primary and verified email flags and the email scope.
- [Google backend authentication guidance](https://developers.google.com/identity/sign-in/web/backend-auth): explains Google-authoritative addresses and the third-party mailbox-ownership limitation.

Meta's public user/permissions documentation returned HTTP 429 during documentation lookup; no unsupported Facebook verification claim was assumed.
