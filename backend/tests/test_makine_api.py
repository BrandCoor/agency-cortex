"""n8n makine kimligi ve makine API'si.

Korunan kurallar:
- Anahtar veritabaninda ACIK SAKLANMAZ; yalnizca ozeti tutulur
- Istekle gelen workspace_id TEK BASINA yetki DEGILDIR
- Iptal edilen anahtar calismaz
- Kapali bir is akisi calistirilamaz
- Basarisizlik gizlenmez, kaydedilir
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.enums import AutomationStatus
from app.models.otomasyon import ApiClient, AutomationRun
from app.services.makine_kimligi import iptal_et, olustur
from app.services.otomasyon import ayar_yaz


@pytest.fixture
def kimlik(db, make_workspace):
    """Bir makine kimligi ve erisebildigi tek musteri."""
    def _kur(musteri_sayisi=1):
        musteriler = [make_workspace(name=f"Musteri {i}") for i in range(musteri_sayisi)]
        db.flush()
        kayit, anahtar = olustur(
            db, ad="n8n testi", olusturan_user_id=None,
            workspace_ids=[w.id for w in musteriler],
        )
        db.commit()
        return kayit, anahtar, musteriler
    return _kur


def _bas(anahtar):
    return {"X-API-Key": anahtar}


# --- Anahtarin saklanmasi ----------------------------------------------------

def test_anahtar_veritabaninda_acik_saklanmiyor(db, kimlik):
    kayit, anahtar, _ = kimlik()
    taze = db.get(ApiClient, kayit.id)

    assert taze.key_hash != anahtar
    assert anahtar not in taze.key_hash
    # Onek yalnizca ACIK KIMLIGI icerir; gizli kisim veritabaninda yok.
    assert taze.key_prefix == anahtar[:12]
    gizli = anahtar[13:]
    assert gizli not in taze.key_prefix
    assert gizli not in taze.key_hash


def test_yalnizca_onek_ile_giris_yapilamiyor(client, db, kimlik):
    """Onek ekranda gorunur; onu bilen biri baglanamamali."""
    kayit, anahtar, _ = kimlik()
    for kisim in (anahtar[:12], anahtar[:12] + "_", anahtar[:20], anahtar[:-1]):
        yanit = client.get("/api/v1/makine/kendim", headers=_bas(kisim))
        assert yanit.status_code == 401, kisim


# --- Kimlik dogrulama --------------------------------------------------------

def test_anahtarsiz_istek_reddediliyor(client):
    assert client.get("/api/v1/makine/kendim").status_code == 401


def test_uydurma_anahtar_reddediliyor(client, db, kimlik):
    kimlik()
    assert client.get(
        "/api/v1/makine/kendim", headers=_bas("acx_uydurma_anahtar_degeri_123456")
    ).status_code == 401


def test_dogru_anahtar_kendi_kapsamini_goruyor(client, db, kimlik):
    _, anahtar, musteriler = kimlik(musteri_sayisi=2)
    yanit = client.get("/api/v1/makine/kendim", headers=_bas(anahtar))

    assert yanit.status_code == 200
    veri = yanit.json()
    assert veri["ad"] == "n8n testi"
    donen = {m["workspace_id"] for m in veri["musteriler"]}
    assert donen == {str(w.id) for w in musteriler}
    # Tanimli tum akislar bildiriliyor ki n8n neyi calistiracagini bilsin.
    assert len(veri["tanimli_akislar"]) == 5


def test_iptal_edilen_anahtar_calismiyor(client, db, kimlik):
    kayit, anahtar, _ = kimlik()
    assert client.get("/api/v1/makine/kendim", headers=_bas(anahtar)).status_code == 200

    iptal_et(db, kayit)
    db.commit()
    assert client.get("/api/v1/makine/kendim", headers=_bas(anahtar)).status_code == 401


def test_son_kullanim_kaydediliyor(client, db, kimlik):
    kayit, anahtar, _ = kimlik()
    assert kayit.last_used_at is None

    client.get("/api/v1/makine/kendim", headers=_bas(anahtar))
    taze = db.get(ApiClient, kayit.id)
    db.refresh(taze)
    assert taze.last_used_at is not None


# --- EN KRITIK: workspace_id'ye guvenilmez -----------------------------------

def test_kapsam_disindaki_musteriye_ulasilamiyor(client, db, kimlik, make_workspace):
    """n8n'den gelen workspace_id tek basina HICBIR SEY ifade etmez."""
    _, anahtar, _ = kimlik()
    baskasi = make_workspace(name="Baska Ajansin Musterisi")
    db.commit()

    baglam = client.get(
        f"/api/v1/makine/workspaces/{baskasi.id}/baglam", headers=_bas(anahtar)
    )
    # 403 degil 404: o musterinin VARLIGI bile ele verilmez.
    assert baglam.status_code == 404

    calistirma = client.post(
        f"/api/v1/makine/workspaces/{baskasi.id}/calistirma",
        headers=_bas(anahtar), json={"workflow_key": "wf01_gunluk_zeka"},
    )
    assert calistirma.status_code == 404
    assert db.execute(
        select(AutomationRun).where(AutomationRun.workspace_id == baskasi.id)
    ).scalar_one_or_none() is None


def test_olmayan_musteri_de_404(client, db, kimlik):
    _, anahtar, _ = kimlik()
    yanit = client.get(
        f"/api/v1/makine/workspaces/{uuid.uuid4()}/baglam", headers=_bas(anahtar)
    )
    assert yanit.status_code == 404


def test_baglam_gizli_bilgi_dondurmuyor(client, db, kimlik):
    """Jeton, sifre veya anahtar n8n'e VERILMEZ."""
    _, anahtar, musteriler = kimlik()
    yanit = client.get(
        f"/api/v1/makine/workspaces/{musteriler[0].id}/baglam", headers=_bas(anahtar)
    )
    assert yanit.status_code == 200
    metin = yanit.text.lower()
    for yasak in ("access_token", "refresh_token", "password", "secret", "api_key"):
        assert yasak not in metin


# --- Calistirma kaydi --------------------------------------------------------

def test_kapali_akis_calistirilamiyor(client, db, kimlik):
    """Varsayilan KAPALI: panelden acilmadan otomasyon calismaz."""
    _, anahtar, musteriler = kimlik()
    yanit = client.post(
        f"/api/v1/makine/workspaces/{musteriler[0].id}/calistirma",
        headers=_bas(anahtar), json={"workflow_key": "wf01_gunluk_zeka"},
    )
    assert yanit.status_code == 409
    assert "kapalı" in yanit.json()["detail"]


def test_tanimsiz_akis_reddediliyor(client, db, kimlik):
    _, anahtar, musteriler = kimlik()
    yanit = client.post(
        f"/api/v1/makine/workspaces/{musteriler[0].id}/calistirma",
        headers=_bas(anahtar), json={"workflow_key": "uydurma_akis"},
    )
    assert yanit.status_code == 409


def test_acik_akis_calisip_basariyla_kapaniyor(client, db, kimlik):
    _, anahtar, musteriler = kimlik()
    ws = musteriler[0]
    ayar_yaz(db, ws.id, "wf01_gunluk_zeka", acik=True)
    db.commit()

    ac = client.post(
        f"/api/v1/makine/workspaces/{ws.id}/calistirma",
        headers=_bas(anahtar),
        json={"workflow_key": "wf01_gunluk_zeka", "external_execution_id": "n8n-42"},
    )
    assert ac.status_code == 201
    run_id = ac.json()["run_id"]

    kapat = client.post(
        f"/api/v1/makine/calistirma/{run_id}/bitir",
        headers=_bas(anahtar),
        json={"basarili": True, "ozet": {"taranan_hesap": 3}},
    )
    assert kapat.status_code == 200
    assert kapat.json()["durum"] == "succeeded"

    kayit = db.get(AutomationRun, uuid.UUID(run_id))
    db.refresh(kayit)
    assert kayit.status is AutomationStatus.SUCCEEDED
    assert kayit.summary == {"taranan_hesap": 3}
    assert kayit.external_execution_id == "n8n-42"
    assert kayit.finished_at is not None


def test_basarisizlik_gizlenmiyor(client, db, kimlik):
    _, anahtar, musteriler = kimlik()
    ws = musteriler[0]
    ayar_yaz(db, ws.id, "wf02_trend", acik=True)
    db.commit()

    run_id = client.post(
        f"/api/v1/makine/workspaces/{ws.id}/calistirma",
        headers=_bas(anahtar), json={"workflow_key": "wf02_trend"},
    ).json()["run_id"]

    kapat = client.post(
        f"/api/v1/makine/calistirma/{run_id}/bitir",
        headers=_bas(anahtar),
        json={"basarili": False, "hata_mesaji": "Manus zaman asimina ugradi"},
    )
    assert kapat.status_code == 200
    assert kapat.json()["durum"] == "failed"

    kayit = db.get(AutomationRun, uuid.UUID(run_id))
    db.refresh(kayit)
    assert kayit.status is AutomationStatus.FAILED
    assert kayit.error_message == "Manus zaman asimina ugradi"


def test_ayni_calistirma_iki_kez_kapatilamiyor(client, db, kimlik):
    _, anahtar, musteriler = kimlik()
    ws = musteriler[0]
    ayar_yaz(db, ws.id, "wf02_trend", acik=True)
    db.commit()

    run_id = client.post(
        f"/api/v1/makine/workspaces/{ws.id}/calistirma",
        headers=_bas(anahtar), json={"workflow_key": "wf02_trend"},
    ).json()["run_id"]

    client.post(
        f"/api/v1/makine/calistirma/{run_id}/bitir",
        headers=_bas(anahtar), json={"basarili": True},
    )
    ikinci = client.post(
        f"/api/v1/makine/calistirma/{run_id}/bitir",
        headers=_bas(anahtar), json={"basarili": False, "hata_mesaji": "sonradan"},
    )
    assert ikinci.status_code == 409


def test_baskasinin_calistirmasi_kapatilamiyor(client, db, kimlik, make_workspace):
    _, anahtar, musteriler = kimlik()

    # Ayri bir kimlik, ayri bir musteri.
    yabanci_ws = make_workspace(name="Yabanci")
    db.flush()
    _, yabanci_anahtar = olustur(
        db, ad="baska n8n", olusturan_user_id=None, workspace_ids=[yabanci_ws.id],
    )
    ayar_yaz(db, musteriler[0].id, "wf02_trend", acik=True)
    db.commit()

    run_id = client.post(
        f"/api/v1/makine/workspaces/{musteriler[0].id}/calistirma",
        headers=_bas(anahtar), json={"workflow_key": "wf02_trend"},
    ).json()["run_id"]

    yanit = client.post(
        f"/api/v1/makine/calistirma/{run_id}/bitir",
        headers=_bas(yabanci_anahtar), json={"basarili": True},
    )
    assert yanit.status_code == 404


# --- "Tum musteriler" kapsami ------------------------------------------------

def test_tum_musteriler_kapsami_sonradan_eklenen_musteriyi_de_kapsiyor(
    client, db, make_workspace
):
    """Otomasyon her yeni musteri icin elle yetki beklememeli."""
    ilk = make_workspace(name="Ilk Musteri")
    db.flush()
    _, anahtar = olustur(
        db, ad="n8n (otomatik)", olusturan_user_id=None,
        workspace_ids=[], tum_musteriler=True,
    )
    db.commit()

    veri = client.get("/api/v1/makine/kendim", headers=_bas(anahtar)).json()
    assert {m["workspace_id"] for m in veri["musteriler"]} == {str(ilk.id)}

    # ANAHTAR DEGISMEDEN yeni musteri eklendi.
    sonraki = make_workspace(name="Sonradan Eklenen")
    db.commit()

    veri = client.get("/api/v1/makine/kendim", headers=_bas(anahtar)).json()
    assert {m["workspace_id"] for m in veri["musteriler"]} == {
        str(ilk.id), str(sonraki.id),
    }


def test_pasif_musteri_tum_musteriler_kapsaminda_bile_gorunmuyor(
    client, db, make_workspace
):
    ws = make_workspace(name="Pasif Musteri")
    ws.is_active = False
    db.flush()
    _, anahtar = olustur(
        db, ad="n8n", olusturan_user_id=None, workspace_ids=[], tum_musteriler=True,
    )
    db.commit()

    veri = client.get("/api/v1/makine/kendim", headers=_bas(anahtar)).json()
    assert veri["musteriler"] == []

    yanit = client.get(
        f"/api/v1/makine/workspaces/{ws.id}/baglam", headers=_bas(anahtar)
    )
    assert yanit.status_code == 404


# --- Toplu calistirma --------------------------------------------------------

def test_toplu_calistirma_kapali_musterileri_atliyor(client, db, kimlik):
    from app.services.otomasyon import ayar_yaz

    _, anahtar, musteriler = kimlik(musteri_sayisi=2)
    ayar_yaz(db, musteriler[0].id, "wf04_haftalik_rapor", acik=True)
    db.commit()

    yanit = client.post(
        "/api/v1/makine/akis/wf04_haftalik_rapor/calistir-hepsi",
        headers=_bas(anahtar), json={},
    )
    assert yanit.status_code == 200
    veri = yanit.json()
    assert veri["musteri_sayisi"] == 2
    assert veri["basarili"] == 1
    assert veri["atlanan"] == 1
    assert veri["hatali"] == 0

    calistirmalar = db.execute(select(AutomationRun)).scalars().all()
    assert len(calistirmalar) == 1
    assert calistirmalar[0].workspace_id == musteriler[0].id


def test_toplu_calistirmada_bir_musterinin_hatasi_digerlerini_durdurmuyor(
    client, db, kimlik
):
    from app.models.enums import Platform
    from app.models.social import SocialAccount
    from app.services.otomasyon import ayar_yaz

    _, anahtar, musteriler = kimlik(musteri_sayisi=2)
    bozuk, saglam = musteriler

    # Ilk musteride anahtarsiz hesap var -> WF-01 hata verir.
    db.add(SocialAccount(
        workspace_id=bozuk.id, platform=Platform.INSTAGRAM,
        external_id="yok", username="yok", is_active=True,
    ))
    ayar_yaz(db, bozuk.id, "wf01_gunluk_zeka", acik=True)
    ayar_yaz(db, saglam.id, "wf01_gunluk_zeka", acik=True)
    db.commit()

    yanit = client.post(
        "/api/v1/makine/akis/wf01_gunluk_zeka/calistir-hepsi",
        headers=_bas(anahtar), json={},
    )
    assert yanit.status_code == 200
    veri = yanit.json()
    assert veri["hatali"] == 1
    assert veri["basarili"] == 1

    hatali = next(s for s in veri["sonuclar"] if s["durum"] == "hata")
    assert "veri çekilemedi" in hatali["aciklama"]

    # Iki calistirma da KAYDEDILDI; biri hata, biri basarili.
    kayitlar = db.execute(select(AutomationRun)).scalars().all()
    assert len(kayitlar) == 2
    assert {k.status.value for k in kayitlar} == {"failed", "succeeded"}


def test_toplu_calistirma_tanimsiz_akisi_reddediyor(client, db, kimlik):
    _, anahtar, _ = kimlik()
    yanit = client.post(
        "/api/v1/makine/akis/uydurma_akis/calistir-hepsi",
        headers=_bas(anahtar), json={},
    )
    assert yanit.status_code == 409
