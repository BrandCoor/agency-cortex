"""Panelin TEK sablon nesnesi ve ortak filtreleri.

NEDEN TEK YERDE
Her panel modulu kendi `Jinja2Templates` nesnesini kuruyordu (on bir
tane). Ortak bir filtre eklemek icin on bir yere dokunmak gerekiyordu;
bu yuzden hicbiri eklenmemisti ve saatler HAM haliyle basiliyordu.

SAAT SORUNU
Veritabani zamanlari UTC olarak saklar ve UTC olarak geri verir. Sablonlar
bu degeri dogrudan `strftime` ile basiyordu; yani kullanici saatleri
UC SAAT GERIDE goruyordu. Ekran goruntusunde "01:29" yazan bir kaydin
gercekte saat kacta olustugunu ben de soyleyemedim.

Artik tek bir filtre var: `yerel`. Zamani sistemin saat dilimine cevirir
ve bicimlendirir.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.core.config import get_settings

BICIM = "%d.%m.%Y %H:%M"


def _dilim() -> ZoneInfo:
    """Sistemin saat dilimi. Taninmayan bir ad sayfayi COKERTMEZ."""
    try:
        return ZoneInfo(get_settings().tz)
    except Exception:  # noqa: BLE001 - bilinmeyen dilimde UTC'ye duseriz
        return ZoneInfo("UTC")


def yerel(deger: date | datetime | None, bicim: str = BICIM) -> str:
    """Zamani sistemin saat dilimine cevirip bicimlendirir.

    SADE TARIH CEVRILMEZ. Kampanya baslangici gibi alanlar `date`tir;
    saat tasimazlar, dolayisiyla saat dilimleri de yoktur. Boyle bir
    degeri cevirmeye calismak sayfayi COKERTIR (ilk denememde oyle oldu)
    ve cevrilseydi tarih bir gun kayabilirdi.

    Saat dilimi BILGISI OLMAYAN bir zaman gelirse UTC kabul edilir:
    veritabanindaki tum zamanlar UTC yazilir, bu yuzden dogru varsayim
    budur. "Bilinmiyor" deyip bos donmek, ekranda tarihi yok etmek olurdu.
    """
    if deger is None:
        return "—"
    if not isinstance(deger, datetime):
        # Sade tarih: cevrilecek bir saat yok.
        return deger.strftime(bicim)
    if deger.tzinfo is None:
        deger = deger.replace(tzinfo=ZoneInfo("UTC"))
    return deger.astimezone(_dilim()).strftime(bicim)


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["yerel"] = yerel
