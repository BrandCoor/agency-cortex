"""Otomasyon paneli testleri.

Korunan kurallar:
- Anahtar yonetimi yalnizca sistem yoneticisine acik
- Yeni anahtar EKRANDA BIR KEZ gorunur, sonra bir daha gorunmez
- Is akisi acip kapatmak icin en az yonetici yetkisi gerekir
- Uye olunmayan musteride ayar degistirilemez
"""

from __future__ import annotations

import re

from sqlalchemy import select

from app.models.enums import AutomationStatus, AutomationTrigger, WorkspaceRole
from app.models.otomasyon import ApiClient, AutomationRun, AutomationSetting
from app.panel.auth import COOKIE_NAME
from app.services.otomasyon import acik_mi, ayar_yaz

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return yanit.cookies.get(COOKIE_NAME)


# --- Sayfa -------------------------------------------------------------------

def test_giris_yapmadan_girise_yonlendirir(client):
    yanit = client.get("/panel/otomasyon", follow_redirects=False)
    assert yanit.status_code == 303


def test_sayfa_akislari_listeliyor(client, db, make_user, make_workspace, add_member):
    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Otomasyon Musterisi")
    add_member(ws, kullanici, WorkspaceRole.OWNER)
    db.commit()
    _giris(client, kullanici)

    yanit = client.get("/panel/otomasyon")
    assert yanit.status_code == 200
    assert "Günlük sosyal zekâ" in yanit.text
    assert "Haftalık zekâ raporu" in yanit.text
    assert "Otomasyon Musterisi" in yanit.text


def test_normal_kullanici_anahtar_bolumunu_gormuyor(
    client, db, make_user, make_workspace, add_member
):
    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    add_member(ws, kullanici, WorkspaceRole.OWNER)
    db.commit()
    _giris(client, kullanici)

    yanit = client.get("/panel/otomasyon")
    assert yanit.status_code == 200
    assert "n8n bağlantı anahtarları" not in yanit.text


# --- Is akisi ac / kapat -----------------------------------------------------

def test_akis_acilip_kapatilabiliyor(client, db, make_user, make_workspace, add_member):
    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    add_member(ws, kullanici, WorkspaceRole.ADMIN)
    db.commit()
    _giris(client, kullanici)

    assert acik_mi(db, ws.id, "wf01_gunluk_zeka") is False

    ac = client.post(
        "/panel/otomasyon/akis",
        data={"workspace_id": str(ws.id), "workflow_key": "wf01_gunluk_zeka", "acik": "1"},
    )
    assert ac.status_code == 200
    ayar = db.execute(
        select(AutomationSetting).where(AutomationSetting.workspace_id == ws.id)
    ).scalar_one()
    db.refresh(ayar)
    assert ayar.is_enabled is True

    kapat = client.post(
        "/panel/otomasyon/akis",
        data={"workspace_id": str(ws.id), "workflow_key": "wf01_gunluk_zeka"},
    )
    assert kapat.status_code == 200
    db.refresh(ayar)
    assert ayar.is_enabled is False


def test_stratejist_akis_ayari_degistiremiyor(
    client, db, make_user, make_workspace, add_member
):
    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    add_member(ws, kullanici, WorkspaceRole.STRATEGIST)
    db.commit()
    _giris(client, kullanici)

    yanit = client.post(
        "/panel/otomasyon/akis",
        data={"workspace_id": str(ws.id), "workflow_key": "wf01_gunluk_zeka", "acik": "1"},
    )
    assert yanit.status_code == 403
    assert acik_mi(db, ws.id, "wf01_gunluk_zeka") is False


def test_uye_olunmayan_musteride_ayar_degistirilemiyor(
    client, db, make_user, make_workspace
):
    kullanici = make_user(password=SIFRE)
    baskasi = make_workspace(name="Baskasinin Musterisi")
    db.commit()
    _giris(client, kullanici)

    yanit = client.post(
        "/panel/otomasyon/akis",
        data={"workspace_id": str(baskasi.id), "workflow_key": "wf01_gunluk_zeka", "acik": "1"},
    )
    assert yanit.status_code == 404
    assert acik_mi(db, baskasi.id, "wf01_gunluk_zeka") is False


def test_tanimsiz_akis_kaydedilmiyor(client, db, make_user, make_workspace, add_member):
    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    add_member(ws, kullanici, WorkspaceRole.OWNER)
    db.commit()
    _giris(client, kullanici)

    yanit = client.post(
        "/panel/otomasyon/akis",
        data={"workspace_id": str(ws.id), "workflow_key": "uydurma", "acik": "1"},
    )
    assert yanit.status_code == 400
    assert db.execute(select(AutomationSetting)).scalars().all() == []


# --- Anahtar yonetimi --------------------------------------------------------

def _yonetici(db, make_user):
    k = make_user(password=SIFRE)
    k.is_superuser = True
    db.commit()
    return k


def test_anahtar_uretiliyor_ve_bir_kez_gosteriliyor(
    client, db, make_user, make_workspace
):
    yonetici = _yonetici(db, make_user)
    ws = make_workspace(name="Kapsamdaki Musteri")
    db.commit()
    _giris(client, yonetici)

    yanit = client.post(
        "/panel/otomasyon/anahtar/ekle",
        data={"ad": "n8n üretim", "workspace_ids": [str(ws.id)]},
    )
    assert yanit.status_code == 200
    bulunanlar = re.findall(r"acx_[A-Za-z0-9_-]{20,}", yanit.text)
    assert bulunanlar, "Anahtar ekranda gosterilmedi"
    tam_anahtar = bulunanlar[0]

    kayit = db.execute(select(ApiClient)).scalar_one()
    assert kayit.name == "n8n üretim"

    # Sayfa yenilendiginde TAM ANAHTAR artik gorunmez.
    tekrar = client.get("/panel/otomasyon")
    assert tam_anahtar not in tekrar.text
    # Yalnizca acik kimlik gorunur; gizli kisimdan tek karakter bile gorunmez.
    assert kayit.key_prefix in tekrar.text
    gizli_kisim = tam_anahtar[len(kayit.key_prefix) + 1:]
    assert gizli_kisim not in tekrar.text
    assert gizli_kisim[:8] not in tekrar.text


def test_normal_kullanici_anahtar_uretemiyor(client, db, make_user, make_workspace):
    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    db.commit()
    _giris(client, kullanici)

    yanit = client.post(
        "/panel/otomasyon/anahtar/ekle",
        data={"ad": "izinsiz", "workspace_ids": [str(ws.id)]},
    )
    assert yanit.status_code == 404
    assert db.execute(select(ApiClient)).scalars().all() == []


def test_anahtar_kapsami_daraltilabiliyor(client, db, make_user, make_workspace):
    yonetici = _yonetici(db, make_user)
    bir = make_workspace(name="Bir")
    iki = make_workspace(name="Iki")
    db.commit()
    _giris(client, yonetici)

    client.post(
        "/panel/otomasyon/anahtar/ekle",
        data={"ad": "n8n", "workspace_ids": [str(bir.id), str(iki.id)]},
    )
    kayit = db.execute(select(ApiClient)).scalar_one()

    from app.services.makine_kimligi import yetkili_workspace_idleri
    assert len(yetkili_workspace_idleri(db, kayit.id)) == 2

    # Isareti kaldirmak gercekten yetkiyi kaldirmali.
    client.post(
        "/panel/otomasyon/anahtar/yetki",
        data={"api_client_id": str(kayit.id), "workspace_ids": [str(bir.id)]},
    )
    assert yetkili_workspace_idleri(db, kayit.id) == [bir.id]


def test_anahtar_iptal_ediliyor_ama_kayit_silinmiyor(client, db, make_user, make_workspace):
    yonetici = _yonetici(db, make_user)
    ws = make_workspace(name="Musteri")
    db.commit()
    _giris(client, yonetici)

    client.post(
        "/panel/otomasyon/anahtar/ekle",
        data={"ad": "n8n", "workspace_ids": [str(ws.id)]},
    )
    kayit = db.execute(select(ApiClient)).scalar_one()

    client.post("/panel/otomasyon/anahtar/iptal", data={"api_client_id": str(kayit.id)})
    db.refresh(kayit)
    assert kayit.is_active is False
    assert kayit.revoked_at is not None
    # Gecmis calistirmalarin izi kaybolmasin diye kayit SILINMEZ.
    assert db.get(ApiClient, kayit.id) is not None


def test_olmayan_musteriye_yetki_verilemiyor(client, db, make_user):
    import uuid as _uuid
    yonetici = _yonetici(db, make_user)
    _giris(client, yonetici)

    yanit = client.post(
        "/panel/otomasyon/anahtar/ekle",
        data={"ad": "n8n", "workspace_ids": [str(_uuid.uuid4())]},
    )
    assert yanit.status_code == 400
    assert db.execute(select(ApiClient)).scalars().all() == []


# --- n8n giris bilgisi -------------------------------------------------------

def test_n8n_sifresi_yalnizca_sistem_yoneticisine_gosteriliyor(
    client, db, make_user, make_workspace, add_member, monkeypatch
):
    """Kapi sifresi panelde durur; normal kullaniciya GOSTERILMEZ."""
    from app.core.config import get_settings

    ayarlar = get_settings()
    monkeypatch.setattr(ayarlar, "n8n_domain", "n8n.ornek.test")
    monkeypatch.setattr(ayarlar, "n8n_basic_user", "ajans")
    monkeypatch.setattr(ayarlar, "n8n_basic_password", "CokGizliKapiSifresi99")

    normal = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    add_member(ws, normal, WorkspaceRole.OWNER)
    db.commit()
    _giris(client, normal)

    yanit = client.get("/panel/otomasyon")
    assert yanit.status_code == 200
    assert "CokGizliKapiSifresi99" not in yanit.text
    assert "n8n.ornek.test" not in yanit.text

    client.post("/panel/cikis")
    yonetici = _yonetici(db, make_user)
    _giris(client, yonetici)

    yonetici_yanit = client.get("/panel/otomasyon")
    assert "CokGizliKapiSifresi99" in yonetici_yanit.text
    assert "n8n.ornek.test" in yonetici_yanit.text


# --- Elle calistirma ---------------------------------------------------------

def test_elle_calistirma_kuyruga_atiyor(
    client, db, make_user, make_workspace, add_member, monkeypatch
):
    """Uzun suren akis paneli kilitlemesin diye is kuyruga alinir."""
    from app.workers import tasks

    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    add_member(ws, kullanici, WorkspaceRole.STRATEGIST)
    ayar_yaz(db, ws.id, "wf04_haftalik_rapor", acik=True)
    db.commit()
    _giris(client, kullanici)

    kuyruk: list[dict] = []
    monkeypatch.setattr(
        tasks.otomasyon_akisi_calistir, "delay",
        lambda **kw: kuyruk.append(kw),
    )

    yanit = client.post(
        "/panel/otomasyon/calistir",
        data={"workspace_id": str(ws.id), "workflow_key": "wf04_haftalik_rapor"},
    )
    assert yanit.status_code == 200
    assert "başlatıldı" in yanit.text

    kayit = db.execute(select(AutomationRun)).scalar_one()
    assert kayit.trigger is AutomationTrigger.MANUAL
    assert kayit.status is AutomationStatus.RUNNING

    assert len(kuyruk) == 1
    assert kuyruk[0]["run_id"] == str(kayit.id)
    assert kuyruk[0]["workflow_key"] == "wf04_haftalik_rapor"


def test_kuyruga_atilamazsa_hata_gizlenmiyor(
    client, db, make_user, make_workspace, add_member, monkeypatch
):
    """Kuyruk calismiyorsa kullanici 'basladi' sanmamali."""
    from app.workers import tasks

    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    add_member(ws, kullanici, WorkspaceRole.OWNER)
    ayar_yaz(db, ws.id, "wf04_haftalik_rapor", acik=True)
    db.commit()
    _giris(client, kullanici)

    def patla(**kw):
        raise OSError("redis yok")

    monkeypatch.setattr(tasks.otomasyon_akisi_calistir, "delay", patla)

    yanit = client.post(
        "/panel/otomasyon/calistir",
        data={"workspace_id": str(ws.id), "workflow_key": "wf04_haftalik_rapor"},
    )
    assert yanit.status_code == 503
    assert "kuyruğa alınamadı" in yanit.text

    kayit = db.execute(select(AutomationRun)).scalar_one()
    db.refresh(kayit)
    assert kayit.status is AutomationStatus.FAILED
    assert "kuyruğa alınamadı" in kayit.error_message


def test_editor_elle_calistiramiyor(
    client, db, make_user, make_workspace, add_member
):
    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    add_member(ws, kullanici, WorkspaceRole.EDITOR)
    ayar_yaz(db, ws.id, "wf04_haftalik_rapor", acik=True)
    db.commit()
    _giris(client, kullanici)

    yanit = client.post(
        "/panel/otomasyon/calistir",
        data={"workspace_id": str(ws.id), "workflow_key": "wf04_haftalik_rapor"},
    )
    assert yanit.status_code == 403
    assert db.execute(select(AutomationRun)).scalars().all() == []


def test_uye_olunmayan_musteride_elle_calistirilamiyor(
    client, db, make_user, make_workspace
):
    kullanici = make_user(password=SIFRE)
    baskasi = make_workspace(name="Baskasinin")
    ayar_yaz(db, baskasi.id, "wf04_haftalik_rapor", acik=True)
    db.commit()
    _giris(client, kullanici)

    yanit = client.post(
        "/panel/otomasyon/calistir",
        data={"workspace_id": str(baskasi.id), "workflow_key": "wf04_haftalik_rapor"},
    )
    assert yanit.status_code == 404
    assert db.execute(select(AutomationRun)).scalars().all() == []


def test_kapali_akis_elle_de_calistirilamiyor(
    client, db, make_user, make_workspace, add_member
):
    kullanici = make_user(password=SIFRE)
    ws = make_workspace(name="Musteri")
    add_member(ws, kullanici, WorkspaceRole.OWNER)
    db.commit()
    _giris(client, kullanici)

    yanit = client.post(
        "/panel/otomasyon/calistir",
        data={"workspace_id": str(ws.id), "workflow_key": "wf04_haftalik_rapor"},
    )
    assert yanit.status_code == 409
    assert db.execute(select(AutomationRun)).scalars().all() == []


# --- "Tum musteriler" anahtari ----------------------------------------------

def test_tum_musteriler_anahtari_panelde_boyle_gorunuyor(
    client, db, make_user, make_workspace
):
    yonetici = _yonetici(db, make_user)
    make_workspace(name="Bir Musteri")
    db.commit()
    _giris(client, yonetici)

    client.post(
        "/panel/otomasyon/anahtar/ekle",
        data={"ad": "n8n", "tum_musteriler": "1"},
    )
    kayit = db.execute(select(ApiClient)).scalar_one()
    assert kayit.all_workspaces is True

    sayfa = client.get("/panel/otomasyon")
    assert "Tüm müşteriler" in sayfa.text


def test_tum_musteriler_anahtarinin_kapsami_daraltilamiyor(
    client, db, make_user, make_workspace
):
    yonetici = _yonetici(db, make_user)
    ws = make_workspace(name="Bir")
    db.commit()
    _giris(client, yonetici)

    client.post(
        "/panel/otomasyon/anahtar/ekle",
        data={"ad": "n8n", "tum_musteriler": "1"},
    )
    kayit = db.execute(select(ApiClient)).scalar_one()

    yanit = client.post(
        "/panel/otomasyon/anahtar/yetki",
        data={"api_client_id": str(kayit.id), "workspace_ids": [str(ws.id)]},
    )
    assert yanit.status_code == 400
    db.refresh(kayit)
    assert kayit.all_workspaces is True
