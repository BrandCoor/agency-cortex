"""Panel gorunum tercihleri: tema ve vurgu rengi.

NEDEN KISIYE OZEL: sunucu genelinde tek bir tema dayatmak yanlis olurdu.
Aydinlik bir odada calisan biriyle gece calisan birinin ihtiyaci ayni
degildir.

NEDEN SINIRLI BIR LISTE: serbest renk girisi (ornegin bir metin kutusu)
okunabilirligi bozabilir - acik temada cok acik bir vurgu rengi yaziyi
okunmaz yapar. Buradaki renkler her iki temada da kontrast kontrolunden
gecirilmis degerlerdir.
"""

from __future__ import annotations

from dataclasses import dataclass

TEMALAR: tuple[tuple[str, str], ...] = (
    ("sistem", "Sistemi izle"),
    ("koyu", "Koyu"),
    ("acik", "Açık"),
)
TEMA_ANAHTARLARI = frozenset(a for a, _ in TEMALAR)


@dataclass(frozen=True)
class Vurgu:
    anahtar: str
    ad: str
    #: Koyu temada kullanilan ton.
    koyu: str
    #: Acik temada kullanilan ton (daha doygun; acik zeminde soluk kalmasin).
    acik: str


VURGULAR: tuple[Vurgu, ...] = (
    Vurgu("mavi", "Mavi", "#4f8ef7", "#1f6feb"),
    Vurgu("mor", "Mor", "#9b6ef0", "#7a3fe4"),
    Vurgu("yesil", "Yeşil", "#3fb950", "#1a7f37"),
    Vurgu("turuncu", "Turuncu", "#e08c3c", "#bc5f10"),
    Vurgu("kirmizi", "Kırmızı", "#f0574f", "#cf222e"),
    Vurgu("turkuaz", "Turkuaz", "#2eb6b0", "#0f7c78"),
)
VURGU_ANAHTARLARI = frozenset(v.anahtar for v in VURGULAR)
VURGU_SOZLUGU = {v.anahtar: v for v in VURGULAR}

VARSAYILAN_TEMA = "sistem"
VARSAYILAN_VURGU = "mavi"


def tema_gecerli(deger: str) -> str:
    """Bilinmeyen deger sessizce varsayilana duser; sayfa ASLA bozulmaz."""
    return deger if deger in TEMA_ANAHTARLARI else VARSAYILAN_TEMA


def vurgu_gecerli(deger: str) -> str:
    return deger if deger in VURGU_ANAHTARLARI else VARSAYILAN_VURGU
