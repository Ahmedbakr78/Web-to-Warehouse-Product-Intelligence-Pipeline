"""Browser session tracking.

Every login writes an `app_session` row so the Account screen can show the user their
own signed-in devices and revoke any of them. The refresh token is stored only as a
SHA-256 digest: a database read must not be enough to replay a session.

Revocation is what gives "sign out everywhere" meaning. Without it, ending a session
only discards the access token and the refresh token keeps minting new ones.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.models.app_users import AppSession

log = get_logger(__name__)


def hash_refresh_token(token: str) -> str:
    """Digest a refresh token for storage.

    A plain SHA-256 (not Argon2) is correct here: the input is already 256 bits of
    signed, unguessable entropy, so there is nothing for a slow KDF to defend against,
    and lookups must stay indexable and fast.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def is_active(row: AppSession) -> bool:
    if row.revoked_at is not None:
        return False
    expires = row.expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.timezone.utc)
        return expires > _now()
    return True


def assert_session_active(session: Session, session_key: str, user_id: int) -> AppSession:
    """Refuse a refresh for a session that was revoked or has expired."""
    row = (
        session.execute(sa.select(AppSession).where(AppSession.session_key == session_key)).scalars().first()
    )
    if row is None or row.user_id != user_id:
        raise AuthenticationError("unknown session")
    if not is_active(row):
        reason = "revoked" if row.revoked_at else "expired"
        raise AuthenticationError(f"this session has been {reason}; sign in again")
    return row


def touch(session: Session, session_key: str) -> None:
    """Record activity so the UI can show a last-seen timestamp."""
    session.execute(
        sa.update(AppSession)
        .where(AppSession.session_key == session_key, AppSession.revoked_at.is_(None))
        .values(last_seen_at=_now())
    )


def revoke_session(
    session: Session,
    session_key: str,
    user_id: int,
    *,
    reason: str = "revoked",
) -> bool:
    """Revoke one session. Returns False when the key is unknown or not theirs."""
    result = session.execute(
        sa.update(AppSession)
        .where(
            AppSession.session_key == session_key,
            AppSession.user_id == user_id,
            AppSession.revoked_at.is_(None),
        )
        .values(revoked_at=_now(), revoked_reason=reason)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


def revoke_all(session: Session, user_id: int, *, keep: str | None = None) -> int:
    """Revoke every session for a user, optionally keeping the current one."""
    conditions = [AppSession.user_id == user_id, AppSession.revoked_at.is_(None)]
    if keep:
        conditions.append(AppSession.session_key != keep)
    result = session.execute(
        sa.update(AppSession)
        .where(*conditions)
        .values(revoked_at=_now(), revoked_reason="signed out everywhere")
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def purge_expired(session: Session, older_than_days: int = 30) -> int:
    """Delete rows for sessions that ended long ago, so the table cannot grow forever."""
    cutoff = _now() - dt.timedelta(days=older_than_days)
    result = session.execute(sa.delete(AppSession).where(AppSession.expires_at < cutoff))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def list_sessions(session: Session, user_id: int, *, current_key: str | None = None) -> list[dict]:
    """The user's sessions, newest first, flagged with the current one."""
    rows = (
        session.execute(
            sa.select(AppSession)
            .where(AppSession.user_id == user_id)
            .order_by(AppSession.created_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    sessions: list[dict] = []
    for row in rows:
        sessions.append(
            {
                "session_key": row.session_key,
                "created_at": row.created_at,
                "last_seen_at": row.last_seen_at,
                "expires_at": row.expires_at,
                "ip_address": row.ip_address,
                "user_agent": row.user_agent,
                "revoked_at": row.revoked_at,
                "revoked_reason": row.revoked_reason,
                "is_active": is_active(row),
                "is_current": row.session_key == current_key,
            }
        )
    return sessions


def describe_agent(user_agent: str | None) -> str:
    """A short, human label for a user-agent string.

    Deliberately coarse: the goal is "Chrome on Linux", not a full parser.
    """
    if not user_agent:
        return "Unknown device"
    agent = user_agent.lower()
    browser = "Unknown browser"
    for needle, label in (
        ("edg/", "Edge"),
        ("opr/", "Opera"),
        ("chrome/", "Chrome"),
        ("firefox/", "Firefox"),
        ("safari/", "Safari"),
    ):
        if needle in agent:
            browser = label
            break
    platform = "Unknown platform"
    for needle, label in (
        ("android", "Android"),
        ("iphone", "iPhone"),
        ("ipad", "iPad"),
        ("windows", "Windows"),
        ("mac os", "macOS"),
        ("linux", "Linux"),
    ):
        if needle in agent:
            platform = label
            break
    return f"{browser} on {platform}"


__all__ = [
    "assert_session_active",
    "describe_agent",
    "hash_refresh_token",
    "is_active",
    "list_sessions",
    "purge_expired",
    "revoke_all",
    "revoke_session",
    "touch",
]
