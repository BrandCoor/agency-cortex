"""Model fiyatlari ve maliyet hesabi.

KAYNAKLAR:
- Anthropic: resmi fiyat listesi (skill onbellegi)
- Google Gemini: ai.google.dev/gemini-api/docs/pricing , 21 Eylul 2026
Fiyatlar degisebilir; bu tablo guncel tutulmalidir.

NEDEN BURADA: Maliyet hesabi tek bir yerde olmali. Her musteri icin aylik
butce siniri bu hesaba dayanir; iki farkli yerde hesaplanirsa butce kontrolu
guvenilmez olur.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Fiyat tablosunun alindigi tarih. Guncellenirse burasi da degismelidir.
PRICING_AS_OF = "2026-09-21"


@dataclass(frozen=True)
class ModelPricing:
    """1 milyon token basina USD fiyat."""

    input_per_million: Decimal
    output_per_million: Decimal


# Yalnizca kullandigimiz modeller. Bilinmeyen model maliyeti TAHMIN EDILMEZ.
#
# Gemini fiyatlari: ai.google.dev/gemini-api/docs/pricing (Standard tablosu),
# 21 Eylul 2026'da okundu.
#
# DIKKAT - ZAMANA BAGLI FIYAT: Gemini 3.8 / 3.7 / 3.6 Flash icin doküman iki
# fiyat veriyor: 31 Aralik 2026'ya kadar $0.75/$3.75 , 1 Ocak 2027'den sonra
# $1.50/$7.50 . Burada YUKSEK olan (2027 sonrasi) fiyat yazildi. Gerekce:
# butce kilidi icin maliyeti olduğundan dusuk gostermek, butcenin sessizce
# asilmasina yol acar. Dusuk gosterip asmaktansa yuksek gosterip erken
# uyarmak tercih edildi. Bu bir URUN KARARIDIR, doküman degeri degildir.
MODEL_PRICING: dict[str, ModelPricing] = {
    # --- Anthropic ---
    "claude-opus-5": ModelPricing(Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-5": ModelPricing(Decimal("2.00"), Decimal("10.00")),
    "claude-haiku-4-5": ModelPricing(Decimal("1.00"), Decimal("5.00")),
    # --- Google Gemini (Standard, paid tier) ---
    "gemini-3.8-flash": ModelPricing(Decimal("1.50"), Decimal("7.50")),
    "gemini-3.7-flash": ModelPricing(Decimal("1.50"), Decimal("7.50")),
    "gemini-3.6-flash": ModelPricing(Decimal("1.50"), Decimal("7.50")),
    "gemini-3.5-flash": ModelPricing(Decimal("1.50"), Decimal("9.00")),
    "gemini-3.5-flash-lite": ModelPricing(Decimal("0.30"), Decimal("2.50")),
    "gemini-3.1-flash-lite": ModelPricing(Decimal("0.25"), Decimal("1.50")),
    "gemini-2.5-flash": ModelPricing(Decimal("0.30"), Decimal("2.50")),
    "gemini-2.5-flash-lite": ModelPricing(Decimal("0.10"), Decimal("0.40")),
    # gemini-2.5-pro ve gemini-3.1-pro-preview istem uzunluguna gore iki
    # farkli fiyat uygular (<=200k / >200k). Tek fiyatla temsil edilemezler;
    # bu yuzden BILEREK eklenmediler. Kullanilmak istenirse once bu tablonun
    # istem uzunlugunu da hesaba katacak sekilde genisletilmesi gerekir.
}

# Fiyati istem uzunluguna gore degisen ve bu tabloya sigmayan modeller.
# Listelenmelerinin sebebi: "unutuldu mu?" sorusunu ortadan kaldirmak.
KADEMELI_FIYATLI_MODELLER = frozenset({
    "gemini-2.5-pro",
    "gemini-3.1-pro-preview",
})

# Gelistirme ve testte kullanilan sahte saglayici bedava kabul edilir.
FAKE_MODEL = "fake-model-v1"


class UnknownModelPricing(Exception):
    """Fiyati bilinmeyen model icin maliyet hesaplanamaz.

    Tahmini bir fiyat uydurmak, butce kontrolunu sessizce bozar.
    """

    def __init__(self, model: str) -> None:
        super().__init__(
            f"'{model}' modelinin fiyati tanimli degil. "
            "Maliyet tahmin edilemez; fiyat tablosuna eklenmelidir."
        )
        self.model = model


def estimate_cost(
    model: str, *, input_tokens: int | None, output_tokens: int | None
) -> Decimal | None:
    """Bir cagrinin tahmini maliyetini hesaplar (USD).

    Token sayisi bilinmiyorsa None doner - 0 DONMEZ. Bilinmeyen maliyeti
    sifir saymak, butce siniri asilsa bile sistemin calismaya devam etmesine
    yol acardi.
    """
    if model == FAKE_MODEL:
        return Decimal("0")

    fiyat = MODEL_PRICING.get(model)
    if fiyat is None:
        raise UnknownModelPricing(model)

    if input_tokens is None or output_tokens is None:
        return None

    milyon = Decimal("1000000")
    return (
        Decimal(input_tokens) / milyon * fiyat.input_per_million
        + Decimal(output_tokens) / milyon * fiyat.output_per_million
    )
