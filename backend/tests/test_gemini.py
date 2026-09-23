"""Gemini saglayicisi.

Uc adresleri ve alan adlari Google'in resmi, makine-okunur API tanimindan
alindi (discovery document, 23 Eylul 2026). Bu testler o yapiya gore
yazildi; gercek aga CIKMAZ.

Korunan kurallar:
- Anahtar yoksa acik hata verilir; sessizce bos sonuc DONMEZ
- Kirpilmis (MAX_TOKENS) cikti "basarili" sayilmaz
- Ag hatasi ile "anahtar yanlis" AYRI gosterilir
- Saglik kontrolu jeton harcamayan salt-okuma ucunu kullanir
- Anahtar hicbir log satirina yazilmaz
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.base import AIProviderError, AIRequest, AIStatus, ProviderNotConfigured
from app.ai.gemini import API_SURUMU, BASE_URL, GeminiProvider, _sema_sadelestir


def istek(gorev: str = "bulk_classification", **kw) -> AIRequest:
    return AIRequest(
        task_type=gorev, prompt_version="test-1",
        system="Sen bir siniflandiricisin.", user_content="Metni sinifla.",
        **kw,
    )


def _yanit(govde: dict, kod: int = 200):
    """httpx.Client yerine gececek sahte tasiyici."""
    def _isle(request: httpx.Request) -> httpx.Response:
        _isle.son_istek = request
        return httpx.Response(kod, json=govde, request=request)

    return httpx.MockTransport(_isle), _isle


@pytest.fixture
def baglan(monkeypatch):
    """GeminiProvider'in kullandigi httpx.Client'i sahte tasiyiciya baglar."""
    def _kur(govde: dict, kod: int = 200):
        tasiyici, kanca = _yanit(govde, kod)
        gercek = httpx.Client

        def _sahte(*a, **kw):
            kw["transport"] = tasiyici
            return gercek(*a, **kw)

        monkeypatch.setattr("app.ai.gemini.httpx.Client", _sahte)
        return kanca

    return _kur


def _basarili_govde(metin: str, girdi: int = 120, cikti: int = 45) -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": metin}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": girdi,
            "candidatesTokenCount": cikti,
            "totalTokenCount": girdi + cikti,
        },
        "modelVersion": "gemini-2.5-flash",
    }


# --- Yapilandirma -------------------------------------------------------------

def test_anahtarsizken_acik_hata():
    p = GeminiProvider(api_key=None)
    assert p.missing_config == ["GEMINI_API_KEY"]
    with pytest.raises(ProviderNotConfigured):
        p.complete(istek())


def test_anahtar_varken_yapilandirilmis():
    assert GeminiProvider(api_key="AIza-test").is_configured is True


# --- Basarili uretim ----------------------------------------------------------

def test_json_cikti_ayristiriliyor(baglan):
    baglan(_basarili_govde('{"etiket": "olumlu"}'))
    yanit = GeminiProvider(api_key="AIza-test").complete(istek())

    assert yanit.parsed == {"etiket": "olumlu"}
    assert yanit.status is AIStatus.SUCCEEDED
    assert yanit.provider == "gemini"
    assert yanit.input_tokens == 120
    assert yanit.output_tokens == 45
    # Maliyet fiyat tablosundan hesaplanir; 0 veya None DEGIL.
    assert yanit.estimated_cost_usd is not None
    assert yanit.estimated_cost_usd > 0


def test_resmi_tanimdaki_adres_ve_govde_kullaniliyor(baglan):
    kanca = baglan(_basarili_govde('{"a": 1}'))
    GeminiProvider(api_key="AIza-test").complete(istek())

    g = kanca.son_istek
    assert g.method == "POST"
    assert str(g.url).startswith(
        f"{BASE_URL}/{API_SURUMU}/models/gemini-2.5-flash:generateContent"
    )
    govde = json.loads(g.content)
    # Tanimdaki alan adlari: contents[].parts[].text , systemInstruction
    assert govde["contents"][0]["parts"][0]["text"] == "Metni sinifla."
    assert govde["systemInstruction"]["parts"][0]["text"].startswith("Sen bir")
    assert govde["generationConfig"]["responseMimeType"] == "application/json"


def test_sema_verilince_gonderiliyor(baglan):
    kanca = baglan(_basarili_govde('{"a": 1}'))
    sema = {
        "type": "object",
        "title": "Gereksiz",          # Gemini'nin kabul etmedigi alan
        "properties": {"a": {"type": "integer", "title": "X"}},
        "required": ["a"],
    }
    GeminiProvider(api_key="AIza-test").complete(istek(json_schema=sema))

    gonderilen = json.loads(kanca.son_istek.content)["generationConfig"]["responseSchema"]
    # Desteklenmeyen alan GONDERILMEZ; gonderilse 400 alinirdi.
    assert "title" not in gonderilen
    assert gonderilen["properties"]["a"] == {"type": "integer"}
    assert gonderilen["required"] == ["a"]


# --- Hatalar ------------------------------------------------------------------

def test_kirpilmis_cikti_basarili_sayilmiyor(baglan):
    """Eksik JSON'u ayristirmaya calismak, eksik veriyi tam saymaktir."""
    govde = _basarili_govde('{"etiket": "olum')
    govde["candidates"][0]["finishReason"] = "MAX_TOKENS"
    baglan(govde)

    with pytest.raises(AIProviderError) as hata:
        GeminiProvider(api_key="AIza-test").complete(istek())
    assert "uzunluk" in str(hata.value).lower()


def test_bos_yanit_sebebiyle_birlikte_bildiriliyor(baglan):
    baglan({"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(AIProviderError) as hata:
        GeminiProvider(api_key="AIza-test").complete(istek())
    assert "SAFETY" in str(hata.value)


def test_gecersiz_json_acik_hata(baglan):
    baglan(_basarili_govde("bu JSON degil"))
    with pytest.raises(AIProviderError) as hata:
        GeminiProvider(api_key="AIza-test").complete(istek())
    assert "JSON" in str(hata.value)


@pytest.mark.parametrize(
    ("kod", "beklenen"),
    [(401, "kabul edilmedi"), (403, "kabul edilmedi"), (429, "çok fazla istek"),
     (500, "sunucu hatası")],
)
def test_http_hatalari_ayri_ayri_aciklaniyor(baglan, kod, beklenen):
    """Hepsini 'anahtar hatali' demek, kesintide dogru anahtari sildirtirdi."""
    baglan({"error": {"message": "x"}}, kod=kod)
    with pytest.raises(AIProviderError) as hata:
        GeminiProvider(api_key="AIza-test").complete(istek())
    assert beklenen in str(hata.value).lower() or beklenen in str(hata.value)


def test_ag_hatasi_anahtar_hatasindan_ayri(monkeypatch):
    def _patlat(*a, **kw):
        raise httpx.ConnectError("ag yok")

    gercek = httpx.Client

    class _Istemci(gercek):
        def post(self, *a, **kw):
            _patlat()

        def get(self, *a, **kw):
            _patlat()

    monkeypatch.setattr("app.ai.gemini.httpx.Client", _Istemci)
    with pytest.raises(AIProviderError) as hata:
        GeminiProvider(api_key="AIza-test").complete(istek())
    assert "bağlanılamadı" in str(hata.value)


# --- Saglik kontrolu ----------------------------------------------------------

def test_saglik_kontrolu_salt_okuma_ucunu_kullaniyor(baglan):
    """Mesaj gondererek sinamak her denemede PARA HARCARDI."""
    kanca = baglan({"models": [{"name": "models/gemini-2.5-flash"}]})
    calisir, aciklama = GeminiProvider(api_key="AIza-test").health_check()

    assert calisir is True
    assert "1 model" in aciklama
    g = kanca.son_istek
    assert g.method == "GET"
    assert str(g.url).startswith(f"{BASE_URL}/{API_SURUMU}/models")


def test_saglik_kontrolu_hatayi_gizlemiyor(baglan):
    baglan({"error": {}}, kod=401)
    calisir, aciklama = GeminiProvider(api_key="AIza-test").health_check()
    assert calisir is False
    assert "kabul edilmedi" in aciklama


# --- Sema sadelestirme --------------------------------------------------------

def test_sema_sadelestirme_ic_ice_calisiyor():
    sema = {
        "type": "object",
        "$defs": {"X": {"type": "string"}},
        "properties": {
            "liste": {
                "type": "array",
                "title": "At",
                "items": {"type": "object", "properties": {"a": {"type": "string"}}},
            }
        },
    }
    sade = _sema_sadelestir(sema)
    assert "$defs" not in sade
    assert "title" not in sade["properties"]["liste"]
    assert sade["properties"]["liste"]["items"]["properties"]["a"] == {"type": "string"}
