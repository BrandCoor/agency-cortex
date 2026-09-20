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
