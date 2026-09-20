from __future__ import annotations

import os

# Testler gercek bir sunucuya baglanmamali; ayarlar test degerleriyle sabitlenir.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("REDIS_HOST", "localhost")
