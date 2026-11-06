"""Reader credential changes with the same session revocation as account deletion."""

from datetime import datetime
from password_security import generate_password_hash, check_password_hash
from studio_auth import AuthError


class ReaderSettings:
    def __init__(self, store, auth, lifecycle, clock=None):
        self.store, self.auth, self.lifecycle = store, auth, lifecycle
        self.clock = clock or datetime.now

    @staticmethod
    def validate_new(password, confirmation):
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            raise AuthError("Choose a password with 8–128 characters.")
        if password != confirmation:
            raise AuthError("The new passwords do not match.")

    def invalidate(self, cur, uid, email):
        self.lifecycle.revoke_all(cur, uid)
        cur.execute("DELETE FROM password_resets WHERE email=%s", (email,))
        cur.execute(
            "UPDATE security_otp SET consumed_at=%s WHERE user_id=%s AND consumed_at IS NULL",
            (self.auth.clock(), uid),
        )

    def change_password(self, uid, current, password, confirmation, ip):
        self.auth.throttle("password-change-ip:" + str(ip), 20, 900)
        self.auth.throttle("password-change-account:" + str(uid), 5, 900)
        self.validate_new(password, confirmation)
        if not isinstance(current, str) or not current or len(current) > 1024:
            raise AuthError("Enter your current password.")
        with self.store.transaction() as cur:
            cur.execute("SELECT password,email FROM users WHERE id=%s FOR UPDATE", (uid,))
            user = cur.fetchone()
            if not user or not check_password_hash(user[0], current):
                raise AuthError("Your current password is incorrect.")
            if check_password_hash(user[0], password):
                raise AuthError("Choose a new password different from your current password.")
            cur.execute("UPDATE users SET password=%s WHERE id=%s", (generate_password_hash(password), uid))
            self.invalidate(cur, uid, user[1])
        self.auth.audit("reader_password_changed", uid)

    def reset_available(self, token):
        if not isinstance(token, str) or not token or len(token) > 256:
            return False
        row = self.store.query(
            "SELECT expires_at FROM password_resets WHERE token=%s", (token,), one=True
        )
        return bool(row and row[0] and row[0] > self.clock())

    def reset_password(self, token, password, confirmation):
        self.validate_new(password, confirmation)
        if not self.reset_available(token):
            raise AuthError("This reset link is invalid or has expired. Request a new link.")
        row = self.store.query(
            "SELECT u.id FROM users u JOIN password_resets r ON r.email=u.email WHERE r.token=%s",
            (token,), one=True,
        )
        if not row:
            raise AuthError("This reset link is invalid or has expired. Request a new link.")
        uid = row[0]
        with self.store.transaction() as cur:
            # Lock the user first, as in change_password, then recheck the token.
            cur.execute("SELECT email FROM users WHERE id=%s FOR UPDATE", (uid,))
            user = cur.fetchone()
            cur.execute("SELECT email,expires_at FROM password_resets WHERE token=%s FOR UPDATE", (token,))
            reset = cur.fetchone()
            if not user or not reset or reset[0] != user[0] or reset[1] <= self.clock():
                raise AuthError("This reset link is invalid or has expired. Request a new link.")
            cur.execute("UPDATE users SET password=%s WHERE id=%s", (generate_password_hash(password), uid))
            self.invalidate(cur, uid, user[0])
        self.auth.audit("reader_password_reset", uid)
