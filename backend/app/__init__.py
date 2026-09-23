"""Agency Cortex.

Surum numarasi BURADA tanimlanir ve tek kaynaktir.

NEDEN: Surum uc ayri yerde (main.py, health.py, pyproject.toml) elle
yaziliydi ve uclu birlikte guncellenmedigi icin sunucudaki sistem
CHANGELOG 0.16.1'deyken `/version` ucunda hala "0.1.0" diyordu.
"Sunucuda hangi surum calisiyor?" sorusunun yanlis cevaplanmasi,
bir hatayi ararken en cok zaman kaybettiren seydir.

`tests/test_surum.py` bu dosya ile `pyproject.toml` arasindaki farki
yakalar; ikisi ayri dusemez.
"""

__version__ = "0.16.1"
