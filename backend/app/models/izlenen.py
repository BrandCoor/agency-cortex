"""Izlenen hesaplar: BAGLI hesaplardan ayri bir kavram.

IKI FARKLI SEY, IKI FARKLI TABLO:

1. BAGLI HESAP (social_accounts)
   Hesap sahibi Instagram/Facebook izin ekranindan yetki vermistir.
   Erisim anahtari vardir. Tam veri gelir: erisim, etkilesim, icgoru.
   Genellikle musterinin KENDI hesabidir veya yonetimini ustlendigimiz
   bir hesaptir.

2. IZLENEN HESAP (bu tablo)
   Yalnizca kullanici adi veya baglantisi yazilmistir. HICBIR yetki
   yoktur, anahtar yoktur. Rakip hesaplar boyle takip edilir.

BU AYRIM NEDEN ONEMLI:
Ikisi ayni listede gosterilseydi, izlenen bir hesabin verisi de bagli
hesap kadar tam saniirdi. Rakip hesaptan gelen sinirli veriyi kendi
hesabimizin verisiyle ayni kefeye koymak, raporu YANLIS yapardi.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import Platform


class IzlemeTuru(str, enum.Enum):
    """Bu hesap NEDEN izleniyor?"""

    KENDI = "kendi"        # Musterinin hesabi; henuz baglanmamis
    RAKIP = "rakip"        # Rakip marka
    REFERANS = "referans"  # Ilham/ornek alinan hesap


class TrackedAccount(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Yetkilendirilmemis, yalnizca adiyla takip edilen hesap."""

    __tablename__ = "tracked_accounts"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "platform", "username", name="uq_tracked_account"
        ),
    )

    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, name="platform"), nullable=False
    )
    #: Kullanici adi, '@' olmadan ve kucuk harfle saklanir.
    username: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(300))
    tur: Mapped[IzlemeTuru] = mapped_column(
        Enum(IzlemeTuru, name="izleme_turu"), nullable=False
    )
    notlar: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: En son ne zaman veri cekilebildi. Hic cekilemediyse None.
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Veri cekilemiyorsa SEBEBI. Bos birakilmaz; sessiz basarisizlik olmaz.
    veri_durumu: Mapped[str | None] = mapped_column(Text)
