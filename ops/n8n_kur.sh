#!/usr/bin/env bash
#
# n8n is akislarini kurar. TEKRAR CALISTIRILABILIR.
#
# NEDEN BIR BETIK (ve zamanlanmis tekrar):
# n8n'e is akisi yuklemek icin n8n'de bir SAHIP HESABI olmasi gerekir
# (n8n kaynagi: import komutu global owner'i bulamazsa hata verir).
# O hesabi kullanici ilk girisinde kendisi olusturur. Kurulum aninda
# hesap henuz yoktur. Bu betik zamanlanmis olarak tekrar dener; kullanici
# hesabini actiktan birkac dakika sonra akislar kendiliginden kurulur.
# Kullanicinin baska bir sey yapmasi gerekmez.
#
# ADIMLAR
# 1. Agency Cortex'te n8n icin makine anahtari uretilir
# 2. Anahtar, n8n'e SIFRELI kimlik bilgisi olarak aktarilir
#    (n8n import:credentials duz veriyi alip kendi anahtariyla sifreler)
# 3. Is akislari yuklenir
# 4. Her akis yayinlanir (n8n 2.x'te etkinlestirme boyle yapilir)
# 5. n8n yeniden baslatilir - yayinlama calisir haldeyken etkili olmaz
# 6. Dort akisin da ETKIN oldugu dogrulanir; degilse betik HATA verir
#
# ANAHTAR HICBIR YERDE LOGLANMAZ.
#
set -euo pipefail

DIZIN="${DIZIN:-/opt/agency-cortex}"
AKIS_DIZINI="${AKIS_DIZINI:-$DIZIN/n8n/akislar}"
ISARET="$DIZIN/.n8n-akislari-kuruldu"

KIMLIK_ID="agency-cortex-api"
KIMLIK_AD="Agency Cortex API"
AKIS_IDLERI="agency-cortex-wf01 agency-cortex-wf02 agency-cortex-wf03 agency-cortex-wf04"

cd "$DIZIN"

yaz() { echo "[$(date -Is)] $*"; }

if [ -f "$ISARET" ]; then
  yaz "Akislar zaten kurulu. Yeniden kurmak icin: rm $ISARET"
  exit 0
fi

if [ ! -d "$AKIS_DIZINI" ]; then
  yaz "HATA: akis dizini yok: $AKIS_DIZINI"
  exit 1
fi

# --- n8n ayakta mi ----------------------------------------------------------
if ! docker compose ps --status running --services </dev/null 2>/dev/null | grep -qx n8n; then
  yaz "n8n calismiyor; sonraki denemede tekrar bakilacak."
  exit 1
fi

# --- 1) Makine anahtari -----------------------------------------------------
# Ciktinin SON satiri anahtardir; onceki satirlar log olabilir.
yaz "Agency Cortex makine anahtari uretiliyor..."
if ! ham=$(docker compose exec -T api python -m app.cli.otomasyon n8n-anahtari </dev/null 2>/tmp/n8n_anahtar_hata.log); then
  yaz "HATA: makine anahtari uretilemedi."
  sed -e 's/acx_[A-Za-z0-9_-]*/acx_***/g' /tmp/n8n_anahtar_hata.log >&2 || true
  exit 1
fi
ANAHTAR=$(printf '%s' "$ham" | tr -d '\r' | grep -oE '^acx_[A-Za-z0-9_-]+$' | tail -1)
if [ -z "$ANAHTAR" ]; then
  yaz "HATA: uretilen deger beklenen bicimde degil."
  exit 1
fi
yaz "Anahtar uretildi (deger loglanmaz)."

# --- 2) Kimlik bilgisini n8n'e aktar ----------------------------------------
# n8n duz veriyi alip KENDI anahtariyla sifreler; dosya hemen silinir.
gecici=$(mktemp)
chmod 600 "$gecici"
temizle() { rm -f "$gecici"; docker compose exec -T n8n rm -f /tmp/ac-kimlik.json </dev/null 2>/dev/null || true; }
trap temizle EXIT

python3 - "$gecici" "$ANAHTAR" <<'PY'
import json, sys
hedef, anahtar = sys.argv[1], sys.argv[2]
json.dump([{
    "id": "agency-cortex-api",
    "name": "Agency Cortex API",
    "type": "httpHeaderAuth",
    "data": {"name": "X-API-Key", "value": anahtar},
}], open(hedef, "w"), ensure_ascii=False)
PY
unset ANAHTAR

docker compose cp "$gecici" n8n:/tmp/ac-kimlik.json >/dev/null
rm -f "$gecici"

yaz "Kimlik bilgisi n8n'e aktariliyor..."
if ! docker compose exec -T n8n n8n import:credentials --input=/tmp/ac-kimlik.json </dev/null; then
  yaz "HATA: kimlik bilgisi aktarilamadi."
  yaz "Olasi neden: n8n'de henuz SAHIP HESABI olusturulmadi."
  yaz "n8n adresine girip hesabinizi olusturun; bu betik kendiliginden tekrar deneyecek."
  exit 1
fi
docker compose exec -T n8n rm -f /tmp/ac-kimlik.json </dev/null || true

# --- 3) Is akislarini yukle -------------------------------------------------
yaz "Is akislari yukleniyor..."
docker compose exec -T n8n n8n import:workflow --separate --input=/akislar </dev/null

# --- 4) Yayinla (n8n 2.x'te etkinlestirme budur) ----------------------------
for id in $AKIS_IDLERI; do
  yaz "Yayinlaniyor: $id"
  docker compose exec -T n8n n8n publish:workflow --id="$id" </dev/null
done

# --- 5) n8n yeniden baslatilir ----------------------------------------------
# n8n'in kendi ciktisi: "Changes will not take effect if n8n is running."
yaz "n8n yeniden baslatiliyor..."
docker compose restart n8n >/dev/null
for i in $(seq 1 40); do
  if docker compose exec -T api curl -fsS http://n8n:5678/healthz >/dev/null 2>&1 </dev/null; then
    break
  fi
  sleep 5
done

# --- 6) GERCEKTEN etkin mi ---------------------------------------------------
# "Yukledim" demek yetmez. Etkin olmayan bir akis hic calismaz ve bu
# sessizce fark edilmez.
yaz "Etkin akislar dogrulaniyor..."
etkinler=$(docker compose exec -T n8n n8n list:workflow --active=true --onlyId </dev/null 2>/dev/null | tr -d '\r')

eksik=""
for id in $AKIS_IDLERI; do
  if ! printf '%s\n' "$etkinler" | grep -qx "$id"; then
    eksik="$eksik $id"
  fi
done

if [ -n "$eksik" ]; then
  yaz "HATA: su akislar etkin degil:$eksik"
  yaz "Etkin gorunenler:"
  printf '%s\n' "$etkinler" | sed 's/^/  /'
  exit 1
fi

touch "$ISARET"
yaz "TAMAM: dort is akisi da kuruldu ve ETKIN."
