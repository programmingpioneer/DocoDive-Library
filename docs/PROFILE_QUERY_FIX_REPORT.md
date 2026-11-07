# Profile missing-result crash — 1 November 2026

The supplied Sentry email reports a development request to the local user profile route. At the reported `app.py` line, `cur.fetchone()` returned `None`; indexing `[0]` raised `TypeError: 'NoneType' object is not subscriptable`.

## Fix

- The profile now checks every uploads, reviews, favorites, points and downloads result before reading it. A missing row stays unavailable rather than becoming a fabricated zero. The page shows a dash and a small status notice.
- Real zero counts still show zero. A present `SUM(points)` row containing SQL NULL still becomes zero, as expected for no recorded points.
- Achievements are calculated only when their required download/favorite/review totals are available. A missing unrelated upload or points result does not hide otherwise valid achievements.
- The cursor closes in `finally`, including on missing-user 404s and SQL errors. The site-setting helper runs after that cursor is finished, avoiding overlapping result access.
- Parameterized queries, owner-only profile email and the missing-user 404 remain intact. Actual SQL failures are still raised and logged rather than silently converted to zero.

An ordinary COUNT aggregate should return a row even for an account with no activity. The screenshot establishes the missing-result crash; it does not establish why the database driver returned no row. This patch handles that unexpected condition and adds cursor cleanup, without claiming a verified TiDB/driver diagnosis. Sentry reporting remains enabled.

## Verification

- The original TypeError was reproduced before the fix for each of the five aggregate-result positions.
- Five new regression tests pass: missing results, valid positive counts/achievements, an empty account with NULL point sum, missing-user 404 and cursor cleanup after SQL errors.
- **99 tests pass** in the full isolated suite. Python source compiles without importing configured `app.py`; all 143 Jinja templates parse.
- A separate read-only review found no actionable issues and independently ran the five focused tests.
- The synthetic profile preview rendered the missing-data state at 1366px and 320px, plus the normal profile at 320px. Three browser observations show no horizontal overflow and no console errors. Screenshots and measurements are in `deliverables/profile-query-fix/`.

No real database, Sentry dashboard, Gmail account, environment file, credentials, email delivery, staging/live environment or deployment was accessed. No new migration or dependency is required. The synthetic preview is only a visual check; the route's missing-result path was exercised by isolated database-boundary tests.

Restart the local app and reopen the profile. The existing Sentry email is a record of the earlier event; this work changes the local source and does not mark a remote Sentry issue resolved.
