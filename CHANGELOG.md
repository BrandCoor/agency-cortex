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

## [0.4.0] - 2026-09-20 — Meta OAuth altyapısı

Kullanıcının ilettiği Meta entegrasyon rehberi doğrultusunda yapıldı.

### Eklendi
- **Gerçek `MetaAdapter`**: OAuth akışı, token değişimi, token yenileme,
  hata yönetimi, zaman aşımı, istek sınırı (rate limit) yakalama
- Meta'ya özgü değerler **ayardan** okunuyor, koda gömülmüyor
- **OAuth `state` korumasi**: tahmin edilemez, Redis'te saklanan,
  **tek kullanımlık** değer (CSRF ve replay koruması)
- OAuth uçları: izin akışını başlatma ve geri dönüş işleme
- **Webhook güvenliği**: verify token kontrolü, HMAC-SHA256 imza
  doğrulama, tekrar koruma (idempotency)
- `META_LOGIN_MODE` ayarı: Instagram Login / Facebook Login seçimi
- 19 Meta ortam değişkeni `.env.example` içinde tanımlandı
- **`INSTALLATION.md`**: kullanıcının Meta panelinde yapacağı adımlar
- Üretilen adresler (redirect, webhook, deauthorize, veri silme)

### Düzeltildi
- **Webhook tekrar kaydında veri kaybı hatası.** Aynı olay ikinci kez
  geldiğinde `db.rollback()` çağrılıyordu; bu, o işlemde yapılmış **tüm**
  değişiklikleri geri alırdı. SAVEPOINT kullanımına geçildi: artık yalnızca
  başarısız ekleme geri alınıyor. Bu hatayı test yakaladı.

### Doğrulandı
- 118/118 test geçti (önceki 90)
- Ayar eksikken adaptörün hiçbir yetenek bildirmediği
- Ayarlar dolunca yeteneklerin otomatik açıldığı — kod değişikliği olmadan
- Yayınlama/yorum/mesaj yeteneklerinin açılmadığı
- `state` değerinin tek kullanımlık olduğu (ikinci kullanım reddediliyor)
- 20 state üretiminin hepsinin benzersiz olduğu
- Gövde değiştirilince webhook imzasının geçersizleştiği
- App secret ayarlanmamışken imzanın geçerli sayılmadığı
- Aynı webhook olayının iki kez işlenmediği
- İmzasız ve sahte imzalı isteklerin 401 ile reddedildiği
- Gizli anahtarın izin adresine konulmadığı
- Yetkisiz kullanıcının hesap bağlayamadığı (izleyici → 403)
- Başka müşterinin çalışma alanına hesap bağlanamadığı (→ 404)

### Tamamlanmadı
- **4 Meta sabiti doğrulanmadı**: `META_API_VERSION`, `META_AUTHORIZE_URL`,
  `META_TOKEN_URL`, `META_SCOPES`. Resmî dokümana erişim hâlâ engelli
  (HTTP 403). Boş oldukları için sistem canlı moda geçmiyor.
- Gerçek bir Instagram hesabıyla uçtan uca test yapılmadı
- Docker imajları indirilemediği için konteyner içi test yapılamadı

## [0.5.0] - 2026-09-20 — CI/CD ve sunucu hazırlığı

### Eklendi
- **GitHub Actions CI**: testler, lint, migration uyum kontrolü, Docker imaj
  derlemesi ve **imajın gerçekten açıldığının doğrulanması**
- **Deploy iş akışı**: SSH üzerinden sunucuya kurulum. Kod ve imaj **gizli
  kalır**; gizli değerler **sunucuda üretilir**, hiçbir yere kopyalanmaz
- `ops/docker-compose.prod.yml`: üretim tanımı (sunucuda derleme yapmaz)
- `.dockerignore`: `.env`, testler ve derleme artıkları imaja girmez
- `OPERATIONS.md`, `FINAL_STATUS.md`, `DEPLOYMENT.md`

### Düzeltildi — üçü de yerel ortamda görülemezdi
1. **Dockerfile derleme sırası.** `pip install .` çalıştığında `app` klasörü
   henüz kopyalanmamıştı; kurulum "package directory 'app' does not exist"
   ile başarısız oluyordu. İmaj bu ortamda hiç derlenemediği için hata ilk
   kez CI'da görüldü.
2. **Docker imaj adında büyük harf.** `github.repository` değeri
   `BrandCoor/...` şeklinde büyük harf içeriyor; Docker imaj adları küçük
   harf olmak zorunda.
3. **Test veritabanı koruması.** Testler `POSTGRES_DB` ortam değişkeni
   tanımlıysa o veritabanına bağlanıyordu — kabukta üretim adı tanımlıysa
   testler üretim verisini silebilirdi. Artık test veritabanı zorla
   ayarlanıyor ve adı `_test` ile bitmiyorsa testler hiç başlamıyor.
4. **Testler şemayı migration ile kuruyor.** Önceden `create_all`
   kullanılıyordu; bozuk bir migration hiçbir testte yakalanmaz, hata ilk
   kez üretimde çıkardı.

### Doğrulandı
- CI'da 118/118 test geçti
- Lint temiz, migration'lar modellerle uyumlu
- **Docker imajı derlendi, kayıt defterine gönderildi ve konteyner
  gerçekten açılıp `/healthz` ucuna yanıt verdi** — projenin başından beri
  açık olan doğrulama boşluğu kapandı
- Bağımlılıklar erişilemezken `/healthz` yanıt verdi (onlara bakmadığı
  doğrulandı)

## [0.6.0] - 2026-09-20 — ÜRETİM KURULUMU TAMAMLANDI

Sistem Hostinger VPS'e (1990274) kuruldu ve dışarıdan doğrulandı.

### Doğrulandı (gerçek sunucuda)
- Sunucu içi sağlık kontrolü:
  `{"status":"ready","checks":{"database":{"ok":true},"redis":{"ok":true}}}`
- Sürüm bilgisi: `environment: production`, `publishing_enabled: false`
- **Dışarıdan HTTPS**: `https://agencycortex.tech/healthz` → HTTP 200
- HTTPS sertifikası otomatik alındı (Caddy), ikinci denemede hazırdı
- Veritabanı şeması migration ile kuruldu
- Gizli anahtarlar sunucuda üretildi — hiçbiri GitHub'a veya sohbete geçmedi

### Kurulum sırasında çözülen sorunlar
1. **GitHub kasasına anahtarın eksik ulaşması.** Çok satırlı anahtar metni
   üç denemede de eksik yapıştırıldı. Çözüm: tek satır base64 biçimi desteği
   eklendi; tek satır bölünemediği için insan hatası ortadan kalktı.
2. **Base64 tanıma hatası (kendi hatam).** Çözülen içeriğin
   `openssh-key-v1` ile başladığını varsaymıştım; aslında
   `-----BEGIN ... PRIVATE KEY-----` ile başlıyor. Üç biçim de yerelde test
   edilerek düzeltildi.
3. **Hostinger anahtarı çalışan sunucuya yazmıyor.** API anahtarı hesaba
   kaydediyor ancak `/root/.ssh/authorized_keys` dosyasına işlemiyor.
   Kullanıcı tarayıcı terminalinden ekledi.
4. **`authorized_keys` satır sonu hatası (kendi hatam).** Verdiğim
   `echo >>` komutu, dosya satır sonuyla bitmediği için anahtarı önceki
   satırın sonuna yapıştırdı. Dosya yedeklenip anahtarlar ayrıştırılarak
   yeniden yazıldı.

### Henüz doğrulanmadı
- Sunucu yeniden başladığında servislerin kendiliğinden gelmesi
  (`restart: unless-stopped` tanımlı, ancak gerçek yeniden başlatmayla
  test edilmedi)
- Yedekleme/geri yükleme testi (Aşama 10)
