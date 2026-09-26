"""Panelde gorunen hata mesaji NE ZAMAN olustugunu soylemeli.

OLAY: Kullanici, kapali bir is akisinin yaninda kirmizi bir hata gordu.
Hatanin yaninda tarih YOKTU; cunku tarih yalnizca akis ACIKKEN
yaziliyordu, hata ise her durumda. Gunler onceki bir hata guncel bir
ariza gibi gorunuyordu.

Tarihsiz bir hata mesaji, olmayan bir arizayi arattirir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import AutomationStatus, AutomationTrigger
from app.models.otomasyon import AutomationRun, AutomationSetting
from app.panel.auth import COOKIE_NAME

SIFRE = "GucluSifre123!"
HATA_METNI = "AI ciktisi beklenen yapiya uymadi"


@pytest.fixture
def kurulum(client, db, make_user, make_workspace, add_member):
    """Kapali bir akis ve gecmiste kalmis basarisiz bir calisma."""
    kullanici = make_user(password=SIFRE)
    kullanici.is_superuser = True
    ws = make_workspace(name="RYMedya")
    db.flush()
    add_member(ws, kullanici)

    db.add(AutomationSetting(
        workspace_id=ws.id, workflow_key="wf02_trend", is_enabled=False,
    ))
    eski = datetime.now(UTC) - timedelta(days=3)
    db.add(AutomationRun(
        workspace_id=ws.id, workflow_key="wf02_trend",
        trigger=AutomationTrigger.SCHEDULE, status=AutomationStatus.FAILED,
        started_at=eski, finished_at=eski, error_message=HATA_METNI,
    ))
    db.flush()

    assert client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    ).status_code == 303
    assert client.cookies.get(COOKIE_NAME)
    return ws, eski


def _hatanin_hucresi(metin: str) -> str:
    """Hata mesajinin GECTIGI tablo hucresini doner.

    Sayfanin tamaminda tarih aramak yetmez: alttaki "son calismalar"
    tablosu da tarih yazar. Ilk yazdigim test bu yuzden hata GERI
    KONULDUGUNDA BILE geciyordu. Olculen sey, hatanin yanindaki tarih
    olmali - sayfanin herhangi bir yerindeki tarih degil.
    """
    yer = metin.index(HATA_METNI)
    bas = metin.rindex("<td", 0, yer)
    son = metin.index("</td>", yer)
    return metin[bas:son]


def test_kapali_akisin_hatasi_tarihiyle_gosteriliyor(client, kurulum):
    _, eski = kurulum
    metin = client.get("/panel/otomasyon").text
    assert HATA_METNI in metin
    assert eski.strftime("%d.%m.%Y") in _hatanin_hucresi(metin)


def test_kapali_akista_hatanin_eski_oldugu_yaziyor(client, kurulum):
    """Kullanici "su an mi bozuk?" diye sormak zorunda kalmamali."""
    metin = client.get("/panel/otomasyon").text
    assert "Akış kapatılmadan önceki son çalışma" in _hatanin_hucresi(metin)
