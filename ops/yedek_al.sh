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
# n8n veritabani: is akislari ve kayitli kimlik bilgileri burada durur.
# Yoksa (n8n henuz kurulmadiysa) yedek yine alinir, yalnizca atlanir.
N8N_DB=$(env_oku N8N_DB || true)

mkdir -p "$YEDEK_DIZINI"
chmod 700 "$YEDEK_DIZINI"

damga="$(date +%Y%m%d-%H%M%S)"
hedef="$YEDEK_DIZINI/agency-cortex-$damga.dump"
gecici="$hedef.yaziliyor"

echo "[$(date -Is)] yedek aliniyor -> $(basename "$hedef")"

# -T yok: stdout'u dosyaya yonlendiriyoruz, terminal gerekmiyor.
if ! docker compose exec -T postgres \
      pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc </dev/null > "$gecici" 2>/tmp/yedek_hata.log; then
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

# --- n8n veritabani ---------------------------------------------------------
# Ayri bir dosyaya alinir: geri yuklerken birini digerinden bagimsiz
# secebilmek gerekir.
if [ -n "${N8N_DB:-}" ]; then
  n8n_var=$(docker compose exec -T postgres \
      psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
      "SELECT 1 FROM pg_database WHERE datname = '$N8N_DB'" </dev/null 2>/dev/null || true)

  if [ "$(printf '%s' "$n8n_var" | tr -d '[:space:]')" = "1" ]; then
    n8n_hedef="$YEDEK_DIZINI/n8n-$damga.dump"
    n8n_gecici="$n8n_hedef.yaziliyor"
    echo "[$(date -Is)] n8n yedegi aliniyor -> $(basename "$n8n_hedef")"

    if docker compose exec -T postgres \
         pg_dump -U "$POSTGRES_USER" -d "$N8N_DB" -Fc </dev/null > "$n8n_gecici" 2>/tmp/yedek_n8n_hata.log; then
      n8n_boyut=$(stat -c%s "$n8n_gecici")
      if [ "$n8n_boyut" -lt 1024 ]; then
        echo "HATA: n8n yedegi cok kucuk ($n8n_boyut bayt). Gecersiz sayildi." >&2
        rm -f "$n8n_gecici"
        exit 1
      fi
      mv "$n8n_gecici" "$n8n_hedef"
      chmod 600 "$n8n_hedef"
      echo "[$(date -Is)] TAMAM: $(basename "$n8n_hedef") ($n8n_boyut bayt)"
    else
      echo "HATA: n8n pg_dump basarisiz." >&2
      sed -e 's/password=[^ ]*/password=***/g' /tmp/yedek_n8n_hata.log >&2 || true
      rm -f "$n8n_gecici"
      exit 1
    fi
  else
    echo "[$(date -Is)] n8n veritabani ($N8N_DB) henuz yok; atlandi."
  fi
fi

# Eski yedekleri temizle. Yeni yedek basariyla yazildiktan SONRA yapilir.
silinen=$(find "$YEDEK_DIZINI" -maxdepth 1 \( -name 'agency-cortex-*.dump' -o -name 'n8n-*.dump' \) \
            -type f -mtime "+$SAKLAMA_GUN" -print -delete | wc -l)
echo "[$(date -Is)] $SAKLAMA_GUN gunden eski $silinen yedek silindi."

echo "[$(date -Is)] mevcut yedekler:"
ls -lh "$YEDEK_DIZINI"/*.dump 2>/dev/null | tail -8 || echo "  (yok)"
