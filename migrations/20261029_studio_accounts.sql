-- Studio security/account lifecycle additions. Review and apply with the existing migration runner.
-- All times are UTC. No user data is deleted by this migration.
CREATE TABLE IF NOT EXISTS security_rate_limits (
 bucket_key CHAR(64) PRIMARY KEY, window_start DATETIME(6) NOT NULL, hits INT NOT NULL DEFAULT 0
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS security_account_lock (
 account_key CHAR(64) PRIMARY KEY, failures INT NOT NULL DEFAULT 0, locked_until DATETIME(6) NOT NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS security_otp (
 challenge_id CHAR(64) PRIMARY KEY, purpose VARCHAR(24) NOT NULL, user_id BIGINT NOT NULL,
 binding_hash CHAR(64) NOT NULL, code_hash CHAR(64) NOT NULL, password_hash VARCHAR(255), pw_fingerprint CHAR(64),
 created_at DATETIME(6) NOT NULL, expires_at DATETIME(6) NOT NULL, attempts INT NOT NULL DEFAULT 0,
 consumed_at DATETIME(6), sent TINYINT NOT NULL DEFAULT 0,
 INDEX otp_user_purpose (user_id,purpose), INDEX otp_expiry (expires_at)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS admin_login_sessions (
 token_hash CHAR(64) PRIMARY KEY, user_id BIGINT NOT NULL, pw_fingerprint CHAR(64) NOT NULL,
 created_at DATETIME(6) NOT NULL, expires_at DATETIME(6) NOT NULL,
 INDEX session_user (user_id), INDEX session_expiry (expires_at)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS account_security (
 user_id BIGINT PRIMARY KEY, session_version INT NOT NULL DEFAULT 0
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS account_deletions (
 request_id CHAR(32) PRIMARY KEY, user_id BIGINT NOT NULL UNIQUE, username VARCHAR(255) NOT NULL,
 display_name VARCHAR(255) NOT NULL, email VARCHAR(254) NOT NULL, reason TEXT NOT NULL,
 status VARCHAR(20) NOT NULL, requested_at DATETIME(6) NOT NULL, deadline DATETIME(6) NOT NULL,
 approved_by BIGINT, approved_at DATETIME(6), deleted_at DATETIME(6), retention_until DATETIME(6),
 INDEX deletion_due (status,deadline), INDEX deletion_retention (retention_until)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS lifecycle_mail (
 event_key VARCHAR(100) PRIMARY KEY, user_id BIGINT, recipient VARCHAR(254) NOT NULL,
 subject VARCHAR(255) NOT NULL, body TEXT NOT NULL, html MEDIUMTEXT NOT NULL,
 created_at DATETIME(6) NOT NULL, next_attempt DATETIME(6) NOT NULL, attempts INT NOT NULL DEFAULT 0,
 sent_at DATETIME(6), lease_until DATETIME(6), INDEX mail_due (sent_at,next_attempt)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS activity_daily (
 activity_day DATE NOT NULL, user_id BIGINT NOT NULL, page_views INT NOT NULL DEFAULT 0,
 reads INT NOT NULL DEFAULT 0, downloads INT NOT NULL DEFAULT 0, last_seen DATETIME(6) NOT NULL,
 PRIMARY KEY (activity_day,user_id), INDEX activity_user (user_id,last_seen)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
 snapshot_day DATE NOT NULL, user_id INT NOT NULL, points BIGINT NOT NULL DEFAULT 0,
 PRIMARY KEY(snapshot_day,user_id), INDEX score_user(user_id)
) ENGINE=InnoDB;
