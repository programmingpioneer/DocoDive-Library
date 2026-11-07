# Optional review books migration

`20261106_optional_review_books.sql` makes `reviews.book_id` and `book_comments.book_id` accept SQL `NULL`. A review without a selected book is general DocoDive feedback. Official replies to that review also have a null book ID. Existing book reviews retain their associations.

This file has **not been run against a database**. The repository does not provide the current schema, so review the actual column definitions before applying it.

## Apply

1. Take a database backup using the deployment's established process. Schedule the change when an `ALTER TABLE` metadata lock or table rebuild is acceptable.
2. Connect using the MySQL client to **one explicitly selected target database**. Confirm `SELECT DATABASE();` names the intended database. Inspect `SHOW CREATE TABLE reviews;` and `SHOW CREATE TABLE book_comments;`.
3. Run the complete file in one connection with stop-on-error enabled. For the command-line MySQL client on PowerShell, the following supplies batch input; replace the saved connection and database names with the reviewed target. Use the deployment's existing authentication method rather than putting a password in the command:

   ```powershell
   Get-Content -Raw -LiteralPath 'D:\MY PROJECTS\PioneerDocoDive\migrations\20261106_optional_review_books.sql' | mysql --login-path=YOUR_SAVED_CONNECTION --database=YOUR_DATABASE --default-character-set=utf8mb4
   ```

   Do not add `--force` or use a script runner that continues after errors. If using an administration interface instead, open the file and select its stop-on-error execution option.

4. Confirm the preflight says `READY`, no statements failed, and the final result contains exactly these two rows with `IS_NULLABLE = YES`. `COLUMN_TYPE` must match the preflight definitions, including size and `unsigned` where present.
5. Deploy the matching application change only after both columns permit nulls. Verify general feedback and selected-book reviews in the approved deployment test process, including an official reply to general feedback.

Apply each environment separately. `run_migration.py` is hardcoded to an older staging migration and continues after errors; it is not the runner for this file. Do not append this file to an automatic multi-environment migration without reviewing that runner's handling of session variables, prepared statements, and failures.

## Behavior and limits

The script obtains each exact integer `COLUMN_TYPE` from `information_schema.COLUMNS`, so it does not guess a foreign-key type or change signedness. It preserves ordinary integer defaults and column comments. Existing foreign keys, indexes, and rows remain in place. Already-nullable columns are left untouched, making a second application a no-op for them.

Both expected columns must exist on base tables as ordinary, non-primary-key integer columns. Generated columns, special `EXTRA` attributes, non-integer defaults, missing columns, or no selected database fail preflight before either `ALTER`. A failure includes `DOCODIVE_OPTIONAL_REVIEW_BOOKS_SCHEMA_PRECONDITION_FAILED`; inspect the actual schema and adapt the migration deliberately. The script does not create absent tables or remove constraints.

MySQL DDL can commit immediately. The two column changes are not one atomic transaction, and a database error on the second `ALTER` can leave only the first changed. Correct the failure and rerun the file; an already-nullable first column will be skipped. Do not disable foreign-key checks to bypass a schema error.

There is no automatic rollback to `NOT NULL`: once general feedback exists, that would reject real rows with null book IDs. Keep the nullable columns when rolling back only application code, or plan an explicit data decision before tightening the schema.
