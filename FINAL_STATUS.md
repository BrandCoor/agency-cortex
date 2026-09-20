# Proje Durumu

Son güncelleme: 20 Eylül 2026

---

## Özet

| | |
|---|---|
| Depo | https://github.com/BrandCoor/agency-cortex (özel) |
| Kod | ~6.100 satır Python |
| Test | 220, tamamı geçiyor (CI'da da) |
| Docker imajı | ✅ Derlendi ve çalıştığı doğrulandı |
| Sunucu | Hostinger KVM 4 (`1990274`) — ✅ **ÇALIŞIYOR** |
| Canlı adres | https://agencycortex.tech ✅ HTTPS aktif |
| Domain | agencycortex.tech → 187.124.22.8 ✅ |
| Sunucu yedeği | 20 Eylül 2026'da alındı ✅ |

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
| 7 | İnsan onay paneli | ⬜ |
| 8 | Rakip ve trend modülü | ⬜ |
| 9 | Gemini sağlayıcısı | ⬜ |
| 10 | Güvenlik, yedekleme, üretim kurulumu | 🟡 Kurulum ✅, yedekleme testi kaldı |

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

---

## Eksik kalanlar

### 1. Gerçek Instagram bağlantısı
**Durum:** Kod hazır, 4 sabit doğrulanmadı.
**Sebep:** Geliştirme ortamından Meta dokümanlarına erişim engelli (HTTP 403).
**Çözüm:** `developers.facebook.com` adresinin ağ erişim listesine eklenmesi.
**Ayrıntı:** `docs/platforms/meta.md`

### 2. Sunucu kurulumu
**Durum:** ✅ Tamamlandı. Sistem canlıda, HTTPS aktif, dışarıdan doğrulandı.

### 3. İçerik üretimi, araştırma, panel
Aşama 5-9. Sıradaki iş.

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
| Backup/restore testi geçiyor | ⬜ Aşama 10 |
| Sunucu yeniden başlayınca servisler geliyor | ⬜ Yeniden başlatma testi yapılmadı |
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
4. **Panel henüz yok.** Aşama 7'ye kadar işlemler API üzerinden yapılır.
