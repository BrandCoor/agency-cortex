# Değişiklik Günlüğü

## [0.1.0] - 2026-09-20 — Aşama 1

### Eklendi
- Docker Compose yapısı: api, worker, beat, postgres, redis, caddy
- FastAPI uygulaması ve sağlık kontrolü uçları (`/healthz`, `/readyz`, `/version`)
- Ayar sistemi: ortam değişkenlerini okur, üretimde şablon şifreleri reddeder
- JSON loglama ve hassas veri maskeleme (token, şifre, kişisel bilgi)
- Her isteğe izlenebilir kimlik (`x-request-id`) atanması
- Celery kuyruk ve zamanlayıcı; zaman aşımı ve tekrar deneme sınırlarıyla
- Alembic migration altyapısı ve başlangıç sürümü
- 17 otomatik test

### Doğrulandı
- 17/17 test geçti
- Uygulama gerçek PostgreSQL 16 ve Redis 7 ile çalıştırıldı
- Redis kasten durduruldu: `/readyz` doğru şekilde HTTP 503 döndü
- Celery işi kuyruğa atıldı ve başarıyla tamamlandı
- Alembic migration gerçek veritabanına uygulandı
- `docker-compose.yml` sözdizimi doğrulandı

### Doğrulanamadı (ortam kısıtı)
- Docker imajları indirilemediği için konteyner içi smoke testi yapılamadı.
  Bu test VPS'e kurulumda yapılacak.

## [0.2.0] - 2026-09-20 — Aşama 2

### Eklendi
- **28 veritabanı tablosu** (kullanıcı, müşteri, marka, sosyal hesap, metrik,
  içerik, rakip, rapor, AI, onay, denetim kaydı)
- Ham API verisi ile normalize verinin ayrı tablolarda tutulması
- Kullanıcı girişi, oturum yenileme ve `/me` ucu
- Argon2 ile şifre özetleme
- Sosyal medya token'larının şifreli saklanması (Fernet)
- 5 rol: sahip, yönetici, stratejist, editör, izleyici
- Müşteri izolasyonunu zorlayan yetki katmanı (`require_workspace`)
- Müşteri oluşturma, üye ekleme/çıkarma uçları

### Güvenlik kararları
- Yetkisiz erişimde **403 değil 404** döner: 403, o müşterinin var olduğunu
  ele verirdi
- Sistem yöneticisi (`is_superuser`) olmak müşteri verisine **otomatik erişim
  vermez**; erişim yalnızca açık üyelikle olur
- Giriş hatalarında e-posta yanlış da olsa şifre yanlış da olsa **aynı yanıt**
  döner; yanıt süresi de sabittir
- Yenileme anahtarı erişim anahtarı yerine **kullanılamaz**
- Son sahip çalışma alanından çıkarılamaz

### Doğrulandı
- 61/61 test geçti (Aşama 1'de 17 idi)
- Migration gerçek PostgreSQL'e uygulandı, 28 tablo oluştu
- **Uçtan uca izolasyon kanıtı** gerçek HTTP sunucusu üzerinde çalıştırıldı:
  iki ayrı müşteri oluşturuldu, biri diğerinin verisine hiçbir yoldan
  erişemedi (müşteri ayrıntısı, üye listesi, üye ekleme — hepsi 404)
- Yetkisiz müşteri ile var olmayan müşteri **birebir aynı** yanıtı verdi
- Testlerin veritabanında kalıntı bırakmadığı doğrulandı

### Doğrulanamadı (ortam kısıtı)
- Docker imajları indirilemediği için konteyner içi test hâlâ yapılamadı

## [0.3.0] - 2026-09-20 — Aşama 3 (kısmi)

### Eklendi
- **Platform adaptör arayüzü**: 9 ortak metot (`authorize`, `callback`,
  `refresh_token`, `list_media`, `fetch_media_metrics`,
  `fetch_account_metrics`, `fetch_comments_if_allowed`,
  `publish_draft_if_enabled`, `health_check`)
- **Yetenek bildirimi**: her adaptör gerçekten yapabildiği işleri bildirir
- **Sahte Instagram adaptörü**: gerçek hesap olmadan tüm sistem çalışır
- Şifreli anahtar saklama servisi (`token_store`)
- Senkronizasyon servisi: ham veri → normalize ölçüm
- Kuyruk işi: `sync_social_accounts` (artan bekleme süresiyle tekrar deneme)
- `/api/v1/platforms` ucu: hangi platformun gerçekten çalıştığını bildirir
- `docs/platforms/meta.md`: gerçek Meta entegrasyonu için doğrulanacaklar

### Doğrulandı
- 90/90 test geçti (Aşama 2'de 61 idi)
- **Tekrar çalıştırma testi**: aynı senkronizasyon 3 kez çalıştırıldı,
  içerik 12'de, ölçüm 72'de sabit kaldı — veri katlanmadı
- Ham veri ikinci seferde tekrar yazılmadı (12 kayıt atlandı)
- Her normalize ölçümün ham veriye bağlı olduğu doğrulandı
- Anahtar olmayan hesapta **sessiz sıfır değil, açık hata** döndüğü doğrulandı
- Yayınlama kilidinin adaptör içinde olduğu ve atlanamadığı doğrulandı
- Geliştirilmemiş 5 platformun "yok" olarak bildirildiği doğrulandı
- Token'ların veritabanında düz metin olmadığı doğrulandı

### Tamamlanmadı
- **Gerçek Meta (Instagram/Facebook) bağlantısı.** Resmî dokümantasyona
  erişim ağ politikası tarafından engellendi (HTTP 403). Endpoint ve izin
  adları tahminle yazılmayacak. Ayrıntı: `docs/platforms/meta.md`
- Docker imajları indirilemediği için konteyner içi test hâlâ yapılamadı
