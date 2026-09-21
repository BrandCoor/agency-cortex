#!/usr/bin/env bash
#
# En son yedegin GERCEKTEN geri yuklenebildigini dogrular.
#
# NEDEN GEREKLI:
# Geri yuklenmemis bir yedek, yedek degildir. Bozuk bir dump dosyasi
# felaket anina kadar fark edilmez. Bu betik yedegi AYRI ve GECICI bir
# veritabanina geri yukler, icindekileri sayar ve sonra o veritabanini siler.
# Uretim veritabanina HIC DOKUNMAZ.
#
set -euo pipefail

DIZIN="${DIZIN:-/opt/agency-cortex}"
YEDEK_DIZINI="${YEDEK_DIZINI:-$DIZIN/yedek}"
DENEME_DB="yedek_dogrulama_gecici"

cd "$DIZIN"
# .env'den TEK BIR degeri guvenle okur.
#
# NEDEN "set -a; . ./.env" DEGIL:
# O yontem .env dosyasini KABUKLA CALISTIRIR. Bosluk iceren bir deger
# (APP_NAME=Agency Cortex) "Cortex: command not found" hatasi verir; daha
# kotusu, dosyaya girmis herhangi bir komut CALISIR. .env yalnizca
# okunmalidir, calistirilmamalidir.
env_oku() {
  local ad="$1" satir deger
  satir=$(grep -E "^[[:space:]]*${ad}=" "$DIZIN/.env" | tail -1 || true)
  [ -n "$satir" ] || return 1
  deger="${satir#*=}"
  # Bastaki/sondaki tirnaklari ve bosluklari temizle
  deger="${deger#"${deger%%[![:space:]]*}"}"
  deger="${deger%"${deger##*[![:space:]]}"}"
  case "$deger" in
    \"*\") deger="${deger#\"}"; deger="${deger%\"}" ;;
    \'*\') deger="${deger#\'}"; deger="${deger%\'}" ;;
  esac
  printf '%s' "$deger"
}

POSTGRES_DB=$(env_oku POSTGRES_DB) || { echo "HATA: POSTGRES_DB .env icinde yok." >&2; exit 1; }
POSTGRES_USER=$(env_oku POSTGRES_USER) || { echo "HATA: POSTGRES_USER .env icinde yok." >&2; exit 1; }

son=$(ls -1t "$YEDEK_DIZINI"/agency-cortex-*.dump 2>/dev/null | head -1 || true)
if [ -z "$son" ]; then
  echo "HATA: dogrulanacak yedek bulunamadi." >&2
  exit 1
fi
echo "[$(date -Is)] dogrulanan yedek: $(basename "$son")"

# GUVENLIK: gecici veritabaninin adi uretim veritabaniyla ayni olamaz.
if [ "$DENEME_DB" = "$POSTGRES_DB" ]; then
  echo "HATA: gecici veritabani adi uretim adiyla ayni. Durduruldu." >&2
  exit 1
fi

temizle() {
  docker compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $DENEME_DB" >/dev/null 2>&1 || true
}
trap temizle EXIT

temizle
docker compose exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE $DENEME_DB" >/dev/null

# pg_restore uyarilari (sahiplik vb.) hata sayilmaz; asil olcut sonraki sayim.
docker compose exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$DENEME_DB" --no-owner --no-privileges \
  < "$son" >/dev/null 2>/tmp/geri_yukleme.log || true

tablo_sayisi=$(docker compose exec -T postgres psql -U "$POSTGRES_USER" \
  -d "$DENEME_DB" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" | tr -d '[:space:]')

echo "[$(date -Is)] geri yuklenen tablo sayisi: $tablo_sayisi"

# Sema 28 tablo iceriyor. Cok daha azi, yedegin eksik oldugunu gosterir.
EN_AZ_TABLO="${EN_AZ_TABLO:-20}"
if [ "${tablo_sayisi:-0}" -lt "$EN_AZ_TABLO" ]; then
  echo "HATA: beklenen en az $EN_AZ_TABLO tablo, bulunan $tablo_sayisi." >&2
  echo "--- geri yukleme kaydi ---" >&2
  tail -20 /tmp/geri_yukleme.log >&2 || true
  exit 1
fi

# Kullanici tablosu okunabiliyor mu? (Sema var ama veri okunamiyor olabilir.)
kullanici_sayisi=$(docker compose exec -T postgres psql -U "$POSTGRES_USER" \
  -d "$DENEME_DB" -tAc "SELECT count(*) FROM users" | tr -d '[:space:]')
echo "[$(date -Is)] geri yuklenen kullanici sayisi: $kullanici_sayisi"

echo "[$(date -Is)] BASARILI: yedek geri yuklenebilir durumda."
