"""Sistem genelinde kullanilan sabit deger kumeleri."""

from __future__ import annotations

import enum


class WorkspaceRole(str, enum.Enum):
    """Bir kullanicinin bir musteri calisma alanindaki yetkisi.

    Yetki sirasi yukaridan asagiya azalir.
    """

    OWNER = "owner"            # Her sey + calisma alanini silme
    ADMIN = "admin"            # Her sey + uye yonetimi
    STRATEGIST = "strategist"  # Icerik/rapor uretir, onaya sunar
    EDITOR = "editor"          # Icerik duzenler, onaya sunamaz
    VIEWER = "viewer"          # Yalnizca okur

    @property
    def level(self) -> int:
        return _ROLE_LEVELS[self]

    def covers(self, required: WorkspaceRole) -> bool:
        """Bu rol, istenen yetkiyi karsiliyor mu?"""
        return self.level >= required.level


_ROLE_LEVELS: dict[WorkspaceRole, int] = {
    WorkspaceRole.VIEWER: 10,
    WorkspaceRole.EDITOR: 20,
    WorkspaceRole.STRATEGIST: 30,
    WorkspaceRole.ADMIN: 40,
    WorkspaceRole.OWNER: 50,
}


class ReklamPlatformu(str, enum.Enum):
    """Kampanya butcesinin dagitildigi mecra.

    ORGANIK bilerek listede: her kampanyanin reklam butcesi olmak
    zorunda degildir. Yalnizca organik icerikle yurutulen bir kampanyayi
    "platformsuz" birakmak, onu kampanya listesinde eksik gosterirdi.
    """

    META = "meta"                  # Facebook + Instagram reklamlari
    GOOGLE_ADS = "google_ads"
    TIKTOK_ADS = "tiktok_ads"
    LINKEDIN_ADS = "linkedin_ads"
    X_ADS = "x_ads"
    YOUTUBE_ADS = "youtube_ads"
    ORGANIK = "organik"            # Reklam harcamasi yok


class PermissionPackage(str, enum.Enum):
    """Bir KULLANICININ hazir yetki paketi.

    NEDEN KULLANICIDA, MUSTERIDE DEGIL:
    Bir kisinin neyi yapabilecegi o kisinin isiyle ilgilidir, hangi
    musteride calistigiyla degil. Once yetkiler musteri basina rol olarak
    tutuluyordu; ayni kisi iki musteride iki farkli sey yapabiliyordu ve
    "bu kullanici neyi yapabilir?" sorusunun tek bir cevabi yoktu.

    Paket yalnizca BASLANGIC noktasidir: paket secildikten sonra her izin
    kullanici bazinda tek tek acilip kapatilabilir.
    """

    ADMIN = "admin"            # Her sey
    STRATEGIST = "strategist"  # Icerik/rapor uretir, musteri onayina sunar
    EDITOR = "editor"          # Icerik duzenler, ic incelemeye gonderir
    VIEWER = "viewer"          # Yalnizca okur


class Platform(str, enum.Enum):
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    LINKEDIN = "linkedin"
    X = "x"
    PINTEREST = "pinterest"


class ContentStatus(str, enum.Enum):
    """Icerik ve raporlarin onay durumu.

    `APPROVED` olmadan hicbir sey yayinlanamaz, yorumlanamaz veya gonderilemez.
    """

    DRAFT = "draft"
    INTERNAL_REVIEW = "internal_review"
    CLIENT_REVIEW = "client_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AITaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AIProviderName(str, enum.Enum):
    CLAUDE = "claude"
    MANUS = "manus"
    GEMINI = "gemini"
    FAKE = "fake"


class ReportPeriod(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class MediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    REEL = "reel"
    STORY = "story"
    SHORT = "short"
    TEXT = "text"
    OTHER = "other"


class AutomationStatus(str, enum.Enum):
    """Bir otomasyon calistirmasinin durumu."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AutomationTrigger(str, enum.Enum):
    """Calistirmayi ne baslatti?"""

    SCHEDULE = "schedule"   # n8n zamanlayicisi
    MANUAL = "manual"       # panelden elle
