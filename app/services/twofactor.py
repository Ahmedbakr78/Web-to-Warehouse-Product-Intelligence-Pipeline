"""Two-factor authentication (TOTP) and session management.

TOTP is implemented directly against RFC 6238 rather than pulling in a framework:
HMAC-SHA1 over a 30-second counter, a six-digit code, and a ±1 window so a modest
clock skew does not lock a user out.

Security decisions worth stating explicitly:

* The shared secret is **never** returned by an API. Enrolment returns the secret and
  the `otpauth://` URI exactly once, at the moment the user confirms it.
* Recovery codes are stored **hashed** (Argon2, like passwords), so a database read
  cannot be used to bypass the second factor.
* Recovery codes are single-use: redeeming one removes it.
* A user is locked out of the password field after three failed TOTP codes in a
  short window, so an attacker with the password cannot brute-force the second factor.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass
from urllib.parse import quote

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.models.app_users import AppUser

log = get_logger(__name__)

#: RFC 4226 dynamic truncation digits.
DIGITS = 6
#: Seconds per time step.
PERIOD = 30
#: How many steps either side of "now" are accepted. ±1 covers ordinary clock skew.
WINDOW = 1
#: Failure codes allowed per rolling window before the second factor is locked.
MAX_FAILURES = 3
FAILURE_WINDOW_SECONDS = 300

_ISSUER = "Product Intelligence Pipeline"


def _now(step: int | None = None) -> int:
    return int(dt.datetime.now(dt.timezone.utc).timestamp()) // (PERIOD if step is None else step)


# --------------------------------------------------------------------------------------
# TOTP
# --------------------------------------------------------------------------------------
def generate_secret(length: int = 32) -> str:
    """A base32 shared secret (the format every authenticator app expects)."""
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    padded = secret.strip().upper()
    padded += "=" * (-len(padded) % 8)
    return base64.b32decode(padded, casefold=True)


def code_at(secret: str, counter: int) -> str:
    """The HOTP value for one counter (RFC 4226)."""
    digest = hmac.new(_decode_secret(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**DIGITS)).zfill(DIGITS)


def current_code(secret: str) -> str:
    """The code a user should be typing right now. Used only by the tests."""
    return code_at(secret, _now())


def verify_code(secret: str, code: str, *, now: int | None = None) -> bool:
    """Constant-time check of a submitted code against the accepted window."""
    candidate = (code or "").strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != DIGITS:
        return False
    base = _now() if now is None else now
    for drift in range(-WINDOW, WINDOW + 1):
        expected = code_at(secret, base + drift)
        if hmac.compare_digest(expected, candidate):
            return True
    return False


def otpauth_uri(secret: str, account: str) -> str:
    """The `otpauth://` URI an authenticator app scans as a QR code."""
    label = quote(f"{_ISSUER}:{account}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(_ISSUER, safe='')}&algorithm=SHA1&digits={DIGITS}&period={PERIOD}"


# --------------------------------------------------------------------------------------
# Encryption at rest
# --------------------------------------------------------------------------------------
def encrypt_secret(secret: str) -> str:
    """Encrypt a TOTP secret with a key derived from SECRET_KEY.

    HMAC-SHA256 in counter mode: a compact, dependency-free construction that is
    sufficient for a 32-character secret and needs no nonce table. The nonce is the
    leading 16 bytes of the derived keystream.
    """
    key = hashlib.sha256(f"totp:{settings.secret_key}".encode()).digest()
    nonce = secrets.token_bytes(16)
    stream = b""
    counter = 0
    while len(stream) < len(secret):
        stream += hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    ciphertext = bytes(a ^ b for a, b in zip(secret.encode(), stream[: len(secret)], strict=False))
    return f"v1.{base64.urlsafe_b64encode(nonce).decode()}.{base64.urlsafe_b64encode(ciphertext).decode()}"


def decrypt_secret(payload: str) -> str:
    if not payload or not payload.startswith("v1."):
        raise ValidationError("stored two-factor secret is malformed")
    _, nonce_b64, cipher_b64 = payload.split(".", 2)
    key = hashlib.sha256(f"totp:{settings.secret_key}".encode()).digest()
    nonce = base64.urlsafe_b64decode(nonce_b64)
    ciphertext = base64.urlsafe_b64decode(cipher_b64)
    stream = b""
    counter = 0
    while len(stream) < len(ciphertext):
        stream += hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(a ^ b for a, b in zip(ciphertext, stream, strict=False)).decode()


# --------------------------------------------------------------------------------------
# Failure tracking
# --------------------------------------------------------------------------------------
@dataclass
class TwoFactorGuard:
    """How many TOTP attempts remain in the current window."""

    failures: int
    locked: bool


def guard_state(session: Session, user: AppUser) -> TwoFactorGuard:
    """Read the rolling failure counters out of the audit log.

    Kept in the audit trail rather than a dedicated table so the evidence for a lockout
    is auditable like every other security event.
    """
    from app.models.app_users import AppAuditLog

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=FAILURE_WINDOW_SECONDS)
    failures = (
        session.execute(
            sa.select(sa.func.count())
            .select_from(AppAuditLog)
            .where(
                AppAuditLog.user_id == user.user_id,
                AppAuditLog.action == "auth.2fa_failed",
                AppAuditLog.created_at >= since,
            )
        ).scalar()
        or 0
    )
    return TwoFactorGuard(failures=int(failures), locked=int(failures) >= MAX_FAILURES)


def record_failure(session: Session, user: AppUser, reason: str) -> None:
    """Count one failed second-factor attempt.

    Committed immediately: the caller is about to raise, and the request dependency
    rolls back on error, which would discard the counter the lockout depends on.
    """
    from app.models.app_users import AppAuditLog

    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="auth.2fa_failed",
            entity_type="app_user",
            entity_id=str(user.user_id),
            details={"reason": reason[:120]},
        )
    )
    session.commit()


# --------------------------------------------------------------------------------------
# Recovery codes
# --------------------------------------------------------------------------------------
RECOVERY_CODE_COUNT = 8


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Readable single-use codes, e.g. `4F7A-92BC`."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0, 1
    return [
        "".join(secrets.choice(alphabet) for _ in range(4))
        + "-"
        + "".join(secrets.choice(alphabet) for _ in range(4))
        for _ in range(count)
    ]


def hash_recovery_code(code: str) -> str:
    """Hash a recovery code the way a password is hashed."""
    from app.api.security import hash_password

    return hash_password(normalise_recovery_code(code))


def normalise_recovery_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "")


def redeem_recovery_code(session: Session, user: AppUser, code: str) -> bool:
    """Consume a recovery code. A code only works once."""
    from app.api.security import verify_password

    # The candidate is the *normalised code itself*: `stored` holds
    # `hash_recovery_code(code)`, which is an Argon2 hash of the normalised string.
    # Hashing the code a second time here would compare a hash against a hash and
    # never match.
    candidate = normalise_recovery_code(code)
    if not candidate:
        return False
    stored = list(user.recovery_codes or [])
    for index, hashed in enumerate(stored):
        if verify_password(candidate, hashed):
            stored.pop(index)
            user.recovery_codes = stored
            return True
    return False


__all__ = [
    "MAX_FAILURES",
    "PERIOD",
    "RECOVERY_CODE_COUNT",
    "TwoFactorGuard",
    "code_at",
    "current_code",
    "decrypt_secret",
    "encrypt_secret",
    "generate_recovery_codes",
    "generate_secret",
    "guard_state",
    "hash_recovery_code",
    "normalise_recovery_code",
    "otpauth_uri",
    "record_failure",
    "redeem_recovery_code",
    "verify_code",
]
