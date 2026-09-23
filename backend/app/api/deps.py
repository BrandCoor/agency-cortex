"""Istek bagimliliklari: kimlik dogrulama ve calisma alani yetkilendirme.

Bu dosya sistemin guvenlik kapisidir. Musteri verisine dokunan HER uc,
`require_workspace` uzerinden gecmek zorundadir. Bir uc bunu atlarsa
izolasyon kirilir.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import TokenError, decode_token
from app.models.identity import User, WorkspaceMember

bearer_scheme = HTTPBearer(auto_error=False)

# Yetkisiz erisimde her zaman AYNI yanit doner. "Calisma alani yok" ile
# "yetkiniz yok" ayrimi yapilmaz; aksi halde bir musteri, baska bir musterinin
# VARLIGINI ogrenebilir.
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Calisma alani bulunamadi.",
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Oturum anahtarindan kullaniciyi cozer."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum acmaniz gerekiyor.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum anahtari gecersiz.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanici bulunamadi veya pasif.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


class WorkspaceContext:
    """Dogrulanmis calisma alani erisimi.

    Bu nesne yalnizca kullanicinin gercekten uye oldugu bir calisma alani
    icin olusturulabilir. Sorgular `context.workspace_id` ile sinirlandirilir.
    """

    __slots__ = ("workspace_id", "user")

    def __init__(self, workspace_id: uuid.UUID, user: User) -> None:
        self.workspace_id = workspace_id
        self.user = user



def require_workspace(
    workspace_id: Annotated[uuid.UUID, Path(description="Calisma alani kimligi")],
    user: CurrentUser,
    db: DbSession,
) -> WorkspaceContext:
    """Kullanicinin bu calisma alanina erisimi var mi?

    Uyelik yoksa 404 doner. Sistem yoneticisi (`is_superuser`) olmak bile
    otomatik erisim VERMEZ: musteri verisine erisim yalnizca acik uyelikle
    olur.
    """
    membership = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).scalar_one_or_none()

    if membership is None:
        raise _FORBIDDEN

    # Uyelik YETKI tasimaz; yalnizca erisimi belirler. Ne yapabilecegi
    # kullanicinin kendi izinlerinde yazar (services/yetkiler.py).
    return WorkspaceContext(workspace_id=workspace_id, user=user)


Workspace_ = Annotated[WorkspaceContext, Depends(require_workspace)]




def require_permission(izin: str):
    """Belirli bir IZIN isteyen uclar icin bagimlilik uretir.

    Izinler kullanici bazinda panelden ayarlanabilir. Sabit bir rol
    beklemek, yetki ekraninda yapilan ayarin bu ucta ISE YARAMAMASI
    demekti.

    Kullanimi:
        ctx: Annotated[WorkspaceContext, Depends(require_permission("icerik.uret"))]
    """

    def _dependency(ctx: Workspace_, db: DbSession) -> WorkspaceContext:
        from app.services.yetkiler import izin_var_mi

        if not izin_var_mi(db, ctx.user, izin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu islem icin '{izin}' izni gerekir.",
            )
        return ctx

    return _dependency
