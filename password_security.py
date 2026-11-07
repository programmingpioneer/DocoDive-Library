"""Argon2id for new passwords, with compatibility for existing Werkzeug hashes."""

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from werkzeug.security import check_password_hash as check_legacy_hash

_hasher = PasswordHasher()


def generate_password_hash(password):
    return _hasher.hash(password)


def check_password_hash(encoded, password):
    if not encoded or not isinstance(password, str) or len(password) > 1024:
        return False
    if encoded.startswith("$argon2"):
        try:
            return _hasher.verify(encoded, password)
        except (VerificationError, InvalidHashError):
            return False
    try:
        return check_legacy_hash(encoded, password)
    except (ValueError, TypeError):
        return False


def needs_rehash(encoded):
    return not encoded.startswith("$argon2") or _hasher.check_needs_rehash(encoded)
