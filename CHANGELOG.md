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

## [0.11.2] - 2026-09-21 — Panel: kampanya yönetimi

### Eklendi
- **Kampanya sayfası** (`/panel/musteri/<id>/kampanya`). Kampanya adı, hedef,
  başlangıç ve bitiş tarihi. Eklemek/silmek için en az **stratejist** yetkisi.

### Kurallar (hepsi test edildi)
- Kampanya bir **markaya bağlıdır**; marka girilmeden kampanya oluşturulamaz
  ve form gösterilmez.
- **Bitiş tarihi başlangıçtan önce olamaz.** Sessizce kabul edilseydi sonradan
  üretilen rapor anlamsız olurdu. Aynı gün başlayıp biten kampanya geçerlidir.
- Tarayıcı dışından gelen bozuk tarih kampanyayı engellemiyor; tarih boş
  sayılıyor.
- **İzolasyon:** başka müşterinin kampanyası, kimliği bilinse bile
  silinemiyor (404). Çalışma alanı kontrolü sorgunun içinde yapılıyor.

### Doğrulandı
- 338/338 test geçti (önceki 325 + 13 yeni).

## [0.12.0] - 2026-09-21 — Panel arayüzü ve API anahtarları

### Değişti
- **Panel arayüzü yeniden düzenlendi.** Solda kalıcı kenar menü; seçili
  müşterinin sayfaları grup halinde listeleniyor ve bulunduğunuz sayfa
  vurgulanıyor. Telefonda menü üste taşınıyor.
- Müşteri ekranına **özet kutuları** eklendi: onay bekleyen sayısı, bağlı
  hesap sayısı, bu ayki AI harcaması, marka bilgisi girilmiş mi.
- Form ve düğme görünümü elden geçirildi (odak halkası, birincil düğme,
  tehlikeli işlem rengi).

### Eklendi
- **Sistem ayarları sayfası** (`/panel/ayarlar`) — API anahtarları panelden
  giriliyor. Gerekçe: DECISIONS.md K-024.
  - Değer **Fernet ile şifrelenerek** saklanıyor.
  - Değer **ekrana geri yazılmıyor**; yalnızca son 4 karakter gösteriliyor.
  - Değer **loglanmıyor**; yalnızca hangi ayarın kim tarafından değiştiği.
  - Sayfa yalnızca sistem yöneticisine açık; yetkisiz kişi **404** alıyor.
  - Panelden girilen değer, sunucudaki ortam değişkenini geçiyor.
  - Şifre çözülemezse (ör. `ENCRYPTION_KEY` değiştiyse) uydurma değer
    döndürmek yerine "tanımsız" deniyor.
- `system_settings` tablosu ve migration.

### Doğrulandı
- 351/351 test geçti (önceki 338 + 13 yeni).
- Anahtarın veritabanında düz metin olmadığı, yanıtlarda geçmediği ve
  loglara düşmediği ayrı ayrı test edildi.

## [0.13.0] - 2026-09-21 — Doğrulanmış API entegrasyonları

Kullanıcının sağladığı "Resmî API Teknik Referansı" belgesi (21 Eylül 2026)
esas alındı. Belgedeki her değer kaynak URL'siyle birlikte koda yazıldı;
belgede "DOKÜMANDA BULUNAMADI" diyen hiçbir değer uydurulmadı.

### Eklendi
- **Manus API v2 sağlayıcısı** (`app/ai/manus.py`). Artık taslak değil,
  çalışan entegrasyon. Gerekçe: DECISIONS.md K-027.
  - Base URL `https://api.manus.ai`, başlık `x-manus-api-key`
  - `task.create` → `task.detail` → `task.listMessages` yaşam döngüsü
  - v2 durumları: running / stopped / waiting / error
  - Dokümandaki 6 hata kodu tanınıyor; `rate_limited` ve `internal`
    tekrar denenebilir olarak işaretli
  - **`waiting` durumunda otomatik onay verilmiyor** (K-028)
  - Polling aralığı 5 sn — bu **bizim kararımız**, dokümanda yok; 100/dk
    limitine göre seçildi (dakikada 12 istek)
  - Maliyet: Manus kredi ile çalışıyor ve dokümanda para karşılığı yok;
    bu yüzden maliyet **uydurulmuyor**, boş bırakılıyor
- **Manus webhook imza doğrulaması** (`app/ai/manus_webhook.py`).
  RSA-SHA256, 2048-bit, `{timestamp}.{url}.{body_sha256_hex}` biçimi,
  5 dakikalık tekrar oynatma penceresi.

### Değişti
- **7 Meta sabitinden 5'i dolduruldu** (K-026). Kalan 3'ü (App ID, App
  Secret, Redirect URI) dokümandan alınamaz — sizin Meta uygulamanıza ait.
- **Gemini fiyatları eklendi** (K-029). 8 model fiyatlandı.

### Doğrulandı
- 385/385 test geçti (önceki 351 + 34 yeni).
- Webhook imzası **gerçek 2048-bit RSA anahtar çifti** ile test edildi:
  geçerli imza kabul, gövde değiştirilince ret, URL değiştirilince ret,
  başka anahtarla imzalanınca ret, 5 dakikadan eski istek ret.
- v1 başlığının (`API_KEY`) kullanılmadığı ayrıca test edildi.

## [0.13.1] - 2026-09-21 — Bağlantı sınaması

### Eklendi
- **"Bağlantıyı sına" düğmesi** (Sistem ayarları). Kaydedilen anahtarın
  gerçekten çalıştığı sunucudan doğrulanıyor.
  - **Manus:** `usage.availableCredits` ile gerçek API çağrısı. Bu uç salt
    okumadır ve **kredi harcamaz**; sınama için görev oluşturulmuyor.
    Kredi durumu ekranda gösteriliyor.
  - **Meta:** yalnızca **biçim** denetimi. Meta'nın kimlik bilgilerini tek
    başına doğrulayan salt okuma bir ucu elimizdeki resmî referansta
    tanımlı değil; tahminle uç çağırmak yerine bunun canlı sınama
    **olmadığı** ekranda açıkça yazılıyor.
  - **Claude:** yalnızca kayıtlı mı diye bakılıyor. En ucuz canlı sınama
    bile ücret doğurur; kullanıcının haberi olmadan harcama yapılmıyor.
- Geçersiz anahtarda mesaj **ne yapılacağını** söylüyor ("yeni bir anahtar
  üretip tekrar girin"), yalnızca "hata" demiyor.

### Güvenlik (test edildi)
- Sınama sonucu **hiçbir yolda** anahtarı içermiyor — başarı, kimlik
  doğrulama hatası ve hız sınırı yollarının üçü de ayrı test edildi.
  (Manus hata mesajının içine anahtar konsa bile sızmıyor.)
- Sınama yalnızca sistem yöneticisine açık; başkası **404** alıyor.

### Doğrulandı
- 399/399 test geçti (önceki 385 + 14 yeni).
- Bir testim kendi kendini vurdu ve düzeltildi: `httpx` yaması
  TestClient'ın panele yaptığı isteği de yakalıyordu. Yama yalnızca
  `api.manus.ai` çağrılarını kapsayacak şekilde daraltıldı.

## [0.9.0] - 2026-09-21 — AI bütçesi atomik hale getirildi

n8n iş akışları aynı anda çalışacağı için, bütçe kilidinin eşzamanlılık
altında doğru çalışması şart. Mevcut kilit doğru çalışmıyordu.

### Düzeltildi
- **AI bütçe kilidi atomik değildi (kritik).** Eski akış: topla →
  karşılaştır → AI'yi çağır → maliyeti yaz. Aynı anda başlayan iki iş aynı
  toplamı okuyor, ikisi de "bütçe var" diyor ve bütçe aşılıyordu. Maliyet
  ancak çağrı **bittikten sonra** yazıldığı için ikinci iş birincisini hiç
  göremiyordu.
- Yeni akış (`backend/app/services/ai_butce.py`): müşteri satırı
  `SELECT ... FOR UPDATE` ile kilitlenir → toplam kilit altında okunur →
  tahmini tutar **açık rezervasyon** olarak yazılır → kilit bırakılır →
  AI çağrılır → rezervasyon gerçek maliyete çekilir.
- Kilit yalnızca milisaniyeler tutuluyor; 15 dakika süren bir Manus
  araştırması aynı müşterinin diğer işlerini bekletmiyor.

### Eklendi
- `ai_cost_events.reserved_until` sütunu (migration `4c1d6a2f9b30`).
  NULL ise kayıt kesinleşmiştir; dolu ise çağrı hâlâ sürüyordur.
- Rezervasyonun 45 dakikalık ömrü var. Süreç çökerse rezervasyon bütçeyi
  sonsuza kadar tutmuyor; süresi geçmiş rezervasyon toplama katılmıyor.
- `AIProvider.tahmini_ust_maliyet()`: çağrıdan önce en kötü durum maliyet
  tahmini. Çıktı `max_tokens` üzerinden hesaplanıyor — az tahmin etmek
  bütçenin aşılması demek olurdu.
- Sağlayıcı maliyet bildirmezse rezervasyon **silinmiyor**, tahminle
  kesinleşiyor. Bilinmeyen maliyeti sıfır saymak bütçeyi sessizce bozardı.

### Bilinen sınır (gizlenmiyor)
- **Manus harcaması USD bütçesine girmiyor.** Manus kredi ile çalışıyor,
  resmî dokümanda kredinin USD karşılığı yok. Uydurma fiyat yazmak yerine
  bu sınır açıkça bırakıldı; Manus'un kendi kredi sınırı geçerli.
  (Bkz. DECISIONS.md K-031.)

### Doğrulandı
- 407/407 test geçti (önceki 399 + 8 yeni).
- Eşzamanlılık testi **iki ayrı veritabanı bağlantısı** açıyor: 10 USD
  bütçe, her iş 6 USD tahmin ediyor. Tek iş geçiyor, ikincisi reddediliyor.
- **Testin gerçekten bir şey ölçtüğü kanıtlandı:** `with_for_update()`
  kaldırılınca test düşüyor ("Iki is de gecti; butce asildi: [UUID, UUID]").
  İlk yazdığım hâli kilit olmadan da geçiyordu — yani hiçbir şey
  kanıtlamıyordu; okuma ile yazma arasına bilerek gecikme konarak yarış
  penceresi ölçülebilir hâle getirildi.
- `alembic check`: yeni migration modelle örtüşüyor, fark yok.

## [0.10.0] - 2026-09-21 — Kullanıcı yönetimi, panel yenileme ve n8n

### Eklendi — Kullanıcı yönetimi
- **Kullanıcılar** sayfası (sistem yöneticisine açık): hesap açma, ad
  düzenleme, etkin/pasif yapma, sistem yöneticiliği verme/alma, silme.
- **Kullanıcı detay sayfası**: kişinin hangi müşteride hangi yetkiye sahip
  olduğu tek ekranda.
- **Şifre belirleme bağı**: yönetici şifre belirlemez. Hesap kimsenin
  bilmediği bir değerle kilitli açılır; kişi şifresini tek kullanımlık
  bağdan kendisi belirler. Bağ 24 saat geçerli ve **bir kez** kullanılır.
- **Ekip sayfasında yetki değiştirme**: daha önce yalnızca ekle/çıkar vardı.
- Her değişiklik **denetim kaydına** yazılıyor — ne değiştiği yazılıyor,
  **değerler yazılmıyor**.

### Kilitlenme koruması
- Son etkin sistem yöneticisi silinemez, pasifleştirilemez, yetkisi alınamaz.
- Kimse kendi hesabını silemez, kendini pasifleştiremez, kendi yönetici
  yetkisini alamaz, kendi müşteri yetkisini değiştiremez.
- Bu kurallar olmadan tek bir yanlış tıklama panele girişi tamamen kapatırdı.

### Panel yenilendi
- Yeni düzen: yapışkan yan menü, üst yol çubuğu, gerçek SVG simgeler
  (emoji yerine), özet kutuları, hover'lı tablolar, boş durum ekranları.
- Açık/koyu tema cihaz ayarına göre.
- Telefon genişliğinde menü üste taşınıyor.

### Eklendi — n8n otomasyonu
- **n8n üretim kurulumu**: `n8n.agencycortex.tech`, sürüm `2.39.10`
  (Docker Hub'da `stable` etiketinin karşılığı; tahmin edilmedi, doğrulandı).
  Kendi PostgreSQL veritabanında çalışıyor.
- **DNS**: `n8n` A kaydı eklendi (mevcut kayıtlara dokunulmadı).
- **Makine kimliği**: n8n insan hesabı kullanmıyor. `X-API-Key` ile çalışan,
  kapsamı müşteri bazında sınırlı, iptal edilebilir kendi kimliği var.
  Anahtar veritabanında açık saklanmıyor.
- **Makine API'si** (`/api/v1/makine/...`): kimlik, müşteri bağlamı,
  çalıştırma başlat/bitir.
- **Otomasyon paneli**: 4 iş akışının müşteri bazında açık/kapalı durumu,
  son çalışma zamanı, başarı/hata ve hata mesajı. **n8n'e girmeye gerek yok.**
- İş akışları varsayılan **KAPALI**. Panelden açılmadan çalışmıyor.

### Güvenlik
- **İstekle gelen `workspace_id`ye güvenilmiyor.** Her makine isteğinde
  anahtarın o müşteride yetkili olup olmadığına ayrıca bakılıyor; değilse
  **404** dönüyor (403 değil — 403 o müşterinin varlığını ele verirdi).
- n8n arayüzünün önünde ikinci bir kilit (HTTP basic auth) var. Kurulum
  adımı dışarıdan **HTTP 401** bekliyor; 200 dönerse kurulum **duruyor**.
  Gerekçe: ilk açan kişi n8n'in sahibi olur (bkz. DECISIONS.md K-034).
- Makine API'si n8n'e **hiçbir gizli bilgi vermiyor** — erişim jetonu,
  şifre veya anahtar dönmüyor. Test ediliyor.
- n8n kapı şifresi panelde **yalnızca sistem yöneticisine** gösteriliyor.

### Yedekleme
- n8n veritabanı da yedekleniyor (ayrı dosya olarak, bağımsız geri
  yüklenebilsin diye). n8n henüz kurulu değilse atlanıyor, hata verilmiyor.

### Doğrulandı
- 458/458 test geçti (önceki 407 + 51 yeni).
- Migration ileri **ve geri** çalıştırıldı; enum türleri geri alımda
  düşürülüyor — aksi halde tekrar ileri alım "tür zaten var" hatası veriyordu
  (bu hata gerçekten görüldü ve düzeltildi).
- `alembic check`: model ile migration örtüşüyor.
- Anahtarın gösterilen öneki gizli kısmından 12 karakter sızdırıyordu;
  biçim `acx_<açık kimlik>_<gizli>` olarak değiştirildi ve test eklendi.

### Henüz yapılmadı (gizlenmiyor)
- **İş akışlarının kendisi (WF-01..04) n8n'de henüz kurulu değil.** Altyapı
  hazır: kimlik, yetki, çalıştırma kaydı ve panel çalışıyor; akışların
  n8n tarafındaki tasarımı bir sonraki adımda.
- **Panelden elle çalıştırma düğmesi yok.** Akışlar n8n'de oluşmadan böyle
  bir düğme hiçbir şey yapmazdı; çalışmayan düğme konulmadı.

## [0.10.1] - 2026-09-21 — Kurulum sırasında yakalanan iki hata

Sistem canlıya alındı. Kurulum ilk denemede durdu, ikincisinde yeşil
göründü ama **gizli bir arıza taşıyordu**. İkisi de düzeltildi.

### Düzeltildi — 1: kurulum "Error: EOF" ile durdu
`caddy hash-password`, terminal değilse şifreyi stdin'den
`ReadBytes('\n')` ile okuyor. `printf '%s'` satır sonu göndermediği için
okuma EOF ile bitiyordu. `printf '%s\n'` yapıldı.
(Caddy v2.10 kaynağından doğrulandı, tahmin edilmedi.)

### Düzeltildi — 2: n8n kapısı hiçbir şifreyle açılmayacaktı
**Kurulum yeşil görünüyordu.** Dışarıdan HTTP 401 dönüyordu, yani kilit
duruyordu — ama doğru şifre de kabul edilmiyordu.

Kök neden: bcrypt özeti `$2a$14$...` biçiminde. Docker Compose, `.env`
içindeki `$` işaretini **değişken başı** sayıyor ve `$14`'ten sonrasını
tanımsız değişken sanıp siliyor. Kurulum logundaki
`"... variable is not set"` uyarısı tam buydu.

Ölçüldü (yerel `docker compose` ile, iki hal yan yana):

| `.env` içindeki hâli | Konteynere giden değer |
|---|---|
| kaçışsız | `$2a$14` — **özet yok** |
| `$$` kaçışlı | tam özet |

Düzeltmeler:
- Özet `.env`'e `$$` kaçışıyla yazılıyor.
- Sunucuda duran kaçışsız özet tespit edilip yenileniyor.
- Compose'un değeri bütün geçirdiği **uzunlukla** doğrulanıyor (özet
  basılmadan).

### Eklendi — bu hatayı bir daha gizlenemez kılan adım
Kurulum artık kapının **açıldığını da** kanıtlıyor:

- şifresiz istek → **HTTP 401** beklenir (kilit duruyor)
- doğru şifreyle istek → **HTTP 200** beklenir (kapı açılıyor)

İkincisi olmasaydı bozuk özet fark edilmezdi: 401 dönen bir kapı
"çalışıyor" gibi görünür. Şifre sunucuda kalıyor — GitHub'a taşınmıyor,
loga basılmıyor, `curl` komut satırına yazılmıyor (`--netrc-file`).

### Canlı durum (kurulum çıktısından)
```
BASARILI: n8n ic agdan yanit veriyor.
BASARILI: https://n8n.agencycortex.tech sifresiz ACILMIYOR (HTTP 401).
BASARILI: dogru sifreyle aciliyor (HTTP 200).
```

## [0.11.0] - 2026-09-21 — Dört iş akışı ve otomatik n8n kurulumu

### Eklendi — İş akışları çalışır durumda
Dört akışın mantığı Agency Cortex'te (`services/is_akislari.py`):

| Akış | Ne yapar | Ne zaman |
|---|---|---|
| **WF-01** Günlük sosyal zekâ | Bağlı hesapların içerik ve metriklerini çeker | Her gün 07:00 |
| **WF-02** Trend araştırması | Sektör trendlerini araştırır, bulguları kaydeder | Her gün 09:00 |
| **WF-03** İçerik zekâsı | Son bulgulardan içerik senaryosu önerir | Pzt/Çar/Cum 10:00 |
| **WF-04** Haftalık rapor | Haftalık raporu üretir | Her pazartesi 08:00 |

**Sessiz başarı yok.** Veri yoksa akış "yapılacak iş yoktu" der ve nedenini
yazar; sahte sonuç üretmez:
- Bağlı hesap yoksa WF-01 veri uydurmaz.
- Marka girilmemişse WF-02 araştırma yapmaz.
- Trend bulgusu yoksa WF-03 içerik üretmez — bulgusuz içerik tahmin olurdu.
- Hiçbir hesaptan veri çekilemezse WF-01 **hata verir**, "başarılı" demez.

**Üretilen her şey taslaktır** ve insan onayı bekler.

### Eklendi — n8n kurulumu kendi kendine tamamlanıyor
- Dört iş akışı dosyası depoda (`ops/n8n/akislar/`).
- Sunucuda 5 dakikada bir çalışan bir görev, n8n'e iş akışlarını yüklüyor
  ve yayınlıyor. Kurulduğunda kendini durduruyor.
- **Gerekçesi:** n8n'e iş akışı yüklemek için n8n'de sahip hesabı olması
  şart; o hesabı kullanıcı ilk girişinde oluşturuyor. Tek seferlik bir
  kurulum adımı o anda başarısız olur ve bir daha denenmezdi.
- Kullanıcı n8n hesabını oluşturuyor; birkaç dakika sonra akışlar
  kendiliğinden kuruluyor. **Başka bir şey yapması gerekmiyor.**
- Agency Cortex anahtarı n8n'e **şifreli kimlik bilgisi** olarak gidiyor.
  `$env` erişimi açılmadı — açılsaydı iş akışı düzenleyen herkes
  veritabanı şifresi dâhil tüm ortam değişkenlerini okuyabilirdi.

### Eklendi — Panelden elle çalıştırma
- Her akışın yanında **"Şimdi çalıştır"** düğmesi (en az stratejist yetkisi).
- İş **kuyruğa alınıyor**, panelde beklenmiyor: bir araştırma akışı
  dakikalarca sürebilir ve tarayıcı zaman aşımına uğrardı.
- Kuyruk çalışmıyorsa bu **gizlenmiyor**; çalıştırma "hata" olarak
  kapanıyor ve kullanıcı "başladı" sanmıyor.

### Eklendi — n8n bağlantı durumu panelde
Üç aşama gösteriliyor ve **ölçülen** bir şeye dayanıyor (n8n'in Agency
Cortex'e gerçekten ulaşıp ulaşmadığı):
1. "n8n hesabınız henüz oluşturulmadı" + n8n'i açan düğme
2. "İş akışları kuruldu, ilk çalışma bekleniyor"
3. "n8n bağlı ve çalışıyor — son bağlantı: …"

### Eklendi — "Tüm müşteriler" kapsamlı anahtar
- Bir makine anahtarı artık "tüm müşteriler" kapsamında olabilir;
  **sonradan eklenen müşteriler otomatik dâhil** olur.
- Otomasyonun her yeni müşteri için elle yetki beklememesi için.
- Kapsamı daraltmak için anahtarı iptal edip yenisini üretmek gerekiyor —
  sessizce daralan bir kapsam yanlış güven verirdi.

### Eklendi — Manus kredi koruması
- Manus çağrısından önce kredi durumu okunuyor; kredi sıfırsa görev
  başlatılmıyor ve nedeni söyleniyor. Bu uç **kredi harcamıyor**.
- Kredi **okunamazsa** çağrı engellenmiyor: okunamayan bir değere bakıp
  çalışabilecek işi iptal etmek daha kötü olurdu.
- DECISIONS.md K-031'deki açık iş kapandı.

### Eklendi — Takılan çalıştırmalar kendiliğinden kapanıyor
- Bir süreç çökerse çalıştırma kaydı sonsuza kadar "çalışıyor" görünürdü.
- 2 saatten uzun süren kayıtlar **hata** olarak, nedeniyle kapatılıyor.

### Doğrulandı
- 507/507 test geçti (önceki 458 + 49 yeni).
- **n8n düğüm tipleri ve parametre adları tahmin edilmedi:** n8n 2.39
  paketi indirilip kendi kaynağından okundu (`scheduleTrigger` sürümleri,
  `rule.interval[].field='cronExpression'`, `httpRequest` 4.5,
  `httpHeaderAuth` alanları, `import:workflow`/`publish:workflow` bayrakları).
- Bir test, iş akışı dosyalarının çağırdığı anahtarların Cortex'te
  gerçekten tanımlı olduğunu ve kurulum betiğiyle aynı kimlikleri
  kullandığını doğruluyor.
- **Üretimde patlayacak bir migration yakalandı:** `all_workspaces` sütunu
  varsayılansız NOT NULL olarak üretilmişti; test veritabanı boş olduğu
  için görünmüyordu. Tabloya satır eklenip sınandı ve düzeltildi.

### Henüz yapılmadı (gizlenmiyor)
- **Gerçek veri yok.** Instagram hesabı bağlı değil (Meta App Secret
  yenilenmeli), Claude anahtarı girilmedi, Manus anahtarı yenilenmeli.
  Akışlar bu yüzden şu an "yapılacak iş yoktu" diyecek — çalışmadıkları
  için değil, **veri olmadığı için**.
- **Yedeklerin sunucu dışına kopyalanması** yapılmadı; depolama seçimi
  sizin kararınız.

## [0.12.0] - 2026-09-23 — Hesap bağlama düzeltildi, beşinci iş akışı

### Düzeltildi — "Bağla" düğmesi hiç çalışmamıştı
Panel, `GET` yönlendirmesiyle bir API ucuna gidiyordu; o uç ise **POST**
bekliyor ve **Bearer anahtarı** istiyordu. Tarayıcının izlediği yönlendirme
GET'tir ve çerezle gelir. Meta ayarları eksik olduğu için düğme zaten
görünmüyordu — hata bu yüzden gizli kalmıştı.

İzin adresi artık panelin kendisinde üretiliyor.
Kanıt: `test_bagla_dugmesi_meta_izin_ekranina_goturuyor`.

### Düzeltildi — panelden girilen Meta bilgileri hiç okunmuyordu
Adaptör yalnızca **ortam değişkenlerine** bakıyordu. Kullanıcı anahtarı
panele girip kaydediyor, hiçbir şey değişmiyordu — sessiz bir çıkmaz sokak.

Tek okuma yolu tanımlandı (`platforms/meta_ayar.py`): önce panel ayarı,
yoksa ortam değişkeni, o da yoksa doğrulanmış varsayılan.

Ayrıca Meta bilgileri girilmişse sistem **örnek veri moduna düşmüyor**.
Girilen anahtarları görmezden gelip örnek veri üretmek, o veriyi gerçek
sanmasına yol açardı.

### Düzeltildi — Meta dönüşünde ham JSON gösteriliyordu
Bu uca **tarayıcı** gelir. Artık kullanıcı bağlı hesaplar sayfasına,
sonuç yazılı olarak dönüyor — izin vermese bile.

### Eklendi — WF-05 Bağlantı sağlığı (kritik eksikti)
**Anahtar yenileme hiç yoktu.** Instagram'ın erişim anahtarı ~60 gün
geçerli; yenilenmezse bağlı her hesap sessizce çalışmaz hale gelirdi.

- Anahtar **25 gün kala** yenileniyor. Son güne bırakmak riskli olurdu:
  o gün n8n kapalıysa veya Meta hata veriyorsa hesap ölür.
- Bitiş tarihi bilinmiyorsa **tahmin edilmiyor**, yenileme deneniyor.
  Gereksiz bir yenileme zararsız; kaçırılmış bir yenileme değil.
- Yenilenemeyen anahtar **gizlenmiyor**: hesap işaretleniyor, sebebi
  Bağlı hesaplar sayfasında yazıyor.
- Bir hesabın hatası diğerlerini durdurmuyor.

### Düzeltildi — iki iş çift çalışıyordu
Veri senkronu hem Celery'de (6 saatte bir) hem WF-01'de vardı; haftalık
rapor ise ikisinde de **pazartesi 08:00** idi. Celery tarafındaki
çalışmalar panelde **hiç görünmüyordu**. Çift zamanlamalar kaldırıldı;
iş akışlarının tek sahibi n8n.

### Eklendi — panel artık nasıl çalıştığını anlatıyor
- "Nasıl çalışıyor?" açılır kutusu: n8n bir kez çalışır, Cortex tüm
  müşterileri gezer, kapalı olanı atlar.
- Kapalı akış artık "kapalı — bu müşteride çalışmıyor" diyor. Önce
  "hiç çalışmadı" yazıyordu ve n8n bozuk sanılabilirdi.
- "Çalıştı ama yapacak iş yoktu" ayrı gösteriliyor.
- Örnek veri modundaki platform artık "bağlanabilir" diye gösterilmiyor.

### Doğrulandı — n8n canlıda gerçekten çalışıyor
Sunucudan ölçüldü:
```
=== n8n'deki TUM is akislari ===    (dördü de mevcut)
=== ETKIN olanlar ===              (dördü de etkin)
=== Agency Cortex'teki makine anahtari ===
anahtar: var (acx_da2f4305)
tum_musteriler: evet
son_kullanim: 2026-09-23 10:00:00+03:00
```
`son_kullanim`, n8n'in Agency Cortex'e **gerçekten ulaştığının** kanıtı.

### Doğrulandı
- 526/526 test geçti (önceki 507 + 19 yeni).
- Kuruluma `n8n durumu (tanılama)` adımı eklendi: kurulumdan sonra
  n8n'deki gerçek durum ölçülüp yazılıyor. "Kurdum" demek yetmez.

### Belge
- `docs/otomasyon-plani.md`: kaç akış, ne yapıyor, müşteri başına nasıl
  çalışıyor, müşteri sayısı artınca ne değişiyor.
