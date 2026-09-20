"""KPI hesaplama motoru.

TASARIM KURALI - BU MODUL SAF HESAPTIR:
Veritabanina, aga veya yapay zekaya erismez. Sayilar girer, sayilar cikar.
Boylece tum hesaplar tek tek test edilebilir ve bir rapor yanlis ciktiginda
hatanin hesapta mi yoksa veride mi oldugu ayirt edilebilir.

EN ONEMLI KURAL - EKSIK VERI SIFIR DEGILDIR:
Veri yoksa `None` doner, `0` DONMEZ. "Erisim 0" ile "erisim bilinmiyor"
tamamen farkli seylerdir; ilki kotu bir performans, ikincisi bozuk bir
baglantidir. Ikisini karistirmak musteriye yanlis rapor sunmak demektir.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


def to_float(value: float | int | Decimal | None) -> float | None:
    """Veritabanindan gelen Decimal degerleri guvenle float'a cevirir."""
    if value is None:
        return None
    return float(value)


def safe_divide(pay: float | None, payda: float | None) -> float | None:
    """Bolme islemi. Sonuc guvenilir degilse None doner.

    Sifira bolme HATA FIRLATMAZ ve 0 DONDURMEZ; None doner.
    Ornek: erisim 0 iken etkilesim orani hesaplanamaz - bu oranin
    "sifir" oldugu anlamina gelmez, "hesaplanamaz" anlamina gelir.
    """
    if pay is None or payda is None:
        return None
    if payda == 0:
        return None
    return pay / payda


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Comparison:
    """Iki donem arasindaki degisim."""

    current: float | None
    previous: float | None
    change_absolute: float | None
    change_percent: float | None
    direction: Direction

    @property
    def is_reliable(self) -> bool:
        """Bu karsilastirma rapora konulabilir mi?"""
        return self.current is not None and self.previous is not None


def compare(current: float | None, previous: float | None,
            flat_threshold: float = 0.005) -> Comparison:
    """Iki donemi karsilastirir.

    `flat_threshold`: bu orandan kucuk degisimler "degisim yok" sayilir.
    Varsayilan %0.5 - gurultuyu trend gibi sunmamak icin.
    """
    if current is None or previous is None:
        return Comparison(current, previous, None, None, Direction.UNKNOWN)

    fark = current - previous
    # Onceki donem sifirsa yuzde degisim TANIMSIZDIR.
    # "Sonsuz artis" veya "%100 artis" yazmak yaniltici olur.
    yuzde = safe_divide(fark, abs(previous))

    if yuzde is None:
        yon = Direction.UP if fark > 0 else (Direction.DOWN if fark < 0 else Direction.FLAT)
    elif abs(yuzde) < flat_threshold:
        yon = Direction.FLAT
    else:
        yon = Direction.UP if fark > 0 else Direction.DOWN

    return Comparison(current, previous, fark, yuzde, yon)


@dataclass
class MetricSet:
    """Bir icerige veya hesaba ait olcumler.

    Eksik metrikler kaydedilir; rapor "hangi veri yoktu" diyebilsin diye.
    """

    values: dict[str, float] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def get(self, name: str) -> float | None:
        return self.values.get(name)

    def require(self, *names: str) -> None:
        """Beklenen metrikleri isaretler; olmayanlar `missing` listesine girer."""
        for name in names:
            if name not in self.values and name not in self.missing:
                self.missing.append(name)


# --- Etkilesim hesaplari -----------------------------------------------------

ENGAGEMENT_COMPONENTS = ("likes", "comments", "saves", "shares")


def engagement_total(metrics: MetricSet) -> float | None:
    """Toplam etkilesim. HICBIR bileşen yoksa None doner.

    Bazi bileşenler eksikse mevcut olanlar toplanir; bu durum
    `metrics.missing` uzerinden rapora yansir.
    """
    mevcut = [metrics.values[k] for k in ENGAGEMENT_COMPONENTS if k in metrics.values]
    metrics.require(*ENGAGEMENT_COMPONENTS)
    if not mevcut:
        return None
    return float(sum(mevcut))


def engagement_rate(metrics: MetricSet, *, base: str = "reach") -> float | None:
    """Etkilesim orani = toplam etkilesim / erisim.

    Erisim 0 veya bilinmiyorsa None doner.
    """
    return safe_divide(engagement_total(metrics), metrics.get(base))


def save_rate(metrics: MetricSet) -> float | None:
    return safe_divide(metrics.get("saves"), metrics.get("reach"))


def completion_proxy(metrics: MetricSet) -> float | None:
    """Video icerikler icin izlenme/erisim orani."""
    return safe_divide(metrics.get("video_views"), metrics.get("reach"))


# --- Toplu istatistikler -----------------------------------------------------

def average(values: Sequence[float | None]) -> float | None:
    """Ortalama. Gecerli deger yoksa None."""
    gecerli = [v for v in values if v is not None]
    if not gecerli:
        return None
    return sum(gecerli) / len(gecerli)


def median(values: Sequence[float | None]) -> float | None:
    gecerli = [v for v in values if v is not None]
    if not gecerli:
        return None
    return statistics.median(gecerli)


def total(values: Sequence[float | None]) -> float | None:
    gecerli = [v for v in values if v is not None]
    if not gecerli:
        return None
    return float(sum(gecerli))


@dataclass(frozen=True)
class RankedItem:
    """Siralamaya giren bir icerik."""

    key: str
    score: float
    label: str | None = None


def rank(items: Sequence[RankedItem], *, top: int = 3,
         ascending: bool = False) -> list[RankedItem]:
    """En iyi veya en zayif icerikleri siralar.

    Skoru None olan icerikler siralamaya GIRMEZ - bilinmeyen bir deger
    "en zayif" sayilamaz.
    """
    return sorted(items, key=lambda i: i.score, reverse=not ascending)[:top]


# --- Veri kalitesi -----------------------------------------------------------

@dataclass
class DataQuality:
    """Raporun ne kadar saglam veriye dayandigi.

    Her rapor bu bilgiyi icerir; musteri hangi sayiya ne kadar
    guvenebilecegini bilir.
    """

    expected_items: int = 0
    items_with_data: int = 0
    missing_metrics: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def record_missing(self, names: Sequence[str]) -> None:
        for name in names:
            self.missing_metrics[name] = self.missing_metrics.get(name, 0) + 1

    @property
    def coverage(self) -> float | None:
        """Beklenen iceriklerin ne kadarinda veri var?"""
        return safe_divide(self.items_with_data, self.expected_items)

    @property
    def is_sufficient(self) -> bool:
        """Rapor yorumlanabilir mi?

        Kapsam %60'in altindaysa nedensel yorum yapilmamali; bulgular
        yalnizca hipotez olarak sunulmalidir.
        """
        kapsam = self.coverage
        return kapsam is not None and kapsam >= 0.6
