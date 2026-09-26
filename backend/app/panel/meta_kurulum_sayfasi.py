"""Meta kurulum sayfasi: "Meta tarafinda ne yapmam lazim?"

BU SAYFA NEDEN VAR
Meta ayarlari yanlis oldugunda hata SESSIZ ve GEC gelir: izin ekrani
acilir, kullanici izni verir, sonra anahtar degisimi basarisiz olur ve
sebebi hic belli olmaz. Kullanicinin elinde yalnizca anlamsiz bir Meta
hata mesaji kalir.

Bu sayfa sistemin KENDI ayarlarini okuyup Meta'ya girilecek degerleri
birebir gosterir ve bilinen tutarsizliklari onceden bildirir.

NE SOYLEMIYORUZ
Meta'nin kendi ekranlarindaki menu adlarini ve inceleme kurallarini
KESIN diye yazmiyoruz: bu gelistirme ortamindan Meta dokumanina erisim
kapali ve o ekranlar sik degisiyor. Bizim kesin bildigimiz sey,
SISTEMIN NE BEKLEDIGIDIR; sayfa da bunu gosteriyor.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models.identity import User
from app.panel.auth import current_user_from_cookie
from app.platforms.meta_ayar import meta_ayarlarini_oku, tutarlilik_uyarisi

router = APIRouter(prefix="/panel/meta-kurulum", tags=["panel"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

#: Meta paneline girilecek adresler.
#:
#: SADECE GERCEKTEN VAR OLAN UCLAR. Kurulum rehberinde bir donem dort
#: adres yaziyordu; ikisi (deauthorize, data-deletion) kodda YOKTU ve
#: 404 donuyordu. Meta'ya var olmayan bir adres girmek, o adres
#: cagrildiginda sessiz bir basarisizlik demektir.
UCLAR: tuple[tuple[str, str, str], ...] = (
    (
        "Valid OAuth Redirect URI",
        "/api/v1/oauth/meta/callback",
        "İzin ekranından dönüşte kullanılır. Birebir aynı olmalı; "
        "sondaki eğik çizgi farkı bile hata verir.",
    ),
    (
        "Webhook Callback URL",
        "/api/v1/webhooks/meta",
        "Meta'nın olay bildirimleri buraya gelir.",
    ),
)

#: Meta'nin App Review icin istedigi ama BIZDE HENUZ OLMAYAN uclar.
EKSIK_UCLAR: tuple[tuple[str, str], ...] = (
    (
        "Deauthorize Callback URL",
        "Kullanıcı uygulamayı kaldırdığında Meta buraya haber verir. "
        "Bu uç henüz yazılmadı.",
    ),
    (
        "Data Deletion Request URL",
        "Kullanıcı veri silme talep ettiğinde Meta buraya haber verir. "
        "Bu uç henüz yazılmadı.",
    ),
)


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _yonetici(request: Request, db) -> User | None:
    user = current_user_from_cookie(request, db)
    if user is None or not user.is_superuser:
        return None
    return user


def _alan_adi(ayarlar) -> str:
    """Sistemin dis dunyaya gorundugu alan adi."""
    return (ayarlar.public_domain or "").strip()


@router.get("", response_class=HTMLResponse)
def sayfa(request: Request, db: DbSession):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()

    ayarlar = get_settings()
    meta = meta_ayarlarini_oku()
    alan = _alan_adi(ayarlar)
    # localhost gercek bir alan adi degildir; Meta'ya yapistirilamaz.
    # Adresleri yine de yarim gostermek, kullanicinin eksik bir adresi
    # kopyalamasina yol acardi.
    gercek_alan = bool(alan and alan != "localhost")
    kok = f"https://{alan}" if gercek_alan else ""

    # Donus adresinin alan adi, uygulamanin alan adiyla ayni mi?
    # Kullanicinin aldigi "bu baglantinin domaini uygulamanin
    # domainlerinde yer almiyor" hatasi tam olarak buradan cikiyor.
    donus_alan = (urlparse(meta.redirect_uri or "").netloc or "").lower()

    yayin_kapsami = [s for s in meta.scopes if "publish" in s.lower()]

    return templates.TemplateResponse(
        request, "meta_kurulum.html",
        {
            "user": user,
            "aktif": "meta_kurulum",
            "workspace": None,
            "yol": "Meta kurulumu",
            "alan_adi": alan,
            "gercek_alan": gercek_alan,
            "uclar": [
                {"ad": ad, "adres": f"{kok}{yol}" if kok else yol, "aciklama": acikla}
                for ad, yol, acikla in UCLAR
            ],
            "eksik_uclar": [
                {"ad": ad, "aciklama": acikla} for ad, acikla in EKSIK_UCLAR
            ],
            "app_id": meta.app_id,
            "app_secret_var": bool(meta.app_secret),
            "redirect_uri": meta.redirect_uri,
            "donus_alan": donus_alan,
            # Donus adresi baska bir alan adina bakiyorsa Meta izin
            # ekraninda "domaini uygulamanin domainlerinde yer almiyor"
            # hatasi verir - kullanicinin aldigi hata tam olarak budur.
            "alan_uyusmazligi": bool(alan and donus_alan and donus_alan != alan),
            "izin_adresi": meta.authorize_url,
            "anahtar_adresi": meta.token_url,
            "veri_adresi": meta.graph_base_url,
            "kapsamlar": meta.scopes,
            "api_surumu": meta.api_version,
            "eksikler": meta.eksikler,
            "hazir": meta.hazir,
            "tutarsizlik": tutarlilik_uyarisi(meta),
            "yayin_kapsami": yayin_kapsami,
            "yayin_acik": ayarlar.feature_publishing_enabled,
        },
    )
