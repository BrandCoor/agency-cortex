"""Ilk yonetici hesabini olusturur ve sifre sifirlamayi saglar.

NEDEN AYRI BIR KOMUT?
Sisteme disaridan acik bir "kayit ol" sayfasi konulmadi. Boyle bir sayfa
olsaydi adresi bilen herkes hesap acabilirdi. Bunun yerine ilk hesap
yalnizca sunucu uzerinde, bu komutla olusturulur.

GUVENLIK:
- Sifre komut satirina YAZILMAZ; ortam degiskeninden okunur. Komut satirina
  yazilan degerler sunucudaki `ps` ciktisinda ve kabuk gecmisinde gorunur.
- Sifre hicbir zaman ekrana veya loga basilmaz.
- "ilk-yonetici" komutu sistemde zaten kullanici varsa hicbir sey yapmaz.
  Boylece her kurulumda tekrar tekrar calistirilabilir (idempotent).

KULLANIM (sunucuda):
    docker compose exec -T api python -m app.cli.hesap ilk-yonetici
    docker compose exec -T api python -m app.cli.hesap sifre-degistir

Beklenen ortam degiskenleri:
    ILK_YONETICI_EMAIL, ILK_YONETICI_AD, ILK_YONETICI_SIFRE
    (sifre-degistir icin: HESAP_EMAIL, HESAP_YENI_SIFRE)
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.identity import User

# Argon2 ozeti kullanilsa bile kisa sifre kirilabilir. Alt sinir koyuyoruz.
MIN_SIFRE_UZUNLUGU = 12


class KurulumHatasi(Exception):
    """Komut calistirilamadiginda atilir."""


def _ortam(ad: str) -> str:
    deger = (os.environ.get(ad) or "").strip()
    if not deger:
        raise KurulumHatasi(
            f"'{ad}' ortam degiskeni bos. Bu komut gizli bilgileri yalnizca "
            "ortam degiskeninden okur."
        )
    return deger


def _sifreyi_dogrula(sifre: str) -> None:
    if len(sifre) < MIN_SIFRE_UZUNLUGU:
        # Sifrenin kendisi degil, yalnizca uzunlugu bildirilir.
        raise KurulumHatasi(
            f"Sifre en az {MIN_SIFRE_UZUNLUGU} karakter olmali "
            f"(verilen: {len(sifre)} karakter)."
        )


def ilk_yonetici() -> int:
    """Sistemde hic kullanici yoksa ilk yonetici hesabini acar."""
    # Sifre once okunur: eksikse veritabanina hic dokunmadan hata verelim.
    email = _ortam("ILK_YONETICI_EMAIL").lower()
    ad = _ortam("ILK_YONETICI_AD")
    sifre = os.environ.get("ILK_YONETICI_SIFRE") or ""

    with SessionLocal() as db:
        mevcut = db.execute(select(func.count()).select_from(User)).scalar_one()
        if mevcut > 0:
            print(
                f"ATLANDI: sistemde zaten {mevcut} kullanici var. "
                "Ilk yonetici yeniden olusturulmaz."
            )
            return 0

        if not sifre:
            raise KurulumHatasi(
                "'ILK_YONETICI_SIFRE' ortam degiskeni bos. Bu komut gizli "
                "bilgileri yalnizca ortam degiskeninden okur."
            )
        _sifreyi_dogrula(sifre)

        kullanici = User(
            email=email,
            full_name=ad,
            password_hash=hash_password(sifre),
            is_active=True,
            is_superuser=True,
        )
        db.add(kullanici)
        db.commit()

    print(f"TAMAM: ilk yonetici hesabi olusturuldu ({email}).")
    print("Sifre hicbir yere yazilmadi; yalnizca geri cevrilemez ozeti saklandi.")
    return 0


def sifre_degistir() -> int:
    """Var olan bir hesabin sifresini degistirir (panel disindan kurtarma)."""
    email = _ortam("HESAP_EMAIL").lower()
    sifre = _ortam("HESAP_YENI_SIFRE")
    _sifreyi_dogrula(sifre)

    with SessionLocal() as db:
        kullanici = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if kullanici is None:
            raise KurulumHatasi(f"Kullanici bulunamadi: {email}")
        kullanici.password_hash = hash_password(sifre)
        db.commit()

    print(f"TAMAM: {email} hesabinin sifresi degistirildi.")
    return 0


KOMUTLAR = {
    "ilk-yonetici": ilk_yonetici,
    "sifre-degistir": sifre_degistir,
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in KOMUTLAR:
        print("Kullanim: python -m app.cli.hesap <komut>", file=sys.stderr)
        print(f"Komutlar: {', '.join(KOMUTLAR)}", file=sys.stderr)
        return 2
    try:
        return KOMUTLAR[argv[0]]()
    except KurulumHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
