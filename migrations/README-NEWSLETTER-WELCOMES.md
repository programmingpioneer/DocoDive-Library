# Newsletter welcome deployment

The existing subscription route only upserts a Brevo contact. The same contact helper is used during account registration, so an existing Brevo contact does not identify a repeated newsletter subscription. There is no existing local subscription table or local unsubscribe endpoint in the source.

Apply `20261106_newsletter_welcomes.sql` manually to the reviewed target database before deploying the matching application code and `newsletter_presentation.py`. This migration has not been executed. It creates a small independent ledger with a unique SHA-256 key of the trimmed, lowercase email address, a welcome status and UTC timestamps. It stores no raw address, user ID or email content. Confirm `SHOW CREATE TABLE newsletter_welcomes;` matches the migration, including the primary key. Do not use a migration runner that continues after errors.

Use the deployment's established backup and database authentication process. For a saved MySQL connection, after replacing both connection and database names with the reviewed target:

```powershell
Get-Content -Raw -LiteralPath 'D:\MY PROJECTS\PioneerDocoDive\migrations\20261106_newsletter_welcomes.sql' | mysql --login-path=YOUR_SAVED_CONNECTION --database=YOUR_DATABASE --default-character-set=utf8mb4
```

Keep `PUBLIC_SITE_URL` set to the public HTTPS site origin so email links use the intended public library, Python Learning Hub, contact and privacy pages. If it is empty, the renderer uses the repository README's existing production address, `https://docodive-library.onrender.com`. It never uses an incoming Host header. Configuration rejects credentials, query strings, fragments, paths and control characters; HTTP is accepted only for an explicitly configured loopback preview. Invalid configuration fails before contacting the provider. The existing Brevo sender configuration and transactional sending permission are also required. The code does not create campaigns, change provider contact lists or add a mail queue.

## Once means one automatic attempt

After a successful contact upsert, a unique database insert reserves the welcome attempt before calling the existing sender. Only the request that inserts the key may send. Repeated and concurrent submissions still run the existing contact upsert but cannot send another welcome. Case variants share one key; plus tags and provider-specific dot rules are not merged.

The provider helper's `True` means the API accepted the email, not that it reached an inbox. The ledger records `accepted` or `unconfirmed`. A timeout, rejected message or sender exception leaves the subscription successful but shows an honest welcome warning. There is no automatic retry: a timeout might have accepted the email, so retrying could produce duplicates. A process crash after the durable claim can leave `claimed` without a sent message. This is an at-most-one automatic attempt, not a guarantee of delivery.

If contact sync fails, no claim or welcome is made and the route reports an error. If the ledger is absent or inaccessible, the route fails closed before sending a welcome. A result-update failure after sending leaves the original claim in place; it never authorizes another attempt.

Do not delete claims or add retries without first checking provider history and deciding how duplicate risk should be handled. Existing contacts may receive their first welcome when they next submit the form after deployment; there was no welcome send in the previous subscription route. There is no automatic backfill.

## Existing suppression and deletion behavior

The Brevo upsert remains unchanged: it sends email, name attributes and `updateEnabled`, and does not clear blacklist/suppression flags. The ledger governs welcome attempts only and does not gate contact updates, remove contacts or automatically re-enable unsubscribed addresses. Existing provider unsubscribe links and account notification preferences are unchanged. The existing webhook only logs events; it does not maintain local unsubscribe state. The sample welcome links to real contact/privacy pages and does not invent an unsubscribe URL.

Account deletion already deletes account-owned rows by user ID. Newsletter welcomes are independent of an account and the anonymous email-hash claim remains to prevent another welcome after account re-creation. It is not a contact list or a delivery log. Any future newsletter privacy-deletion or re-consent workflow must make an explicit decision about retaining this deduplication key and provider suppression state; this change does not alter those workflows.

## Local verification

`tests/test_newsletter_subscribe.py` executes the real route/helpers by AST in an isolated Flask app with SQLite and fake contact/mail providers. It covers simultaneous first requests, repeat and case variants, invalid addresses, CSRF, false/exceptional contact sync, unavailable schema, durable pending claims and ambiguous sends without retry. `tests/test_newsletter_presentation.py` checks multipart content, actual links and safe markup. No provider requests, configured application startup or database migration were performed.
