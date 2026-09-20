"""OAuth `state` degeri: sahte istek (CSRF) korumasi.

NEDEN GEREKLI:
Saldirgan, kurbani kendi hazirladigi bir izin adresine yonlendirip kendi
sosyal medya hesabini kurbanin calisma alanina baglatabilir. Bundan sonra
kurbanin ajansi, saldirganin hesabini kendi musterisi sanir.

KORUMA:
1. Izin akisi baslatilirken tahmin edilemez bir `state` uretilir.
2. `state`, hangi calisma alani ve hangi kullanici icin uretildigiyle birlikte
   Redis'te kisa sureli saklanir.
3. Geri donuste `state` dogrulanir ve HEMEN SILINIR (tek kullanimlik).
   Boylece ayni geri donus ikinci kez islenemez.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.core.redis_client import client as redis_client

log = get_logger("oauth_state")

_PREFIX = "oauth:state:"


class StateError(Exception):
    """State gecersiz, suresi dolmus veya daha once kullanilmis."""


@dataclass(frozen=True)
class StatePayload:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    platform: str
    redirect_uri: str


def create_state(
    *, workspace_id: uuid.UUID, user_id: uuid.UUID, platform: str, redirect_uri: str
) -> str:
    """Tahmin edilemez, tek kullanimlik bir state uretir ve saklar."""
    settings = get_settings()
    state = secrets.token_urlsafe(32)

    redis_client.setex(
        _PREFIX + state,
        settings.oauth_state_ttl_seconds,
        json.dumps(
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "platform": platform,
                "redirect_uri": redirect_uri,
            }
        ),
    )
    log.info(
        "oauth_state_uretildi",
        workspace_id=str(workspace_id),
        platform=platform,
        ttl_seconds=settings.oauth_state_ttl_seconds,
    )
    return state


def consume_state(state: str) -> StatePayload:
    """State'i dogrular ve TEK KULLANIMLIK olarak tuketir.

    Ayni state ikinci kez gonderilirse hata verir; boylece geri donus
    adresinin tekrar oynatilmasi (replay) engellenir.
    """
    if not state:
        raise StateError("State degeri bos.")

    key = _PREFIX + state
    # Once sil, sonra degeri kullan: iki es zamanli istekten yalnizca biri
    # degeri alabilir.
    raw = redis_client.getdel(key)
    if raw is None:
        raise StateError(
            "State gecersiz, suresi dolmus veya daha once kullanilmis."
        )

    data = json.loads(raw)
    return StatePayload(
        workspace_id=uuid.UUID(data["workspace_id"]),
        user_id=uuid.UUID(data["user_id"]),
        platform=data["platform"],
        redirect_uri=data["redirect_uri"],
    )
