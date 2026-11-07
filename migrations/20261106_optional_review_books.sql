-- Optional book selection for written reviews and their official replies.
-- Review and run manually against ONE explicitly selected database before deploying
-- the matching application change. Do not run with a client that ignores errors.
-- No rows are inserted, updated, or deleted. Foreign keys and indexes stay in place.
-- See migrations/README-OPTIONAL-REVIEW-BOOKS.md for preflight and verification.

-- Both columns must exist as ordinary integer columns on base tables before either
-- ALTER is attempted. Unexpected schemas fail closed for manual review.
SET @optional_review_books_valid = (
    SELECT COUNT(*) = 2
       AND COALESCE(SUM(
           c.DATA_TYPE IN ('tinyint', 'smallint', 'mediumint', 'int', 'bigint')
           AND c.EXTRA = ''
           AND c.COLUMN_KEY <> 'PRI'
           AND (c.COLUMN_DEFAULT IS NULL OR c.COLUMN_DEFAULT REGEXP '^-?[0-9]+$')
           AND t.TABLE_TYPE = 'BASE TABLE'
       ), 0) = 2
    FROM information_schema.COLUMNS c
    JOIN information_schema.TABLES t
      ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
    WHERE c.TABLE_SCHEMA = DATABASE()
      AND c.TABLE_NAME IN ('reviews', 'book_comments')
      AND c.COLUMN_NAME = 'book_id'
);

SELECT IF(
    @optional_review_books_valid,
    'READY: both review book_id columns have supported definitions',
    'STOP: select the intended database and inspect both book_id definitions; no ALTER is permitted'
) AS optional_review_books_preflight;

-- This intentionally invalid, harmless statement makes PREPARE fail if preflight
-- failed. Both ALTER builders depend on the same guard, even if a client continues.
SET @optional_review_books_invalid_sql = 'DOCODIVE_OPTIONAL_REVIEW_BOOKS_SCHEMA_PRECONDITION_FAILED';

SET @optional_review_books_sql = IF(
    @optional_review_books_valid,
    (
        SELECT IF(
            IS_NULLABLE = 'YES',
            'SELECT ''reviews.book_id already permits NULL'' AS optional_review_books_status',
            CONCAT(
                'ALTER TABLE `reviews` MODIFY COLUMN `book_id` ', COLUMN_TYPE, ' NULL DEFAULT ',
                IF(COLUMN_DEFAULT IS NULL, 'NULL', COLUMN_DEFAULT),
                ' COMMENT ',
                IF(
                    FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@SESSION.sql_mode) > 0,
                    CONCAT(CHAR(39), REPLACE(COLUMN_COMMENT, CHAR(39), CONCAT(CHAR(39), CHAR(39))), CHAR(39)),
                    QUOTE(COLUMN_COMMENT)
                )
            )
        )
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reviews' AND COLUMN_NAME = 'book_id'
    ),
    @optional_review_books_invalid_sql
);
PREPARE optional_review_books_statement FROM @optional_review_books_sql;
EXECUTE optional_review_books_statement;
DEALLOCATE PREPARE optional_review_books_statement;

SET @optional_review_books_sql = IF(
    @optional_review_books_valid,
    (
        SELECT IF(
            IS_NULLABLE = 'YES',
            'SELECT ''book_comments.book_id already permits NULL'' AS optional_review_books_status',
            CONCAT(
                'ALTER TABLE `book_comments` MODIFY COLUMN `book_id` ', COLUMN_TYPE, ' NULL DEFAULT ',
                IF(COLUMN_DEFAULT IS NULL, 'NULL', COLUMN_DEFAULT),
                ' COMMENT ',
                IF(
                    FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@SESSION.sql_mode) > 0,
                    CONCAT(CHAR(39), REPLACE(COLUMN_COMMENT, CHAR(39), CONCAT(CHAR(39), CHAR(39))), CHAR(39)),
                    QUOTE(COLUMN_COMMENT)
                )
            )
        )
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'book_comments' AND COLUMN_NAME = 'book_id'
    ),
    @optional_review_books_invalid_sql
);
PREPARE optional_review_books_statement FROM @optional_review_books_sql;
EXECUTE optional_review_books_statement;
DEALLOCATE PREPARE optional_review_books_statement;

SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('reviews', 'book_comments')
  AND COLUMN_NAME = 'book_id'
ORDER BY TABLE_NAME;

SET @optional_review_books_valid = NULL;
SET @optional_review_books_invalid_sql = NULL;
SET @optional_review_books_sql = NULL;
