# DECISIONS.md — Karar Kayıtları

Format: Karar / Seçenekler / Neden / Risk / Geri alma

---

## K-001 — Proje ayrı bir repository'de geliştirilecek

- **Karar:** Sosyal medya asistanı, `BrandCoor/agency-cortex` adlı yeni ve ayrı
  bir GitHub deposunda geliştirilecek. `gaziantepli-taha-usta-erp` deposuna
  dokunulmayacak.
- **Seçenekler:** (a) Yeni ayrı depo, (b) restoran deposunun içine klasör,
  (c) restoran projesine devam.
- **Neden:** İki proje farklı müşteri, farklı teknoloji (Electron+SQLite+PHP vs.
  Docker+PostgreSQL), farklı barındırma (cPanel vs. VPS) ve farklı domain.
  Tek depoda birleştirmek restoran müşterisinin çalışan üretim sistemini riske
  atar ve yayın süreçlerini birbirine bağlar.
- **Risk:** Düşük. Ek olarak ikinci bir depo yönetmek gerekir.
- **Geri alma:** Depo silinebilir veya içeriği başka depoya taşınabilir; restoran
  deposunda hiçbir iz kalmaz.
- **Onay:** Kullanıcı 2026-09-20'de onayladı.

---

## K-002 — Proje adı: Agency Cortex

- **Karar:** Ürün adı "Agency Cortex", domain `agencycortex.tech`.
- **Seçenekler:** Yeni isim üretmek veya mevcut domaini kullanmak.
- **Neden:** Kullanıcı 18.09.2026'da bu domaini bu proje için almış; isim
  uyumu karışıklığı önler ve ek maliyet doğurmaz.
- **Risk:** Yok.
- **Geri alma:** Domain değiştirilebilir; isim yalnızca dokümanlarda ve panel
  başlığında geçer.

---

## K-003 — Deploy yöntemi: GitHub Actions ile otomatik deploy

- **Karar:** Kod GitHub'a gönderildiğinde, GitHub Actions VPS'e SSH ile bağlanıp
  otomatik kurulum/güncelleme yapacak. SSH anahtarı GitHub'ın şifreli
  "Secrets" alanında tutulacak.
- **Seçenekler:** (a) GitHub Actions otomatik deploy, (b) kullanıcının elle komut
  yapıştırması, (c) Hostinger post-install betiği.
- **Neden:** (b) her adımda kullanıcı müdahalesi gerektirir ve yavaştır;
  (c) VPS'i sıfırlar. (a) tek seferlik kurulumdan sonra tekrarlanabilir,
  kayıt altında ve kullanıcıyı süreçten çıkarır.
- **Risk:** Orta. SSH özel anahtarı GitHub Secrets'ta tutulur. Azaltma: anahtar
  yalnızca deploy için kullanılacak ayrı bir anahtar olacak, `root` yerine
  sınırlı yetkili `deploy` kullanıcısına bağlanacak, ve sudo yetkisi yalnızca
  ilgili servislerle sınırlanacak.
- **Geri alma:** VPS'te `~/.ssh/authorized_keys` içinden ilgili satır silinir ve
  GitHub'daki secret kaldırılır; erişim anında kesilir.
- **Onay:** Kullanıcı 2026-09-20'de onayladı.

---

## K-004 — Bu oturum VPS'in içinde değil

- **Karar:** Geliştirme ve testler bu geçici makinede yapılacak; VPS'e yalnızca
  GitHub Actions üzerinden dokunulacak.
- **Neden:** Bu oturumda SSH istemcisi yok ve dış ağ erişimi proxy tarafından
  kısıtlı (agencycortex.tech'e erişim 403). VPS'e doğrudan bağlanmak teknik
  olarak mümkün değil.
- **Risk:** Orta. VPS'in gerçek durumu (üzerinde ne var, disk, Docker kurulu mu)
  bu oturumdan görülemiyor. Azaltma: ilk deploy betiği, var olan dosyaları
  silmeden önce kontrol eder ve çakışma varsa durur.
- **Geri alma:** Uygulanamaz (ortam kısıtı).

---

## K-005 — Geliştirme ortamı burada doğrulandı

- **Karar:** Kod bu makinede Docker + PostgreSQL 16 + Redis 7 ile gerçekten
  çalıştırılıp test edilecek; "yazıldı" demekle yetinilmeyecek.
- **Neden:** Bu makinede Docker 29.3.1 çalışıyor, PostgreSQL 16.13 ve Redis 7.0.15
  mevcut, npm erişimi açık (HTTP 200). Testleri gerçekten koşturmak mümkün.
- **Risk:** Düşük. VPS ile bu makinenin sürümleri farklı olabilir. Azaltma: her
  şey Docker imajlarıyla sabit sürüme sabitlenecek.
- **Geri alma:** Uygulanamaz.

---

## K-006 — Teknoloji yığını (ön karar, Aşama 1'de kesinleşir)

- **Karar:** Backend Python + FastAPI, veritabanı PostgreSQL, kuyruk Redis,
  worker Celery, panel React, reverse proxy Caddy (otomatik HTTPS),
  dağıtım Docker Compose.
- **Seçenekler:** TypeScript + NestJS + BullMQ alternatifi.
- **Neden:** Mevcut restoran deposu ayrı bir proje olduğu için oradaki
  teknolojiye bağlı kalma zorunluluğu yok. FastAPI, AI sağlayıcı entegrasyonları
  ve veri işleme için daha az kod ve daha olgun kütüphane desteği sunuyor.
  Caddy, HTTPS sertifikasını otomatik alıp yeniler — elle sertifika yönetimi
  gerekmez. KVM 4 kaynakları (4 vCPU / 16 GB) bu yığın için fazlasıyla yeterli.
- **Risk:** Düşük. İleride TypeScript'e geçmek isterseniz maliyetli olur.
- **Geri alma:** Aşama 1 tamamlanmadan önce düşük maliyetle değiştirilebilir;
  sonrasında yeniden yazım gerektirir.

---

## K-007 — Deploy yöntemi revize: Hostinger API birincil, GitHub Actions ikincil

- **Karar:** VPS'e ilk kurulum ve güncellemeler **Hostinger API'sinin
  `createNewProject` (Docker Compose deploy)** aracıyla yapılacak. GitHub Actions
  ile SSH tabanlı deploy, yedek/ileri aşama seçeneği olarak bırakılacak.
- **Bunun K-003'ü değiştirme nedeni:** K-003 alındığında Hostinger bağlayıcısının
  SSH'sız Docker Compose deploy yeteneği olduğu bilinmiyordu. Ayrıca yapılan
  ayrıntılı ağ testi, bu oturumdan SSH'ın (port 22) yapısal olarak imkânsız
  olduğunu kesinleştirdi — yalnızca VPS'e değil, hiçbir hedefe.
- **Seçenekler:** (a) Hostinger API deploy, (b) GitHub Actions + SSH,
  (c) kullanıcının elle komut yapıştırması.
- **Neden (a):** Kullanıcıdan tek seferlik bir sayı (VPS kimliği) dışında hiçbir
  şey istemez; SSH özel anahtarının hiçbir yere kopyalanması gerekmez — bu,
  anahtarın sızma yüzeyini tamamen ortadan kaldırır; deploy'u ben doğrudan
  yapabilirim, kullanıcı beklemez.
- **Risk:** Orta.
  1. `createNewProject` açıklaması "If project with the same name already exists,
     existing project will be replaced" diyor — **aynı isimli mevcut bir proje
     varsa üzerine yazar.** Azaltma: deploy öncesi benzersiz bir proje adı
     kullanılacak (`agency-cortex`) ve ilk deploy öncesi VPS snapshot'ı alınacak.
  2. VPS'in üzerinde hâlihazırda ne olduğu bu oturumdan görülemiyor. Azaltma:
     ilk deploy öncesi kullanıcıdan panelde mevcut projeleri kontrol etmesi
     istenecek.
  3. Deploy sonrası sunucu içi hata ayıklama yapılamaz; yalnızca HTTPS ile
     dışarıdan kontrol mümkün (o da egress izni gerektirir).
- **Geri alma:** `VPS_deleteProjectV1` ile proje tamamen kaldırılır; snapshot
  varsa sunucu eski haline döndürülür.
- **Onay durumu:** Deploy işlemi üretim ortamını değiştirdiği için ayrıca
  kullanıcı onayı alınacak. Bu karar yalnızca yöntemi belirler.

---

## K-008 — SSH özel anahtarı hiçbir koşulda bu sohbete veya GitHub'a girmeyecek

- **Karar:** Kullanıcının oluşturduğu SSH özel anahtarı istenmeyecek, sohbete
  yazdırılmayacak, GitHub Secrets'a konulması da (Hostinger API yolu seçildiği
  için) artık gerekmeyecek.
- **Neden:** Hostinger API yolu SSH gerektirmediğinden anahtarın dolaşıma
  girmesine gerek kalmadı. Anahtarı yalnızca kullanıcının kendi bilgisayarında
  tutması en güvenli durumdur.
- **Risk:** Yok.
- **Geri alma:** İleride GitHub Actions yolu seçilirse ayrı, yalnızca deploy için
  üretilmiş bir anahtar oluşturulur; mevcut kişisel anahtar yine kullanılmaz.

---

## K-009 — Doğrulanmamış hiçbir platform yeteneği "hazır" gösterilmeyecek

- **Karar:** Her platform adaptörü, gerçekten yapabildiği işleri
  `capabilities` ile açıkça bildirir. Bildirmediği bir iş çağrıldığında
  sessizce boş sonuç dönmez, **açık hata** verir.
- **Seçenekler:** (a) Yetenek bildirimi + açık hata, (b) yapamadığı işte boş
  liste dönmek, (c) Meta uçlarını ezberden yazmak.
- **Neden (a):** (b) en tehlikeli seçenek: rapor "erişim 0" der, bu gerçek bir
  sıfır mı yoksa çalışmayan bir bağlantı mı ayırt edilemez ve müşteriye yanlış
  bilgi gider. (c) ise yanlış veri üretir; yanlış veri normalize edilip rapora
  girdiğinde hatayı bulmak çok zorlaşır.
- **Risk:** Düşük. Panelde bazı platformlar "yok" görünür — ama bu gerçeğin
  kendisidir.
- **Geri alma:** Gerçek adaptör yazıldığında yalnızca `capabilities` kümesi
  doldurulur; başka hiçbir katman değişmez.

---

## K-010 — Gerçek Meta adaptörü resmî doküman doğrulanmadan yazılmayacak

- **Karar:** `MetaAdapter` sınıfı boş bırakıldı; hiçbir yetenek bildirmiyor.
  Tamamlanması için gerekenler `docs/platforms/meta.md` içinde madde madde
  listelendi.
- **Neden:** Geliştirme ortamından `developers.facebook.com` ve
  `graph.facebook.com` adreslerine erişim ağ politikası tarafından engellendi
  (HTTP 403). Ortam belgesi bu durumda "raporla, etrafından dolaşma" diyor.
  Ezberden yazılan endpoint ve izin adları sessizce yanlış veri üretir.
- **Risk:** Orta. Aşama 3 tam tamamlanmış sayılmaz.
- **Azaltma:** Sahte adaptör ile tüm üst katmanlar (senkronizasyon, normalize
  etme, şifreli anahtar saklama, kuyruk işleri) eksiksiz yazıldı ve test edildi.
  Gerçek adaptör geldiğinde bu katmanların hiçbiri değişmeyecek.
- **Engeli kaldırma:** (1) `developers.facebook.com` adresinin ortam erişim
  listesine eklenmesi, veya (2) doküman içeriğinin kullanıcı tarafından
  iletilmesi.

---

## K-011 — Senkronizasyon işleri tekrar çalıştırmaya dayanıklı (idempotent)

- **Karar:** Ham veri parmak izi (SHA-256) ile, normalize ölçümler ise
  veritabanı benzersizlik kısıtı + `ON CONFLICT DO UPDATE` ile korunur.
- **Neden:** Bir iş yarıda kalıp yeniden başlarsa veya zamanlayıcı aynı işi
  tekrar tetiklerse, müşteri raporlarında iki katına çıkmış sahte rakamlar
  oluşurdu. Bu, fark edilmesi en zor hata türüdür.
- **Risk:** Düşük.
- **Doğrulama:** Aynı senkronizasyon üç kez çalıştırıldı; içerik ve ölçüm
  sayıları değişmedi.

---

## K-012 — Instagram Login seçildi (Facebook Login değil)

- **Karar:** Meta entegrasyonunda **Instagram Login (Business Login for
  Instagram)** kullanılacak. `META_LOGIN_MODE=instagram_login`.
- **Seçenekler:** (a) Instagram Login, (b) Facebook Login for Business.
- **Neden (a):**
  1. Bağlı bir Facebook Sayfası gerektirmiyor — müşterilerinizin bağlanma
     adımı sadeleşiyor. Facebook Login, her müşterinin Instagram hesabının
     bir Facebook Sayfasına bağlı olmasını zorunlu kılardı.
  2. İlk sürümümüz yalnızca okuma yapıyor; Facebook varlık yönetimine
     ihtiyaç yok.
  3. Meta'nın App Review dokümanı, bir uygulamanın bu iki modelden
     **yalnızca birini** seçmesini belirtiyor — sonradan geçiş maliyetli
     olduğu için baştan doğru seçim önemli.
- **Risk:** Orta. İleride Facebook Sayfası verisi (reklam, sayfa içgörüsü)
  gerekirse model değişimi gerekir.
- **Azaltma:** `META_LOGIN_MODE` ayarı ve `facebook_login` için gereken tüm
  değişkenler (`META_FACEBOOK_*`, `META_PAGE_ID`, `META_BUSINESS_ID`)
  şimdiden tanımlandı; geçiş kod değişikliği değil ayar değişikliği olacak.
- **Geri alma:** Ayar değiştirilir ve Meta panelinde yeni bir uygulama
  kurulur; bağlı hesapların yeniden yetkilendirilmesi gerekir.
- **Kaynak:** Kullanıcının ilettiği "Meta/Instagram Entegrasyonu Rehberi"
  (Manus AI), Meta resmî dokümanlarına atıfla.

---

## K-013 — Meta'ya özgü değerler koda gömülmüyor, ayardan geliyor

- **Karar:** İzin ekranı adresi, token ucu, API sürümü ve izin adları koda
  yazılmadı; `META_API_VERSION`, `META_AUTHORIZE_URL`, `META_TOKEN_URL`,
  `META_GRAPH_BASE_URL`, `META_SCOPES` ayarlarından okunuyor.
  **Varsayılan değerleri yok.**
- **Seçenekler:** (a) Ayardan okumak, (b) ezberden koda yazmak,
  (c) adaptörü tamamen boş bırakmak (önceki durum).
- **Neden (a):** (b) sessizce yanlış veri üretir — en tehlikeli senaryo.
  (c) ise gereğinden fazla muhafazakârdı: OAuth akışının kendisi (state
  üretimi, tek kullanımlık kod, hata yönetimi, token yenileme) Meta'ya özgü
  değil ve doğru yazılabilir. (a) ile akış tamamen yazıldı, yalnızca
  doğrulanması gereken 4-5 sabit dışarıda bırakıldı.
- **Risk:** Düşük. Ayar boşken sistem canlı moda geçmez ve açık hata verir;
  yanlış veri üretme ihtimali yok.
- **Doğrulama:** `test_ayar_eksikken_acik_hata_verir` ve
  `test_ayarlar_tamamlaninca_yetenekler_acilir` testleri bu davranışı
  doğruluyor.
- **Geri alma:** Gerekmez; doğrulanan değerler `.env` dosyasına yazılınca
  kod değişikliği olmadan çalışır.

---

## K-014 — İlk sürümde yalnızca okuma izinleri istenecek

- **Karar:** `MetaAdapter` yalnızca okuma yeteneklerini açıyor:
  `AUTHORIZE`, `REFRESH_TOKEN`, `LIST_MEDIA`, `FETCH_MEDIA_METRICS`,
  `FETCH_ACCOUNT_METRICS`. Yayınlama, yorum yönetimi ve mesajlaşma
  **bilerek dışarıda**.
- **Neden:** Gereksiz izin istemek Meta uygulama inceleme sürecini
  zorlaştırır ve uzatır. Meta, istenen her izin için uçtan uca kullanım
  kaydı ister; kullanılmayan izin reddedilme sebebidir. Ayrıca ürün kuralımız
  zaten insan onayı olmadan yayın yapılmamasını gerektiriyor.
- **Risk:** Düşük. İzinler aşama aşama genişletilebilir.
- **Geri alma:** Yeni izinler ayrı bir inceleme başvurusuyla eklenir.

---

## K-015 — Gizli değerler sunucuda üretilir, hiçbir yerden geçmez

- **Karar:** `SECRET_KEY`, `ENCRYPTION_KEY`, veritabanı şifresi ve webhook
  doğrulama anahtarı **kurulum sırasında sunucuda** `openssl` ile üretilir.
  GitHub Secrets'ta tutulmaz, sohbete yazılmaz, bana gösterilmez.
- **Seçenekler:** (a) Sunucuda üretmek, (b) benim üretip GitHub Secrets'a
  kullanıcıya yazdırmam, (c) benim üretip kullanıcıya iletmem.
- **Neden (a):** (c) gizli değeri sohbet geçmişine sokar — kabul edilemez.
  (b) kullanıcıya 4 ayrı yapıştırma işi yükler ve değerler GitHub'da bir
  kopya daha oluşturur. (a) ile değer hiçbir zaman sunucudan çıkmaz; sızma
  yüzeyi tek noktaya iner.
- **Risk:** Düşük. Değerleri ben de bilmiyorum; gerekirse sunucudaki `.env`
  dosyasından okunur. Kurulum tekrarlandığında mevcut `.env` **korunur** —
  şifreler değişmez, veritabanı erişimi bozulmaz.
- **Geri alma:** Sunucudaki `.env` silinip kurulum tekrarlanırsa yeni
  değerler üretilir. **Dikkat:** `ENCRYPTION_KEY` değişirse kayıtlı sosyal
  medya anahtarları çözülemez hale gelir; hesapların yeniden bağlanması
  gerekir.

---

## K-016 — Sunucuya erişim ayrı bir dağıtım anahtarıyla yapılır

- **Karar:** Kurulum için `agency-cortex-deploy` adlı, yalnızca bu işe
  ayrılmış bir SSH anahtar çifti kullanılıyor. Açık anahtar Hostinger
  üzerinden VPS'e tanıtıldı (anahtar kimliği: 583029).
- **Neden:** Kullanıcının kişisel SSH anahtarı kullanılsaydı, GitHub'daki
  bir sızıntı kullanıcının tüm sunucularını etkilerdi. Ayrı anahtar, etkiyi
  tek sunucu ve tek amaçla sınırlar.
- **Risk:** Düşük. Gizli anahtar yalnızca GitHub'ın şifreli kasasında.
- **Geri alma:** Hostinger panelinden anahtar kaldırılır veya sunucudaki
  `~/.ssh/authorized_keys` içinden ilgili satır silinir; erişim anında biter.

---

## K-017 — Panel, ayrı bir JavaScript uygulaması yerine sunucuda üretilen HTML

- **Karar:** Onay paneli, FastAPI içinde Jinja2 şablonlarıyla sunucu tarafında
  üretiliyor. Ayrı bir React uygulaması yazılmadı.
- **Seçenekler:** (a) Sunucu tarafında HTML, (b) React tek-sayfa uygulaması,
  (c) panel yok, yalnızca API.
- **Neden (a):**
  1. React için Docker imajına ayrı bir Node derleme adımı gerekirdi —
     bakım yükü ve yeni kırılma noktaları.
  2. Panelin işi form doldurmak ve liste göstermek; React'in çözdüğü
     karmaşıklık burada yok.
  3. Tek imaj, tek dağıtım. Kurulum karmaşıklaşmıyor.
  4. Kullanıcı teknik değil; az parça, az arıza.
- **Risk:** Düşük. İleride zengin bir arayüz gerekirse React eklenebilir —
  API katmanı zaten ayrı ve hazır, panelin kaldırılması bir şeyi bozmaz.
- **Geri alma:** `app/panel/` silinir, API olduğu gibi çalışmaya devam eder.

---

## K-018 — Panel oturumu httpOnly çerezle tutuluyor

- **Karar:** Panel girişinde oturum anahtarı, JavaScript'in okuyamayacağı bir
  çerezde saklanıyor (`httponly`, `samesite=lax`, üretimde `secure`).
- **Seçenekler:** (a) httpOnly çerez, (b) tarayıcı deposunda (localStorage)
  saklamak.
- **Neden (a):** (b) seçilseydi, sayfaya sızan herhangi bir betik anahtarı
  okuyup çalabilirdi. httpOnly çerezi JavaScript göremez.
  `samesite=lax` ise başka sitelerden gelen sahte isteklerde çerezin
  gönderilmesini engeller.
- **Risk:** Düşük.
- **Geri alma:** Gerekmez.

---

## K-019 — Yayınlama seçeneği panelde hiç gösterilmiyor

- **Karar:** Onay ekranındaki durum listesinde "Yayınlandı" seçeneği yer
  almıyor. Ayrıca her ekranda yayının kapalı olduğu açıkça yazıyor.
- **Neden:** Kullanıcıya yapamayacağı bir seçeneği sunup sonra hata vermek
  kötü bir deneyimdir. Kilit zaten sunucuda üç katmanlı olarak duruyor;
  panel de aynı gerçeği gösteriyor.
- **Risk:** Yok.
- **Geri alma:** Yayın özelliği açıldığında seçenek listeye eklenir.

---

## K-020 — Sisteme açık "kayıt ol" sayfası konulmadı

- **Karar:** Hesap açmanın tek yolu sunucu üzerinde çalışan bir komut
  (`python -m app.cli.hesap ilk-yonetici`). Panelde veya API'de dışarıya
  açık bir kayıt ucu yok.
- **Seçenekler:** (a) sunucudaki komut, (b) panelde "kayıt ol" sayfası,
  (c) davet bağlantısı sistemi.
- **Neden (a):** (b) seçilseydi adresi bilen herkes hesap açabilirdi.
  (c) daha iyi bir son çözüm ama e-posta gönderimi gerektiriyor; henüz
  e-posta altyapısı yok. Gerçekte olmayan bir şeyi varmış gibi göstermemek
  için en basit ve en kapalı yol seçildi.
- **Risk:** Düşük. Yeni kullanıcı eklemek için sunucuya erişim gerekir.
- **Geri alma:** E-posta altyapısı kurulunca davet sistemi eklenebilir;
  bu komut yerinde kalır (kurtarma yolu olarak gereklidir).

---

## K-021 — İlk şifre GitHub Secrets üzerinden giriliyor, sohbete yazılmıyor

- **Karar:** İlk yönetici şifresi, GitHub deposunun Secrets alanına
  kullanıcı tarafından girilir. Kurulum iş akışı bu değeri yalnızca
  standart girdi (stdin) üzerinden sunucuya aktarır.
- **Seçenekler:** (a) GitHub Secrets + stdin, (b) sunucuda rastgele şifre
  üretip kuruluma yazdırmak, (c) şifreyi sohbette istemek.
- **Neden (a):** (c) kesinlikle yasak (şifre sohbet geçmişine düşer).
  (b) seçilseydi şifre GitHub Actions kayıtlarına düşerdi ve kayıtlar
  silinene kadar orada kalırdı. (a)'da değer GitHub tarafından şifreli
  saklanır, kayıtlarda maskelenir, komut satırına ve dosyaya yazılmaz.
- **Risk:** Şifre ilk girişe kadar GitHub Secrets içinde durur. Bu yüzden
  panele ilk girişten sonra şifre değiştirme sayfası eklendi ve secret'ın
  silinmesi önerilir.
- **Geri alma:** Secret silinir; şifre `sifre-degistir` komutuyla veya
  panelden değiştirilir.

---

## K-022 — Şifreler özetlenmeden önce Unicode olarak tekilleştiriliyor

- **Karar:** `hash_password` ve `verify_password`, şifreyi önce NFKC
  biçimine çevirir.
- **Sorun:** Türkçe harfler (ğ, ü, ş, ı, ö, ç) iki farklı şekilde
  kodlanabilir: tek karakter olarak (`ğ` = U+011F) veya taban harf +
  birleşik işaret olarak (`g` + U+0306). Ekranda **birebir aynı** görünürler,
  bayt düzeyinde farklıdırlar. Kullanıcı şifresini bir cihazda oluşturup
  başka bir cihazda yazdığında iki gösterim karışabilir ve şifre doğru
  olduğu hâlde "şifre hatalı" hatası alınır.
- **Seçenekler:** (a) NFKC ile tekilleştirmek, (b) Türkçe harfleri
  şifrelerde yasaklamak, (c) hiçbir şey yapmamak.
- **Neden (a):** (c) gerçek bir arızaydı — ilk yönetici hesabında bu tam
  olarak yaşandı. (b) kullanıcıya kendi dilini yasaklamak olurdu.
  (a) RFC 8265'in (PRECIS OpaqueString) şifreler için önerdiği yaklaşımdır.
- **Risk:** Düşük. Tekilleştirme yalnızca gösterimi birleştirir; farklı
  şifrelerin birbirinin yerine geçmesine yol açmaz — bu ayrıca test edildi.
- **Geri alma:** Gerekmez. Mevcut özetler çalışmaya devam eder: eski özet
  NFKC biçiminde üretilmişti, aynı biçimle doğrulanıyor.

---

## K-023 — Şifre, kullanıcının kendi tarayıcısında belirleniyor

- **Karar:** Panele girilemediğinde, kullanıcıya tek kullanımlık bir bağlantı
  üretiliyor. Kullanıcı şifresini o sayfada, kendi tarayıcısında belirliyor.
- **Sorun:** Şifre, kullanıcıdan sisteme ulaşana kadar birkaç durak geçiyordu
  (gizli değer kutusu → kurulum → sunucu → veritabanı). Her durak şifrenin
  biçimini değiştirebiliyor: kopyala-yapıştırda kaçan boşluk, Türkçe
  harflerin farklı Unicode gösterimleri, klavye düzeni farkları. Sonuç her
  seferinde aynı: "şifre doğru ama giriş olmuyor".
- **Seçenekler:** (a) tek kullanımlık bağlantı, (b) her aktarım durağını tek
  tek sağlamlaştırmak, (c) e-posta ile şifre sıfırlama.
- **Neden (a):** (b) denendi — boşluk kontrolü ve Unicode tekilleştirme
  eklendi, ikisi de gerçek kusurdu ve kaldı. Ama yeni bir durak her zaman
  eklenebilir. (a) durakları tamamen ortadan kaldırıyor: şifre hiç
  aktarılmıyor. (c) daha iyi bir son çözüm ama e-posta altyapısı yok;
  olmayan bir şeyi varmış gibi göstermemek için (a) seçildi.
- **Risk:** Bağlantıyı ele geçiren biri şifreyi değiştirebilir. Bu yüzden:
  jeton 32 bayt rastgele, 30 dakika geçerli, tek kullanımlık, ve jetonun
  kendisi değil yalnızca SHA-256 özeti saklanıyor.
- **Geri alma:** E-posta altyapısı kurulunca bağlantı sohbet/kurulum kaydı
  yerine e-postayla gönderilir; akışın geri kalanı aynı kalır.

---

## K-024 — API anahtarları panelden giriliyor, şifreli saklanıyor

- **Karar:** API anahtarları (Claude, Gemini, Manus, Meta) panelden girilir,
  Fernet ile şifrelenerek veritabanında saklanır ve **ekrana bir daha
  yazılmaz** — yalnızca son 4 karakter gösterilir.
- **Seçenekler:** (a) panelden girilip şifreli saklamak, (b) sunucudaki `.env`
  dosyasına yazmak, (c) GitHub Secrets üzerinden geçirmek.
- **Neden (a):** Bu anahtarlar kuruluma değil, ajansın hesaplarına ait ve
  zamanla değişiyor. (b) her değişiklikte sunucuya girmeyi gerektirir;
  ajans sahibi bunu yapamaz. (c) ilk yönetici şifresinde denendi ve o
  yolculuğun kaç adımda bozulabildiğini gördük.
- **Risk:** Değer artık veritabanında. Bu yüzden şifreli saklanıyor:
  veritabanı yedeği ele geçse bile sunucudaki `ENCRYPTION_KEY` olmadan
  çözülemez. Sayfa yalnızca sistem yöneticisine açık ve yetkisiz kişiye
  **404** dönüyor (403 sayfanın varlığını bildirirdi).
- **Geri alma:** Panelden silinince sunucudaki ortam değişkenine geri düşer.

---

## K-025 — Panel kenar menüye taşındı

- **Karar:** Panel, üstte tek satır bağlantı yerine solda kalıcı bir menüyle
  çalışıyor. Menü, seçili müşterinin sayfalarını grup halinde gösteriyor.
- **Neden:** Sayfa sayısı arttıkça üstteki "·" ile ayrılmış bağlantılar
  okunmaz hale geldi ve kullanıcı nerede olduğunu göremiyordu. Kenar
  menüde bulunduğunuz sayfa vurgulanıyor.
- **Risk:** Yok. Telefonda menü üste taşınıyor.
- **Geri alma:** Yalnızca `base.html` değişir; sayfa içerikleri aynı kalır.

---

## K-026 — Meta sabitleri doğrulanmış değerlerle dolduruldu

- **Karar:** Meta API sürümü, izin ekranı, token ucu, Graph adresi ve izin
  listesi artık boş değil; resmî dokümandan doğrulanmış değerlerle dolu
  (21 Eylül 2026 tarihli referans).
- **Seçilen değerler:** `v26.0`, `www.instagram.com/oauth/authorize`,
  `api.instagram.com/oauth/access_token`, `graph.instagram.com/v26.0/`,
  izinler: `instagram_business_basic,instagram_business_manage_insights`.
- **Instagram Login seçildi**, Facebook Login değil. Nedeni: Instagram
  Login'de müşterinin Facebook Sayfası olması **gerekmiyor**. Ajans
  müşterilerinin çoğunda Sayfa bağlantısı ya yok ya da karışık.
- **İzinler bilerek salt okuma.** Yayınlama, yorum ve mesaj izinleri
  istenmiyor: (a) v1'de yayınlama kapalı, (b) Meta yalnızca gerçekten
  kullanılan izinlerin istenmesini şart koşuyor; kullanılmayan izin istemek
  App Review'da reddedilme sebebi.
- **Belgelenmiş belirsizlik:** Meta'nın iki resmî sayfası izin ekranı için
  farklı adres veriyor — güncel Business Login rehberi (13 Mart 2026)
  `www.instagram.com`, eski OAuth referansı (17 Temmuz 2025)
  `api.instagram.com`. Aradaki farkı açıklayan ortak bir kural yok.
  Daha güncel sayfa esas alındı ve bu belirsizlik koda yorum olarak yazıldı.
- **Geri alma:** Panelden veya ortam değişkeninden ezilebilir.

---

## K-027 — Manus v2 kullanılıyor, v1 kullanılmıyor

- **Karar:** Manus entegrasyonu API **v2** ile yazıldı.
- **Neden:** v1 resmî ama **deprecated**. İkisi karıştırılamaz çünkü
  temelden farklılar:
  | | v1 | v2 |
  |---|---|---|
  | Başlık | `API_KEY` | `x-manus-api-key` |
  | Durumlar | pending/running/completed/failed | running/stopped/waiting/error |
  Yanlış başlık veya yanlış durum adı, sessizce "görev hiç bitmiyor"
  davranışına yol açardı.
- **Risk:** v2'nin de değişmesi. Bu yüzden durum alanı yanıtta bulunamazsa
  sistem "durum yok" varsaymıyor, açıkça hata veriyor.

---

## K-028 — Manus "waiting" durumunda otomatik onay verilmiyor

- **Karar:** Görev `waiting` durumuna geçerse (Manus kullanıcıdan girdi veya
  onay bekliyor) sistem **otomatik yanıt vermiyor**; görevi durduruyor ve
  durumu bildiriyor.
- **Neden:** Sistemin temel kuralı, insan onayı olmadan iş yapmaması.
  Manus'un sorusuna otomatik "evet" demek bu kuralın etrafından dolaşmak
  olurdu — hem de sistemin göremediği bir soruya.
- **Risk:** Bazı görevler yarıda kalır. Kabul edilebilir: yarım kalan görev,
  onaysız tamamlanmış görevden iyidir.

---

## K-029 — Gemini fiyatlarında yüksek olan değer yazıldı

- **Karar:** Gemini 3.8/3.7/3.6 Flash için dokümandaki iki fiyattan
  **yüksek** olanı (1 Ocak 2027 sonrası: $1.50/$7.50) tabloya yazıldı.
- **Neden:** Bu tablo aylık bütçe kilidini besliyor. Maliyeti olduğundan
  düşük göstermek, bütçenin sessizce aşılmasına yol açar. Düşük gösterip
  aşmaktansa yüksek gösterip erken uyarmak tercih edildi.
- **Not:** Bu bir **ürün kararıdır**, doküman değeri değildir; koda böyle
  yazıldı.
- **Ayrıca:** `gemini-2.5-pro` ve `gemini-3.1-pro-preview` istem uzunluğuna
  göre iki farklı fiyat uyguluyor (≤200k / >200k). Tek fiyatla temsil
  edilemedikleri için **bilerek** tabloya eklenmediler; unutulmuş
  sanılmasın diye ayrı bir listede adları yazıldı.

---

## K-030 — AI bütçe kilidi "rezerve et, sonra kesinleştir" yöntemine geçti

- **Karar:** Aylık AI bütçesi artık **atomik** (bölünemez) kontrol ediliyor.
  Çağrı yapılmadan **önce** tahmini üst maliyet "açık rezervasyon" olarak
  veritabanına yazılıyor; çağrı bitince satır gerçek maliyete çekiliyor.
  Kontrol, müşteri satırı `SELECT ... FOR UPDATE` ile kilitlenerek yapılıyor.
- **Seçenekler:**
  1. Eski yöntem: topla, karşılaştır, çağır, sonra maliyeti yaz.
  2. Kilidi AI çağrısı boyunca tutmak.
  3. Rezervasyon: kısa kilit + ön kayıt + kesinleştirme. **(seçilen)**
- **Neden:** (1) yanlış. İki iş aynı anda başlarsa ikisi de aynı toplamı
  okur, ikisi de "bütçe var" der ve bütçe aşılır. Tek kullanıcı tek iş
  yaparken görünmüyordu; n8n iş akışları aynı anda çalışacağı için
  görünür hale gelecekti. (2) doğru ama 15 dakika süren bir araştırma
  çağrısı, aynı müşterinin panelden yaptığı işi de 15 dakika bekletirdi.
  (3) kilidi milisaniyelere indiriyor.
- **Kanıt:** `test_ayni_anda_calisan_iki_is_butceyi_asamaz` — iki **ayrı**
  veritabanı bağlantısı, aynı anda, 10 USD bütçe ve 6+6 USD tahmin.
  Kilit varken tek iş geçiyor. Kilit kaldırıldığında test **düşüyor**
  ("Iki is de gecti; butce asildi"). Yani test gerçekten kilidi ölçüyor.
- **Risk:** Rezervasyon bir tahmindir ve çıktı en büyük değerden
  (`max_tokens`) hesaplanır; yani gerçekten harcanacaktan yüksektir.
  Bütçenin son kuruşlarında, aslında sığacak bir iş reddedilebilir.
  Az tahmin edip bütçeyi aşmaktansa bu tercih edildi.
- **Çöken süreç:** Rezervasyonun bir ömrü var (45 dakika). Süresi geçmiş
  rezervasyon toplama katılmaz; çöken bir süreç bütçeyi sonsuza kadar
  kilitleyemez.
- **Geri alma:** `4c1d6a2f9b30` migration'ı geri alınır ve `ai_butce.py`
  içindeki `rezerve_et` çağrıları kaldırılır. Veri kaybı olmaz.

---

## K-031 — Manus'un maliyeti USD bütçesine giremiyor (bilinen sınır)

- **Karar:** Manus çağrıları için USD rezervasyonu **yapılmıyor**.
- **Neden:** Manus v2 kredi ile çalışıyor; resmî dokümanda kredinin USD
  karşılığı yok. Bir fiyat uydurmak, bütçe kilidini sessizce yanlış
  hesaplatırdı.
- **Bu ne demek:** Aylık USD bütçesi Manus harcamasını **kapsamıyor**.
  Manus'un kendi kredi sınırı geçerli.
- **Açık iş:** Manus çağrısından önce `usage.availableCredits` ile kredi
  kontrolü eklenecek. Bu yapılana kadar sınır, Manus tarafındaki kredi
  bitişidir.
- **Risk:** Manus kredisi beklenmedik şekilde tükenebilir; panelde bunun
  uyarısı henüz yok.

---

## K-032 — n8n bir otomasyon motorudur, ikinci bir uygulama değildir

- **Karar:** n8n **yalnızca** zamanlama, sıralama, tekrar deneme ve dış
  servis çağrılarından sorumludur. Kimlik, yetki, müşteri izolasyonu, AI
  bütçesi, onay sistemi ve iş kuralları **Agency Cortex'te** kalır.
  n8n veritabanına **doğrudan yazmaz**; her şey Agency Cortex API'sinden geçer.
- **Seçenekler:**
  1. n8n'i PostgreSQL'e doğrudan bağlamak (hızlı, az kod).
  2. n8n'i ayrı bir arayüz olarak kullanıcıya sunmak.
  3. n8n → Agency Cortex API → veritabanı. **(seçilen)**
- **Neden:** (1) izolasyonu n8n'in iş akışı tasarımına emanet ederdi; bir
  node'daki yanlış `workspace_id`, başka bir müşterinin verisine yazardı ve
  bunu hiçbir kural engellemezdi. (2) kullanıcıyı teknik bir araca mahkûm
  ederdi. (3) tek bir güvenlik kapısı bırakıyor.
- **Sonuç:** Panelde **Otomasyon** bölümü var; kullanıcı n8n'e girmeden
  hangi akışın açık olduğunu, ne zaman çalıştığını ve hata verip
  vermediğini görüyor.
- **Risk:** Her yeni iş akışı için Agency Cortex tarafında bir uç yazmak
  gerekiyor — n8n'den doğrudan yazmaya göre daha yavaş ilerliyor.
  Kabul edildi: izolasyon pazarlık konusu değil.
- **Geri alma:** n8n servisi compose'dan çıkarılır, Caddy'deki site bloğu
  silinir. Agency Cortex etkilenmez.

---

## K-033 — n8n insan hesabı kullanmaz; kendi makine kimliği vardır

- **Karar:** n8n, `X-API-Key` başlığıyla taşınan bir **makine kimliği**
  kullanır. Anahtar veritabanında **açık saklanmaz** (SHA-256 özeti).
  Biçim: `acx_<açık kimlik>_<gizli>`. Ekranda ve loglarda yalnızca
  `acx_<açık kimlik>` görünür; gizli kısımdan tek karakter bile sızmaz.
- **Neden SHA-256, Argon2 değil:** Anahtar 32 bayt **rastgeledir**; sözlük
  saldırısı mümkün değil. Argon2 gibi bilerek yavaş bir özet, her API
  çağrısına gereksiz gecikme eklerdi. (Kullanıcı şifreleri farklı: onlar
  tahmin edilebilir olduğu için Argon2 ile saklanıyor.)
- **Kapsam:** `api_client_workspaces` tablosu, anahtarın hangi müşterilerde
  çalışabileceğini tutar. **İstekle gelen `workspace_id` tek başına hiçbir
  şey ifade etmez** — her istekte bu tabloya bakılır. Kapsam dışındaki
  müşteride **404** döner (403 değil; 403, o müşterinin varlığını ele verirdi).
- **İptal:** Anahtar iptal edilince kayıt **silinmez**; geçmiş
  çalıştırmaların hangi kimlikle yapıldığı kaybolmasın diye iz kalır.
- **Risk:** Anahtar bir kez gösterilir. Kaybedilirse yenisi üretilir —
  eskisi geri getirilemez. Bu bilerek böyledir.

---

## K-034 — n8n arayüzünün önüne ikinci bir kilit kondu

- **Karar:** `n8n.agencycortex.tech` adresinin önünde Caddy tarafında HTTP
  basic auth var. Şifrenin bcrypt özeti sunucudaki `.env`'de; düz hali
  **panelde yalnızca sistem yöneticisine** gösteriliyor.
- **Neden:** n8n kurulduktan sonra **ilk açan kişi** "sahip" hesabını
  oluşturur. Yeni bir alan adı, sertifika şeffaflık kayıtlarından
  (Certificate Transparency) dakikalar içinde herkese görünür olur. Kurulum
  ile kullanıcının ilk girişi arasındaki süre saatler sürebilir; bu aralıkta
  bir yabancı sahip hesabını alabilirdi.
- **Seçenekler:** (a) sahip hesabını kurulumda API ile açmak — n8n'in bu
  akışı elimizdeki doğrulanmış belgede tanımlı değil, uydurmak istemedim;
  (b) kilitsiz bırakıp kullanıcıdan hemen girmesini istemek — zamanlamaya
  bel bağlamak; (c) basic auth. **(c) seçildi.**
- **Kanıt:** Kurulum adımı `https://n8n.<alan adı>/` adresine **dışarıdan**
  istek atar ve **HTTP 401** bekler. 200 dönerse kurulum **durur**.
- **Risk:** Kullanıcı iki ayrı giriş görüyor (kapı şifresi + n8n hesabı).
  Panelde bu ayrım açıkça yazıldı.

---

## K-035 — Kullanıcı şifresini yönetici belirlemez

- **Karar:** Yeni hesap, **kimsenin bilmediği** rastgele bir değerle
  kilitli açılır. Yönetici tek kullanımlık bir bağ üretir; kişi şifresini
  o bağdan kendisi belirler.
- **Neden:** Şifre yöneticiden kullanıcıya giderken (sohbet, e-posta,
  kâğıt) her durakta kopyalanabilir ve biçim bozulabilir. 21 Eylül'de
  Türkçe karakterlerin farklı Unicode gösterimi yüzünden tam olarak bu
  yaşandı. Bu akışta şifre **hiç aktarılmaz**.
- **Kanıt:** `test_yeni_hesap_bag_kullanilmadan_giris_yapamaz` — yeni hesap
  boş şifre, boşluk, yaygın şifreler dahil hiçbir değerle giriş yapamıyor.
- **Risk:** Bağ 24 saat geçerli. Asıl koruma süre değil, **tek kullanımlık**
  olmasıdır: kullanıldığı anda geçersizleşir.

---

## K-036 — Sistemde her zaman en az bir etkin yönetici kalır

- **Karar:** Son etkin sistem yöneticisi silinemez, pasifleştirilemez ve
  yetkisi alınamaz. Kimse kendi hesabını silemez, kendini pasifleştiremez
  veya kendi yönetici yetkisini alamaz.
- **Neden:** Bu kural olmadan tek bir yanlış tıklama panele girişi tamamen
  kapatır. Kurtarma yalnızca sunucuya SSH ile bağlanıp komut çalıştırarak
  mümkün olurdu — kullanıcının kendi başına yapamayacağı bir şey.
- **Kanıt:** `test_son_yonetici_silinemez`, `test_son_yonetici_pasiflestirilemez`,
  `test_tek_yoneticinin_yetkisi_alinamaz`, `test_kendini_pasiflestiremez`.
- **Risk:** Yöneticinin yetkisini almak için ikinci bir yönetici gerekiyor.
  Bilerek böyle.

---

## K-037 — "Servis ayakta" ile "servis çalışıyor" aynı şey değil

- **Karar:** Bir kilit kurulduğunda, kurulum hem **kapalı olduğunu** hem
  **doğru anahtarla açıldığını** ayrı ayrı kanıtlar.
- **Neden:** n8n kurulumu bir kez yeşil göründü, dışarıdan HTTP 401
  dönüyordu ve her şey doğru sanıldı. Oysa bcrypt özeti Docker Compose
  tarafından kırpılmıştı; kapı **hiçbir şifreyle** açılmıyordu.
  401 dönen bozuk bir kapı, çalışan bir kapıdan ayırt edilemez.
- **Genel kural:** Bir koruma eklendiğinde "engelliyor mu" testi tek
  başına yetmez; "izin vermesi gerekeni veriyor mu" da sınanmalıdır.
  Aynı hata sınıfı bu projede daha önce üç kez çıktı (Caddy yolları,
  Caddy yeniden yükleme, yedek doğrulama).
- **Risk:** Kurulum adımı sunucudaki düz şifreyi okuyor. Şifre GitHub'a
  taşınmıyor, loga basılmıyor ve `ps` çıktısında görünmüyor
  (`--netrc-file`, geçici dosya 600 izniyle ve hemen siliniyor).

---

## K-038 — n8n iş akışları iki düğümden ibaret; iş Agency Cortex'te yapılır

- **Karar:** Her iş akışı **Zamanlayıcı → HTTP çağrısı** şeklinde iki
  düğümden oluşuyor. Müşteri dolaşımı, hata yakalama ve tüm iş mantığı
  Agency Cortex'in `calistir-hepsi` ucunda.
- **Seçenekler:**
  1. n8n'de müşteri listesini çekip döngü kurmak, her müşteri için ayrı
     çağrı yapmak, hataları n8n'de yönetmek.
  2. n8n'de yalnızca zamanlama; geri kalan her şey Cortex'te. **(seçilen)**
- **Neden:** (1) her iş akışında 6-8 düğüm demekti ve müşteri izolasyonu
  n8n'in düğüm ayarlarına bağlı hale gelirdi — yanlış bir ifade başka bir
  müşterinin verisine yazardı. (2) düğüm sayısını 2'ye indiriyor, yanlış
  ayar yüzeyini neredeyse sıfırlıyor ve n8n'i gerçekten yaptığı işe
  (zamanlama, tekrar deneme, çalışma geçmişi) indirgiyor.
- **Bir müşterinin hatası diğerlerini durdurmuyor:** `calistir-hepsi` her
  müşteriyi ayrı ele alıyor, hatayı o müşterinin çalıştırma kaydına
  yazıyor ve devam ediyor.
- **Risk:** Tek bir HTTP çağrısı tüm müşterileri işlediği için uzun
  sürebilir. Zaman aşımları akış başına ayarlandı (araştırma için 30 dk).
- **Doğrulandı:** Düğüm tipleri ve parametre adları (`scheduleTrigger`
  `rule.interval[].field='cronExpression'`, `httpRequest` 4.5) n8n 2.39
  paketinin kendi kaynağından okundu, tahmin edilmedi. Bir test, dosyaların
  çağırdığı akış anahtarlarının Cortex'te gerçekten tanımlı olduğunu
  doğruluyor.

---

## K-039 — İş akışları kurulumu kendi kendine tamamlanıyor

- **Karar:** İş akışlarını n8n'e yükleyen betik, sunucuda **5 dakikada bir**
  çalışan bir görev olarak kuruluyor. Kurulduğunda kendini durduruyor.
- **Neden:** n8n'e iş akışı yüklemek için n8n'de bir **sahip hesabı**
  olması şart (n8n kaynağı: import komutu global owner'ı bulamazsa hata
  veriyor). O hesabı kullanıcı ilk girişinde kendisi oluşturur ve bu,
  kurulumdan saatler sonra olabilir. Tek seferlik bir kurulum adımı o anda
  başarısız olur ve bir daha denenmezdi.
- **Sonuç:** Kullanıcı n8n hesabını oluşturuyor; birkaç dakika sonra
  akışlar kendiliğinden kuruluyor. **Başka bir şey yapması gerekmiyor.**
- **Anahtar nasıl gidiyor:** Betik Agency Cortex'ten makine anahtarı
  üretiyor ve n8n'e **şifreli kimlik bilgisi** olarak aktarıyor
  (`import:credentials` düz veriyi alıp n8n'in kendi anahtarıyla şifreliyor).
  Anahtar hiçbir yerde loglanmıyor, geçici dosya hemen siliniyor.
- **Neden `$env` değil:** n8n'de `$env` erişimi açılsaydı (varsayılan
  kapalı), iş akışı düzenleyebilen herkes veritabanı şifresi dâhil tüm
  ortam değişkenlerini okuyabilirdi. Şifreli kimlik bilgisi bunu gerektirmiyor.
- **Kanıt:** Betik yükleme sonrası `n8n list:workflow --active=true` ile
  dört akışın da **etkin** olduğunu doğruluyor; değilse hata veriyor.
  "Yükledim" demek yetmez — etkin olmayan akış hiç çalışmaz.

---

## K-040 — Manus için kredi koruması eklendi (K-031'in kapanışı)

- **Karar:** Manus çağrısından **önce** `usage.availableCredits` okunuyor;
  kredi sıfırsa görev başlatılmıyor ve neden söyleniyor.
- **Neden:** Manus USD ile değil kredi ile çalışıyor ve dokümanda kredinin
  para karşılığı yok, bu yüzden aylık USD bütçesi Manus'u kapsayamıyor
  (K-031). Kapsayamadığı için en azından "kredi bitmişken boşuna çağrı
  yapma" koruması kondu.
- **Kredi okunamazsa çağrı ENGELLENMİYOR:** Okunamayan bir değere bakıp
  çalışabilecek bir işi iptal etmek daha kötü olurdu. Yalnızca kredinin
  sıfır olduğu **kesin** olduğunda duruluyor.
- **Bu uç kredi harcamıyor** (salt okuma).

---

## K-041 — Hesap bağlama: şifre değil, OAuth izni

- **Karar:** Müşterinin sosyal medya hesabı **Instagram'ın kendi izin
  ekranından** bağlanıyor. Panelde müşteri şifresi veya müşteriye ait API
  anahtarı **istenmiyor**.
- **Seçenekler:**
  1. Müşterinin kullanıcı adı/şifresini panele girmek.
  2. Her müşteri için ayrı bir Meta uygulaması/anahtarı istemek.
  3. Ajansın tek bir Meta uygulaması + müşteri başına OAuth izni. **(seçilen)**
- **Neden:** (1) en kötüsü: şifre bizde durur, sızarsa hesabın tamamı
  gider, müşteri izni geri alamaz ve iki adımlı doğrulama zaten engeller.
  (2) her müşteriden teknik bir kurulum beklemek demek; çoğu yapamaz.
  (3) hesap sahibi kendi girişini yapar, **ne izni verdiğini görür**, bize
  yalnızca **okuma yetkili, süreli ve iptal edilebilir** bir anahtar gelir.
  İzni istediği an Instagram ayarlarından geri alabilir.
- **İstenen izinler yalnızca okuma:** `instagram_business_basic`,
  `instagram_business_manage_insights`. Paylaşım, yorum ve mesaj izinleri
  **bilerek istenmiyor** — bu sürümde sistem hiçbir şey yayınlamıyor.
- **Anahtarlar şifreli saklanıyor** (`oauth_credentials`, Fernet).
- **Ajansın kendi uygulama bilgileri** (App ID + Secret) bir kez sistem
  ayarlarından giriliyor; sonra her müşteri tek tıkla bağlanıyor.
- **Dönüş adresi elle yazılmıyor:** alan adından üretilip kopyalanabilir
  şekilde gösteriliyor. Meta'ya birebir aynı girilmesi gerekiyor ve tek
  harf farkı bağlantıyı bozardı.

---

## K-042 — Panelden girilen Meta bilgileri artık gerçekten okunuyor

- **Sorun:** Meta uygulama bilgileri panelde giriliyordu ama adaptör
  yalnızca **ortam değişkenlerine** bakıyordu. Kullanıcı anahtarı girip
  kaydediyor, hiçbir şey değişmiyordu — **sessiz bir çıkmaz sokak**.
- **Karar:** Tek okuma yolu tanımlandı (`platforms/meta_ayar.py`): önce
  panel ayarı, yoksa ortam değişkeni, o da yoksa doğrulanmış varsayılan.
- **Ayrıca:** Meta bilgileri girilmişse sistem **örnek veri moduna
  düşmüyor**. Kullanıcının girdiği anahtarları görmezden gelip örnek veri
  üretmek, o veriyi gerçek sanmasına yol açardı. Sunucuda bir ortam
  değişkeni değiştirmeye de gerek kalmıyor.
- **Dürüstlük:** Örnek veri modundaki platform artık "bağlanabilir" diye
  gösterilmiyor. Sahte adaptör "sağlıklı" der ama gerçek hesap bağlayamaz.

---

## K-043 — "Bağla" düğmesi hiç çalışmamıştı

- **Bulgu:** Panel, `GET` yönlendirmesiyle bir API ucuna gidiyordu; o uç
  ise **POST** bekliyor ve **Bearer anahtarı** istiyordu. Tarayıcının
  izlediği yönlendirme GET'tir ve çerezle gelir. Düğme hiçbir zaman
  çalışmamıştı — ama Meta ayarları eksik olduğu için düğme zaten
  görünmüyordu ve bu gizli kalmıştı.
- **Karar:** İzin adresi panelin kendisinde üretiliyor. Panel zaten çerez
  oturumuyla yetkilendirilmiş durumda; araya bir API çağrısı koymak hem
  gereksiz hem de kırıktı.
- **Dönüş de panele:** Meta geri döndüğünde kullanıcı ham JSON görmüyor;
  bağlı hesaplar sayfasına, sonuç yazılı olarak dönüyor.
- **Kanıt:** `test_bagla_dugmesi_meta_izin_ekranina_goturuyor` — düğmeye
  basınca gerçekten `instagram.com/oauth/authorize` adresine gidiliyor,
  gizli anahtar adreste **yer almıyor** ve yayın izni istenmiyor.

---

## K-044 — Sistem ayarları 10 alandan 4 alana indirildi

- **Sorun:** Ayarlar sayfasında hiçbir şeyi açmayan alanlar vardı.
  `META_API_VERSION`, `META_AUTHORIZE_URL`, `META_TOKEN_URL`,
  `META_GRAPH_BASE_URL`, `META_SCOPES` kodda zaten sabitti; panelden
  değiştirilse bile bir etkisi olmuyordu. `GEMINI_API_KEY` ise hiçbir
  yerde kullanılmıyordu. Kullanıcı "çalışmayan bir alan olmasın" dedi;
  bunlar tam olarak öyle alanlardı.
- **Karar:** Geriye **yalnızca dört** alan kaldı: `ANTHROPIC_API_KEY`,
  `MANUS_API_KEY`, `META_APP_ID`, `META_APP_SECRET`. Kaldırılanlar
  `KALDIRILAN_AYARLAR` listesine alındı; eski kayıt veritabanında kalsa
  bile **okunmuyor**, böylece "girdim ama işe yaramıyor" durumu
  tekrarlanamaz.
- **Redirect URI artık sorulmuyor:** `public_domain` alanından türetiliyor.
  Kullanıcının elle adres yazması, yanlış yazıldığında Meta tarafında
  anlaşılmaz bir hataya dönüşüyordu.
- **Her alan ne açıyor:** Ayar tanımına `acar` alanı eklendi; panel
  "bu anahtarı girersen şu özellik açılır" diye yazıyor.
- **Risk:** Meta bir gün API sürümünü değiştirirse kod güncellemesi
  gerekir. Bunu panelden ayarlanabilir bırakmak, doğrulanmamış bir sürüm
  numarası girilip tüm entegrasyonun sessizce bozulması riskini taşıyordu.
- **Geri alma:** Kaldırılan anahtarlar `KALDIRILAN_AYARLAR` listesinden
  çıkarılırsa tekrar okunur hale gelir.

---

## K-045 — Anthropic anahtarı gerçek bir çağrı ile sınanıyor

- **Karar:** "Test et" düğmesi artık anahtarın biçimine bakmıyor;
  `GET https://api.anthropic.com/v1/models` çağrısı yapıyor.
- **Neden bu uç:** Model listesi ücretsizdir ve **token harcamaz**. Bir
  mesaj gönderip sınamak, her testte para harcamak olurdu.
- **Hata ayrımı:** 401 "anahtar kabul edilmedi", 403 "anahtarın yetkisi
  yok", 429 "çok fazla istek" ve ağ hatası "Anthropic'e bağlanılamadı"
  olarak **ayrı ayrı** gösteriliyor. Hepsini "anahtar hatalı" diye
  göstermek, internet kesintisinde kullanıcıya doğru anahtarını
  sildirtirdi.
- **Risk:** Test, dışarıya gerçek bir istek gönderir. Zaman aşımı konuldu.

---

## K-046 — Yetkiler rol başına, müşteri başına ayarlanabilir

- **Karar:** 5 sabit rolün yapabildikleri artık **17 ayrı izne** ayrıldı
  (marka.duzenle, hesap.bagla, icerik.onayla, takvim.planla, rapor.onayla,
  otomasyon.calistir, ekip.yonet, yetki.duzenle …). Her müşteri için her
  rolün her izni tek tek açılıp kapatılabiliyor.
- **Seçenekler:** (a) rolleri çoğaltmak, (b) kullanıcı başına izin,
  (c) rol + müşteri başına izin.
- **Neden (c):** (a) "editör2, editör3" gibi anlamsız roller üretir;
  (b) 50 kullanıcıda 850 satır yönetmek demektir ve kimin neyi
  yapabildiği görülemez hale gelir. (c) ekranda 5 satır × 17 sütunluk
  tek bir tabloyla anlaşılır kalır.
- **Yalnızca farklar saklanıyor:** Varsayılanla aynı olan satır
  veritabanına **yazılmaz**. Böylece ileride bir varsayılan değişirse,
  değişiklik eski müşterilere de yansır.
- **SAHİP kısıtlanamaz:** `KISITLANAMAZ_ROL = OWNER`. Aksi halde bir
  yönetici, sahibin yetkisini kapatıp müşteriyi kilitleyebilirdi.
- **Sunucu tarafında zorlanıyor:** Kontrol yalnızca arayüzde gizlemek
  değil; uçlar izne bakıyor. Testler, yetkisi alınmış bir kullanıcının
  isteği **elle** gönderdiğinde de reddedildiğini gösteriyor.
- **Geri alma:** `role_grants` tablosu boşaltılırsa sistem eski sabit
  davranışa döner; `VARSAYILAN` tablosu eski davranışın birebir aynısıdır.

---

## K-047 — Yayın takvimi planlar, PAYLAŞMAZ

- **Karar:** Takvim, onaylanmış içeriğin **ne zaman paylaşılacağını**
  planlar. Paylaşımı kullanıcı yapar ve takvimde "yayınlandı" olarak
  işaretler.
- **Neden kendisi paylaşmıyor:** v1'de Meta'dan yayın izni bilerek
  istenmiyor (K-021, K-041). İzin olmadan "paylaşıldı" yazmak, takvimin
  gerçeği değil varsayımı göstermesi olurdu. Panelde bu açıkça yazıyor:
  "Sistem kendisi paylaşmaz."
- **Yalnızca ONAYLANMIŞ içerik planlanabilir:** Onaysız içeriği takvime
  koymak, onay sistemini etkisiz hale getirirdi.
- **Taşıma, kopyalama değil:** Zaten planlı bir içerik yeni bir saate
  alındığında ikinci kayıt oluşmaz; mevcut kayıt taşınır. Aksi halde
  takvimde aynı içerik iki kez görünürdü.
- **Geçmiş silinemez:** "Yayınlandı" işaretli bir plan kaldırılamaz;
  neyin ne zaman paylaşıldığı kaydı kaybolmamalı.
- **Gecikme gizlenmiyor:** Zamanı geçmiş ama yayınlanmamış plan
  `gecikti` olarak işaretlenir.
- **Geri alma:** Takvim sayfası kaldırılabilir; `content_calendar`
  tablosu zaten vardı, yeni sütunlar (kim planladı / ne zaman
  yayınlandı) geri alınabilir bir migration ile eklendi.

---

## K-048 — İzinler artık gerçekten uygulanıyor (K-046'nın açık kalan yarısı)

- **Bulgu:** K-046 ile 17 izin tanımlanmıştı ama **8'i hiçbir yerde
  kontrol edilmiyordu**: `hesap.gor`, `ekip.gor`, `rapor.gor`,
  `rapor.onayla`, `icerik.uret`, `icerik.duzenle`, `icerik.onaya_sun`,
  `icerik.onayla`. Panelde bu anahtarlar açılıp kapatılıyor, hiçbir şey
  değişmiyordu. İçerik ve rapor onayı hâlâ koda gömülü **role** bakıyordu.
  Yani yetki ekranının yarısı **çalışmayan düğmeydi**.
- **Karar:** Onay durum makinesindeki sabit rol tablosu (`REQUIRED_ROLE`)
  kaldırıldı; yerine izin tablosu geldi (`IZIN_ICERIK`, `IZIN_RAPOR`).
  Görüntüleme izinleri sayfaların kendisinde zorlanıyor. AI üretim ucu
  için `require_permission` bağımlılığı eklendi.
- **Kimsenin yetkisi değişmedi:** İzin→varsayılan eşlemesi eski rol
  tablosunu **birebir** tekrar edecek şekilde seçildi:
  `icerik.duzenle`→EDİTÖR+, `icerik.onaya_sun`→STRATEJİST+,
  `icerik.onayla`→YÖNETİCİ+, `takvim.planla`→STRATEJİST+. Kanıt: bu
  değişiklikten sonra mevcut onay testlerinin **hiçbiri değişmedi**.
- **İki yeni izin:** Raporun iç incelemeye alınması (editör) ile müşteriye
  sunulması (stratejist) eski tabloda **farklı** seviyelerdeydi. Tek izne
  indirmek birinin yetkisini değiştirirdi; bu yüzden `rapor.hazirla` ve
  `rapor.sun` ayrı tanımlandı. Toplam izin 17 → 19.
- **Tekrarlanmasın diye test:** `test_her_izin_bir_yerde_gercekten_
  kontrol_ediliyor` katalogdaki her izni kaynakta arar. Kontrolsüz bir
  izin eklenirse test düşer. Bu test yazıldığında **8 izinle düşüyordu**.
- **Risk:** İzin anahtarı metin olarak aranıyor; farklı yazılan bir
  anahtar testi yanıltabilir. Buna karşı `izin_var_mi` tanımsız izinde
  **hata fırlatır**, sessizce kapı açmaz.

---

## K-049 — Kenar menüde yalnızca açılabilen sayfalar görünür

- **Sorun:** Menü, üyeliği olan herkese bütün bağlantıları gösteriyordu.
  İzni olmayan biri "Yetkiler"e tıklayınca "Bulunamadı" alıyordu.
- **Karar:** Üyelik bulunan her istekte kişinin bu müşterideki geçerli
  izinleri `request.state.izinler` içine konur; şablon buna bakar.
- **Gizlemek güvenlik değildir:** Asıl kilit sayfaların kendisindedir.
  `test_menude_gizlenen_sayfa_adres_yazilinca_da_acilmiyor` bunu
  kanıtlıyor: adres elle yazıldığında da 404 dönüyor.
- **Menü sayfayı düşürmez:** İzinler okunamazsa menü eksik görünür ama
  sayfa yine açılır. Menü yüzünden çalışan bir sayfanın kapanması, kârdan
  çok zarar olurdu.
- **Yan fayda:** Üyelik sorgusunun **üç ayrı kopyası** tek bir yardımcıya
  (`panel/ortak.py`) indirildi. Kopyalar zamanla birbirinden ayrılırdı.
