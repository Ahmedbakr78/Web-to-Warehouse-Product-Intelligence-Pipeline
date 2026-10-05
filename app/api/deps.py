"""FastAPI dependencies: database session, pagination, authentication and RBAC."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Generator
from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.security import (
    ROLE_RIGHTS,
    decode_token,
    has_right,
    hash_api_key,
    verify_api_key,
)
from app.core.config import settings
from app.core.db import get_session_factory
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.logging import get_logger
from app.models.app_users import AppApiKey, AppUser

log = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token (Bearer) or API key")

# A bare, optionally schema-qualified SQL identifier: letters, digits, underscore
# and at most one dot. Anything else can never reach an ORDER BY clause.
_SORTABLE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?")


# --------------------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """Yield a transactional session bound to the active database."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_optional_db() -> Generator[Session, None, None]:
    """Session for endpoints that must answer even when the DB is down."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


DbOptional = Annotated[Session, Depends(get_optional_db)]


# --------------------------------------------------------------------------------------
# Pagination / sorting
# --------------------------------------------------------------------------------------
class Pagination:
    """``?page=&page_size=&sort_by=&sort_dir=`` with sane upper bounds."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1, le=10_000, description="1-based page number")] = 1,
        page_size: Annotated[int, Query(ge=1, le=200, description="Rows per page")] = 25,
        sort_by: Annotated[str | None, Query(description="Field to sort by")] = None,
        sort_dir: Annotated[Literal["asc", "desc"], Query(description="Sort direction")] = "desc",
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.sort_by = sort_by
        self.sort_dir = sort_dir

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def order(self) -> str:
        """A safe ORDER BY fragment.

        The previous implementation interpolated `sort_by` straight into the
        clause, which was a latent SQL-injection footgun for any future caller.
        The column is now validated against `SORTABLE_COLUMNS` (identifier
        characters only) and falls back to `created_at`, and the direction is
        constrained to ASC/DESC. Routers with a wider allow-list build their own
        fragment from their `SORTABLE` map.
        """
        direction = "ASC" if str(self.sort_dir).lower() == "asc" else "DESC"
        candidate = (self.sort_by or "created_at").strip()
        if not _SORTABLE_RE.fullmatch(candidate):
            candidate = "created_at"
        return f"{candidate} {direction}"


PaginationDep = Annotated[Pagination, Depends(Pagination)]


# --------------------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------------------
def _resolve_token(session: Session, credentials: HTTPAuthorizationCredentials | None) -> AppUser:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError(
            "authentication required", details={"hint": "send an 'Authorization: Bearer <token>' header"}
        )
    token = credentials.credentials

    # API key authentication (machine clients)
    if token.startswith("pip_"):
        digest = hash_api_key(token)
        row = (
            session.execute(
                sa.select(AppApiKey).where(AppApiKey.hashed_key == digest, AppApiKey.is_active.is_(True))
            )
            .scalars()
            .first()
        )
        if row is None:
            raise AuthenticationError("invalid API key")
        if row.expires_at and row.expires_at < dt.datetime.now(dt.timezone.utc):
            raise AuthenticationError("API key expired")
        user = session.get(AppUser, row.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("API key owner is not active")
        row.usage_count = (row.usage_count or 0) + 1
        row.last_used_at = dt.datetime.now(dt.timezone.utc)
        return user

    payload = decode_token(token, expected_type="access")
    user = session.get(AppUser, int(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("user not found or deactivated")
    return user


def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> AppUser:
    return _resolve_token(session, credentials)


CurrentUser = Annotated[AppUser, Depends(get_current_user)]


def get_current_user_optional(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> AppUser | None:
    try:
        return _resolve_token(session, credentials)
    except AuthenticationError:
        return None


OptionalUser = Annotated[AppUser | None, Depends(get_current_user_optional)]


def require_rights(*rights: str):
    """Dependency factory: require every listed right on the caller's role."""

    def dependency(user: CurrentUser) -> AppUser:
        missing = [right for right in rights if not has_right(user.role, right)]
        if missing:
            raise PermissionDeniedError(
                f"role '{user.role}' lacks the required permission(s): {', '.join(missing)}",
                details={
                    "role": user.role,
                    "missing": missing,
                    "granted": sorted(ROLE_RIGHTS.get(user.role, set())),
                },
            )
        return user

    return dependency


ReadUser = Annotated[AppUser, Depends(require_rights("read"))]
WriteUser = Annotated[AppUser, Depends(require_rights("write"))]
AdminUser = Annotated[AppUser, Depends(require_rights("manage_users"))]
PipelineUser = Annotated[AppUser, Depends(require_rights("run_pipeline"))]
QueryUser = Annotated[AppUser, Depends(require_rights("query"))]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def request_meta(request: Request) -> dict[str, str]:
    """Values stored in the audit log."""
    return {
        "ip_address": client_ip(request),
        "user_agent": request.headers.get("user-agent", "")[:255],
    }


__all__ = [
    "get_db",
    "get_optional_db",
    "DbSession",
    "DbOptional",
    "Pagination",
    "PaginationDep",
    "get_current_user",
    "get_current_user_optional",
    "CurrentUser",
    "OptionalUser",
    "require_rights",
    "ReadUser",
    "WriteUser",
    "AdminUser",
    "PipelineUser",
    "QueryUser",
    "client_ip",
    "request_meta",
    "verify_api_key",
    "settings",
    "Header",
]
