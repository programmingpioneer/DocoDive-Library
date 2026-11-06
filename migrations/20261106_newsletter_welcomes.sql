-- Apply to one reviewed database before deploying the newsletter welcome code.
-- No existing data is changed. No raw email addresses are stored in this ledger.
CREATE TABLE IF NOT EXISTS newsletter_welcomes (
    email_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    welcome_status VARCHAR(12) NOT NULL DEFAULT 'claimed',
    claimed_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NULL
) ENGINE=InnoDB;
