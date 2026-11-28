"""Saved views (per-user filter presets) endpoints."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.api.schemas import Message, SavedViewCreate, SavedViewRead, SavedViewUpdate
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError

router = APIRouter(prefix="/saved-views", tags=["saved-views"])


def _audit(session: DbSession, user: CurrentUser, action: str, view: Any) -> None:
    """Record a saved-view mutation. Reads (list/get/use) stay out of the audit log."""
    from app.models.app_users import AppAuditLog

    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action=action,
            entity_type="saved_view",
            entity_id=str(view.view_id),
            details={"name": view.name, "entity": view.entity},
        )
    )


def _visible(session: DbSession, view_id: int, user: CurrentUser) -> Any:
    """A view the caller may see: their own, or shared. Anything else is a 404."""
    from app.models.app_users import AppSavedView

    view = session.get(AppSavedView, view_id)
    if view is None or (view.user_id != user.user_id and not view.is_shared):
        raise NotFoundError(f"view {view_id} not found")
    return view


def _owned(session: DbSession, view_id: int, user: CurrentUser) -> Any:
    """A view the caller may mutate: their own, full stop."""
    view = _visible(session, view_id, user)
    if view.user_id != user.user_id:
        raise PermissionDeniedError("you can only change your own views")
    return view


@router.get("", response_model=list[SavedViewRead], summary="My views + shared views")
def list_views(session: DbSession, user: CurrentUser, entity: str | None = None) -> list[SavedViewRead]:
    from app.models.app_users import AppSavedView

    conditions = [sa.or_(AppSavedView.user_id == user.user_id, AppSavedView.is_shared.is_(True))]
    if entity:
        conditions.append(AppSavedView.entity == entity)
    views = (
        session.execute(
            sa.select(AppSavedView)
            .where(*conditions)
            .order_by(AppSavedView.is_default.desc(), AppSavedView.is_favorite.desc(), AppSavedView.name)
        )
        .scalars()
        .all()
    )
    return [SavedViewRead.model_validate(view) for view in views]


@router.post("", response_model=SavedViewRead, status_code=201, summary="Save a view")
def create_view(payload: SavedViewCreate, session: DbSession, user: CurrentUser) -> SavedViewRead:
    from app.models.app_users import AppSavedView

    duplicate = (
        session.execute(
            sa.select(AppSavedView).where(
                AppSavedView.user_id == user.user_id, AppSavedView.name == payload.name
            )
        )
        .scalars()
        .first()
    )
    if duplicate is not None:
        raise ConflictError(f"a view named '{payload.name}' already exists")
    view = AppSavedView(
        user_id=user.user_id,
        name=payload.name,
        entity=payload.entity,
        description=payload.description,
        filters=payload.filters,
        sort_by=payload.sort_by,
        sort_dir=payload.sort_dir,
        visible_columns=payload.visible_columns,
        is_shared=payload.is_shared,
        is_favorite=payload.is_favorite,
    )
    session.add(view)
    session.flush()
    _audit(session, user, "saved_view.created", view)
    session.flush()
    return SavedViewRead.model_validate(view)


@router.get("/{view_id}", response_model=SavedViewRead, summary="Get one view")
def get_view(view_id: int, session: DbSession, user: CurrentUser) -> SavedViewRead:
    return SavedViewRead.model_validate(_visible(session, view_id, user))


@router.patch("/{view_id}", response_model=SavedViewRead, summary="Update a view")
def update_view(
    view_id: int, payload: SavedViewUpdate, session: DbSession, user: CurrentUser
) -> SavedViewRead:
    from app.models.app_users import AppSavedView

    view = _owned(session, view_id, user)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in data and data["name"] != view.name:
        clash = (
            session.execute(
                sa.select(AppSavedView).where(
                    AppSavedView.user_id == user.user_id,
                    AppSavedView.name == data["name"],
                    AppSavedView.view_id != view.view_id,
                )
            )
            .scalars()
            .first()
        )
        if clash is not None:
            raise ConflictError(f"a view named '{data['name']}' already exists")
    for field_name, value in data.items():
        setattr(view, field_name, value)
    session.flush()
    _audit(session, user, "saved_view.updated", view)
    session.flush()
    return SavedViewRead.model_validate(view)


@router.post("/{view_id}/duplicate", response_model=SavedViewRead, status_code=201, summary="Copy a view")
def duplicate_view(view_id: int, session: DbSession, user: CurrentUser) -> SavedViewRead:
    from app.models.app_users import AppSavedView

    source = _visible(session, view_id, user)
    base = f"{source.name} (copy)"
    name, counter = base, 2
    while (
        session.execute(
            sa.select(AppSavedView).where(AppSavedView.user_id == user.user_id, AppSavedView.name == name)
        )
        .scalars()
        .first()
        is not None
    ):
        counter += 1
        name = f"{base} {counter}"
    view = AppSavedView(
        user_id=user.user_id,
        name=name,
        entity=source.entity,
        description=source.description,
        filters=dict(source.filters or {}),
        sort_by=source.sort_by,
        sort_dir=source.sort_dir,
        visible_columns=list(source.visible_columns or []),
        is_shared=False,
        is_favorite=False,
    )
    session.add(view)
    session.flush()
    _audit(session, user, "saved_view.duplicated", view)
    session.flush()
    return SavedViewRead.model_validate(view)


@router.post("/{view_id}/default", response_model=SavedViewRead, summary="Pin as the default view")
def make_default(view_id: int, session: DbSession, user: CurrentUser) -> SavedViewRead:
    from app.models.app_users import AppSavedView

    view = _owned(session, view_id, user)
    session.execute(
        sa.update(AppSavedView)
        .where(
            AppSavedView.user_id == user.user_id,
            AppSavedView.entity == view.entity,
            AppSavedView.view_id != view.view_id,
        )
        .values(is_default=False)
    )
    view.is_default = True
    session.flush()
    _audit(session, user, "saved_view.default", view)
    session.flush()
    return SavedViewRead.model_validate(view)


@router.post("/{view_id}/favorite", response_model=SavedViewRead, summary="Toggle favourite")
def toggle_favorite(view_id: int, session: DbSession, user: CurrentUser) -> SavedViewRead:
    view = _owned(session, view_id, user)
    view.is_favorite = not view.is_favorite
    session.flush()
    return SavedViewRead.model_validate(view)


@router.delete("/{view_id}", response_model=Message, summary="Delete a view")
def delete_view(view_id: int, session: DbSession, user: CurrentUser) -> Message:
    view = _owned(session, view_id, user)
    name = view.name
    _audit(session, user, "saved_view.deleted", view)
    session.delete(view)
    session.flush()
    return Message(message=f"View '{name}' deleted")


@router.post("/{view_id}/use", response_model=SavedViewRead, summary="Increment usage counter")
def use_view(view_id: int, session: DbSession, user: CurrentUser) -> SavedViewRead:
    view = _visible(session, view_id, user)
    view.use_count = (view.use_count or 0) + 1
    session.flush()
    return SavedViewRead.model_validate(view)
