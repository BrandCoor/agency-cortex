"""Kampanyanin platform bazinda dagilimi.

NEDEN AYRI TABLO:
Bir kampanya ayni anda Meta'da, Google Ads'te ve organik olarak
yurutulebilir; her birinin butcesi, hedefi ve durumu farklidir. Bunlari
tek satirda tutmak (ornegin "butce" diye tek alan) hangi paranin nereye
gittigi sorusunu yanitsiz birakirdi.

DURUSTLUK: buradaki rakamlar KULLANICININ GIRDIGI planlama verisidir.
Reklam platformlarindan otomatik cekilen gercek harcama DEGILDIR; oyle
olsaydi panelde ayrica belirtilirdi.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import ReklamPlatformu


class CampaignPlatform(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Bir kampanyanin tek bir platformdaki ayagi."""

    __tablename__ = "campaign_platforms"
    __table_args__ = (
        # Ayni kampanyada ayni platform iki kez yer alamaz; aksi halde
        # toplam butce sessizce iki kez sayilirdi.
        UniqueConstraint("campaign_id", "platform", name="uq_campaign_platform"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    platform: Mapped[ReklamPlatformu] = mapped_column(
        Enum(ReklamPlatformu, name="reklam_platformu"), nullable=False
    )
    #: Planlanan butce. Numeric kullanilir; para FLOAT ile tutulmaz.
    butce: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    hedef: Mapped[str | None] = mapped_column(String(200))
    notlar: Mapped[str | None] = mapped_column(Text)
    #: Reklam platformundaki kampanya kimligi (varsa). Ileride gercek
    #: harcama cekilirse baglanti noktasi budur.
    harici_kimlik: Mapped[str | None] = mapped_column(String(120))
