"""Otomasyon kurulumu icin komut satiri araclari.

Bu komutlar SUNUCUDA, kurulum betigi tarafindan calistirilir. Amaci:
n8n'in Agency Cortex'e baglanacagi makine anahtarini insan araya
girmeden uretmek.

ANAHTAR EKRANA BASILIR ama loga yazilmaz. Cagiran betik onu dogrudan
n8n'in sifreli kimlik bilgisi dosyasina aktarir ve hemen siler.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.otomasyon import ApiClient
from app.services.makine_kimligi import olustur

#: Otomatik uretilen anahtarin adi. Panelde bu adla gorunur.
OTOMATIK_AD = "n8n (otomatik)"


def n8n_anahtari(_args) -> int:
    """n8n icin makine anahtari uretir ve TEK SATIR olarak basar.

    Daha once otomatik uretilmis anahtarlar IPTAL EDILIR: ayni anda iki
    gecerli anahtar dolasmasin. Anahtarin kendisi geri okunamadigi icin
    yenisi uretmek tek yoldur.
    """
    with SessionLocal() as db:
        eskiler = db.execute(
            select(ApiClient).where(
                ApiClient.name == OTOMATIK_AD,
                ApiClient.is_active.is_(True),
            )
        ).scalars().all()

        for eski in eskiler:
            eski.is_active = False
            eski.revoked_at = datetime.now(UTC)

        # "Tum musteriler": sonradan eklenen musteri de otomasyona girsin.
        _, anahtar = olustur(
            db, ad=OTOMATIK_AD, olusturan_user_id=None,
            workspace_ids=[], tum_musteriler=True,
        )
        db.commit()

    # Yalnizca anahtar basilir; betik bunu dogrudan okur.
    print(anahtar)
    return 0


def durum(_args) -> int:
    """Otomatik anahtar var mi, kac musteri kapsiyor?"""
    with SessionLocal() as db:
        kayit = db.execute(
            select(ApiClient).where(
                ApiClient.name == OTOMATIK_AD,
                ApiClient.is_active.is_(True),
            )
        ).scalar_one_or_none()

        if kayit is None:
            print("anahtar: yok")
            return 1
        print(f"anahtar: var ({kayit.key_prefix})")
        print(f"tum_musteriler: {'evet' if kayit.all_workspaces else 'hayir'}")
        print(f"son_kullanim: {kayit.last_used_at or 'hic'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(
        prog="otomasyon", description="Otomasyon kurulum araclari"
    )
    altlar = ayristirici.add_subparsers(dest="komut", required=True)
    altlar.add_parser("n8n-anahtari", help="n8n icin makine anahtari uret").set_defaults(
        islev=n8n_anahtari
    )
    altlar.add_parser("durum", help="Otomatik anahtarin durumu").set_defaults(islev=durum)

    args = ayristirici.parse_args(argv)
    return args.islev(args)


if __name__ == "__main__":
    sys.exit(main())
