"""Panelde gosterilen her AI isi, kodda GERCEKTEN cagriliyor mu?

NEDEN BU TEST VAR
Yapay zeka sayfasinda yedi is listeleniyordu. Ucu ("stratejik yorum",
"marka dili denetimi", "toplu siniflandirma") hicbir kod tarafindan
cagrilmiyordu: kullanici saglayici atayabiliyor, ayari degistirebiliyor
ama hicbir sey olmuyordu.

Calismayan bir ayar, bozuk bir ayardan daha kotudur: bozuk olan
hata verir, calismayani sessizce hicbir sey yapmaz.

Bu test, panelde gosterilen is listesinin koddaki gercek
`run_ai_task(task_type=...)` cagrilariyla AYNI kalmasini zorunlu kilar.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.services.ai_saglayicilar import GOREVLER

SERVIS_DIZINI = Path(__file__).resolve().parents[1] / "app" / "services"


def _cagrilan_gorev_turleri() -> set[str]:
    """Kodda `task_type="..."` ile cagrilan gorev turleri."""
    bulunan: set[str] = set()
    for yol in SERVIS_DIZINI.glob("*.py"):
        metin = yol.read_text(encoding="utf-8")
        bulunan |= set(re.findall(r'task_type="([a-z_]+)"', metin))
    return bulunan


def test_panelde_gosterilen_her_is_kodda_cagriliyor():
    gosterilen = {g.kod for g in GOREVLER}
    cagrilan = _cagrilan_gorev_turleri()
    calismayan = gosterilen - cagrilan
    assert not calismayan, (
        "Bu işler panelde seçilebiliyor ama hiçbir kod onları çağırmıyor; "
        f"ayarı değiştirmek hiçbir şey yapmaz: {sorted(calismayan)}"
    )


def test_kodda_cagrilan_her_is_panelde_gosteriliyor():
    """Tersi de gecerli: cagrilan ama panelde olmayan is yonetilemez."""
    gosterilen = {g.kod for g in GOREVLER}
    eksik = _cagrilan_gorev_turleri() - gosterilen
    assert not eksik, (
        "Bu işler kodda çağrılıyor ama panelde görünmüyor; sağlayıcıları "
        f"değiştirilemez: {sorted(eksik)}"
    )


def test_her_isin_varsayilan_saglayicisi_taninan_bir_saglayici():
    from app.services.ai_saglayicilar import YERLESIKLER

    yerlesik_anahtarlar = {y["anahtar"] for y in YERLESIKLER}
    for gorev in GOREVLER:
        assert gorev.varsayilan in yerlesik_anahtarlar, (
            f"'{gorev.kod}' işinin varsayılanı '{gorev.varsayilan}', "
            "ama böyle bir yerleşik sağlayıcı yok."
        )
