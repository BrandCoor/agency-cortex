"""Sunucuya gonderilen n8n is akisi dosyalari.

Bu dosyalar n8n'e oldugu gibi yuklenir. Icindeki bir yazim hatasi
uretimde, akis calismadigi anda anlasilirdi - ve sessizce.

Kontrol edilenler:
- Dosya gecerli JSON mu
- Cagirdigi is akisi Agency Cortex'te GERCEKTEN tanimli mi
- Kurulum betigindeki kimlikler dosyalarla ayni mi
- Cagri IC AGA gidiyor mu (internete cikmamali)
- Kimlik bilgisi ADI geciyor, anahtarin KENDISI dosyada YOK
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.is_akislari import AKISLAR
from app.services.otomasyon import IS_AKISI_ANAHTARLARI

KOK = Path(__file__).resolve().parents[2]
AKIS_DIZINI = KOK / "ops" / "n8n" / "akislar"
KURULUM_BETIGI = KOK / "ops" / "n8n_kur.sh"


def _dosyalar() -> list[Path]:
    return sorted(AKIS_DIZINI.glob("*.json"))


def test_akis_dosyalari_mevcut():
    assert AKIS_DIZINI.is_dir(), f"Akis dizini yok: {AKIS_DIZINI}"
    # Sayi SABIT YAZILMAZ: katalogdan turetilir. Sabit yazilsaydi yeni bir
    # akis eklendiginde bu test, gercek bir sorun olmadigi halde duserdi.
    from app.services.otomasyon import IS_AKISLARI

    assert len(_dosyalar()) == len(IS_AKISLARI), (
        f"Her is akisi icin bir n8n dosyasi olmali. "
        f"Katalog: {len(IS_AKISLARI)}, dosya: {len(_dosyalar())}"
    )


@pytest.mark.parametrize("yol", _dosyalar(), ids=lambda p: p.name)
def test_dosya_gecerli_ve_tutarli(yol: Path):
    akis = json.loads(yol.read_text(encoding="utf-8"))

    assert akis["id"] == yol.stem
    assert akis["name"]
    # Kurulum betigi yayinlayana kadar etkin OLMAMALI.
    assert akis["active"] is False

    dugumler = {d["name"]: d for d in akis["nodes"]}
    assert len(dugumler) == 2, "Akis iki dugumden olusmali (zamanlayici + cagri)."

    zaman = dugumler["Zamanlayici"]
    assert zaman["type"] == "n8n-nodes-base.scheduleTrigger"
    aralik = zaman["parameters"]["rule"]["interval"][0]
    assert aralik["field"] == "cronExpression"
    # Cron bes alanli olmali.
    assert len(aralik["expression"].split()) == 5, aralik["expression"]

    cagri = dugumler["Agency Cortex'e calistir"]
    assert cagri["type"] == "n8n-nodes-base.httpRequest"
    assert cagri["parameters"]["method"] == "POST"
    # Gecici ag hatasi akisi bitirmemeli.
    assert cagri["retryOnFail"] is True

    # Baglanti dugumleri gercekten var olan dugumleri gostermeli.
    for kaynak, baglanti in akis["connections"].items():
        assert kaynak in dugumler
        for grup in baglanti["main"]:
            for hedef in grup:
                assert hedef["node"] in dugumler


@pytest.mark.parametrize("yol", _dosyalar(), ids=lambda p: p.name)
def test_cagrilan_akis_cortexte_tanimli(yol: Path):
    """Dosyadaki anahtar Cortex'te yoksa akis her calismada 409 alirdi."""
    akis = json.loads(yol.read_text(encoding="utf-8"))
    url = next(
        d["parameters"]["url"] for d in akis["nodes"]
        if d["type"] == "n8n-nodes-base.httpRequest"
    )

    # .../makine/akis/<anahtar>/calistir-hepsi
    parcalar = url.rstrip("/").split("/")
    assert parcalar[-1] == "calistir-hepsi"
    anahtar = parcalar[-2]

    assert anahtar in IS_AKISI_ANAHTARLARI, f"Tanimsiz akis anahtari: {anahtar}"
    assert anahtar in AKISLAR, f"Akisin calistirici islevi yok: {anahtar}"


@pytest.mark.parametrize("yol", _dosyalar(), ids=lambda p: p.name)
def test_cagri_ic_agda_kaliyor(yol: Path):
    """n8n, Agency Cortex'e IC AGDAN ulasir; bu istek internete cikmaz."""
    akis = json.loads(yol.read_text(encoding="utf-8"))
    url = next(
        d["parameters"]["url"] for d in akis["nodes"]
        if d["type"] == "n8n-nodes-base.httpRequest"
    )
    assert url.startswith("http://api:8000/"), url


@pytest.mark.parametrize("yol", _dosyalar(), ids=lambda p: p.name)
def test_anahtar_dosyada_yok(yol: Path):
    """Dosyalar Git'te duruyor; icinde gizli bir deger olmamali."""
    metin = yol.read_text(encoding="utf-8")
    assert "acx_" not in metin
    assert "sk-" not in metin

    akis = json.loads(metin)
    cagri = next(
        d for d in akis["nodes"] if d["type"] == "n8n-nodes-base.httpRequest"
    )
    # Anahtar, n8n'in sifreli kimlik bilgisinden gelir.
    assert cagri["parameters"]["authentication"] == "genericCredentialType"
    assert cagri["parameters"]["genericAuthType"] == "httpHeaderAuth"
    assert cagri["credentials"]["httpHeaderAuth"]["id"] == "agency-cortex-api"


def test_kurulum_betigi_dosyalarla_ayni_kimlikleri_kullaniyor():
    """Betikteki liste ile dosyalar ayrilirsa akislar yayinlanmaz."""
    betik = KURULUM_BETIGI.read_text(encoding="utf-8")

    satir = next(
        s for s in betik.splitlines() if s.startswith("AKIS_IDLERI=")
    )
    betikteki = set(satir.split("=", 1)[1].strip('"').split())
    dosyadaki = {y.stem for y in _dosyalar()}

    assert betikteki == dosyadaki, (
        f"Betik {betikteki}, dosyalar {dosyadaki}"
    )
    assert 'KIMLIK_ID="agency-cortex-api"' in betik


def test_kurulum_isareti_akis_listesini_tutuyor():
    """Yeni akis eklendiginde kurulum TEKRAR calismali.

    Isaret dosyasi yalnizca "kuruldu mu" bilgisini tutsaydi, WF-05 gibi
    sonradan eklenen bir akis hic kurulmazdi: betik "zaten kurulu" deyip
    atlardi.
    """
    betik = KURULUM_BETIGI.read_text(encoding="utf-8")

    # Beklenen liste isaret dosyasiyla KARSILASTIRILMALI.
    assert "BEKLENEN=" in betik
    assert 'cat "$ISARET"' in betik
    # Ve kurulum bitince liste YAZILMALI (bos bir dokunus degil).
    assert 'printf \'%s\' "$BEKLENEN" > "$ISARET"' in betik
    assert "touch \"$ISARET\"" not in betik
