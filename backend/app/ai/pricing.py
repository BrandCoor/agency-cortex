"""Model fiyatlari ve maliyet hesabi.

KAYNAK: Anthropic resmi fiyat listesi (skill onbellegi: 2026-06-24).
Fiyatlar degisebilir; bu tablo guncel tutulmalidir.

NEDEN BURADA: Maliyet hesabi tek bir yerde olmali. Her musteri icin aylik
butce siniri bu hesaba dayanir; iki farkli yerde hesaplanirsa butce kontrolu
guvenilmez olur.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Fiyat tablosunun alindigi tarih. Guncellenirse burasi da degismelidir.
PRICING_AS_OF = "2026-06-24"


@dataclass(frozen=True)
class ModelPricing:
    """1 milyon token basina USD fiyat."""

    input_per_million: Decimal
    output_per_million: Decimal


# Yalnizca kullandigimiz modeller. Bilinmeyen model maliyeti TAHMIN EDILMEZ.
MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-opus-5": ModelPricing(Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-5": ModelPricing(Decimal("2.00"), Decimal("10.00")),
    "claude-haiku-4-5": ModelPricing(Decimal("1.00"), Decimal("5.00")),
}

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
