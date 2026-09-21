#!/usr/bin/env bash
#
# Veritabani yedegi alir.
#
# TASARIM KARARLARI
# - pg_dump "custom" bicimiyle (-Fc) alinir: sikistirilmis ve secmeli geri
#   yuklemeye izin verir.
# - Yedek ONCE gecici bir dosyaya yazilir, basarili biterse asil adina
#   tasinir. Boylece yarim kalan bir yedek "gecerli yedek" sanilmaz.
# - Dosya izinleri 600: yedek tum musteri verisini icerir.
# - Eski yedekler SILINMEDEN once yenisinin basarili oldugu dogrulanir.
#
set -euo pipefail

DIZIN="${DIZIN:-/opt/agency-cortex}"
YEDEK_DIZINI="${YEDEK_DIZINI:-$DIZIN/yedek}"
SAKLAMA_GUN="${SAKLAMA_GUN:-14}"

cd "$DIZIN"

# .env'den veritabani bilgileri okunur. Degerler ekrana BASILMAZ.
if [ ! -f .env ]; then
  echo "HATA: $DIZIN/.env bulunamadi." >&2
  exit 1
fi
# shellcheck disable=SC1091
set -a; . ./.env; set +a
: "${POSTGRES_DB:?POSTGRES_DB tanimsiz}"
: "${POSTGRES_USER:?POSTGRES_USER tanimsiz}"

mkdir -p "$YEDEK_DIZINI"
chmod 700 "$YEDEK_DIZINI"

damga="$(date +%Y%m%d-%H%M%S)"
hedef="$YEDEK_DIZINI/agency-cortex-$damga.dump"
gecici="$hedef.yaziliyor"

echo "[$(date -Is)] yedek aliniyor -> $(basename "$hedef")"

# -T yok: stdout'u dosyaya yonlendiriyoruz, terminal gerekmiyor.
if ! docker compose exec -T postgres \
      pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$gecici" 2>/tmp/yedek_hata.log; then
  echo "HATA: pg_dump basarisiz." >&2
  sed -e 's/password=[^ ]*/password=***/g' /tmp/yedek_hata.log >&2 || true
  rm -f "$gecici"
  exit 1
fi

# Bos veya sacma kucuk bir dosya "yedek" sayilmamali.
boyut=$(stat -c%s "$gecici")
if [ "$boyut" -lt 1024 ]; then
  echo "HATA: yedek dosyasi cok kucuk ($boyut bayt). Gecersiz sayildi." >&2
  rm -f "$gecici"
  exit 1
fi

mv "$gecici" "$hedef"
chmod 600 "$hedef"
echo "[$(date -Is)] TAMAM: $(basename "$hedef") ($boyut bayt)"

# Eski yedekleri temizle. Yeni yedek basariyla yazildiktan SONRA yapilir.
silinen=$(find "$YEDEK_DIZINI" -maxdepth 1 -name 'agency-cortex-*.dump' \
            -type f -mtime "+$SAKLAMA_GUN" -print -delete | wc -l)
echo "[$(date -Is)] $SAKLAMA_GUN gunden eski $silinen yedek silindi."

echo "[$(date -Is)] mevcut yedekler:"
ls -lh "$YEDEK_DIZINI"/agency-cortex-*.dump 2>/dev/null | tail -5 || echo "  (yok)"
