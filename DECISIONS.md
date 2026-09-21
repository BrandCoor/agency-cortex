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
