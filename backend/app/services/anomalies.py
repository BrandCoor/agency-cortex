"""Anormal degisim tespiti.

AMAC: "Bugun erisim dustu" demek yetmez. Normal dalgalanma ile gercekten
dikkat gerektiren degisimi ayirmak gerekir. Her kucuk inisi alarma
cevirirsek musteri raporlari okumayi birakir.

YONTEM: Medyan ve MAD (medyandan mutlak sapmalarin medyani).
Ortalama ve standart sapma yerine bunlar kullanilir cunku tek bir viral
icerik ortalamayi bozup sonraki gunlerin hepsini "anormal dusuk" gosterir.
Medyan bu etkiye dayaniklidir.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

# Anlamli bir "normal" tanimi icin gereken en az gozlem sayisi.
# Daha azi ile yapilan tespit guvenilir degildir.
MIN_OBSERVATIONS = 5

# Sabit carpan: medyandan kac MAD uzakligi anormal sayilir.
DEFAULT_THRESHOLD = 3.5


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Anomaly:
    metric_name: str
    value: float
    expected_median: float
    deviation_score: float
    direction: str          # "spike" | "drop"
    severity: Severity
    explanation: str


def _mad(values: Sequence[float], med: float) -> float:
    """Medyandan mutlak sapmalarin medyani."""
    return statistics.median([abs(v - med) for v in values])


def detect(
    metric_name: str,
    history: Sequence[float],
    current: float | None,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> Anomaly | None:
    """Gecmise gore bugunku degerin anormal olup olmadigini soyler.

    `history`: onceki donemlerin degerleri (bugun HARIC).
    Yeterli gecmis yoksa veya deger bilinmiyorsa None doner - yani
    "anormal degil" demez, "soyleyemem" der.
    """
    if current is None:
        return None
    if len(history) < MIN_OBSERVATIONS:
        return None

    med = statistics.median(history)
    yayilim = _mad(history, med)

    if yayilim == 0:
        # Gecmis tamamen sabit. Herhangi bir sapma dikkat cekicidir,
        # ancak MAD ile olculemez; basit bir oran kontrolu yapilir.
        if current == med:
            return None
        fark_orani = abs(current - med) / (abs(med) if med else 1)
        if fark_orani < 0.5:
            return None
        skor = fark_orani
    else:
        # 0.6745 sabiti MAD'i standart sapmaya denk olcege cevirir.
        skor = abs(current - med) * 0.6745 / yayilim
        if skor < threshold:
            return None

    yon = "spike" if current > med else "drop"

    if skor >= threshold * 2:
        seviye = Severity.CRITICAL
    elif skor >= threshold:
        seviye = Severity.WARNING
    else:
        seviye = Severity.INFO

    yon_metni = "beklenenin cok uzerinde" if yon == "spike" else "beklenenin cok altinda"
    aciklama = (
        f"{metric_name}: {current:,.0f} - {yon_metni} "
        f"(normal seviye yaklasik {med:,.0f})."
    )

    return Anomaly(
        metric_name=metric_name,
        value=current,
        expected_median=med,
        deviation_score=skor,
        direction=yon,
        severity=seviye,
        explanation=aciklama,
    )


def detect_many(
    series: dict[str, tuple[Sequence[float], float | None]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[Anomaly]:
    """Birden fazla metrigi tarar, bulunanlari onem sirasina gore doner."""
    bulunanlar: list[Anomaly] = []
    for ad, (gecmis, simdi) in series.items():
        sonuc = detect(ad, gecmis, simdi, threshold=threshold)
        if sonuc is not None:
            bulunanlar.append(sonuc)
    return sorted(bulunanlar, key=lambda a: a.deviation_score, reverse=True)
