"""Manus API v2 saglayicisi ve webhook imza dogrulamasi.

Bu testlerdeki her beklenti, resmi Manus v2 dokumanindaki degerlere
dayanir. Dokumanda bulunmayan hicbir davranis "dogru" kabul edilmez.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.ai.base import ProviderNotConfigured
from app.ai.manus import (
    API_KEY_HEADER,
    BASE_URL,
    ManusError,
    ManusGorevBasarisiz,
    ManusProvider,
    kredi_maliyeti,
)
from app.ai.manus_webhook import (
    ZAMAN_PENCERESI_SANIYE,
    WebhookImzaHatasi,
    imzayi_dogrula,
    olayi_coz,
)

ANAHTAR = "manus-deneme-anahtari"


# --- Yapilandirma ------------------------------------------------------------

def test_anahtarsiz_saglayici_hazir_degil():
    p = ManusProvider(api_key="")
    assert not p.is_configured
    assert p.missing_config == ["MANUS_API_KEY"]
    calisir, aciklama = p.health_check()
    assert calisir is False
    assert "MANUS_API_KEY" in aciklama


def test_anahtarsiz_cagri_acik_hata_veriyor():
    p = ManusProvider(api_key="")
    with pytest.raises(ProviderNotConfigured):
        p.gorev_olustur("deneme")


def test_anahtarli_saglayici_hazir():
    p = ManusProvider(api_key=ANAHTAR)
    assert p.is_configured
    calisir, _ = p.health_check()
    assert calisir is True


# --- Dokumana uygunluk -------------------------------------------------------

def test_dogru_adres_ve_baslik_kullaniliyor(monkeypatch):
    """Dokumanda: base https://api.manus.ai , header x-manus-api-key"""
    yakalanan = {}

    def sahte_istek(self, metod, url, **kwargs):
        yakalanan["metod"] = metod
        yakalanan["url"] = url
        yakalanan["basliklar"] = kwargs.get("headers", {})
        yakalanan["json"] = kwargs.get("json")
        return httpx.Response(
            200, json={"ok": True, "task_id": "t1", "request_id": "r1"}
        )

    monkeypatch.setattr(httpx.Client, "request", sahte_istek)
    ManusProvider(api_key=ANAHTAR).gorev_olustur("rakip arastirmasi")

    assert yakalanan["metod"] == "POST"
    assert yakalanan["url"] == f"{BASE_URL}/v2/task.create"
    assert yakalanan["basliklar"][API_KEY_HEADER] == ANAHTAR
    # Dokumanda zorunlu: ust duzey "message", icinde "content"
    assert yakalanan["json"] == {"message": {"content": "rakip arastirmasi"}}


def test_v1_basligi_kullanilmiyor(monkeypatch):
    """v1 header adi API_KEY'dir ve v2 ile karistirilmamali."""
    yakalanan = {}

    def sahte_istek(self, metod, url, **kwargs):
        yakalanan.update(kwargs.get("headers", {}))
        return httpx.Response(200, json={"ok": True, "task_id": "t1"})

    monkeypatch.setattr(httpx.Client, "request", sahte_istek)
    ManusProvider(api_key=ANAHTAR).gorev_olustur("x")

    assert "API_KEY" not in yakalanan
    assert API_KEY_HEADER in yakalanan


def test_bos_metin_reddediliyor():
    with pytest.raises(ManusError) as bilgi:
        ManusProvider(api_key=ANAHTAR).gorev_olustur("   ")
    assert bilgi.value.kod == "invalid_argument"


# --- Hata govdesi ------------------------------------------------------------

def _hata_yaniti(kod: str, http: int = 400):
    def sahte(self, metod, url, **kwargs):
        return httpx.Response(
            http,
            json={"ok": False, "request_id": "r1",
                  "error": {"code": kod, "message": f"{kod} aciklamasi"}},
        )

    return sahte


@pytest.mark.parametrize(
    "kod", ["unauthenticated", "invalid_argument", "not_found",
            "permission_denied", "rate_limited", "internal"],
)
def test_dokumandaki_hata_kodlari_okunuyor(kod, monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _hata_yaniti(kod))
    with pytest.raises(ManusError) as bilgi:
        ManusProvider(api_key=ANAHTAR).gorev_olustur("x")
    assert bilgi.value.kod == kod


def test_yeniden_denenebilir_hatalar_ayirt_ediliyor():
    assert ManusError("rate_limited", "x").yeniden_denenebilir
    assert ManusError("internal", "x").yeniden_denenebilir
    # Bunlar tekrar denenmemeli: istek duzeltilmeli.
    assert not ManusError("invalid_argument", "x").yeniden_denenebilir
    assert not ManusError("unauthenticated", "x").yeniden_denenebilir


def test_json_olmayan_yanit_sessizce_gecmiyor(monkeypatch):
    def sahte(self, metod, url, **kwargs):
        return httpx.Response(502, text="<html>gateway hatasi</html>")

    monkeypatch.setattr(httpx.Client, "request", sahte)
    with pytest.raises(ManusError) as bilgi:
        ManusProvider(api_key=ANAHTAR).gorev_olustur("x")
    assert bilgi.value.kod == "invalid_response"


def test_baglanti_hatasi_acikliyor(monkeypatch):
    def sahte(self, metod, url, **kwargs):
        raise httpx.ConnectError("baglanti yok")

    monkeypatch.setattr(httpx.Client, "request", sahte)
    with pytest.raises(ManusError) as bilgi:
        ManusProvider(api_key=ANAHTAR).gorev_olustur("x")
    assert bilgi.value.kod == "network"


# --- Yasam dongusu -----------------------------------------------------------

def _durum_akisi(monkeypatch, durumlar, mesajlar=None):
    """Sirayla verilen durumlari donduren sahte API."""
    kalan = list(durumlar)

    def sahte(self, metod, url, **kwargs):
        if url.endswith("/v2/task.detail"):
            durum = kalan.pop(0) if kalan else "stopped"
            return httpx.Response(
                200, json={"ok": True, "task": {"status": durum,
                                                "error_message": "gorev coktu"}}
            )
        if url.endswith("/v2/task.listMessages"):
            return httpx.Response(200, json={"ok": True, "messages": mesajlar or []})
        if url.endswith("/v2/task.stop"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True, "task_id": "t1"})

    monkeypatch.setattr(httpx.Client, "request", sahte)
    monkeypatch.setattr(time, "sleep", lambda _s: None)


def test_stopped_durumunda_sonuc_okunuyor(monkeypatch):
    mesajlar = [{"type": "assistant_message", "content": "Bulgu"}]
    _durum_akisi(monkeypatch, ["running", "running", "stopped"], mesajlar)

    sonuc = ManusProvider(api_key=ANAHTAR).sonucu_bekle("t1")
    assert sonuc["messages"] == mesajlar


def test_error_durumunda_hata_mesaji_okunuyor(monkeypatch):
    _durum_akisi(monkeypatch, ["running", "error"])
    with pytest.raises(ManusGorevBasarisiz) as bilgi:
        ManusProvider(api_key=ANAHTAR).sonucu_bekle("t1")
    assert "gorev coktu" in str(bilgi.value)


def test_waiting_durumunda_otomatik_onay_verilmiyor(monkeypatch):
    """Sistem insan onayi olmadan is yapmamali; gorev durduruluyor."""
    _durum_akisi(monkeypatch, ["waiting"])
    with pytest.raises(ManusGorevBasarisiz) as bilgi:
        ManusProvider(api_key=ANAHTAR).sonucu_bekle("t1")
    assert "Otomatik onay verilmedi" in str(bilgi.value)


def test_durum_alani_yoksa_sessizce_gecilmiyor(monkeypatch):
    def sahte(self, metod, url, **kwargs):
        return httpx.Response(200, json={"ok": True, "task": {}})

    monkeypatch.setattr(httpx.Client, "request", sahte)
    with pytest.raises(ManusError) as bilgi:
        ManusProvider(api_key=ANAHTAR)._durum("t1")
    assert bilgi.value.kod == "invalid_response"


# --- Sonuc metni -------------------------------------------------------------

def test_assistant_mesajlari_dogru_sirada_birlestiriliyor():
    """listMessages varsayilani desc; okunabilir sira icin ters cevrilmeli."""
    yanit = {"messages": [
        {"type": "assistant_message", "content": "Ikinci"},
        {"type": "user_message", "content": "Bu alinmamali"},
        {"type": "assistant_message", "content": "Birinci"},
    ]}
    assert ManusProvider.metni_topla(yanit) == "Birinci\n\nIkinci"


def test_content_part_dizisi_de_okunuyor():
    yanit = {"messages": [
        {"type": "assistant_message",
         "content": [{"type": "text", "text": "Parca"},
                     {"type": "image", "url": "x"}]},
    ]}
    assert ManusProvider.metni_topla(yanit) == "Parca"


def test_bos_mesaj_listesi_bos_metin_veriyor():
    assert ManusProvider.metni_topla({"messages": []}) == ""


def test_kredi_kullanimi_okunuyor():
    assert kredi_maliyeti({"task": {"credit_usage": 42}}) == 42
    # Deger yoksa UYDURULMAZ.
    assert kredi_maliyeti({"task": {}}) is None


# --- Webhook imzasi ----------------------------------------------------------

@pytest.fixture
def anahtar_cifti():
    ozel = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    genel_pem = ozel.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return ozel, genel_pem


def _imzala(ozel_anahtar, url: str, govde: bytes, zaman: int) -> str:
    """Dokumandaki bicim: {timestamp}.{url}.{body_sha256_hex}"""
    ozet = hashlib.sha256(govde).hexdigest()
    imzalanan = f"{zaman}.{url}.{ozet}".encode()
    imza = ozel_anahtar.sign(imzalanan, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(imza).decode()


def test_gecerli_imza_kabul_ediliyor(anahtar_cifti):
    ozel, genel = anahtar_cifti
    url = "https://agencycortex.tech/api/v1/webhooks/manus"
    govde = json.dumps({"event": "task_stopped"}).encode()
    zaman = int(time.time())

    imzayi_dogrula(
        public_key_pem=genel, url=url, body=govde,
        signature_b64=_imzala(ozel, url, govde, zaman), timestamp=str(zaman),
    )


def test_govde_degistirilirse_imza_gecersiz(anahtar_cifti):
    """Saldirgan govdeyi degistirirse yakalanmali."""
    ozel, genel = anahtar_cifti
    url = "https://ornek.test/webhook"
    zaman = int(time.time())
    imza = _imzala(ozel, url, b'{"sonuc":"dogru"}', zaman)

    with pytest.raises(WebhookImzaHatasi):
        imzayi_dogrula(
            public_key_pem=genel, url=url, body=b'{"sonuc":"sahte"}',
            signature_b64=imza, timestamp=str(zaman),
        )


def test_url_degistirilirse_imza_gecersiz(anahtar_cifti):
    ozel, genel = anahtar_cifti
    govde = b"{}"
    zaman = int(time.time())
    imza = _imzala(ozel, "https://dogru.test/webhook", govde, zaman)

    with pytest.raises(WebhookImzaHatasi):
        imzayi_dogrula(
            public_key_pem=genel, url="https://sahte.test/webhook", body=govde,
            signature_b64=imza, timestamp=str(zaman),
        )


def test_eski_istek_reddediliyor(anahtar_cifti):
    """Tekrar oynatma (replay) korumasi: 5 dakikalik pencere."""
    ozel, genel = anahtar_cifti
    url = "https://ornek.test/webhook"
    govde = b"{}"
    simdi = int(time.time())
    eski = simdi - ZAMAN_PENCERESI_SANIYE - 1

    with pytest.raises(WebhookImzaHatasi) as bilgi:
        imzayi_dogrula(
            public_key_pem=genel, url=url, body=govde,
            signature_b64=_imzala(ozel, url, govde, eski),
            timestamp=str(eski), simdi=simdi,
        )
    assert "pencere" in str(bilgi.value)


def test_pencere_icindeki_eski_istek_kabul_ediliyor(anahtar_cifti):
    ozel, genel = anahtar_cifti
    url = "https://ornek.test/webhook"
    govde = b"{}"
    simdi = int(time.time())
    biraz_eski = simdi - (ZAMAN_PENCERESI_SANIYE - 10)

    imzayi_dogrula(
        public_key_pem=genel, url=url, body=govde,
        signature_b64=_imzala(ozel, url, govde, biraz_eski),
        timestamp=str(biraz_eski), simdi=simdi,
    )


def test_baska_anahtarla_imzalanmis_istek_reddediliyor(anahtar_cifti):
    """Saldirganin kendi anahtariyla imzalamasi ise yaramamali."""
    _, genel = anahtar_cifti
    saldirgan = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    url = "https://ornek.test/webhook"
    govde = b"{}"
    zaman = int(time.time())

    with pytest.raises(WebhookImzaHatasi):
        imzayi_dogrula(
            public_key_pem=genel, url=url, body=govde,
            signature_b64=_imzala(saldirgan, url, govde, zaman), timestamp=str(zaman),
        )


def test_eksik_baslik_reddediliyor(anahtar_cifti):
    _, genel = anahtar_cifti
    for imza, zaman in [("", "123"), ("abc", "")]:
        with pytest.raises(WebhookImzaHatasi):
            imzayi_dogrula(
                public_key_pem=genel, url="https://x.test", body=b"{}",
                signature_b64=imza, timestamp=zaman,
            )


def test_bozuk_zaman_damgasi_reddediliyor(anahtar_cifti):
    _, genel = anahtar_cifti
    with pytest.raises(WebhookImzaHatasi):
        imzayi_dogrula(
            public_key_pem=genel, url="https://x.test", body=b"{}",
            signature_b64="abc", timestamp="zaman-degil",
        )


# --- Webhook olaylari --------------------------------------------------------

def test_finish_olayi_sonuc_hazir_diyor():
    cozum = olayi_coz({"event": "task_stopped", "stop_reason": "finish",
                       "task_id": "t1"})
    assert cozum["sonuc_hazir"] is True
    assert cozum["girdi_bekliyor"] is False


def test_ask_olayi_girdi_bekliyor_diyor():
    cozum = olayi_coz({"event": "task_stopped", "stop_reason": "ask"})
    assert cozum["sonuc_hazir"] is False
    assert cozum["girdi_bekliyor"] is True


def test_task_created_olayi_sonuc_degil():
    cozum = olayi_coz({"event": "task_created", "task_id": "t1"})
    assert cozum["sonuc_hazir"] is False
    assert cozum["girdi_bekliyor"] is False


# --- Kredi korumasi ---------------------------------------------------------

def test_kredi_bitmisse_gorev_baslatilmiyor(monkeypatch):
    """USD butcesi krediyi olcemez; sinir burada uygulanir."""
    from app.ai.base import AIRequest
    from app.ai.manus import ManusKrediYetersiz, ManusProvider

    saglayici = ManusProvider(api_key="sk-test-anahtar")
    cagrilan: list[str] = []

    def sahte_istek(self, yontem, uc, **kw):
        cagrilan.append(uc)
        if uc == "/v2/usage.availableCredits":
            return {"total_credits": 0, "free_credits": 0}
        raise AssertionError(f"Kredi bitmisken cagrilmamaliydi: {uc}")

    monkeypatch.setattr(ManusProvider, "_istek", sahte_istek)

    with pytest.raises(ManusKrediYetersiz) as hata:
        saglayici.complete(AIRequest(
            task_type="trend_research", prompt_version="v1",
            system="sistem", user_content="icerik",
        ))

    assert "krediniz bitmiş" in str(hata.value)
    # Gorev olusturma ucu HIC cagrilmamali.
    assert cagrilan == ["/v2/usage.availableCredits"]


def test_kredi_okunamazsa_cagri_engellenmiyor(monkeypatch):
    """Okunamayan bir degere bakip calisacak isi iptal etmek yanlis olur."""
    from app.ai.base import AIRequest
    from app.ai.manus import ManusError, ManusProvider

    saglayici = ManusProvider(api_key="sk-test-anahtar")
    cagrilan: list[str] = []

    def sahte_istek(self, yontem, uc, **kw):
        cagrilan.append(uc)
        if uc == "/v2/usage.availableCredits":
            raise ManusError("network", "baglanti yok")
        if uc == "/v2/task.create":
            return {"task_id": "t1"}
        if uc == "/v2/task.detail":
            return {"task": {"status": "stopped", "stop_reason": "finish"}}
        if uc == "/v2/task.listMessages":
            return {"messages": [
                {"type": "assistant_message", "content": "sonuc"}
            ]}
        raise AssertionError(uc)

    monkeypatch.setattr(ManusProvider, "_istek", sahte_istek)

    yanit = saglayici.complete(AIRequest(
        task_type="trend_research", prompt_version="v1",
        system="sistem", user_content="icerik",
    ))
    assert yanit.status.value == "succeeded"
    assert "/v2/task.create" in cagrilan


def test_kredi_varsa_cagri_yapiliyor(monkeypatch):
    from app.ai.base import AIRequest
    from app.ai.manus import ManusProvider

    saglayici = ManusProvider(api_key="sk-test-anahtar")

    def sahte_istek(self, yontem, uc, **kw):
        if uc == "/v2/usage.availableCredits":
            return {"total_credits": 500}
        if uc == "/v2/task.create":
            return {"task_id": "t2"}
        if uc == "/v2/task.detail":
            return {"task": {"status": "stopped", "stop_reason": "finish"}}
        if uc == "/v2/task.listMessages":
            return {"messages": [
                {"type": "assistant_message", "content": "arastirma sonucu"}
            ]}
        raise AssertionError(uc)

    monkeypatch.setattr(ManusProvider, "_istek", sahte_istek)

    yanit = saglayici.complete(AIRequest(
        task_type="trend_research", prompt_version="v1",
        system="sistem", user_content="icerik",
    ))
    assert "arastirma sonucu" in yanit.text
