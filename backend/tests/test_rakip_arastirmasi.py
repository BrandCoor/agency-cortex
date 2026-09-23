"""WF-06 rakip arastirmasi ve Rakip/Trend sayfasi.

Korunan kurallar:
- Rakip yoksa SAHTE SONUC uretilmez; "yapilacak is yoktu" denir
- Izlenmeyen bir hesap hakkindaki bulgu KAYDEDILMEZ (yanlis hesaba
  atfedilirdi)
- Kaniti zayif bulgu "kesin" diye kaydedilmez
- Bulgu yoksa NEDENI yazilir; kullanici "bozuk mu?" diye sormaz
- Rakip sayisi sinirlidir: her rakip AI maliyeti demektir
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.brand import Brand
from app.models.enums import PermissionPackage, Platform
from app.models.izlenen import IzlemeTuru, TrackedAccount
from app.models.research import CompetitorObservation
from app.panel.auth import COOKIE_NAME
from app.services.is_akislari import AZAMI_RAKIP, wf06_rakip_arastirmasi

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return yanit.cookies.get(COOKIE_NAME)


@pytest.fixture
def musteri(db, make_workspace):
    def _kur(markali=True, rakip_sayisi=0):
        ws = make_workspace(name="Rakip Musterisi")
        db.flush()
        if markali:
            db.add(Brand(workspace_id=ws.id, name="Taha Usta"))
        for i in range(rakip_sayisi):
            db.add(TrackedAccount(
                workspace_id=ws.id, platform=Platform.INSTAGRAM,
                username=f"rakip{i}", tur=IzlemeTuru.RAKIP,
            ))
        db.flush()
        return ws

    return _kur


# --- Bos durumlar -------------------------------------------------------------

def test_rakip_yokken_sahte_sonuc_uretilmiyor(db, musteri):
    ws = musteri(rakip_sayisi=0)
    sonuc = wf06_rakip_arastirmasi(db, ws)

    assert sonuc.yapilacak_is_yoktu is True
    assert sonuc.ozet["rakip"] == 0
    # Kullaniciya NE YAPMASI gerektigi soylenir.
    assert any("rakip hesap yok" in n for n in sonuc.notlar)


def test_marka_yokken_arastirma_yapilmiyor(db, musteri):
    """Bulgular markaya gore yorumlanir; marka yoksa yorum anlamsiz olur."""
    ws = musteri(markali=False, rakip_sayisi=2)
    sonuc = wf06_rakip_arastirmasi(db, ws)

    assert sonuc.yapilacak_is_yoktu is True
    assert any("Marka bilgisi" in n for n in sonuc.notlar)


def test_yalnizca_rakip_turundekiler_inceleniyor(db, musteri):
    """Kendi hesabi ve referans hesap rakip arastirmasina girmez."""
    ws = musteri(rakip_sayisi=0)
    db.add(TrackedAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM,
        username="kendimiz", tur=IzlemeTuru.KENDI,
    ))
    db.add(TrackedAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM,
        username="ilham", tur=IzlemeTuru.REFERANS,
    ))
    db.flush()

    sonuc = wf06_rakip_arastirmasi(db, ws)
    assert sonuc.ozet["rakip"] == 0


# --- Ornek veri modunda gercek calisma ---------------------------------------

def test_bulgular_kaydediliyor(db, musteri):
    ws = musteri(rakip_sayisi=2)
    sonuc = wf06_rakip_arastirmasi(db, ws)

    kayitlar = db.execute(
        select(CompetitorObservation).where(
            CompetitorObservation.workspace_id == ws.id
        )
    ).scalars().all()
    assert sonuc.ozet["rakip"] == 2
    assert len(kayitlar) == sonuc.ozet["bulgu"]


def test_ornek_veri_kesin_bilgi_gibi_kaydedilmiyor(db, musteri):
    """Ornek veri 'fact' sayilirsa strateji yanlis yone doner."""
    ws = musteri(rakip_sayisi=1)
    wf06_rakip_arastirmasi(db, ws)

    for kayit in db.execute(
        select(CompetitorObservation).where(
            CompetitorObservation.workspace_id == ws.id
        )
    ).scalars().all():
        assert kayit.confidence == "low"
        assert kayit.uncertainties, "Belirsizlikler boş bırakılmamalı."


def test_izlenmeyen_hesap_bulgusu_kaydedilmiyor(db, musteri, monkeypatch):
    """Kime ait oldugu belirsiz veri, yanlis hesaba atfedilirdi."""
    from app.ai import fake

    ws = musteri(rakip_sayisi=1)
    gercek = fake.FakeProvider._build

    def _sahte(self, request):
        if request.task_type == "competitor_research":
            veri = gercek(self, request)
            veri["findings"].append({
                **veri["findings"][0],
                "username": "hic-izlenmeyen-hesap",
            })
            return veri
        return gercek(self, request)

    monkeypatch.setattr(fake.FakeProvider, "_build", _sahte)

    sonuc = wf06_rakip_arastirmasi(db, ws)
    kayitlar = db.execute(
        select(CompetitorObservation).where(
            CompetitorObservation.workspace_id == ws.id
        )
    ).scalars().all()

    adlar = {k.tracked_account_id for k in kayitlar}
    izlenenler = {
        r.id for r in db.execute(
            select(TrackedAccount).where(TrackedAccount.workspace_id == ws.id)
        ).scalars().all()
    }
    assert adlar <= izlenenler
    assert any("kaydedilmedi" in n for n in sonuc.notlar)


def test_rakip_sayisi_sinirli(db, musteri):
    """Her rakip AI maliyetidir; sinirsiz birakmak butceyi bitirebilirdi."""
    ws = musteri(rakip_sayisi=AZAMI_RAKIP + 5)
    sonuc = wf06_rakip_arastirmasi(db, ws)
    assert sonuc.ozet["rakip"] == AZAMI_RAKIP


def test_baska_musterinin_rakibi_incelenmiyor(db, musteri, make_workspace):
    ws = musteri(rakip_sayisi=1)
    baskasi = make_workspace(name="Baskasi")
    db.flush()
    db.add(TrackedAccount(
        workspace_id=baskasi.id, platform=Platform.INSTAGRAM,
        username="baskasinin-rakibi", tur=IzlemeTuru.RAKIP,
    ))
    db.flush()

    sonuc = wf06_rakip_arastirmasi(db, ws)
    assert sonuc.ozet["rakip"] == 1


# --- Panel --------------------------------------------------------------------

@pytest.fixture
def panel(client, db, make_user, make_workspace, add_member):
    def _kur(paket=PermissionPackage.ADMIN):
        kullanici = make_user(password=SIFRE)
        kullanici.permission_package = paket
        ws = make_workspace(name="Rakip Paneli")
        add_member(ws, kullanici)
        db.add(Brand(workspace_id=ws.id, name="Taha Usta"))
        db.commit()
        _giris(client, kullanici)
        return kullanici, ws

    return _kur


def test_sayfa_aciliyor(client, panel):
    _, ws = panel()
    yanit = client.get(f"/panel/musteri/{ws.id}/rakip-trend")
    assert yanit.status_code == 200
    assert "Rakip ve trend" in yanit.text


def test_bulgu_yokken_sebebi_yaziyor(client, panel):
    """'Bos' demek yetmez; kullanici 'bozuk mu?' diye sormamali."""
    _, ws = panel()
    yanit = client.get(f"/panel/musteri/{ws.id}/rakip-trend")
    assert "izlenen <strong>rakip hesap" in yanit.text
    assert "kapalı" in yanit.text


def test_rakip_eklenince_sebep_degisiyor(client, db, panel):
    _, ws = panel()
    db.add(TrackedAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM,
        username="rakip", tur=IzlemeTuru.RAKIP,
    ))
    db.commit()

    yanit = client.get(f"/panel/musteri/{ws.id}/rakip-trend")
    assert "1 rakip izleniyor" in yanit.text


def test_rapor_izni_yoksa_sayfa_acilmiyor(client, db, panel):
    from app.services.yetkiler import PAKET_VARSAYILANI, izinleri_yaz

    kullanici, ws = panel(PermissionPackage.VIEWER)
    izinleri_yaz(
        db, kullanici,
        set(PAKET_VARSAYILANI[PermissionPackage.VIEWER] - {"rapor.gor"}),
    )
    db.commit()

    assert client.get(f"/panel/musteri/{ws.id}/rakip-trend").status_code == 404


def test_uye_olunmayan_musterinin_sayfasi_404(client, make_user, make_workspace):
    kullanici = make_user(password=SIFRE)
    baskasi = make_workspace(name="Baskasinin")
    _giris(client, kullanici)
    assert client.get(f"/panel/musteri/{baskasi.id}/rakip-trend").status_code == 404
