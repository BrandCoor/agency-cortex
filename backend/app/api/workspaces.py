"""Calisma alani (musteri) uclari.

Buradaki her uc, kullanicinin yalnizca kendi uyesi oldugu calisma alanlarini
gormesini saglar.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, Workspace_, WorkspaceContext, require_role
from app.core.logging_config import get_logger
from app.models.enums import WorkspaceRole
from app.models.identity import User, Workspace, WorkspaceMember
from app.schemas import (
    MemberCreate,
    MemberOut,
    WorkspaceCreate,
    WorkspaceMembershipOut,
    WorkspaceOut,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["calisma alanlari"])
log = get_logger("workspaces")


@router.get("", response_model=list[WorkspaceMembershipOut], summary="Erisebildigim musteriler")
def list_my_workspaces(user: CurrentUser, db: DbSession) -> list[WorkspaceMembershipOut]:
    """Yalnizca kullanicinin UYE OLDUGU calisma alanlarini doner.

    Sistemdeki tum calisma alanlarini listeleyen bir uc bilerek yoktur.
    """
    rows = db.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.name)
    ).all()

    return [
        WorkspaceMembershipOut(workspace=WorkspaceOut.model_validate(ws), role=role)
        for ws, role in rows
    ]


@router.post(
    "", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED,
    summary="Yeni musteri olustur",
)
def create_workspace(payload: WorkspaceCreate, user: CurrentUser, db: DbSession) -> Workspace:
    """Yeni calisma alani acar ve olusturani sahip (owner) yapar."""
    workspace = Workspace(name=payload.name, slug=payload.slug, timezone=payload.timezone)
    db.add(workspace)
    db.flush()

    db.add(
        WorkspaceMember(
            workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER
        )
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kisa ad (slug) zaten kullaniliyor.",
        ) from exc

    db.refresh(workspace)
    log.info("calisma_alani_olusturuldu", workspace_id=str(workspace.id), user_id=str(user.id))
    return workspace


@router.get("/{workspace_id}", response_model=WorkspaceOut, summary="Musteri ayrintisi")
def get_workspace(ctx: Workspace_, db: DbSession) -> Workspace:
    workspace = db.get(Workspace, ctx.workspace_id)
    if workspace is None:  # pragma: no cover - uyelik varsa calisma alani da vardir
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bulunamadi.")
    return workspace


@router.get("/{workspace_id}/members", response_model=list[MemberOut], summary="Uyeler")
def list_members(ctx: Workspace_, db: DbSession) -> list[WorkspaceMember]:
    return list(
        db.execute(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == ctx.workspace_id)
        ).scalars()
    )


@router.post(
    "/{workspace_id}/members", response_model=MemberOut,
    status_code=status.HTTP_201_CREATED, summary="Uye ekle",
)
def add_member(
    payload: MemberCreate,
    ctx: Annotated[WorkspaceContext, Depends(require_role(WorkspaceRole.ADMIN))],
    db: DbSession,
) -> WorkspaceMember:
    """Calisma alanina uye ekler. En az yonetici (admin) yetkisi gerekir."""
    user = db.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bu e-posta ile kullanici bulunamadi."
        )

    member = WorkspaceMember(workspace_id=ctx.workspace_id, user_id=user.id, role=payload.role)
    db.add(member)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kullanici zaten uye.",
        ) from exc

    db.refresh(member)
    log.info(
        "uye_eklendi",
        workspace_id=str(ctx.workspace_id),
        added_user_id=str(user.id),
        role=payload.role.value,
    )
    return member


@router.delete(
    "/{workspace_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT,
    summary="Uye cikar",
)
def remove_member(
    member_id: uuid.UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_role(WorkspaceRole.ADMIN))],
    db: DbSession,
) -> None:
    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id,
            # Baska bir calisma alaninin uyesi bu uctan silinemez.
            WorkspaceMember.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()

    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uye bulunamadi.")

    if member.role == WorkspaceRole.OWNER:
        owners = db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx.workspace_id,
                WorkspaceMember.role == WorkspaceRole.OWNER,
            )
        ).scalars().all()
        if len(owners) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Son sahip cikarilamaz. Once baska bir sahip atayin.",
            )

    db.delete(member)
    db.commit()
    log.info("uye_cikarildi", workspace_id=str(ctx.workspace_id), member_id=str(member_id))
