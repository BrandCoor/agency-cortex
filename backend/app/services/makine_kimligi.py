"""Makine kimligi: n8n gibi sistemlerin API'ye baglanma yolu.

NEDEN AYRI BIR KIMLIK: n8n bir insan hesabiyla baglanirsa, o hesabin
sifresi degistiginde otomasyon durur; hesap silindiginde otomasyonun
yaptigi her sey sahipsiz kalir; ve n8n'e sizan biri o insanin tum
yetkilerini ele gecirir. Makine kimliginin kapsami dardir, iptal
edilebilir ve her kullanimi kaydedilir.

ANAHTAR YALNIZCA BIR KEZ GOSTERILIR. Veritabaninda SHA-256 ozeti tutulur;
kaybedilirse yenisi uretilir, eskisi geri getirilemez.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.identity import Workspace
from app.models.otomasyon import ApiClient, ApiClientWorkspace

log = get_logger("makine_kimligi")

#: Anahtarin basindaki sabit. Bir sizinti taramasinda "bu bizim anahtarimiz"
#: demeyi kolaylastirir.
ONEK = "acx_"

#: Anahtarin gizli kismi: 32 bayt rastgele. Tahmin edilemez.
GIZLI_BAYT = 32

#: Kaydi bulmak icin kullanilan ACIK kimlik (4 bayt = 8 karakter).
#: Anahtarin bicimi: acx_<acik_kimlik>_<gizli>
#: Acik kimlik gizli kismin HICBIR PARCASINI icermez; ekranda ve loglarda
#: gosterilmesi guvenlidir.
ACIK_KIMLIK_BAYT = 4

#: "acx_" + 8 karakter = 12. Veritabaninda aranan deger budur.
ONEK_UZUNLUGU = len(ONEK) + ACIK_KIMLIK_BAYT * 2


class MakineKimligiHatasi(Exception):
    """Makine kimligi isleminde kurala takilan durum."""


def _ozet(anahtar: str) -> str:
    """Anahtarin geri cevrilemez ozeti.

    SHA-256 yeterlidir: anahtar 32 bayt RASTGELE oldugu icin sozluk veya
    kaba kuvvet saldirisi mumkun degildir. Argon2 gibi yavas bir ozet
    kullanmak her API cagrisina gereksiz gecikme eklerdi.
    """
    return hashlib.sha256(anahtar.encode("utf-8")).hexdigest()


def anahtar_uret() -> tuple[str, str, str]:
    """(tam_anahtar, aranacak_onek, ozet) uretir.

    Bicim: acx_<acik_kimlik>_<gizli>
    Onek yalnizca acik kimligi icerir; gizli kisimdan tek karakter bile
    disari sizmaz.
    """
    acik_kimlik = secrets.token_hex(ACIK_KIMLIK_BAYT)
    tam = f"{ONEK}{acik_kimlik}_{secrets.token_urlsafe(GIZLI_BAYT)}"
    return tam, tam[:ONEK_UZUNLUGU], _ozet(tam)


def olustur(
    db: Session,
    *,
    ad: str,
    olusturan_user_id: uuid.UUID | None,
    workspace_ids: list[uuid.UUID],
) -> tuple[ApiClient, str]:
    """Yeni makine kimligi acar. Doner: (kayit, TAM ANAHTAR).

    Tam anahtar bir daha elde edilemez; cagiran taraf kullaniciya BIR KEZ
    gostermelidir.
    """
    temiz_ad = " ".join((ad or "").split())
    if not temiz_ad:
        raise MakineKimligiHatasi("Ad boş olamaz.")
    if len(temiz_ad) > 120:
        raise MakineKimligiHatasi("Ad çok uzun.")

    tam, onek, ozet = anahtar_uret()
    kayit = ApiClient(
        name=temiz_ad,
        key_prefix=onek,
        key_hash=ozet,
        is_active=True,
        created_by_user_id=olusturan_user_id,
    )
    db.add(kayit)
    db.flush()

    yetki_ver(db, kayit, workspace_ids)
    # Anahtarin kendisi LOGLANMAZ.
    log.info("makine_kimligi_olusturuldu", api_client_id=str(kayit.id), ad=temiz_ad)
    return kayit, tam


def yetki_ver(db: Session, kayit: ApiClient, workspace_ids: list[uuid.UUID]) -> None:
    """Makine kimliginin erisebilecegi musteri listesini YENIDEN yazar.

    Listede olmayan musterilerin yetkisi kaldirilir; boylece panelde
    isareti kaldirmak gercekten yetkiyi kaldirir.
    """
    istenen = set(workspace_ids)

    # Var olmayan bir musteriye yetki verilemez.
    if istenen:
        bulunan = set(
            db.execute(
                select(Workspace.id).where(Workspace.id.in_(istenen))
            ).scalars().all()
        )
        eksik = istenen - bulunan
        if eksik:
            raise MakineKimligiHatasi("Seçilen müşterilerden biri bulunamadı.")

    mevcut = {
        satir.workspace_id: satir
        for satir in db.execute(
            select(ApiClientWorkspace).where(
                ApiClientWorkspace.api_client_id == kayit.id
            )
        ).scalars().all()
    }

    for workspace_id in istenen - set(mevcut):
        db.add(ApiClientWorkspace(api_client_id=kayit.id, workspace_id=workspace_id))
    for workspace_id in set(mevcut) - istenen:
        db.delete(mevcut[workspace_id])
    db.flush()


def yetkili_workspace_idleri(db: Session, api_client_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(ApiClientWorkspace.workspace_id).where(
                ApiClientWorkspace.api_client_id == api_client_id
            )
        ).scalars().all()
    )


def dogrula(db: Session, ham_anahtar: str | None) -> ApiClient | None:
    """Anahtari dogrular. Gecersizse None doner.

    Kaydi ONEK ile bulur, sonra TAM ozeti karsilastirir. Onek tek basina
    yeterli degildir; onu bilen biri giris yapamaz.
    """
    if not ham_anahtar or not ham_anahtar.startswith(ONEK):
        return None
    # Bicim: acx_<8 karakter acik kimlik>_<gizli>
    if len(ham_anahtar) < ONEK_UZUNLUGU + 20:
        return None
    if ham_anahtar[ONEK_UZUNLUGU] != "_":
        return None

    kayit = db.execute(
        select(ApiClient).where(ApiClient.key_prefix == ham_anahtar[:ONEK_UZUNLUGU])
    ).scalar_one_or_none()
    if kayit is None:
        return None

    # Zamanlama saldirisina kapali karsilastirma.
    if not secrets.compare_digest(kayit.key_hash, _ozet(ham_anahtar)):
        return None
    if not kayit.is_active or kayit.revoked_at is not None:
        return None

    kayit.last_used_at = datetime.now(UTC)
    return kayit


def iptal_et(db: Session, kayit: ApiClient) -> None:
    """Anahtari kalici olarak gecersiz kilar.

    Kayit SILINMEZ: gecmis calistirmalarin hangi kimlikle yapildigi
    kaybolmasin diye iz birakilir.
    """
    kayit.is_active = False
    kayit.revoked_at = datetime.now(UTC)
    db.flush()
    log.info("makine_kimligi_iptal_edildi", api_client_id=str(kayit.id))
