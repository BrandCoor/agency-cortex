"""Is akislarinin yapay zekaya verdigi istemler (prompt).

NEDEN VERITABANINDA?
Istemler koda gomuluydu. "Trend arastirmasi biraz daha sektore odaklansin"
demek, kod degisikligi ve yeniden kurulum gerektiriyordu. Oysa istem
metni URUN AYARIDIR, kod degil: isini bilen bir insan onu okuyup
duzeltebilmeli.

KODAKI METIN KAYBOLMAZ
Her yerlesik istemin koddaki hali VARSAYILAN olarak durur. Panelde
"Varsayilana don" her zaman calisir; yanlis bir duzenleme sistemi
kilitleyemez.

SURUM NEDEN TUTULUYOR?
Uretilen her AI ciktisi hangi istem surumuyle uretildigini kaydeder.
Surum artmasaydi, "bu rapor neden boyle cikmis?" sorusunun cevabi
kaybolurdu.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey


class IstemSablonu(UUIDPrimaryKey, Timestamps, Base):
    """Bir is akisinin sistem istemi."""

    __tablename__ = "istem_sablonlari"
    __table_args__ = (UniqueConstraint("kod", name="uq_istem_kod"),)

    #: Kod icinden cagrilan kisa ad, ornegin "trend_research".
    kod: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    ad: Mapped[str] = mapped_column(String(160), nullable=False)
    #: Hangi is akisinda kullanildigi (WF-02 gibi). Bilgi amaclidir.
    akis: Mapped[str | None] = mapped_column(String(20))
    aciklama: Mapped[str] = mapped_column(Text, default="", nullable=False)

    metin: Mapped[str] = mapped_column(Text, nullable=False)
    surum: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    etkin: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    #: Kodda karsiligi olan istemler silinemez; yalnizca duzenlenir veya
    #: varsayilana dondurulur. Kullanicinin ekledigi istemler silinebilir.
    yerlesik: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
