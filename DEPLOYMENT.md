# Dağıtım, Yedekleme ve Geri Alma

Sunucu: Hostinger VPS **KVM 4** (kimlik: `1990274`)
Adres: `187.124.22.8` — `agencycortex.tech`

---

## 1. Sistem nasıl sunucuya çıkıyor?

```
   Kod GitHub'a gönderilir
            ↓
   GitHub Actions testleri çalıştırır
            ↓  (testler geçerse)
   Docker imajı derlenir ve kayıt defterine gönderilir
            ↓
   Sunucu hazır imajı indirir ve çalıştırır
```

**Neden sunucuda derleme yapmıyoruz?** Üretim sunucusunda derleme yavaştır,
kaynak tüketir ve bir derleme hatası çalışan sistemi etkiler. Ayrıca test
edilen imajın **birebir aynısının** çalıştığı garanti edilir.

---

## 2. Servisler

| Servis | Görevi | Dışarı açık mı? |
|---|---|---|
| `caddy` | Dış kapı, HTTPS sertifikası | ✅ 80, 443 |
| `api` | Web istekleri | ❌ sadece iç ağ |
| `worker` | Arka plan işleri | ❌ |
| `beat` | Zamanlayıcı | ❌ |
| `postgres` | Veritabanı | ❌ |
| `redis` | Kuyruk | ❌ |
| `migrate` | Şema güncellemesi (çalışır, biter) | ❌ |

**Önemli:** Veritabanı ve Redis dışarıya **kapalı.** İnternetten doğrudan
erişilemez — sadece diğer servisler ulaşabilir.

**Açılış sırası:** `migrate` başarıyla bitmeden `api`, `worker` ve `beat`
başlamaz. Böylece eski şemayla yeni kod çalışmaz.

---

## 3. Normal güncelleme

Ben yaparım, sizin bir şey yapmanız gerekmez:

1. Kodu GitHub'a gönderirim
2. Testler geçer, imaj derlenir
3. Sunucuya yeni sürümü kurarım
4. Sağlık kontrolü yaparım
5. Sonucu size bildiririm

---

## 4. Geri alma (bir şey ters giderse)

### Seviye 1 — Önceki sürüme dön
Sunucudaki imaj etiketini bir önceki sürüme çevirip yeniden kurmak yeterli.
Veritabanına dokunulmaz. **Birkaç dakika sürer.**

### Seviye 2 — Projeyi tamamen kaldır
Hostinger API üzerinden proje silinir. **Dikkat: veritabanı da silinir.**
Öncesinde yedek alınmalıdır.

### Seviye 3 — Sunucu yedeğine dön
Hostinger panelinden snapshot geri yüklenir. Sunucu snapshot anına döner.
**Snapshot'tan sonraki tüm veri kaybolur.**

| Ne zaman | Hangi seviye |
|---|---|
| Yeni sürümde hata var, veri sağlam | Seviye 1 |
| Kurulum bozuldu, veri önemsiz | Seviye 2 |
| Sunucu genelinde sorun | Seviye 3 |

---

## 5. Yedekleme

### Sunucu yedeği (snapshot)
Kurulum öncesi alındı: **20 Eylül 2026**.

> ⚠️ Hostinger her sunucu için **tek bir snapshot** tutar. Yeni snapshot
> alındığında eskisi **silinir.** Bu yüzden veritabanı yedeği ayrıca alınır.

### Veritabanı yedeği
Günlük otomatik yedek `backup_database` işiyle alınır (Aşama 10'da devreye
girecek). Yedekler sunucu dışında saklanacaktır — sunucu tamamen kaybolursa
veri yine kurtarılabilsin diye.

### Kritik: silinmemesi gerekenler
| Veri birimi | İçeriği | Silinirse |
|---|---|---|
| `postgres_data` | **Tüm müşteri verisi** | Her şey kaybolur |
| `caddy_data` | HTTPS sertifikaları | Sertifika yeniden alınır; Let's Encrypt günlük sınırına takılabilirsiniz |
| `redis_data` | Bekleyen işler | Kuyruktaki işler kaybolur (tekrarlanabilir) |

---

## 6. Sunucu yeniden başlarsa

Tüm servislerde `restart: unless-stopped` tanımlı. Sunucu yeniden
başladığında Docker servisleri **kendiliğinden** ayağa kaldırır.

Bu davranış kurulumdan sonra bilerek test edilecektir.

---

## 7. Sistem çalışıyor mu? — hızlı kontrol

Tarayıcınızdan açabileceğiniz adresler:

| Adres | Ne görmeli |
|---|---|
| `https://agencycortex.tech/healthz` | `{"status":"ok"}` |
| `https://agencycortex.tech/readyz` | `{"status":"ready"...}` |
| `https://agencycortex.tech/version` | Sürüm bilgisi |

- `/healthz` **ok** ama `/readyz` **not_ready** → veritabanı veya kuyruk sorunu
- Hiçbiri açılmıyor → Caddy veya sunucu sorunu
- Sertifika hatası → DNS veya HTTPS sorunu

Bu adreslerden biri beklenen yanıtı vermezse bana söyleyin; log'lara bakarım.

---

## 8. Log'lar

Tüm servisler JSON formatında log tutar. Her log dosyası en fazla 10 MB,
en fazla 3 dosya saklanır — böylece log'lar diski doldurmaz.

Loglarda şifre, token ve kişisel bilgi **otomatik maskelenir.**
