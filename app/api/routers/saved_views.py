"""Saved views (per-user filter presets) endpoints."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.api.schemas import Message, SavedViewCreate, SavedViewRead
from app.core.errors import ConflictError, ProductNotFoundError

router = APIRouter(prefix="/saved-views", tags=["saved-views"])


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
            .order_by(AppSavedView.is_favorite.desc(), AppSavedView.name)
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
    return SavedViewRead.model_validate(view)


@router.post("/{view_id}/favorite", response_model=SavedViewRead, summary="Toggle favourite")
def toggle_favorite(view_id: int, session: DbSession, user: CurrentUser) -> SavedViewRead:
    from app.models.app_users import AppSavedView

    view = session.get(AppSavedView, view_id)
    if view is None:
        raise ProductNotFoundError(f"view {view_id} not found")
    view.is_favorite = not view.is_favorite
    return SavedViewRead.model_validate(view)


@router.delete("/{view_id}", response_model=Message, summary="Delete a view")
def delete_view(view_id: int, session: DbSession, user: CurrentUser) -> Message:
    from app.models.app_users import AppSavedView

    view = session.get(AppSavedView, view_id)
    if view is None:
        raise ProductNotFoundError(f"view {view_id} not found")
    if view.user_id not in (None, user.user_id):
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError("you can only delete your own views")
    session.delete(view)
    return Message(message=f"View '{view.name}' deleted")


@router.post("/{view_id}/use", response_model=SavedViewRead, summary="Increment usage counter")
def use_view(view_id: int, session: DbSession, user: CurrentUser) -> SavedViewRead:
    from app.models.app_users import AppSavedView

    view = session.get(AppSavedView, view_id)
    if view is None:
        raise ProductNotFoundError(f"view {view_id} not found")
    view.use_count = (view.use_count or 0) + 1
    return SavedViewRead.model_validate(view)
