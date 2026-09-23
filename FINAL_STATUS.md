# Proje Durumu

Son güncelleme: 23 Eylül 2026

---

## Özet

| | |
|---|---|
| Depo | https://github.com/BrandCoor/agency-cortex (özel) |
| Kod | ~23.200 satır Python (uygulama + testler) |
| Test | 581, tamamı geçiyor (CI'da da) |
| Docker imajı | ✅ Derlendi ve çalıştığı doğrulandı |
| Sunucu | Hostinger KVM 4 (`1990274`) — ✅ **ÇALIŞIYOR** |
| Canlı adres | https://agencycortex.tech ✅ HTTPS aktif |
| Domain | agencycortex.tech → 187.124.22.8 ✅ |
| Sunucu yedeği | 20 Eylül 2026'da alındı ✅ (sunucu dışı kopya bekliyor) |
| Otomasyon | n8n'de 5 iş akışı kurulu ve **etkin** ✅ |

---

## Aşamalar

| Aşama | Konu | Durum |
|---|---|---|
| 0 | Keşif | ✅ |
| 1 | Docker, veritabanı, kuyruk, sağlık kontrolü, loglama | ✅ |
| 2 | Kullanıcı, müşteri izolasyonu, roller, oturum | ✅ |
| 3 | Platform mimarisi, OAuth, webhook güvenliği | 🟡 Kod hazır, 4 Meta sabiti doğrulanmadı |
| 4 | Metrikler, KPI motoru, raporlar | ✅ Tamamlandı |
| 5 | Claude API ile içerik senaryosu | ✅ Tamamlandı |
| 6 | Manus API ile araştırma | 🟡 Engelli (doküman erişimi yok) |
| 7 | İnsan onay paneli | ✅ Tamamlandı |
| 8 | Rakip ve trend modülü | ⬜ Sırada |
| 9 | Gemini sağlayıcısı | ⬜ Planlanmadı (ayarlardan kaldırıldı) |
| 10 | Güvenlik, yedekleme, üretim kurulumu | 🟡 Kurulum ✅, sunucu dışı kopya kaldı |
| 11 | Kullanıcı yönetimi ve panel yenileme | ✅ Tamamlandı |
| 12 | n8n otomasyonu (5 iş akışı) | ✅ Tamamlandı |
| 13 | Yayın takvimi | ✅ Tamamlandı |
| 14 | Ayrıntılı yetkiler (19 izin) | ✅ Tamamlandı |

---

## Doğrulanan özellikler

Bunlar yazıldı **ve çalıştığı kanıtlandı:**

### Müşteri izolasyonu
- İki ayrı müşteri oluşturuldu; biri diğerinin verisine erişemedi
- Yetkisiz müşteri ile var olmayan müşteri **birebir aynı** yanıtı verdi
- Sistem yöneticisi olmak otomatik erişim vermiyor
- Üyelik silinince erişim anında kesiliyor

### Güvenlik
- Şifreler Argon2 ile özetleniyor, aynı şifre farklı özet üretiyor
- Sosyal medya anahtarları şifreli saklanıyor (düz metin yok)
- Loglarda token, şifre ve kişisel bilgi maskeleniyor
- OAuth `state` tek kullanımlık — ikinci kullanım reddediliyor
- Webhook imzası doğrulanıyor; gövde değişirse geçersizleşiyor
- Aynı webhook iki kez işlenmiyor
- Yayınlama kilidi adaptör içinde, atlanamıyor
- Üretim şablon şifrelerle açılmıyor

### Veri bütünlüğü
- Senkronizasyon 3 kez çalıştırıldı, sayılar değişmedi
- Ham veri ile normalize veri ayrı; her ölçüm ham veriye kadar izlenebiliyor
- Anahtar yoksa "0 veri" değil **açık hata** dönüyor
- Testler şemayı migration ile kuruyor — bozuk migration testte yakalanır
- Testler "_test" ile bitmeyen veritabanında **çalışmayı reddediyor**

### Dürüstlük
- Geliştirilmemiş 5 platform "yok" olarak bildiriliyor, "yakında" değil
- Meta adaptörü ayarlar doğrulanmadan hiçbir yetenek bildirmiyor
- Örnek veri modundaki platform "bağlanabilir" diye gösterilmiyor
- Takvim "sistem kendisi paylaşmaz" diye açıkça yazıyor; paylaşım elle
  işaretlenir, böylece takvim varsayımı değil gerçeği gösterir
- Panelde açılıp kapatılan **her izin** gerçekten uygulanıyor; bunu bir
  test sürekli denetliyor (`test_her_izin_bir_yerde_gercekten_...`)

### AI bütçesi
- İki iş aynı anda çalıştırıldı; bütçe **aşılamadı** (veritabanı kilidi)
- Kilit kaldırılınca aynı test **düşüyor** — yani gerçekten ölçüyor

### Yetkiler
- 19 izin, her müşteri için her rol bazında ayarlanabiliyor
- SAHİP rolü kısıtlanamıyor (müşteri kilitlenemez)
- İzni alınan kullanıcı isteği **elle** gönderse de reddediliyor
- Menüde gizlenen sayfa, adres elle yazıldığında da 404 dönüyor

### Otomasyon
- 5 iş akışı n8n'de kurulu ve etkin (sunucudan ölçüldü)
- Kurulum, n8n'in Cortex'e kimliğiyle **gerçekten ulaştığını** doğruluyor

---

## Eksik kalanlar

### 1. Gerçek Instagram bağlantısı
**Durum:** Kod hazır, 4 sabit doğrulanmadı.
**Sebep:** Geliştirme ortamından Meta dokümanlarına erişim engelli (HTTP 403).
**Çözüm:** `developers.facebook.com` adresinin ağ erişim listesine eklenmesi.
**Ayrıntı:** `docs/platforms/meta.md`

### 2. Sunucu kurulumu
**Durum:** ✅ Tamamlandı. Sistem canlıda, HTTPS aktif, dışarıdan doğrulandı.

### 3. Sunucu dışı yedek kopya
**Durum:** Sunucuda günlük yedek alınıyor ve doğrulanıyor. Ancak yedeğin
**başka bir yerde** kopyası yok. Sunucu tamamen kaybolursa yedek de gider.
**Bekleyen karar:** Kopyanın nereye gideceği (depolama sağlayıcısı) size ait.

### 4. Manus araştırma ve rakip/trend modülü
Aşama 6 ve 8. Sıradaki iş.

### 5. Yeniden başlatma testi
Sunucu yeniden başlatıldığında tüm servislerin kendiliğinden gelmesi
henüz **ölçülmedi**.

---

## MVP kabul kriterleri

| Kriter | Durum |
|---|---|
| En az iki müşteri alanı oluşturulabiliyor | ✅ |
| Kullanıcı yalnızca yetkili alanı görüyor | ✅ |
| Instagram hesabı OAuth ile bağlanabiliyor | 🟡 Kod hazır, gerçek hesapla test edilmedi |
| Hesap ve medya verisi alınabiliyor | ✅ (sahte sağlayıcı ile) |
| Ham ve normalize veri ayrılmış | ✅ |
| Günlük ve haftalık rapor üretiliyor | ✅ (sahte veriyle doğrulandı) |
| Claude API senaryo üretiyor | ✅ (sahte sağlayıcıyla doğrulandı) |
| Manus API araştırma yapıyor | ⬜ Aşama 6 |
| AI hataları loglanıyor | ✅ |
| İnsan onayı olmadan yayın yapılamıyor | ✅ |
| Secret'lar Git'e girmiyor | ✅ Her gönderimde kontrol edildi |
| Backup/restore testi geçiyor | 🟡 Sunucuda ✅, sunucu dışı kopya yok |
| Sunucu yeniden başlayınca servisler geliyor | ⬜ Yeniden başlatma testi yapılmadı |
| Yayın takvimi ile planlama yapılabiliyor | ✅ |
| Kullanıcı yetkileri ayrıntılı ayarlanabiliyor | ✅ 19 izin, müşteri başına |
| Otomasyon (n8n) müşteri başına açılıp kapanıyor | ✅ |
| Docker imajı derlenip çalışıyor | ✅ CI'da doğrulandı |
| README teknik olmayan kullanıcıya uygun | ✅ |

---

## Bilinen sınırlar

1. **Bu geliştirme ortamı VPS'e erişemiyor.** SSH (port 22) her hedefe kapalı.
   Kurulum Hostinger API veya GitHub Actions üzerinden yapılır.
2. **Docker imajları bu ortamdan indirilemiyor.** İmaj doğrulaması GitHub
   Actions'ta yapılıyor — nitekim yerelde görülemeyen iki hatayı orada
   yakaladık (Dockerfile sırası ve imaj adındaki büyük harf). İmajın
   açıldığı artık her kod gönderiminde otomatik doğrulanıyor.
3. **Meta dokümanlarına erişim engelli.** 4 sabit boş bırakıldı; boşken sistem
   canlı moda geçmiyor.
4. **Panel hazır** — `https://agencycortex.tech/panel` adresinden girilir.
   20 Eylül'de panelin canlıda açılmadığı fark edildi: ters vekil (Caddy)
   `/panel` yolunu uygulamaya yönlendirmiyordu. Düzeltildi; kurulum kontrolü
   artık giriş sayfasını gerçekten çekiyor.
5. **Bu geliştirme ortamı hiçbir dış adrese çıkamıyor.** `developers.facebook.com`,
   `graph.facebook.com`, `manus.im`, `open.manus.ai` ve hatta kendi domainimiz
   `agencycortex.tech` dahil hepsi ağ geçidinde HTTP 403 ile engelleniyor
   (20 Eylül 2026'da tek tek denendi). Dışarıdan doğrulama yalnızca GitHub
   Actions üzerinden yapılabiliyor.

---

## Dış bağlantılar — doğrulama durumu

| Adres | Amaç | Durum | Not |
|---|---|---|---|
| `developers.facebook.com` | Meta resmî dokümanı okumak | **UNVERIFIED** | Bu ortamdan erişilemiyor; 4 Meta sabiti hâlâ boş |
| `graph.facebook.com` | Meta Graph API çağrıları | **UNVERIFIED** | Sürüm ve uç adresleri doğrulanmadı |
| `open.manus.ai` | Manus API dokümanı (aday) | **NEEDS_URL_CONFIRMATION** | Kullanıcının belgesinde geçiyor; erişilemedi |
| `manus.im/docs/integrations/manus-api` | Manus API dokümanı (aday) | **NEEDS_URL_CONFIRMATION** | Kullanıcının belgesinde geçiyor; erişilemedi |
| `docs.manus.ai` | Manus dokümanı | **UNVERIFIED** | Resmî olduğu teyit edilmedi; kodda kullanılmıyor |
| `api.manus.ai` | Manus API host'u | **UNVERIFIED** | Resmî olduğu teyit edilmedi; **kodda kullanılmıyor** |
| `agencycortex.tech` | Kendi uygulamamız | **VERIFIED** | HTTPS aktif; GitHub Actions'tan doğrulanıyor |
| `ghcr.io` | Docker imaj kayıt defteri | **VERIFIED** | Her kurulumda kullanılıyor |
| `api.anthropic.com` | Claude API | **VERIFIED** | SDK parametreleri doğrulandı; anahtar henüz alınmadı |

Hiçbir Manus adresi koda yazılmadı. Manus sağlayıcısı şu an yalnızca
"henüz bağlanmadı" diyen bir taslaktır (`ManusProviderStub`) — sahte bir
entegrasyon değildir.
