"""Yapay zeka saglayicilari ve hangi gorevi hangisinin yapacagi.

NEDEN VERITABANINDA?
Once saglayici listesi ve gorev dagilimi KODA gomuluydu. Yeni bir
saglayici eklemek ya da "trend arastirmasini Manus yerine Gemini yapsin"
demek kod degisikligi ve yeniden kurulum gerektiriyordu. Artik ikisi de
panelden yonetiliyor; koddaki degerler yalnizca ILK kurulumun
varsayilanidir.

SINANMAMIS SAGLAYICI KULLANILMAZ
Bir saglayici yalnizca "etkin" isaretlenerek is goremez. Once
"Baglantiyi sina" ile GERCEK bir cagri yapilir; cagri basarisizsa
saglayici hicbir goreve atanamaz. Boylece panelde "hazir" gorunup
calismayan bir entegrasyon olusamaz.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey


class SaglayiciTuru(str, enum.Enum):
    """Saglayicinin KONUSTUGU protokol.

    Tur, hangi kodun cagrilacagini belirler. "openai_uyumlu", kendi
    dokumaninda "OpenAI uyumlu" diyen her servis icindir: adresi ve
    modeli kullanici girer, biz uydurmayiz.
    """

    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    MANUS = "manus"
    OPENAI_UYUMLU = "openai_uyumlu"


class AISaglayici(UUIDPrimaryKey, Timestamps, Base):
    """Panelden yonetilen bir yapay zeka saglayicisi."""

    __tablename__ = "ai_saglayicilar"
    __table_args__ = (UniqueConstraint("anahtar", name="uq_ai_saglayici_anahtar"),)

    #: Kod icinde kullanilan kisa ad. Degismez.
    anahtar: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    ad: Mapped[str] = mapped_column(String(120), nullable=False)
    tur: Mapped[SaglayiciTuru] = mapped_column(
        Enum(SaglayiciTuru, name="ai_saglayici_turu"), nullable=False
    )
    #: Panelde checkbox ile degistirilir.
    etkin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    #: OPENAI_UYUMLU icin zorunlu; digerlerinde bos. Kullanici kendi
    #: saglayicisinin dokumanindan kopyalar - biz adres uydurmayiz.
    taban_url: Mapped[str | None] = mapped_column(String(500))
    model: Mapped[str | None] = mapped_column(String(200))

    #: Anahtarin okunacagi sistem ayari adi (ornegin ANTHROPIC_API_KEY).
    #: Deger BURADA DEGIL, sifreli ayar tablosunda durur.
    anahtar_ayari: Mapped[str | None] = mapped_column(String(80))

    #: Yerlesik saglayicilar silinemez; yalnizca kapatilabilir.
    yerlesik: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    son_sinama_zamani: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    son_sinama_basarili: Mapped[bool | None] = mapped_column(Boolean)
    son_sinama_mesaji: Mapped[str | None] = mapped_column(Text)

    @property
    def kullanilabilir(self) -> bool:
        """Bir goreve ATANABILIR mi?

        Etkin olmasi YETMEZ: son sinamanin basarili olmasi da gerekir.
        Sinanmamis bir saglayiciyi goreve atamak, ilk gercek iste
        beklenmedik bir hatayla karsilasmak demektir.
        """
        return self.etkin and self.son_sinama_basarili is True


class GorevAtamasi(UUIDPrimaryKey, Timestamps, Base):
    """Hangi gorev turunu hangi saglayici yapacak."""

    __tablename__ = "ai_gorev_atamalari"
    __table_args__ = (UniqueConstraint("gorev_turu", name="uq_ai_gorev_turu"),)

    gorev_turu: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    saglayici_anahtari: Mapped[str] = mapped_column(String(60), nullable=False)
