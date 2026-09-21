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
from app.core.security import hash_password, verify_password
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
    # Kopyala-yapistirda basa/sona kacan bir bosluk hesabi acar ama girisi
    # kalici olarak bozar: kullanici bosluksuz yazar, ozet tutmaz. Sessizce
    # kirpmak yerine acikca reddediyoruz.
    if sifre != sifre.strip():
        raise KurulumHatasi(
            "Sifrenin basinda veya sonunda bosluk var. Bu, giris yaparken "
            "sifrenin tutmamasina yol acar. Gizli deger kutusuna sifreyi "
            "bosluksuz yapistirin."
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
    # DIKKAT: sifre _ortam() ile okunmaz. _ortam() bastaki/sondaki bosluklari
    # kirpar; bir sifrede bunu sessizce yapmak, kullanicinin bildigi sifre ile
    # saklanan ozetin farklilasmasina yol acar. Ham okunur, sonra reddedilir.
    sifre = os.environ.get("HESAP_YENI_SIFRE") or ""
    if not sifre:
        raise KurulumHatasi("'HESAP_YENI_SIFRE' ortam degiskeni bos.")
    _sifreyi_dogrula(sifre)

    with SessionLocal() as db:
        kullanici = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if kullanici is None:
            raise KurulumHatasi(f"Kullanici bulunamadi: {email}")
        kullanici.password_hash = hash_password(sifre)
        db.commit()

    print(f"TAMAM: {email} hesabinin sifresi degistirildi.")
    return 0


def tanilama() -> int:
    """Giris neden calismiyor? Sifrenin KENDISINI aciga cikarmadan anlatir.

    Standart girdiden iki satir okur: e-posta ve sifre (kurulumdaki gizli
    degerlerin aynisi). Ciktida sifrenin icerigi YOKTUR; yalnizca uzunluk,
    bosluk ve ASCII disi karakter bilgisi ile ozet eslesmesi bildirilir.
    """
    email_ham = sys.stdin.readline().rstrip("\n")
    sifre_ham = sys.stdin.readline().rstrip("\n")

    print("--- e-posta ---")
    print(f"gizli degerdeki hali (gorunur kacis dizileriyle): {email_ham!r}")
    print(f"basta/sonda bosluk var mi: {'EVET' if email_ham != email_ham.strip() else 'hayir'}")

    print("--- sifre (icerigi yazilmaz) ---")
    print(f"uzunluk: {len(sifre_ham)} karakter")
    print(f"basta/sonda bosluk var mi: {'EVET' if sifre_ham != sifre_ham.strip() else 'hayir'}")
    ascii_disi = [k for k in sifre_ham if ord(k) > 127]
    print(f"ASCII disi karakter sayisi: {len(ascii_disi)}")
    if ascii_disi:
        print("  (Turkce harf gibi karakterler farkli klavyelerde sorun cikarabilir.)")
    print(f"sadece gorunur karakterlerden mi olusuyor: {'evet' if sifre_ham.isprintable() else 'HAYIR'}")

    with SessionLocal() as db:
        kullanicilar = db.execute(select(User)).scalars().all()
        print("--- veritabani ---")
        print(f"sistemdeki kullanici sayisi: {len(kullanicilar)}")
        for k in kullanicilar:
            print(f"  kayitli e-posta: {k.email!r}  aktif: {k.is_active}")

        hedef = next(
            (k for k in kullanicilar if k.email == email_ham.strip().lower()), None
        )
        print("--- eslesme ---")
        if hedef is None:
            print("SONUC: Bu e-posta ile kayitli kullanici YOK.")
            print("Nedeni: gizli degerdeki e-posta, kayitli e-postadan farkli.")
            return 0

        print("bu e-posta ile kullanici bulundu.")
        print(f"ozet yontemi: {hedef.password_hash.split('$')[1] if '$' in hedef.password_hash else 'bilinmiyor'}")
        if verify_password(sifre_ham, hedef.password_hash):
            print("SONUC: Gizli degerdeki sifre, kayitli ozetle UYUSUYOR.")
            print("Yani sunucu tarafi dogru. Tarayiciya yazilan sifre farkli olmali.")
        else:
            print("SONUC: Gizli degerdeki sifre, kayitli ozetle UYUSMUYOR.")
            print("Yani hesap, simdikinden farkli bir sifreyle acilmis.")
    return 0


KOMUTLAR = {
    "ilk-yonetici": ilk_yonetici,
    "sifre-degistir": sifre_degistir,
    "tanilama": tanilama,
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
