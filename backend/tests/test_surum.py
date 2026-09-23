"""Surum numarasi tek kaynaktan gelir.

Surum uc ayri yerde elle yaziliyordu ve birlikte guncellenmedigi icin
sunucudaki sistem CHANGELOG 0.16.1'deyken `/version` ucunda "0.1.0"
diyordu. "Sunucuda hangi surum calisiyor?" sorusunun yanlis
cevaplanmasi, bir hatayi ararken en cok zaman kaybettiren seydir.
"""

from __future__ import annotations

import re
from pathlib import Path

from app import __version__

KOK = Path(__file__).resolve().parents[1]


def test_pyproject_ile_paket_surumu_ayni():
    metin = (KOK / "pyproject.toml").read_text(encoding="utf-8")
    eslesme = re.search(r'^version\s*=\s*"([^"]+)"', metin, re.MULTILINE)
    assert eslesme, "pyproject.toml icinde surum satiri bulunamadi."
    assert eslesme.group(1) == __version__, (
        f"pyproject.toml {eslesme.group(1)} diyor, app/__init__.py {__version__}. "
        "Ikisi ayri dusemez."
    )


def test_changelog_en_ust_surum_paketle_ayni():
    """CHANGELOG'un en ustteki surumu, calisan surum olmalidir."""
    metin = (KOK.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    surumler = re.findall(r"^## \[([0-9]+\.[0-9]+\.[0-9]+)\]", metin, re.MULTILINE)
    assert surumler, "CHANGELOG.md icinde surum basligi bulunamadi."
    assert surumler[-1] == __version__, (
        f"CHANGELOG'un son girdisi {surumler[-1]}, paket surumu {__version__}. "
        "Yeni bir surum yazildiysa app/__init__.py de guncellenmeli."
    )
