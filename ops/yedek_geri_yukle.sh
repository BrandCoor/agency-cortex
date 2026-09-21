#!/usr/bin/env bash
#
# Bir yedegi URETIM veritabanina geri yukler.
#
# ⚠️ BU ISLEM GERI ALINAMAZ. Mevcut veri yedekteki veriyle DEGISTIRILIR.
#
# Bu yuzden:
# 1. Once mevcut durumun yedegi alinir (yanlis dosyayi secerseniz donebilmek icin).
# 2. Uygulama durdurulur; yarida kalan yazma islemleri veriyi bozmasin.
# 3. Acik onay istenir: "GERI YUKLE" yazilmadan devam edilmez.
#
set -euo pipefail

DIZIN="${DIZIN:-/opt/agency-cortex}"
YEDEK_DIZINI="${YEDEK_DIZINI:-$DIZIN/yedek}"
DOSYA="${1:-}"

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

if [ -z "$DOSYA" ]; then
  echo "Kullanim: $0 <yedek-dosyasi>"
  echo ""
  echo "Mevcut yedekler:"
  ls -lht "$YEDEK_DIZINI"/agency-cortex-*.dump 2>/dev/null || echo "  (yok)"
  exit 2
fi
[ -f "$DOSYA" ] || { echo "HATA: dosya yok: $DOSYA" >&2; exit 1; }

echo "============================================================"
echo " DIKKAT: URETIM VERITABANI DEGISTIRILECEK"
echo "============================================================"
echo " Veritabani : $POSTGRES_DB"
echo " Yedek      : $DOSYA"
echo " Tarih      : $(date -r "$DOSYA" -Is 2>/dev/null || echo bilinmiyor)"
echo ""
echo " Bu islem GERI ALINAMAZ. Suanki veri yedektekiyle degistirilecek."
echo ""
printf " Devam etmek icin buyuk harfle GERI YUKLE yazin: "
read -r onay
if [ "$onay" != "GERI YUKLE" ]; then
  echo "Iptal edildi. Hicbir sey degismedi."
  exit 1
fi

echo "[$(date -Is)] 1/4 mevcut durumun yedegi aliniyor (guvenlik agi)"
YEDEK_DIZINI="$YEDEK_DIZINI" DIZIN="$DIZIN" bash "$DIZIN/ops/yedek_al.sh"

echo "[$(date -Is)] 2/4 uygulama durduruluyor"
docker compose stop api worker beat

echo "[$(date -Is)] 3/4 yedek geri yukleniyor"
# --clean --if-exists: mevcut nesneleri once dusurur, sonra yeniden kurar.
docker compose exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists --no-owner --no-privileges < "$DOSYA" 2>/tmp/geri_yukleme.log || true
tail -5 /tmp/geri_yukleme.log || true

echo "[$(date -Is)] 4/4 uygulama baslatiliyor"
docker compose start api worker beat

echo "[$(date -Is)] hazir olmasi bekleniyor..."
for i in $(seq 1 40); do
  if docker compose exec -T api curl -fsS http://localhost:8000/readyz >/dev/null 2>&1 </dev/null; then
    echo "[$(date -Is)] BASARILI: sistem geri yuklendi ve calisiyor."
    docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
      -tAc "SELECT 'kullanici sayisi: ' || count(*) FROM users" </dev/null
    exit 0
  fi
  sleep 5
done
echo "HATA: sistem 200 saniyede hazir olmadi. Loglara bakin:" >&2
docker compose logs --tail=40 >&2
exit 1
