# DISCOVERY.md — Keşif Raporu

Tarih: 2026-09-20
Aşama: Aşama 0 (keşif). Kod yazılmadı, hiçbir üretim sistemi değiştirilmedi.

---

## 1. Özet

Bu oturumda hiçbir dosya değiştirilmedi, silinmedi veya gönderilmedi. Yalnızca
okuma yapıldı. İki adet **bloke edici** durum tespit edildi (bkz. Bölüm 6).

---

## 2. Çalıştığım ortam (VPS DEĞİL)

| Özellik | Değer |
|---|---|
| Makine | Geçici bulut sanal makinesi (Claude Code oturum konteyneri) |
| İşletim sistemi | Ubuntu 24.04.4 LTS |
| CPU / RAM / Disk | 4 çekirdek / 15 GB RAM / 252 GB (30 GB boş) |
| Docker | 29.3.1 — çalışıyor (elle başlatıldı) |
| Docker Compose | v5.1.1 |
| PostgreSQL istemcisi | 16.13 |
| Redis | 7.0.15 |
| Node.js | 22.22.2 |
| Python | 3.11.15 |
| Açık port / çalışan servis | Yok |
| npm/paket erişimi | Var (HTTP 200) |
| Hostinger VPS'e (187.124.22.8) erişim | **YOK** — SSH portu kapalı, ssh istemcisi kurulu değil |
| Dış HTTPS erişimi | Sınırlı — proxy üzerinden, agencycortex.tech'e erişim 403 ile engellendi |

**Anlamı:** Bu oturum sizin VPS'inizin içinde değil. Tamamen izole, geçici bir
geliştirme makinesi. Oturum kapandığında bu makine silinir; yalnızca Git'e
gönderilen şeyler kalıcı olur.

---

## 3. Hostinger hesabınızdaki mevcut altyapı

Salt okunur olarak kontrol edildi:

| Kaynak | Durum |
|---|---|
| VPS | **KVM 4**, aylık 1.814,99 TRY, otomatik yenileme açık, 18.09.2026'da alınmış |
| Domain | **agencycortex.tech**, 18.09.2026'da alınmış, 18.09.2027'ye kadar geçerli |
| Domain fiyatı | 2.996,82 TRY / yıl, otomatik yenileme açık |
| DNS A kaydı | `agencycortex.tech` → `187.124.22.8` (TTL 300) |
| DNS AAAA kaydı | `2a02:4780:79:bdf7::1` |
| DNS CNAME | `www` → `agencycortex.tech` |
| DNS MX | `10 agencycortex.tech` |

Yorum: Domain adı ("agencycortex") ve satın alma tarihinin VPS ile aynı gün
olması, bu VPS + domain ikilisinin **sosyal medya ajansı asistanı** projesi için
alındığını gösteriyor. Bu proje için ayrılmış, boş ve uygun bir altyapı var.
KVM 4 paketi bu iş yükü (PostgreSQL + Redis + worker + API + panel) için yeterli.

---

## 4. Bu oturuma bağlı repository

| Özellik | Değer |
|---|---|
| Klasör | `/home/user/gaziantepli-taha-usta-erp` |
| Git remote | `github.com/BrandCoor/gaziantepli-taha-usta-erp` |
| Aktif branch | `claude/admiring-hopper-2ly69w` |
| Çalışma alanı | Temiz (bekleyen değişiklik yok) |
| Kaynak dosya sayısı | 54 (src altında) |

**Bu repo ne içeriyor:** "Gaziantepli Taha Usta" adlı bir **restoran POS ve ERP
otomasyonu**. Tamamen farklı bir iş:

- Windows masaüstü uygulaması (Electron + React + Vite + TypeScript)
- Yerel SQLite veritabanı (Prisma ORM)
- Modüller: kasa/POS, masa adisyonu, garson mobil PWA, paket servis, Caller ID,
  ESC/POS mutfak yazıcıları, cari hesap, personel, giderler, raporlar
- Bulut tarafı: **cPanel üzerinde PHP dosyaları** (`cpanel-yuklenecekler/`),
  `api.rymedya.com.tr`, `garson.rymedya.com.tr`, `patron.rymedya.com.tr`
- `.env.example` içeriği: `VITE_API_URL=https://api.rymedya.com.tr/api`

**Sosyal medya asistanı projesiyle hiçbir ortak noktası yok.** Farklı müşteri,
farklı teknoloji (Electron/PHP/SQLite vs. FastAPI/PostgreSQL/Docker), farklı
barındırma (cPanel vs. VPS), farklı domain (rymedya.com.tr vs. agencycortex.tech).

---

## 5. Risk değerlendirmesi

| Risk | Seviye | Açıklama |
|---|---|---|
| Sosyal medya projesini restoran reposuna yazmak | **Yüksek** | İki proje birbirine karışır, restoran müşterisinin üretim sistemi tehlikeye girer, geri almak zorlaşır |
| VPS'e bu oturumdan erişilememesi | **Yüksek** | Kurulum/deploy/test bu oturumdan doğrudan yapılamaz |
| Oturumun geçici olması | Orta | Git'e gönderilmeyen her şey kaybolur |
| Meta/Instagram uygulama onayı | Orta | Instagram içgörü izinleri Meta'nın uygulama incelemesinden geçmeyi gerektirir; bu süreç günler-haftalar sürebilir |
| Manus API v2 dokümantasyonuna erişim | Orta | Bu ortamdan dış web erişimi kısıtlı; entegrasyon tahminle yazılamaz |
| AI maliyetleri | Orta | Claude + Manus API kullanımı müşteri başına aylık maliyet doğurur; bütçe limiti şart |
| Domain e-posta (MX) yanlış kurulu | Düşük | MX kaydı domainin kendisini gösteriyor; şu an e-posta çalışmaz. Rapor e-postası gerekirse düzeltilmeli |

---

## 6. Bloke edici iki durum

### 6.1. Bu oturum yanlış projeye bağlı

Sosyal medya asistanı için **yeni ve ayrı bir repository** gerekiyor. Mevcut
restoran reposuna yazmak hem teknik olarak yanlış hem de restoran müşterisinin
çalışan sistemi için risklidir.

### 6.2. Bu oturumdan VPS'e bağlanılamıyor

Bu geliştirme makinesinde SSH istemcisi yok ve dış ağ erişimi proxy tarafından
kısıtlanmış. VPS'inize (187.124.22.8) doğrudan bağlanamıyorum.

**Bu durumda uygulanabilir çalışma modeli:**

1. Ben kodun tamamını bu makinede yazarım, Docker + PostgreSQL + Redis ile
   burada çalıştırır ve testlerini gerçekten koştururum.
2. Kodu GitHub'a gönderirim.
3. Size VPS'e yapıştıracağınız, tek seferlik, hazır kurulum komutları veririm.
4. Siz komutu çalıştırıp çıktıyı bana yapıştırırsınız; hata varsa ben düzeltirim.

Bu model işe yarar ama her deploy adımında sizin bir komut çalıştırmanız gerekir.
Bunu ortadan kaldırmanın yolu Bölüm 7'de.

---

## 7. VPS'e doğrudan erişim için seçenekler

| Seçenek | Nasıl çalışır | Avantaj | Dezavantaj |
|---|---|---|---|
| **A. GitHub Actions ile otomatik deploy** (önerilen) | Kodu GitHub'a gönderirim; GitHub sunucusu VPS'e bağlanıp otomatik kurar | Sizin komut çalıştırmanız gerekmez, tekrarlanabilir, kayıt altında | İlk kurulumda VPS'e bir SSH anahtarı eklemeniz gerekir (tek seferlik) |
| **B. Siz komutları yapıştırırsınız** | Ben komut veririm, siz çalıştırırsınız | Ek kurulum yok | Her adımda sizin müdahaleniz gerekir, yavaş |
| **C. Hostinger panelinden başlangıç betiği** | VPS yeniden kurulurken otomatik betik çalışır | Otomatik | VPS'i sıfırlar; üzerinde bir şey varsa gider |

Önerim: **A**. Tek seferlik bir anahtar kurulumundan sonra süreç tamamen
otomatik işler.

---

## 8. Sonraki adım için hazır olanlar

Bloke edici sorular çözülür çözülmez şunlar hemen yapılabilir (onay gerektirmez):

- Proje iskeleti, Docker Compose (PostgreSQL + Redis + API + worker + panel)
- Veritabanı şeması ve migration'lar (29 tablo)
- Kullanıcı / workspace / rol / oturum sistemi
- `AIProvider` arayüzü ve sahte (fake) sağlayıcılar — gerçek API anahtarı gerekmeden
- Instagram adaptör iskeleti ve sahte veri ile testler
- Tüm test paketi ve CI kurulumu

Gerçek API anahtarı, gerçek Instagram hesabı ve üretim deploy'u için ayrıca
onayınızı isteyeceğim.

---

## 9. EK — Ağ erişimi kesin teşhisi (2026-09-20, ikinci kontrol)

Kullanıcı SSH anahtarı oluşturduktan sonra bağlantı tekrar ve ayrıntılı test edildi.

### Yapılan testler

| Test | Sonuç |
|---|---|
| `openssh-client` kurulumu | **Başarılı** (ilk deneme paket listesi eski olduğu için başarısızdı, `apt-get update` sonrası kuruldu) |
| VPS 187.124.22.8 port 22 | Bağlanılamadı |
| VPS port 2222 / 2022 / 8443 / 8080 / 9022 / 65022 / 3306 / 5432 | Hepsi bağlanılamadı |
| VPS port 80 ve 443 | TCP bağlandı |
| **github.com port 22** | **Bağlanılamadı** |
| 1.1.1.1 port 443 | Bağlandı |
| 1.1.1.1 port 22 / 2222 | Bağlanılamadı |

### Teşhis

Port 22 yalnızca VPS için değil, **her hedef için** kapalı (github.com:22 de
kapalı). Yani sorun VPS'te, Hostinger'da veya kullanıcının SSH anahtarında
değil — bu geliştirme ortamının ağ politikasında.

80 ve 443 portlarına "bağlandı" görünmesi yanıltıcı: bu bağlantılar VPS'e değil,
Anthropic'in egress (çıkış) ağ geçidine ulaşıyor. Gelen yanıt:

```
HTTP/2 403
x-deny-reason: host_not_allowed
Host not in allowlist: agencycortex.tech.
Add this host to your network egress settings to allow access.
```

TLS sertifikasının kimden geldiğine bakıldığında da bu doğrulandı:

```
subject = CN = agencycortex.tech
issuer  = O = Anthropic, CN = Egress Gateway SDS Issuing CA (production)
```

Yani VPS'e hiç ulaşılmadı; ağ geçidi araya girip reddetti.

Ortam dokümanı (`/root/.ccr/README.md`) bunu açıkça yazıyor:

> **Not supported through the proxy (report, do not work around):** ...
> raw-TCP databases, non-443 HTTPS ports
>
> **403 / 407 from the proxy:** The destination host is not allowed by your
> organization's egress policy for this session. Do not retry or route around it
> — report the blocked host.

SSH, 22 numaralı portta ham TCP protokolüdür. Bu ortamdan desteklenmiyor ve
etrafından dolaşılması yasak. **Bu bir ayar sorunu değil, ortamın yapısal sınırı.**

### Sonuç: SSH ile doğrudan bağlantı bu oturumdan mümkün değil

Ancak SSH'a gerek kalmadan VPS'e deploy etmenin yolu bulundu (bkz. 9.1).

### 9.1. SSH'sız deploy yolu — Hostinger API

Hostinger bağlayıcısında şu araç mevcut:

**`VPS_createNewProjectV1`** — "Deploy new project from docker-compose.yaml
contents or download contents from URL."

Parametreleri: `virtualMachineId`, `project_name`, `content` (ham YAML veya
GitHub deposu adresi), `environment` (ortam değişkenleri).

Bu, VPS'e **SSH olmadan**, doğrudan Hostinger API'si üzerinden Docker Compose
projesi kurabilmek anlamına gelir. Sunucu yönetimi (snapshot, güvenlik duvarı,
SSH anahtarı ekleme, PTR kaydı) için de araçlar mevcut.

**Eksik olan tek şey:** `virtualMachineId` (VPS'in sayısal kimliği). Bağlayıcıda
VPS listeleme aracı tanımlı olmadığı için bu numarayı okuyamıyorum; kullanıcının
Hostinger panelinden vermesi gerekiyor.

### 9.2. Güncellenmiş çalışma modeli

| Katman | Yöntem | SSH gerekir mi? |
|---|---|---|
| Kod yazma ve test | Bu makinede (Docker + PostgreSQL + Redis mevcut) | Hayır |
| Kod saklama | GitHub deposu | Hayır |
| **VPS'e ilk kurulum ve güncelleme** | **Hostinger API `createNewProject`** | **Hayır** |
| Sunucu bakımı (snapshot, firewall) | Hostinger API | Hayır |
| Kurulum sonrası doğrulama (siteye bakmak) | HTTPS — ancak domainin egress izin listesine eklenmesi gerekir | Hayır |
| Sunucu içinde elle hata ayıklama | Mümkün değil — kullanıcı komut yapıştırmalı | — |

K-003 kararı (GitHub Actions ile deploy) bu bulgu ışığında gözden geçirilmelidir;
bkz. DECISIONS.md K-007.
