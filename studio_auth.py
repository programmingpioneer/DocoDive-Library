"""Persistent OTP and session security. No OTPs/passwords are written to logs."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from html import escape

OTP_TTL = timedelta(minutes=5)  # Every code expires after exactly five minutes.
SESSION_TTL = timedelta(hours=8)


class AuthError(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


class StudioAuth:
    def __init__(self, store, secret, send_mail, logger, clock=None):
        self.store, self.secret = store, str(secret).encode()
        self.send_mail, self.logger = send_mail, logger
        self.clock = clock or datetime.utcnow

    def digest(self, value):
        return hmac.new(self.secret, str(value).encode(), hashlib.sha256).hexdigest()

    def audit(self, event, user_id=None):
        self.logger.info("security_event=%s user_id=%s", event, user_id or "unknown")

    def throttle(self, scope, limit, seconds):
        now = self.clock()
        key = self.digest(scope)
        allowed = False
        with self.store.transaction() as cur:
            cur.execute(
                "INSERT IGNORE INTO security_rate_limits (bucket_key,window_start,hits) VALUES (%s,%s,0)",
                (key, now),
            )
            cur.execute(
                "SELECT window_start,hits FROM security_rate_limits WHERE bucket_key=%s FOR UPDATE",
                (key,),
            )
            started, hits = cur.fetchone()
            if now >= started + timedelta(seconds=seconds):
                started, hits = now, 0
            allowed = hits < limit
            cur.execute(
                "UPDATE security_rate_limits SET window_start=%s,hits=%s WHERE bucket_key=%s",
                (started, hits + 1, key),
            )
        if not allowed:
            raise AuthError("Too many attempts. Please wait before trying again.", 429)

    def login_gate(self, email, ip):
        self.throttle("login-ip:" + ip, 20, 900)
        self.throttle("login-account:" + email.lower(), 5, 900)
        row = self.store.query(
            "SELECT locked_until FROM security_account_lock WHERE account_key=%s",
            (self.digest(email.lower()),),
            one=True,
        )
        if row and row[0] and row[0] > self.clock():
            raise AuthError("Please wait before trying to sign in again.", 429)

    def login_failed(self, email):
        key, now = self.digest(email.lower()), self.clock()
        with self.store.transaction() as cur:
            cur.execute(
                "INSERT IGNORE INTO security_account_lock (account_key,failures,locked_until) VALUES (%s,0,%s)",
                (key, now),
            )
            cur.execute(
                "SELECT failures,locked_until FROM security_account_lock WHERE account_key=%s FOR UPDATE",
                (key,),
            )
            failures, until = cur.fetchone()
            failures = 0 if now > until + timedelta(minutes=15) else failures
            failures += 1
            wait = 900 if failures >= 5 else min(2**failures, 60)
            cur.execute(
                "UPDATE security_account_lock SET failures=%s,locked_until=%s WHERE account_key=%s",
                (failures, now + timedelta(seconds=wait), key),
            )
        self.audit("admin_password_failed")

    def issue(
        self, user_id, purpose, binding, email, ip, password_hash=None, fingerprint=None
    ):
        self.throttle("otp-ip:" + ip, 20, 3600)
        self.throttle("otp-account:" + str(user_id), 5, 3600)
        self.throttle("otp-cooldown:" + str(user_id), 1, 60)
        now, challenge = self.clock(), secrets.token_hex(32)
        code = f"{secrets.randbelow(1_000_000):06d}"
        with self.store.transaction() as cur:
            cur.execute(
                "UPDATE security_otp SET consumed_at=%s WHERE user_id=%s AND purpose=%s AND consumed_at IS NULL",
                (now, user_id, purpose),
            )
            cur.execute(
                "INSERT INTO security_otp (challenge_id,purpose,user_id,binding_hash,code_hash,password_hash,pw_fingerprint,created_at,expires_at,attempts,sent) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0)",
                (
                    challenge,
                    purpose,
                    user_id,
                    self.digest(binding),
                    self.digest(challenge + ":" + code),
                    password_hash,
                    fingerprint,
                    now,
                    now + OTP_TTL,
                ),
            )
        title = (
            "Admin Studio sign-in code"
            if purpose == "admin_login"
            else "Confirm your account deletion request"
        )
        html = (
            '<div style="font-family:Arial;background:#f1f5f9;padding:32px"><div style="max-width:520px;margin:auto;background:white;border-radius:20px;padding:32px"><p style="color:#4f46e5">DOCODIVE</p><h1 style="font-size:24px">'
            + escape(title)
            + '</h1><p>Your one-time verification code:</p><p style="font-size:36px;letter-spacing:8px;font-weight:bold">'
            + code
            + "</p><p>Expires in 5 minutes. Never share this code. If you did not request it, ignore this message.</p></div></div>"
        )
        try:
            delivered = self.send_mail(
                title,
                email,
                "Your code is " + code + ". It expires in 5 minutes.",
                html_body=html,
            )
        except Exception:
            delivered = False
        with self.store.transaction() as cur:
            if delivered:
                cur.execute(
                    "UPDATE security_otp SET sent=1 WHERE challenge_id=%s", (challenge,)
                )
            else:
                cur.execute(
                    "UPDATE security_otp SET consumed_at=%s WHERE challenge_id=%s",
                    (now, challenge),
                )
        self.audit("otp_issued" if delivered else "otp_delivery_failed", user_id)
        if not delivered:
            raise AuthError(
                "Email could not be sent. Wait 60 seconds and try again.", 503
            )
        return challenge

    def verify(self, challenge, purpose, binding, code):
        now, result, error = (
            self.clock(),
            None,
            "This code is invalid or expired. Request a new code.",
        )
        with self.store.transaction() as cur:
            cur.execute(
                "SELECT user_id,binding_hash,code_hash,expires_at,attempts,consumed_at,sent,password_hash,pw_fingerprint FROM security_otp WHERE challenge_id=%s AND purpose=%s FOR UPDATE",
                (challenge, purpose),
            )
            row = cur.fetchone()
            if (
                row
                and hmac.compare_digest(row[1], self.digest(binding))
                and row[5] is None
            ):
                (
                    uid,
                    _,
                    encoded,
                    expires,
                    attempts,
                    _,
                    sent,
                    password_hash,
                    fingerprint,
                ) = row
                if now >= expires or attempts >= 3 or not sent:
                    cur.execute(
                        "UPDATE security_otp SET consumed_at=%s WHERE challenge_id=%s",
                        (now, challenge),
                    )
                    self.audit("otp_expired", uid)
                elif not (
                    isinstance(code, str)
                    and len(code) == 6
                    and code.isascii()
                    and code.isdigit()
                    and hmac.compare_digest(
                        encoded, self.digest(challenge + ":" + code)
                    )
                ):
                    attempts += 1
                    cur.execute(
                        "UPDATE security_otp SET attempts=%s,consumed_at=%s WHERE challenge_id=%s",
                        (attempts, now if attempts >= 3 else None, challenge),
                    )
                    self.audit("otp_failed", uid)
                    error = (
                        "Incorrect code. " + str(3 - attempts) + " attempts remaining."
                        if attempts < 3
                        else "Code invalidated after 3 attempts. Request a new code."
                    )
                else:
                    cur.execute(
                        "UPDATE security_otp SET consumed_at=%s WHERE challenge_id=%s",
                        (now, challenge),
                    )
                    result = (uid, password_hash, fingerprint)
                    self.audit("otp_verified", uid)
        if result is None:
            raise AuthError(error)
        return result

    def new_session(self, uid, fingerprint):
        token, now = secrets.token_urlsafe(32), self.clock()
        with self.store.transaction() as cur:
            cur.execute(
                "INSERT INTO admin_login_sessions (token_hash,user_id,pw_fingerprint,created_at,expires_at) VALUES (%s,%s,%s,%s,%s)",
                (self.digest(token), uid, fingerprint, now, now + SESSION_TTL),
            )
        self.audit("admin_login_success", uid)
        return token

    def valid_session(self, token, uid):
        return bool(
            token
            and self.store.query(
                "SELECT s.user_id FROM admin_login_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.user_id=%s AND s.expires_at>%s AND s.pw_fingerprint=%s",
                (self.digest(token), uid, self.clock(), self.password_fingerprint(uid)),
                one=True,
            )
        )

    def password_fingerprint(self, uid):
        row = self.store.query(
            "SELECT password FROM users WHERE id=%s", (uid,), one=True
        )
        return self.digest(row[0]) if row else ""

    def revoke(self, token):
        with self.store.transaction() as cur:
            cur.execute(
                "DELETE FROM admin_login_sessions WHERE token_hash=%s",
                (self.digest(token or ""),),
            )
