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

## 1b. Panele giriş için ilk hesabı açmak

Sistemde dışarıya açık bir "kayıt ol" sayfası **yoktur** (nedeni:
DECISIONS.md K-020). İlk hesap kurulum sırasında sunucunun içinde açılır.
Bunun için GitHub'a iki bilgi girmeniz gerekir.

### Adım adım (tarayıcıdan)

1. https://github.com/BrandCoor/agency-cortex adresini açın.
2. Üst menüden **Settings** (Ayarlar) sekmesine tıklayın.
3. Sol taraftaki listeden **Secrets and variables** başlığına tıklayın,
   altından **Actions** seçeneğine girin.
4. Yeşil **New repository secret** düğmesine basın.
5. **Name** kutusuna tam olarak şunu yazın: `ILK_YONETICI_EMAIL`
   **Secret** kutusuna giriş yapmak istediğiniz e-posta adresinizi yazın.
   **Add secret** ile kaydedin.
6. Aynı işlemi tekrarlayın:
   **Name**: `ILK_YONETICI_SIFRE`
   **Secret**: kendi seçeceğiniz şifre — **en az 12 karakter.**
7. (İsteğe bağlı) Aynı şekilde `ILK_YONETICI_AD` ekleyip adınızı yazın.
   Yazmazsanız "Ajans Yoneticisi" görünür.

**Bu şifreyi bana sohbette yazmayın.** GitHub'ın bu kutusu şifreli saklar
ve kurulum kayıtlarında yıldızlı görünür; sohbet geçmişi öyle değildir.

### Sonra ne oluyor?

Bir sonraki kurulumda "İlk yönetici hesabı" adımı çalışır ve hesabınızı
açar. Sistemde **zaten bir kullanıcı varsa hiçbir şey yapmaz** — yani bu
adım her kurulumda güvenle tekrar çalışır, mevcut şifrenizi ezmez.

### İlk girişten sonra

1. https://agencycortex.tech/panel adresinden girin.
2. Üstteki **"Şifre değiştir"** bağlantısından şifrenizi değiştirin.
3. Bana haber verin: GitHub'daki `ILK_YONETICI_SIFRE` kaydını sileceğim.
   (Şifre orada kaldığı sürece GitHub'a erişen biri onu kullanabilir.)

### Şifrenizi unutursanız

Sunucudan sıfırlanabilir. Bana söyleyin; `sifre-degistir` komutuyla
sıfırlıyorum. Yeni şifreyi yine GitHub Secrets üzerinden alırım,
sohbetten değil.

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

### Veritabanı yedeği — ✅ çalışıyor

| | |
|---|---|
| Ne zaman | Her gün saat **03:30** |
| Nerede | `/opt/agency-cortex/yedek/` |
| Saklama | **14 gün** (eskiler otomatik silinir) |
| Doğrulama | Her **pazar 04:00** |
| Kayıt | `/var/log/agency-cortex-yedek.log` |

**Yedek gerçekten çalışıyor mu?** Her kurulumda bir yedek alınıp **ayrı ve
geçici** bir veritabanına geri yükleniyor, tabloları sayılıyor, sonra o geçici
veritabanı siliniyor. Üretim veritabanına dokunulmuyor. Geri yüklenemeyen bir
yedek, yedek değildir — bu yüzden "yedek alındı" demekle yetinmiyoruz.

**Elle yedek almak** (sunucuda):
```
cd /opt/agency-cortex && bash ops/yedek_al.sh
```

**Yedeği sınamak** (üretime dokunmaz):
```
cd /opt/agency-cortex && bash ops/yedek_dogrula.sh
```

**Yedeği geri yüklemek** — ⚠️ geri alınamaz:
```
cd /opt/agency-cortex && bash ops/yedek_geri_yukle.sh yedek/agency-cortex-YYYYMMDD-HHMMSS.dump
```
Bu komut önce mevcut durumun yedeğini alır (yanlış dosya seçerseniz
dönebilmeniz için), uygulamayı durdurur, `GERI YUKLE` yazmanızı ister ve
işlem bitince sistemi tekrar başlatıp sağlığını kontrol eder.

### ⚠️ Henüz eksik: sunucu dışına kopya
Yedekler şu an **aynı sunucuda** duruyor. Sunucu tamamen kaybolursa yedekler
de kaybolur. Sunucu dışına kopyalama henüz kurulmadı — bunun için bir
depolama hesabı (örneğin bir nesne deposu) gerekiyor. Bu, olduğundan iyi
gösterilmemesi gereken gerçek bir eksiktir.

Şu an elimizdeki koruma: Hostinger sunucu anlık görüntüsü (tek adet, yenisi
alınınca eskisi silinir) + günlük veritabanı yedeği (aynı sunucuda).

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
