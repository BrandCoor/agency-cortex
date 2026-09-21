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

## [0.7.0] - 2026-09-20 — Aşama 4: KPI motoru ve raporlar

### Eklendi
- **KPI motoru** (`services/kpi.py`): saf hesap katmanı — veritabanına,
  ağa veya yapay zekâya erişmez, böylece her hesap tek tek test edilebilir
- **Anomali tespiti** (`services/anomalies.py`): medyan + MAD yöntemi
- **Rapor üretimi** (`services/reports.py`): günlük, haftalık, aylık
- Rapor uçları: listeleme, ayrıntı, elle üretim
- Zamanlanmış işler: veri senkronu 6 saatte bir, günlük rapor 07:30,
  haftalık pazartesi 08:00, aylık ayın 1'i 09:00

### Rapor bölümleri
Dönem özeti · En iyi/en zayıf içerikler · Format analizi ·
Anormal değişimler · Bu dönemin önerileri (en fazla 3) ·
Veri kalitesi ve eksikler

### Korunan ürün kuralları (her biri testle sabitlendi)
- **Eksik veri sıfır değildir.** Hesaplanamayan değer `None` döner;
  rapor "erişim %0" yerine "veri yok" der
- Sıfıra bölme hata fırlatmaz, `0` da döndürmez
- Önceki dönem 0 iken yüzde değişim hesaplanmaz ("sonsuz artış" yazılmaz)
- Kanıt yetersizse yorum `claim_type="hypothesis"` olarak işaretlenir
- Eksik metrikler raporda açıkça listelenir
- Öneriler en fazla 3 madde
- Anomalide medyan kullanılır: tek viral içerik sonraki günleri
  "anormal düşük" göstermez
- Aynı dönemin raporu iki kez üretilmez

### Düzeltildi
- `assess_quality` eksik metrikleri başka bir fonksiyonun **yan
  etkisinden** okuyordu; çağrı sırası değişince eksikler sessizce boş
  görünüyordu. Artık beklenen metrikler açıkça isteniyor. Testin yakaladığı
  gerçek bir tasarım hatası.

### Doğrulandı
- 168/168 test geçti (önceki 118) — 50 yeni test
- CI'da testler, lint, migration uyumu ve Docker imajı geçti
- **Canlıya kuruldu**: `https://agencycortex.tech/healthz` → HTTP 200
- `environment: production`, `publishing_enabled: false`

## [0.8.0] - 2026-09-20 — Aşama 5: Claude API ve içerik senaryoları

### Eklendi
- **AI sağlayıcı katmanı** (`app/ai/`): ortak arayüz, Claude sağlayıcısı,
  sahte sağlayıcı, Manus ve Gemini durakları
- **18 alanlı içerik senaryosu şeması** (ürün tanımından birebir)
- **Bütçe kilidi**: aylık sınır aşılmışsa AI çağrısı başlamaz
- **Maliyet takibi**: her çağrı için model, istem sürümü, token, maliyet,
  süre, durum, hata kodu ve çıktı parmak izi kaydedilir
- İçerik üretim servisi: marka hafızası + kampanya + KPI + geçmiş performans
- AI uçları: sağlayıcı durumu, kullanım/bütçe, senaryo üretimi

### Anthropic API parametreleri (resmî dokümandan doğrulandı)
- Model: `claude-opus-5` — tarih soneki **eklenmez**
- `thinking={"type": "adaptive"}` — `budget_tokens` kaldırıldı, 400 döner
- `output_config={"effort": ...}` ve `output_config["format"]` ile JSON şema
- Assistant prefill Opus 5'te 400 döner — kullanılmıyor
- `stop_reason == "refusal"` içeriğe bakmadan **önce** kontrol ediliyor
- Tipli istisna zinciri (RateLimit → Timeout → Auth → APIStatus → Connection)
- Resmî SDK kullanılıyor, ham HTTP değil

### Korunan ürün kuralları
- Aynı fikir tüm platformlara **kopyalanmıyor**; her platform için ayrı uyarlama
- Ham sosyal medya API yanıtı AI'ya **gönderilmiyor**; önce kısa özet çıkarılıyor
- AI çıktısı doğrudan doğru kabul edilmiyor; şemayla doğrulanıyor
- Şema hatasında **sınırlı** tekrar (sonsuz döngü yok) — her deneme para harcar
- Başarısız deneme de ücretlidir; maliyeti kaydediliyor
- Bilinmeyen model maliyeti **tahmin edilmiyor**, hata veriyor
- Yasaklı ifadeler üretim sonrası denetleniyor
- Tüm senaryolar `human_approval_required=True`
- Manus ve Gemini hiçbir yetenek bildirmiyor (Manus dokümanına erişim engelli)

### Düzeltildi
- `provider_status()` sahte modda tüm sağlayıcıları "çalışıyor" gösteriyordu.
  Panel, gerçekte çalışmayan bir sağlayıcıyı hazır gibi gösterirdi. Artık
  **gerçek** durumu bildiriyor, ayrıca `using_fake` alanıyla hangi modda
  olunduğunu söylüyor. Testin yakaladığı dürüstlük hatası.

### Doğrulandı
- 220/220 test geçti (önceki 168) — 52 yeni test
- Bütçe aşıldığında hiçbir AI görevi oluşmadığı
- Geçen ayın harcamasının bu ayı kilitlemediği
- Başka müşterinin harcamasının sayılmadığı
- Başarısız denemelerin maliyetinin de kaydedildiği
- Opus 5 fiyatının doğru olduğu ($5/$25 per 1M)
- Model kimliğinde tarih soneki olmadığı
- Başka müşterinin marka bilgisinin isteme karışmadığı
- CI yeşil, canlıya kuruldu, `https://agencycortex.tech/healthz` → HTTP 200

## [0.9.0] - 2026-09-20 — Aşama 7: Onay akışı ve panel

### Eklendi
- **Onay durum makinesi** (`services/approvals.py`): 8 durum, tanımlı geçişler,
  her geçiş için gereken en düşük yetki
- **Onay anı kaydı (snapshot)**: onay, içeriğin o anki haline verilir
- Onay uçları: kuyruk, geçmiş, durum değiştirme, yayın kontrolü
- **Web paneli** (`app/panel/`): giriş, müşteri listesi, müşteri ekranı,
  senaryo inceleme, rapor görüntüleme, onay/ret formu

### Üç katmanlı yayın kilidi
1. `FEATURE_PUBLISHING_ENABLED` kapalı → geçiş reddedilir
2. Kilit açılsa bile onay kaydı yoksa reddedilir
3. Onaydan sonra içerik değiştiyse reddedilir (snapshot karşılaştırması)

Panel ayrıca "Yayınlandı" seçeneğini hiç göstermez.

### Panelde görünenler
- Onay bekleyen içerikler ve raporlar
- Marka riskleri ve doğrulanması gereken iddialar — **uyarı olarak**
- AI harcaması ve aylık bütçe
- Sahte sağlayıcı kullanılıyorsa **açık uyarı**
- Raporlarda "hipotez" etiketi
- Onay geçmişi: kim, ne zaman, hangi notla

### Doğrulandı
- 242/242 test geçti (önceki 220) — 22 yeni onay testi
- Onaylanmış ve planlanmış içerik bile **yayınlanamadı**
- Kilit açıldığında bile onay kaydı silinmişse yayın engellendi
- Onaydan sonra metin değiştirildiğinde yayın engellendi
- Karşıt test: değişmemiş içerik, kilit açıkken yayınlanabildi
- Taslaktan doğrudan onaya/yayına geçilemediği
- İzleyicinin hiçbir geçiş yapamadığı, editörün onay veremediği
- **Panel uçtan uca çalıştırıldı**: giriş → müşteri → senaryo → onay akışı
- Başka müşterinin sayfası ve var olmayan müşteri **aynı 404** yanıtını verdi
- Çıkıştan sonra oturumun kapandığı

## [0.7.1] - 2026-09-20 — Aşama 7 düzeltmesi

### Düzeltildi
- **Panel canlıda açılmıyordu.** Ters vekil (Caddy) yapılandırması yalnızca
  `/api/*`, `/healthz`, `/readyz` ve `/version` yollarını uygulamaya
  yönlendiriyordu; diğer tüm adresler Aşama 1'den kalma "Panel henüz
  kurulmadı." mesajını döndürüyordu. Kurulum kontrolü yalnızca `/healthz`
  adresine baktığı için hata fark edilmemişti.
- Kök adres (`/`) artık panele yönlendiriyor.
- Kurulan paket eksikti: `packages = ["app"]` alt paketleri (`app.api`,
  `app.panel` ...) kapsamıyordu. `app*` kalıbına çevrildi, Jinja şablonları
  paket verisi olarak eklendi. (Çalışmayı bozmuyordu çünkü uygulama kopyalanan
  kaynak ağacından çalışıyor; yine de yanlıştı.)

### Eklendi
- Sunucuda çalışan hesap komutu: `python -m app.cli.hesap ilk-yonetici`
  ve `sifre-degistir`. Şifre yalnızca ortam değişkeninden okunur, hiçbir
  zaman ekrana veya loga yazılmaz.
- Kurulum iş akışına "İlk yönetici hesabı" adımı. Şifre GitHub Secrets'tan
  gelir ve sunucuya yalnızca standart girdi (stdin) üzerinden aktarılır.
- Panelde şifre değiştirme sayfası (`/panel/sifre`). Mevcut şifre
  doğrulanmadan değişiklik yapılamaz.
- Panelde yeni müşteri ekleme formu. Ekleyen kişi otomatik olarak sahip
  (owner) olur; Türkçe harfler URL'ye uygun kısa ada çevrilir.
- **28 yeni test** (panel giriş/oturum/yetki/şifre + hesap komutu).

### Doğrulandı
- 270/270 test geçti (önceki 242 + 28 yeni).
- `ruff check app tests` temiz; `alembic check` bekleyen değişiklik yok.
- Kurulum iş akışının ilk yönetici adımındaki komut, gerçek PostgreSQL
  üzerinde birebir çalıştırıldı: hesap açıldı, ikinci çalıştırmada
  "ATLANDI" dedi (tekrar çalıştırmaya güvenli).
- Kurulum kontrolü artık `/panel/giris` sayfasını dışarıdan çekiyor ve
  giriş formunu bulamazsa kurulumu HATA ile bitiriyor.

### Düzeltildi (ikinci tur)
- **Düzeltilmiş Caddyfile sunucuya gitti ama devreye girmedi.** Caddyfile
  konteynere bağlama (bind mount) ile veriliyor; dosya değişse bile
  `docker compose up -d` caddy servisinin tanımını değişmemiş görüp
  konteynere dokunmuyor, Caddy de yapılandırmayı yalnızca açılışta
  okuduğu için eski ayarla devam ediyordu. Kurulum akışına "Caddy
  yapılandırmasını yeniden yükle" adımı eklendi: önce `caddy validate`
  ile doğrulanıyor, sonra kesintisiz `caddy reload` yapılıyor; reload
  başarısız olursa konteyner yeniden başlatılıyor.
- Bu hata, yeni eklenen panel kontrolü sayesinde **kurulumu kırmızıya
  düşürerek** yakalandı — sessizce geçmedi.

### Düzeltildi (üçüncü tur)
- **Yeniden yükleme adımı eklendi ama hiç çalışmadı.** Uzak betikler
  sunucuya `bash -s` ile standart girdiden veriliyor. `docker compose
  exec -T` de standart girdiyi okuduğu için betiğin geri kalanını
  yutuyordu: `caddy validate` çalıştı ("Valid configuration"), ondan
  sonraki `caddy reload` satırı hiç yürütülmedi. Kurulum kaydında da
  reload çıktısı yok. Tüm `docker compose exec -T` çağrılarına
  `</dev/null` eklendi.
- Hata yerelde birebir üretilip doğrulandı: `printf 'echo A\ncat >/dev/null\necho B\n' | bash -s`
  yalnızca `A` yazıyor; `</dev/null` eklenince `B` de yazıyor.

## [0.7.2] - 2026-09-21 — Giriş tanılaması

### Eklendi
- `python -m app.cli.hesap tanilama` komutu. Giriş çalışmadığında nedenini
  **şifrenin kendisini hiçbir yere yazmadan** bildirir: şifrenin uzunluğu,
  başında/sonunda boşluk olup olmadığı, ASCII dışı karakter sayısı, kayıtlı
  e-posta ve saklanan özetin verilen şifreyle uyuşup uyuşmadığı.
- Kurulum iş akışına isteğe bağlı "Hesap tanılama" adımı
  (`tanilama: EVET` girdisiyle çalışır).

### Düzeltildi
- **Başında/sonunda boşluk olan şifre artık reddediliyor.** Kopyala-yapıştırda
  kaçan bir boşluk hesabı açıyor ama girişi kalıcı olarak bozuyordu:
  kullanıcı boşluksuz yazıyor, özet tutmuyordu. Yerelde birebir üretildi.
- **`sifre-degistir` şifreyi sessizce kırpıyordu.** Ortam değişkeni okuyucusu
  baştaki/sondaki boşlukları siliyordu; bu, kullanıcının bildiği şifre ile
  saklanan özetin farklılaşmasına yol açardı. Artık ham okunuyor ve boşluklu
  şifre açıkça reddediliyor. Bu tutarsızlığı yeni yazılan test yakaladı.

### Doğrulandı
- 277/277 test geçti (önceki 270 + 7 yeni).
- Tanılama üç senaryoda gerçek PostgreSQL üzerinde çalıştırıldı: sondaki
  boşluk, e-posta uyuşmazlığı, her şeyin doğru olduğu durum. Üçünde de doğru
  sonucu verdi ve şifreyi çıktıya yazmadı.

## [0.7.3] - 2026-09-21 — Türkçe harf içeren şifre düzeltmesi

### Düzeltildi
- **Şifresinde Türkçe harf olan kullanıcı panele giremiyordu.** `ğ` gibi
  harfler iki farklı Unicode gösterimiyle yazılabiliyor; ekranda aynı
  görünüyor ama bayt düzeyinde farklılar, dolayısıyla özetleri de farklı
  çıkıyordu. Şifreler artık hem özetlenirken hem doğrulanırken NFKC
  biçimine çevriliyor (RFC 8265 / PRECIS OpaqueString yaklaşımı).
  Gerekçe: DECISIONS.md K-022.

### Nasıl bulundu
- Yeni eklenen "tanilama" komutu sunucuda çalıştırıldı. Şifrenin kendisi
  hiçbir yere yazılmadan şu üç gerçeği verdi: şifre 12 karakter, boşluk
  yok, **1 adet ASCII dışı karakter var**, ve saklanan özet gizli değerle
  **uyuşuyor**. Son madde sunucu tarafının doğru olduğunu kanıtladı;
  geriye tek olasılık olarak gösterim farkı kaldı. Varsayım yerelde
  birebir üretilip doğrulandı.

### Doğrulandı
- 281/281 test geçti (önceki 277 + 4 yeni).
- Aynı şifrenin iki gösterimiyle de panel girişi yapılabiliyor (uçtan uca
  test). Farklı şifrelerin birbirinin yerine geçmediği ayrıca test edildi.
- Mevcut hesap bozulmuyor: kayıtlı özet zaten NFKC biçiminde üretilmişti.

### Düzeltildi (ek)
- **Kurulumdaki SSH hata mesajı yanıltıcıydı.** Sunucuya hiç ulaşılamadığı
  durumda (bağlantı zaman aşımı) "anahtar kabul edilmedi" yazıyordu. Bunlar
  farklı sorunlardır ve çözümleri de farklıdır. Artık 22. kapının açık olup
  olmadığı ayrıca ölçülüyor ve iki durum ayrı ayrı bildiriliyor.
  (21 Eylül'de gerçek bir geçici kesintide bu mesaj yanlış yöne sevk etti;
  bağlantı ikinci denemede sorunsuz kuruldu.)

## [0.7.4] - 2026-09-21 — Şifre belirleme bağlantısı

### Eklendi
- **Tek kullanımlık şifre belirleme bağlantısı** (`/panel/sifre-belirle`).
  Kullanıcı şifresini kendi tarayıcısında belirliyor; şifre hiçbir aktarım
  yolundan geçmiyor. Gerekçe: DECISIONS.md K-023.
  - Jeton 32 bayt rastgele, 30 dakika geçerli, **tek kullanımlık**.
  - Jetonun kendisi değil, yalnızca SHA-256 özeti saklanıyor.
  - Sayfayı açmak veya hatalı şifre girmek bağlantıyı harcamıyor; yalnızca
    başarılı kayıt harcıyor.
  - Şifre belirlenince kullanıcı doğrudan içeri alınıyor.
- `kurtarma-bagi` komutu: bu bağlantıyı sunucuda üretir.
- `giris-denemesi` komutu: üretimdeki girişi sunucunun içinden bir kez
  dener. Sorunun uygulamada mı yoksa tarayıcı tarafında mı olduğunu kesin
  olarak ayırır.
- Kuruluma isteğe bağlı "Şifre belirleme bağı" adımı (`kurtarma: EVET`).

### Doğrulandı
- 294/294 test geçti (önceki 281 + 13 yeni).
- Türkçe harfli şifre (`Çiğdemİş4103+`) bu akışla belirlenip uçtan uca
  giriş yapılabiliyor.
- Bağlantının ikinci kez çalışmadığı, pasif kullanıcıda çalışmadığı,
  jetonun Redis'te düz metin saklanmadığı ayrı ayrı test edildi.

### Düzeltildi (ek)
- **Şifre belirleme bağlantısının ömrü çok kısaydı.** 30 dakika, bağlantının
  üretilip kullanıcıya ulaşması ve kullanılması için pratikte yetmiyordu.
  Varsayılan 24 saate çıkarıldı (`KURTARMA_OMUR_SAAT` ile 1-72 saat arası
  ayarlanabilir). Bağlantı **tek kullanımlık** olmaya devam ediyor: kullanıldığı
  anda geçersizleşir, yani asıl koruma süreden değil tek kullanımlılıktan
  geliyor.

## [0.10.0] - 2026-09-21 — Aşama 10: Yedekleme

### Eklendi
- **Günlük otomatik veritabanı yedeği** (her gün 03:30, 14 gün saklama).
  - `ops/yedek_al.sh` — yedek önce geçici dosyaya yazılır, başarılıysa asıl
    adına taşınır; böylece yarım kalan bir yedek "geçerli yedek" sanılmaz.
    Dosya izni 600, çok küçük dosya geçersiz sayılır, eskiler **ancak yeni
    yedek başarılı olduktan sonra** silinir.
  - `ops/yedek_dogrula.sh` — yedeği **ayrı ve geçici** bir veritabanına geri
    yükler, tablo ve kullanıcı sayar, sonra o veritabanını siler. Üretim
    veritabanına dokunmaz. Her pazar 04:00'te otomatik çalışır.
  - `ops/yedek_geri_yukle.sh` — üretime geri yükler. Önce mevcut durumun
    yedeğini alır, uygulamayı durdurur, `GERI YUKLE` onayı ister, işlem
    sonrası sistemi başlatıp sağlığını doğrular.
- Kuruluma "Yedekleme kur ve doğrula" adımı: her kurulumda görevler kurulur,
  bir yedek alınır ve **gerçekten geri yüklenebildiği sınanır.**

### Doğrulandı
- Gerçek PostgreSQL üzerinde uçtan uca denendi: yedek alındı → **tüm şema
  silindi** (0 tablo) → yedekten geri yüklendi (29 tablo) → kullanıcı kaydı
  ve şema sürümü geri geldi.
- Crontab mantığı ayrıca sınandı: mevcut görevler korunuyor, yedek görevi
  tekrar tekrar eklenmiyor, boş crontab'da da çalışıyor.
- Geri yükleme betiğinin onay koruması sınandı: yanlış onayda hiçbir şey
  değişmiyor.

### Henüz eksik (açıkça)
- **Yedekler sunucu dışına kopyalanmıyor.** Sunucu tamamen kaybolursa
  yedekler de kaybolur. Bunun için bir depolama hesabı gerekiyor.

### Düzeltildi (yedekleme, ilk kurulumda yakalandı)
- **Yedekleme betikleri `.env` dosyasını kabukla çalıştırıyordu.** Üretimdeki
  `.env` boşluk içeren bir değer barındırdığı için betik
  `Cortex: command not found` hatasıyla durdu. Asıl sorun daha derindi:
  bir `.env` dosyasını kabukla okumak, içindeki her satırın **komut olarak
  çalıştırılması** demektir. Artık dosya yalnızca okunuyor; gereken iki
  değer metin olarak ayıklanıyor, hiçbir şey çalıştırılmıyor.
- Okuyucu şu durumlara karşı ayrıca sınandı: boşluklu değer, tırnaklı değer,
  içinde `'` `"` `$` `` ` `` geçen parola, başında boşluk olan satır,
  olmayan değer, ve `.env` içine komut yerleştirme denemesi (çalışmadı).

### Düzeltildi (yedekleme, ikinci tur)
- **Yedek doğrulaması sessizce atlanıyordu ve kurulum yine de yeşil
  görünüyordu.** Yedek alınıyordu, ama `pg_dump` standart girdiyi okuyup
  kurulum betiğinin geri kalanını yutuyordu; `yedek_dogrula.sh` hiç
  çalışmıyordu. Kayıtta yedek satırlarından sonra doğrulama çıktısı yoktu.
  - Betiklerdeki tüm `docker compose exec -T` çağrılarına `</dev/null`
    eklendi (girdiye gerçekten ihtiyaç duyan `pg_restore < dosya` hariç).
  - Kurulum adımı artık uzak betiği `bash -s` ile değil **dosyadan**
    çalıştırıyor; bu tuzağın kaynağı ortadan kalktı.
  - Adım artık çıktıda üç **kanıt izi** arıyor. İzlerden biri yoksa kurulum
    HATA veriyor. Böylece "bir alt adım sessizce atlandı" durumu yeşil
    görünemez.
- Yerelde birebir kanıtlandı: stdin'i yutan sahte bir `docker` ile
  düzeltilmiş betik sonraki adımı çalıştırıyor, eski betik çalıştırmıyor.

## [0.11.0] - 2026-09-21 — Panel: marka bilgileri ve ekip yönetimi

### Eklendi
- **Marka bilgileri sayfası** (`/panel/musteri/<id>/marka`). Marka adı,
  sektör, web sitesi, açıklama, konuşma tonu, hedef kitle, yasaklı ve
  tercih edilen ifadeler, notlar. Yasaklı/tercih edilen ifadeler her satıra
  bir tane yazılır. Değiştirmek için en az **stratejist** yetkisi gerekir.
- **Ekip sayfası** (`/panel/musteri/<id>/ekip`). Üyeleri listeler, kişi
  ekler ve çıkarır. Yönetmek için en az **yönetici** yetkisi gerekir.

### Neden
Bu iki iş daha önce panelde yoktu; ajans sahibi marka bilgisi girmek veya
ekibine kişi eklemek için bana bağımlıydı. Kendi ekibini kendi yönetmeli.

### Güvenlik sınırları (hepsi test edildi)
- Yetki **sunucuda** doğrulanıyor. Formun kapalı görünmesi tek başına koruma
  sayılmıyor: izleyici yetkisiyle gönderilen istek 403 alıyor.
- **Kimse kendi yetkisinden yüksek bir yetki veremiyor.** Yönetici birini
  sahip yapıp kendini aşamıyor.
- Kendinden yüksek yetkili biri ekipten çıkarılamıyor.
- Kimse kendini ekipten çıkaramıyor (müşteri sahipsiz kalmasın).
- Üye olunmayan müşterinin sayfaları **404** dönüyor (403 değil — 403 o
  müşterinin varlığını ele verirdi).

### Doğrulandı
- 312/312 test geçti (önceki 297 + 15 yeni).
- `ruff check` temiz, `alembic check` bekleyen değişiklik yok.

## [0.11.1] - 2026-09-21 — Panel: bağlı hesaplar sayfası

### Eklendi
- **Bağlı hesaplar sayfası** (`/panel/musteri/<id>/hesaplar`). Bağlı hesapları,
  son veri çekim zamanını, profesyonel/kişisel ayrımını ve varsa senkronizasyon
  hatasını gösterir.

### Dürüstlük kuralı (test edildi)
- **"Bağla" düğmesi yalnızca platform gerçekten hazırsa gösterilir.**
  - Sistem sahte sağlayıcı ile çalışıyorsa düğme yok; bunun yerine "gerçek
    hesap bağlanamaz" uyarısı var.
  - Canlı modda Meta ayarları eksikse düğme yok; bunun yerine **neden**
    bağlanamadığı ve **hangi ayarların eksik olduğu** tek tek yazılıyor.
  - Düğme görünmese bile istek elle gönderilebilir; sunucu bu isteği
    **409** ile reddediyor. Her iki durum da ayrı test edildi.
- Hesap bağlamak için en az **yönetici** yetkisi gerekiyor (403 ile test edildi).
- Başka müşterinin hesapları bu sayfada görünmüyor (izolasyon testi).

### Doğrulandı
- 325/325 test geçti (önceki 312 + 13 yeni).
