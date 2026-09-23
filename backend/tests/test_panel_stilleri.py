"""Panel sablonlarindaki CSS siniflari gercekten tanimli mi?

NEDEN BU TEST VAR
-----------------
`base.html` bastan yazildiginda 19 sinif adi (`sayfa-ust`, `sub`, `lock`,
`kutular`, `kod` ...) stil tanimi olmadan kaldi. Sayfalar HTTP 200
donuyordu, testler geciyordu; ama ekranda basliklar hizasiz, kutular
duz metin halindeydi. "Sayfa aciliyor" ile "sayfa dogru gorunuyor"
ayni sey degildir.

Bu test, bir sablonun kullandigi her sinifin ya `base.html` icinde ya da
o sayfanin kendi `<style>` blogunda tanimli oldugunu dogrular.
"""

from __future__ import annotations

import re
from pathlib import Path

SABLON_DIZINI = Path(__file__).resolve().parents[1] / "app" / "panel" / "templates"

# Jinja ifadesi iceren sinif degerleri de ayristirilir: `class="kutu {% if x %}kotu{% endif %}"`
# icinden `kutu` ve `kotu` cikarilir. Jinja anahtar sozcukleri sinif degildir.
JINJA_SOZCUKLERI = frozenset({
    "if", "else", "elif", "endif", "for", "endfor", "not", "and", "or", "in", "is",
})


def _siniflar(metin: str) -> set[str]:
    """Bir sablondaki `class="..."` degerlerinden sinif adlarini cikarir."""
    bulunan: set[str] = set()
    for deger in re.findall(r'class="([^"]*)"', metin):
        # Jinja ifadelerinin icindeki degiskenler ({{ ... }}) sinif adi degil,
        # uretilen degerdir; atilir. Kontrol blogunun ({% ... %}) icindeki
        # duz sozcukler ise sinif adi olabilir.
        deger = re.sub(r"\{\{.*?\}\}", " ", deger)
        deger = re.sub(r"[{}%]", " ", deger)
        for parca in deger.split():
            if parca in JINJA_SOZCUKLERI:
                continue
            # `b-{{ s.status.value }}` gibi dinamik sinifta geriye `b-` on eki
            # kalir. Sonu tire ile biten parca bir sinif adi degil, on ektir;
            # bu durumda goruntuyu tasiyan taban sinif (`badge`) zaten ayrica
            # yaziliyor ve bilinmeyen durumlar notr rozet olarak cizilir.
            if parca.endswith("-"):
                continue
            if re.fullmatch(r"[a-z][a-z0-9-]*", parca):
                bulunan.add(parca)
    return bulunan


def _tanimli_siniflar(metin: str) -> set[str]:
    """Bir `<style>` blogunda tanimlanan sinif adlari."""
    return set(re.findall(r"\.([a-z][a-z0-9-]*)", metin))


def test_kullanilan_her_sinifin_stili_var():
    base = (SABLON_DIZINI / "base.html").read_text(encoding="utf-8")
    ortak = _tanimli_siniflar(base)

    eksikler: dict[str, set[str]] = {}
    for yol in sorted(SABLON_DIZINI.glob("*.html")):
        metin = yol.read_text(encoding="utf-8")
        # Sayfanin kendi stil blogu da gecerli bir tanim yeridir.
        tanimli = ortak | _tanimli_siniflar(metin)
        eksik = _siniflar(metin) - tanimli
        if eksik:
            eksikler[yol.name] = eksik

    assert not eksikler, (
        "Su siniflarin hicbir yerde stil tanimi yok; sayfa acilir ama "
        f"bicimsiz gorunur: {eksikler}"
    )


def test_kullanilan_her_css_degiskeni_tanimli():
    """`var(--x)` yazip `--x`i tanimlamayi unutmak sessizce bosluk birakir."""
    base = (SABLON_DIZINI / "base.html").read_text(encoding="utf-8")
    tanimli = set(re.findall(r"(--[a-z0-9-]+)\s*:", base))

    eksikler: dict[str, set[str]] = {}
    for yol in sorted(SABLON_DIZINI.glob("*.html")):
        metin = yol.read_text(encoding="utf-8")
        kullanilan = set(re.findall(r"var\((--[a-z0-9-]+)\)", metin))
        eksik = kullanilan - tanimli - set(re.findall(r"(--[a-z0-9-]+)\s*:", metin))
        if eksik:
            eksikler[yol.name] = eksik

    assert not eksikler, f"Tanimsiz CSS degiskenleri: {eksikler}"
