# Render deployment health check

7 November 2026.

The live DocoDive service watches the repository's `main` branch and uses
`/healthhz` for its HTTP health check. Deploy `1fe0655` started the application,
but that path repeatedly returned 404 until Render marked the deployment failed.
The configured Gunicorn command already binds to `0.0.0.0:$PORT`; changing its
port or increasing the timeout does not correct a missing HTTP path.

An exact GET/HEAD health handler now returns `ok` as plain text for `/healthhz`
and the conventional `/healthz` alias. It is registered before HTTPS redirects,
rate limits and session/database request hooks. It creates no CSRF session,
renders no page and performs no database or storage operation. Normal request
security remains in place. This is a process-health probe, not an integration
test of the database, email or file storage.

Five isolated regression tests cover probe responses, HEAD, no session cookie,
repeated probes, reader cookies, registration order and normal HTTPS/CSRF rules.
No environment-variable, database, pricing or infrastructure changes are needed.

Render accepts successful HTTP health responses before routing traffic to a new
instance; repeated 404 responses fail readiness. See the official
[health-check documentation](https://render.com/docs/health-checks). Main-branch
updates automatically deploy this service, so a second manual deploy should not
be triggered after merging. See [deploy behavior](https://render.com/docs/deploys).

Deployment verification records belong under `deliverables/render-health-fix/`
and are excluded from source publication. Monitor the resulting deploy until it
is live and confirm that `/healthhz` returns HTTP 200 before reporting success.
