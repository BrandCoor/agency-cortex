"""Sosyal medya hesabi baglama akisi (OAuth).

AKIS:
1. Kullanici "hesap bagla" der       -> POST .../oauth/{platform}/authorize
2. Sistem tahmin edilemez state uretir ve izin adresini doner
3. Kullanici Meta'da izin verir
4. Meta geri doner                   -> GET /api/v1/oauth/meta/callback
5. State dogrulanir ve TUKETILIR (tek kullanimlik)
6. Kod anahtara cevrilir, anahtar sifrelenip saklanir
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import DbSession, WorkspaceContext, require_role
from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models.enums import Platform, WorkspaceRole
from app.models.ops import AuditLog
from app.models.social import SocialAccount
from app.platforms.base import PlatformError
from app.platforms.registry import get_adapter
from app.services.oauth_state import StateError, consume_state, create_state
from app.services.token_store import save_tokens

router = APIRouter(prefix="/api/v1/oauth", tags=["hesap baglama"])
log = get_logger("oauth")


@router.post(
    "/{platform}/authorize/{workspace_id}",
    summary="Hesap baglama akisini baslat",
)
def start_authorization(
    platform: Platform,
    ctx: Annotated[WorkspaceContext, Depends(require_role(WorkspaceRole.ADMIN))],
) -> dict:
    """Izin ekraninin adresini uretir.

    Hesap baglamak calisma alanini kalici olarak etkiledigi icin en az
    yonetici yetkisi gerekir.
    """
    settings = get_settings()
    adapter = get_adapter(platform)
    redirect_uri = settings.meta_redirect_uri

    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "META_REDIRECT_URI ayarlanmamis. Bu adres Meta App Dashboard'a "
                "kayitli adresle birebir ayni olmalidir."
            ),
        )

    state = create_state(
        workspace_id=ctx.workspace_id,
        user_id=ctx.user.id,
        platform=platform.value,
        redirect_uri=redirect_uri,
    )

    try:
        request = adapter.authorize(state=state, redirect_uri=redirect_uri)
    except PlatformError as exc:
        # Ayar eksikse veya platform gelistirilmemisse acik hata doner.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return {"authorization_url": request.url, "state": request.state}


def _panele_don(workspace_id, *, hata: str | None = None,
                baglandi: str | None = None, uyari: str | None = None):
    """Kullaniciyi panele geri gonderir.

    Bu uca TARAYICI gelir (Meta yonlendirir). Ham JSON gostermek yerine
    kullanici bagli hesaplar sayfasina, sonucun yazili oldugu haliyle
    doner.
    """
    parametreler = {}
    if hata:
        parametreler["hata"] = hata
    if baglandi:
        parametreler["baglandi"] = baglandi
    if uyari:
        parametreler["uyari"] = uyari

    adres = f"/panel/musteri/{workspace_id}/hesaplar"
    if parametreler:
        adres += "?" + urlencode(parametreler)
    return RedirectResponse(adres, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/meta/callback", summary="Meta izin ekranindan donus")
def meta_callback(
    db: DbSession,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
):
    """Meta'dan gelen yetkilendirme kodunu isler.

    Kullanici izin vermezse veya bir hata olursa kontrollu sekilde panele
    doner; sistem cokmez ve ekranda ham hata JSON'u gorunmez.
    """
    # State olmadan nereye donecegimizi BILEMEYIZ; tek gercek hata yolu budur.
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Eksik parametre: 'state' zorunludur.",
        )

    # State dogrulanir ve TUKETILIR - ayni donus ikinci kez islenemez.
    # Kullanici izin vermemis olsa bile tuketilir: o state artik gecersizdir.
    try:
        payload = consume_state(state)
    except StateError as exc:
        log.warning("oauth_state_gecersiz", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # Kullanici izin vermedi veya Meta hata dondurdu
    if error:
        log.info("oauth_kullanici_reddetti", error=error)
        return _panele_don(
            payload.workspace_id,
            hata=f"Hesap bağlanmadı: {error_description or error}",
        )

    if not code:
        return _panele_don(
            payload.workspace_id,
            hata="Meta bir yetkilendirme kodu göndermedi. Tekrar deneyin.",
        )

    # Kod anahtara cevrilir
    adapter = get_adapter(Platform.INSTAGRAM)
    try:
        tokens, profile = adapter.callback(code=code, redirect_uri=payload.redirect_uri)
    except PlatformError as exc:
        log.error("oauth_token_degisimi_basarisiz", reason=type(exc).__name__)
        return _panele_don(
            payload.workspace_id,
            hata=f"Meta ile anahtar değişimi başarısız: {exc}",
        )

    # 4) Hesap kaydedilir (varsa guncellenir)
    account = db.execute(
        select(SocialAccount).where(
            SocialAccount.workspace_id == payload.workspace_id,
            SocialAccount.platform == Platform.INSTAGRAM,
            SocialAccount.external_id == profile.external_id,
        )
    ).scalar_one_or_none()

    if account is None:
        account = SocialAccount(
            workspace_id=payload.workspace_id,
            platform=Platform.INSTAGRAM,
            external_id=profile.external_id,
        )
        db.add(account)

    account.username = profile.username
    account.display_name = profile.display_name
    account.is_professional = profile.is_professional
    account.is_active = True
    db.flush()

    # 5) Anahtarlar SIFRELENEREK saklanir
    save_tokens(
        db,
        workspace_id=payload.workspace_id,
        social_account_id=account.id,
        tokens=tokens,
    )

    # 6) Denetim kaydi
    from datetime import UTC, datetime

    db.add(
        AuditLog(
            workspace_id=payload.workspace_id,
            actor_user_id=payload.user_id,
            action="social_account.connected",
            subject_type="social_account",
            subject_id=account.id,
            occurred_at=datetime.now(UTC),
            details={
                "platform": Platform.INSTAGRAM.value,
                "external_id": profile.external_id,
                "is_professional": profile.is_professional,
            },
        )
    )
    db.commit()

    return _panele_don(
        payload.workspace_id,
        baglandi=profile.username or profile.external_id,
        # Profesyonel olmayan hesapta icgoru verisi BULUNMAZ. Bagli
        # gorunup veri gelmemesi kafa karistirirdi; simdiden soylenir.
        uyari=(
            None
            if profile.is_professional
            else (
                "Bu hesabın profesyonel (Business/Creator) olduğu "
                "doğrulanamadı. İçgörü metrikleri alınamayabilir."
            )
        ),
    )
