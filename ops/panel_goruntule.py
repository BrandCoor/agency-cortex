"""Panel sayfalarinin GERCEK bir tarayicida nasil gorundugunu kaydeder.

NEDEN VAR
---------
Testin gecmesi bir seyin dogru GORUNDUGUNU kanitlamaz. 23 Eylul'de panel
bastan yazildiginda 19 CSS sinifi tanimsiz kaldi: butun sayfalar HTTP 200
donuyor ve 703 testin hepsi geciyordu, ama ekranda basliklar hizasiz,
olcu kutulari duz metindi. Bu betik o hata sinifini GORUNUR kilar.

NE YAPAR
--------
1. AYRI bir veritabaninda (adi "_gorsel" ile biter) semayi sifirdan kurar
2. Ornek bir yonetici ve uc musteri yazar
3. Uygulamayi yerel bir portta ayaga kaldirir
4. Chromium ile girer, her sayfayi koyu ve acik temada cizdirir
5. Giris ekranina dusen veya "Not Found" donen sayfayi SORUN diye bildirir

KULLANIM
--------
    pip install playwright
    python ops/panel_goruntule.py <cikti-dizini> [--chromium <yol>]

Chromium yolu verilmezse Playwright'in kendi indirdigi tarayici kullanilir.

DIKKAT: Bu betik gelistirme aracidir; uretimde CALISTIRILMAZ. Veritabanini
SIFIRDAN kurar, yani icindeki her seyi siler. Bu yuzden veritabani adinin
"_gorsel" ile bitmesi ZORUNLUDUR ve kontrol ediliyor.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import threading
import time

KOK = pathlib.Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(KOK))

VERITABANI = os.environ.get("GORSEL_DB", "agency_cortex_gorsel")
if not VERITABANI.endswith("_gorsel"):
    raise SystemExit(
        "Bu betik veritabanini SIFIRDAN kurar. Kazayla gelistirme veya uretim "
        f"verisini silmemek icin ad '_gorsel' ile bitmelidir. Verilen: {VERITABANI}"
    )

# Uygulama ice aktarilmadan ONCE ayarlanmalidir.
os.environ["APP_ENV"] = "development"
os.environ["POSTGRES_DB"] = VERITABANI
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "agency")
os.environ.setdefault("POSTGRES_PASSWORD", "dev-parola")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ["SECRET_KEY"] = "gorsel-dogrulama-anahtari"
os.environ["ENCRYPTION_KEY"] = "gorsel-dogrulama-sifreleme"

import sqlalchemy as sa  # noqa: E402
import uvicorn  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: F401,E402  - tablolarin kayit olmasi icin
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.enums import PermissionPackage  # noqa: E402
from app.models.identity import User, Workspace, WorkspaceMember  # noqa: E402

EPOSTA = "ornek@agencycortex.tech"
PAROLA = "Ornek-Parola-2026"
PORT = int(os.environ.get("GORSEL_PORT", "8771"))
ORNEK_MUSTERILER = (
    ("Gaziantepli Taha Usta", "gaziantepli-taha-usta"),
    ("Anadolu Kahvecisi", "anadolu-kahvecisi"),
    ("Nar Çiçeği Tekstil", "nar-cicegi-tekstil"),
)


def ornek_veri_yaz(motor) -> str:
    """Semayi sifirdan kurar ve bir yonetici ile uc musteri yazar."""
    Base.metadata.drop_all(motor)
    Base.metadata.create_all(motor)
    with Session(motor) as db:
        kisi = User(
            email=EPOSTA,
            password_hash=hash_password(PAROLA),
            full_name="Örnek Yönetici",
            is_superuser=True,
            is_active=True,
            permission_package=PermissionPackage.ADMIN,
        )
        db.add(kisi)
        db.flush()
        for ad, kisa in ORNEK_MUSTERILER:
            ws = Workspace(name=ad, slug=kisa)
            db.add(ws)
            db.flush()
            db.add(WorkspaceMember(workspace_id=ws.id, user_id=kisi.id))
        db.commit()
        return str(
            db.execute(sa.select(Workspace.id).order_by(Workspace.name)).scalars().first()
        )


def sunucuyu_baslat() -> uvicorn.Server:
    from app.main import app as fastapi_app

    sunucu = uvicorn.Server(
        uvicorn.Config(fastapi_app, host="127.0.0.1", port=PORT, log_level="error")
    )
    threading.Thread(target=sunucu.run, daemon=True).start()
    for _ in range(80):
        if getattr(sunucu, "started", False):
            return sunucu
        time.sleep(0.25)
    raise SystemExit("Uygulama acilmadi.")


def sayfalar(workspace_id: str) -> list[tuple[str, str]]:
    return [
        ("gosterge", "/panel/dashboard"),
        ("musteriler", "/panel"),
        ("gorunum", "/panel/gorunum"),
        ("yetkiler", "/panel/yetkiler"),
        ("ayarlar", "/panel/ayarlar"),
        ("kullanicilar", "/panel/kullanicilar"),
        ("otomasyon", "/panel/otomasyon"),
        ("musteri-ozet", f"/panel/musteri/{workspace_id}"),
        ("takvim", f"/panel/musteri/{workspace_id}/takvim"),
        ("kampanya", f"/panel/musteri/{workspace_id}/kampanya"),
        ("hesaplar", f"/panel/musteri/{workspace_id}/hesaplar"),
        ("marka", f"/panel/musteri/{workspace_id}/marka"),
        ("ekip", f"/panel/musteri/{workspace_id}/ekip"),
        ("rakip", f"/panel/musteri/{workspace_id}/rakip-trend"),
    ]


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("cikti", type=pathlib.Path, help="Resimlerin yazilacagi dizin")
    ayristirici.add_argument("--chromium", default=None, help="Chromium calistirilabilir yolu")
    secenekler = ayristirici.parse_args()

    motor = sa.create_engine(get_settings().database_url, future=True)
    workspace_id = ornek_veri_yaz(motor)
    sunucuyu_baslat()

    from playwright.sync_api import sync_playwright

    secenekler.cikti.mkdir(parents=True, exist_ok=True)
    kok = f"http://127.0.0.1:{PORT}"
    sorunlu: list[str] = []

    with sync_playwright() as p:
        baslatma = {"executable_path": secenekler.chromium} if secenekler.chromium else {}
        tarayici = p.chromium.launch(**baslatma)
        sayfa = tarayici.new_page(viewport={"width": 1440, "height": 950})

        sayfa.goto(f"{kok}/panel/giris")
        sayfa.screenshot(path=str(secenekler.cikti / "00-giris.png"))
        sayfa.fill("#email", EPOSTA)
        sayfa.fill("#password", PAROLA)
        sayfa.click("button[type=submit]")
        sayfa.wait_for_load_state("networkidle")
        if "giris" in sayfa.url:
            print("SORUN: giris yapilamadi")
            return 1

        for tema in ("koyu", "acik"):
            sayfa.goto(f"{kok}/panel/gorunum")
            sayfa.check(f"input[name=tema][value={tema}]", force=True)
            # DIKKAT: yan menudeki "Cikis" de bir submit dugmesidir ve DOM'da
            # once gelir. Secici `main` icine kapsanmazsa betik kendini
            # oturumdan atar ve butun resimler giris ekrani olur.
            sayfa.click("main button[type=submit]")
            sayfa.wait_for_load_state("networkidle")

            for ad, yol in sayfalar(workspace_id):
                sayfa.goto(f"{kok}{yol}")
                sayfa.wait_for_load_state("networkidle")
                sayfa.screenshot(path=str(secenekler.cikti / f"{tema}-{ad}.png"), full_page=True)
                govde = sayfa.inner_text("body")[:120]
                bozuk = "Giriş" in sayfa.title() or "Not Found" in govde
                if bozuk:
                    sorunlu.append(f"{tema}/{ad}")
                print(("SORUN " if bozuk else "") + f"{tema}/{ad}: {sayfa.title()}")
        tarayici.close()

    print(f"SORUNLU: {', '.join(sorunlu) if sorunlu else 'yok'}")
    return 1 if sorunlu else 0


if __name__ == "__main__":
    raise SystemExit(main())
