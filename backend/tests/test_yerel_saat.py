"""Panel saatleri KULLANICININ saat diliminde gosterilmeli.

OLAY: Panel, veritabanindan gelen UTC zamanlari oldugu gibi basiyordu.
Kullanici saatleri uc saat geride goruyordu. Ekran goruntusunde "01:29"
yazan bir kaydin gercekte ne zaman olustugunu ben de soyleyemedim ve
yanlis yorum yaptim.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.panel.sablon import yerel


def test_utc_zamani_yerel_saate_cevriliyor():
    zaman = datetime(2026, 9, 27, 1, 29, tzinfo=UTC)
    # Europe/Istanbul = UTC+3
    assert yerel(zaman) == "27.09.2026 04:29"


def test_saat_dilimsiz_zaman_utc_sayiliyor():
    """Veritabanindaki tum zamanlar UTC yazilir; dogru varsayim budur."""
    zaman = datetime(2026, 9, 27, 1, 29)
    assert yerel(zaman) == "27.09.2026 04:29"


def test_sade_tarih_cevrilmiyor():
    """Kampanya baslangici saat tasimaz; cevrilseydi bir gun kayabilirdi."""
    assert yerel(date(2026, 9, 27), "%d.%m.%Y") == "27.09.2026"


def test_bos_deger_sayfayi_bozmuyor():
    assert yerel(None) == "—"


def test_baska_dilimdeki_zaman_dogru_cevriliyor():
    zaman = datetime(2026, 9, 27, 0, 0, tzinfo=ZoneInfo("Europe/London"))
    # Londra 27 Eylul'de UTC+1; Istanbul UTC+3 -> iki saat ileri.
    assert yerel(zaman) == "27.09.2026 02:00"


def test_bicim_degistirilebiliyor():
    zaman = datetime(2026, 9, 27, 1, 29, tzinfo=UTC)
    assert yerel(zaman, "%H:%M") == "04:29"
