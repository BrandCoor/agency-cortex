FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Saglik kontrolu icin curl, psycopg icin gerekli kutuphaneler
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# DIKKAT: `app` klasoru pip install'den ONCE kopyalanmalidir.
# pyproject.toml paketleri "app*" kalibiyla ariyor; klasor yoksa kurulum
# "package directory 'app' does not exist" hatasi verir.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .
COPY alembic.ini ./
COPY alembic ./alembic

# Uygulama root olarak calismaz
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
