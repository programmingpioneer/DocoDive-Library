#!/usr/bin/env python3
"""
DocoDive — single-file migration runner.

Usage:
    python scripts/run_all.py                    # runs staging + prod
    python scripts/run_all.py --dry-run          # preview, no changes
    python scripts/run_all.py --env .env.prod    # only prod
    python scripts/run_all.py --env .env         # only staging

How it works:
    1. Reads migrations/all_changes.sql
    2. Splits into individual statements (by semicolon)
    3. For each statement, computes SHA256 hash
    4. Checks 'statement_log' table — if hash already applied, skip
    5. If new, executes it and records hash

Ye safe hai — dobara chalao, purane statements skip ho jayenge.
"""

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

try:
    import mysql.connector
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install: pip install mysql-connector-python python-dotenv")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANGES_FILE = PROJECT_ROOT / "migrations" / "all_changes.sql"

def strip_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments."""
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    lines = []
    for line in sql.splitlines():
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
    return "\n".join(lines)

def split_statements(sql: str) -> list[str]:
    """Split into individual statements by semicolons."""
    sql = strip_comments(sql)
    parts = [s.strip() for s in sql.split(";")]
    return [s for s in parts if s]

def statement_hash(stmt: str) -> str:
    """Stable hash of a statement (normalized whitespace)."""
    normalized = re.sub(r"\s+", " ", stmt).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

def apply_env(env_file: Path, dry_run: bool) -> list[tuple[str, str]]:
    """Apply all pending statements to the DB in env_file."""
    if not env_file.exists():
        return [("(env)", f"FILE NOT FOUND: {env_file}")]

    for key in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME", "DB_PORT"):
        os.environ.pop(key, None)
    load_dotenv(env_file, override=True)

    db_name = os.getenv("DB_NAME", "?")

    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=db_name,
            port=int(os.getenv("DB_PORT", "4000")),
            connection_timeout=10,
            read_timeout=30,
            write_timeout=30,
        )
    except Exception as e:
        return [("(connect)", f"FAILED: {e}")]

    cur = conn.cursor()

    # Ensure the tracking table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS statement_log (
            hash VARCHAR(32) NOT NULL PRIMARY KEY,
            stmt_preview VARCHAR(200),
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    conn.commit()

    cur.execute("SELECT hash FROM statement_log")
    applied = {row[0] for row in cur.fetchall()}

    if not CHANGES_FILE.exists():
        cur.close(); conn.close()
        return [("(file)", f"MISSING: {CHANGES_FILE}")]

    statements = split_statements(CHANGES_FILE.read_text(encoding="utf-8"))

    results: list[tuple[str, str]] = []
    for idx, stmt in enumerate(statements, start=1):
        h = statement_hash(stmt)
        preview = re.sub(r"\s+", " ", stmt)[:60]

        if h in applied:
            results.append((f"#{idx:03d}", f"SKIP (already applied)  | {preview}"))
            continue

        if dry_run:
            results.append((f"#{idx:03d}", f"WOULD APPLY              | {preview}"))
            continue

        try:
            cur.execute(stmt)
            conn.commit()
            cur.execute(
                "INSERT INTO statement_log (hash, stmt_preview) VALUES (%s, %s)",
                (h, preview),
            )
            conn.commit()
            results.append((f"#{idx:03d}", f"APPLIED                  | {preview}"))
        except mysql.connector.Error as e:
            err = str(e)
            if ("Duplicate column" in err
                    or "Duplicate key name" in err
                    or "already exists" in err
                    or "Duplicate entry" in err):
                conn.rollback()
                cur.execute(
                    "INSERT IGNORE INTO statement_log (hash, stmt_preview) VALUES (%s, %s)",
                    (h, preview),
                )
                conn.commit()
                results.append((f"#{idx:03d}", f"SKIP (guarded: exists)   | {preview}"))
            else:
                conn.rollback()
                results.append((f"#{idx:03d}", f"FAILED: {err[:80]}       | {preview}"))

    cur.close()
    conn.close()
    return results

def main():
    ap = argparse.ArgumentParser(description="DocoDive single-file migration runner")
    ap.add_argument("--env", action="append", default=None,
                    help="Env file (repeatable). Default: .env then .env.prod")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env_files = args.env or [".env", ".env.prod"]
    env_paths = [(PROJECT_ROOT / e).resolve() for e in env_files]

    print(f"File: {CHANGES_FILE}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'APPLY'}")
    print(f"Envs: {[p.name for p in env_paths]}\n")

    any_failure = False
    for env_path in env_paths:
        print("=" * 72)
        print(f"ENV: {env_path.name}")
        print("=" * 72)
        results = apply_env(env_path, args.dry_run)
        for tag, status in results:
            mark = "!! " if "FAILED" in status else "OK "
            print(f"  {mark}{tag}  {status}")
        if any("FAILED" in s for _, s in results):
            any_failure = True
        print()

    if any_failure:
        print("RESULT: One or more environments FAILED.")
        sys.exit(1)
    print("RESULT: All environments OK.")

if __name__ == "__main__":
    main()
