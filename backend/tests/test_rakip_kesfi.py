"""WF-07: rakipleri sistemin KENDISI bulmasi.

EN ONEMLI KURAL: BULUNAN HESAP PASIF EKLENIR.
Bir dil modeli var olmayan bir hesap adi uretebilir. Dogrudan aktif
yazilsaydi, arastirma akisi olmayan bir hesap hakkinda "bulgu" uretir ve
o cikti rapora girerdi. Onaylamak tek tiklik bir is; uydurma bir rakibi
raporda gormek ise fark edilmesi zor bir hatadir.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.brand import Brand
from app.models.enums import Platform
from app.models.izlenen import IzlemeTuru, TrackedAccount
from app.models.social import SocialAccount
from app.services.is_akislari import AZAMI_ADAY, wf07_rakip_kesfi


@pytest.fixture
def musteri(db, make_workspace):
    def _kur(markali=True):
        ws = make_workspace(name="Kesif Musterisi")
        db.flush()
        if markali:
            db.add(Brand(workspace_id=ws.id, name="Taha Usta", sector="Restoran"))
        db.flush()
        return ws

    return _kur


def _adaylar(db, ws):
    return list(db.execute(
        select(TrackedAccount).where(TrackedAccount.workspace_id == ws.id)
    ).scalars())


# --- Bos durumlar -------------------------------------------------------------

def test_marka_yoksa_kesif_yapilmiyor(db, musteri):
    """Kesif sektore ve hedef kitleye dayanir; marka yoksa dayanak yok."""
    ws = musteri(markali=False)
    sonuc = wf07_rakip_kesfi(db, ws)

    assert sonuc.yapilacak_is_yoktu is True
    assert sonuc.ozet["aday"] == 0
    assert any("Marka bilgisi" in n for n in sonuc.notlar)
    assert _adaylar(db, ws) == []


# --- Bulunan adaylar ----------------------------------------------------------

def test_bulunan_aday_pasif_ekleniyor(db, musteri):
    ws = musteri()
    sonuc = wf07_rakip_kesfi(db, ws)

    assert sonuc.ozet["aday"] >= 1
    for kayit in _adaylar(db, ws):
        assert kayit.is_active is False, "Onaysiz hesap arastirilmamali"
        assert kayit.tur is IzlemeTuru.RAKIP


def test_aday_neden_eklendigini_yaziyor(db, musteri):
    """Gerekce, hesabin uydurulmus olma ihtimaline karsi tek kontrol."""
    ws = musteri()
    wf07_rakip_kesfi(db, ws)
    for kayit in _adaylar(db, ws):
        assert kayit.notlar and "Sistem buldu" in kayit.notlar


def test_aday_veri_durumu_neden_beklediklerini_soyluyor(db, musteri):
    ws = musteri()
    wf07_rakip_kesfi(db, ws)
    for kayit in _adaylar(db, ws):
        assert kayit.veri_durumu and "Onaylanana kadar" in kayit.veri_durumu


def test_pasif_aday_arastirma_akisina_girmiyor(db, musteri):
    """WF-06 yalnizca ONAYLANMIS rakiplere bakmali."""
    from app.services.is_akislari import wf06_rakip_arastirmasi

    ws = musteri()
    wf07_rakip_kesfi(db, ws)
    assert _adaylar(db, ws)  # aday var

    sonuc = wf06_rakip_arastirmasi(db, ws)
    assert sonuc.yapilacak_is_yoktu is True
    assert sonuc.ozet["rakip"] == 0


def test_onaylanan_aday_arastirmaya_giriyor(db, musteri):
    from app.services.is_akislari import wf06_rakip_arastirmasi

    ws = musteri()
    wf07_rakip_kesfi(db, ws)
    for kayit in _adaylar(db, ws):
        kayit.is_active = True
    db.flush()

    sonuc = wf06_rakip_arastirmasi(db, ws)
    assert sonuc.ozet["rakip"] >= 1


# --- Tekrar ve sinir ----------------------------------------------------------

def test_zaten_izlenen_hesap_tekrar_eklenmiyor(db, musteri):
    ws = musteri()
    wf07_rakip_kesfi(db, ws)
    ilk_sayi = len(_adaylar(db, ws))

    ikinci = wf07_rakip_kesfi(db, ws)
    assert len(_adaylar(db, ws)) == ilk_sayi
    assert ikinci.ozet["atlanan"] >= 1


def test_bagli_hesap_rakip_diye_eklenmiyor(db, musteri):
    """Musterinin KENDI bagli hesabini rakip yapmak sacma olurdu."""
    ws = musteri()
    # Once bir kesif yapip hangi adi urettigini ogreniyoruz.
    wf07_rakip_kesfi(db, ws)
    adlar = [k.username for k in _adaylar(db, ws)]
    assert adlar
    for kayit in _adaylar(db, ws):
        db.delete(kayit)
    db.flush()

    db.add(SocialAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM,
        external_id="1", username=adlar[0], display_name="Biz",
    ))
    db.flush()

    sonuc = wf07_rakip_kesfi(db, ws)
    assert sonuc.ozet["atlanan"] >= 1
    assert not [k for k in _adaylar(db, ws) if k.username == adlar[0]]


def test_aday_sayisi_sinirli(db, musteri):
    """Sinirsiz olsaydi liste tek calismada onlarca dogrulanmamis hesapla dolardi."""
    ws = musteri()
    sonuc = wf07_rakip_kesfi(db, ws)
    assert sonuc.ozet["aday"] <= AZAMI_ADAY


def test_baska_musterinin_listesine_yazilmiyor(db, musteri, make_workspace):
    baskasi = make_workspace(name="Baskasi")
    db.flush()
    ws = musteri()
    wf07_rakip_kesfi(db, ws)
    assert _adaylar(db, baskasi) == []
