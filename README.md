# Agency Cortex

**Canlı:** https://agencycortex.tech · [Sağlık kontrolü](https://agencycortex.tech/readyz)

Sosyal medya ajansları için çok müşterili sosyal medya asistanı.

Her müşteri kendi izole **çalışma alanında** (workspace) tutulur. Sistem izinli
sosyal medya hesaplarından veri toplar, performansı ölçer, rapor üretir ve
içerik senaryosu önerir.

> **Önemli:** Bu sistem hiçbir paylaşımı, yorumu veya mesajı **insan onayı
> olmadan göndermez.** İlk sürümde otomatik yayınlama tamamen kapalıdır.

---

## Durum

| Aşama | Konu | Durum |
|---|---|---|
| 0 | VPS ve repo keşfi | ✅ Tamamlandı |
| 1 | Docker, PostgreSQL, Redis, sağlık kontrolü, loglama | ✅ Tamamlandı |
| 2 | Kullanıcı, çalışma alanı, rol, oturum | ✅ Tamamlandı |
| 3 | Instagram/Facebook OAuth + veri senkronu | 🟡 Kod hazır, 4 Meta sabiti doğrulanmayı bekliyor |
| 4 | Metrikler, KPI motoru, günlük/haftalık rapor | ✅ Tamamlandı |
| 5 | Claude API ile içerik senaryosu | ✅ Tamamlandı |
| 6 | Manus API ile araştırma | 🟡 Doküman erişimi engelli |
| 7 | İnsan onay paneli | ✅ Tamamlandı |
| 8 | Rakip ve trend modülü | ⬜ Sırada |
| 9 | Gemini sağlayıcısı | ⬜ Planlanmadı (ayarlardan kaldırıldı) |
| 10 | Güvenlik, yedekleme, üretim kurulumu | ✅ Tamamlandı |
| 11 | Kullanıcı yönetimi ve panel yenileme | ✅ Tamamlandı |
| 12 | n8n otomasyon altyapısı | ✅ Tamamlandı (5 iş akışı sunucuda etkin) |
| 13 | Yayın takvimi (planlama; sistem kendisi paylaşmaz) | ✅ Tamamlandı |
| 14 | Ayrıntılı yetkiler (19 izin, müşteri başına ayarlanır) | ✅ Tamamlandı |

---

## Bilgisayarınızda çalıştırmak

Tek gereken Docker'ın kurulu olması.

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

Sonra tarayıcıdan kontrol edin:

| Adres | Ne gösterir |
|---|---|
| http://localhost:8000/healthz | Uygulama ayakta mı |
| http://localhost:8000/readyz | Veritabanı ve kuyruk çalışıyor mu |
| http://localhost:8000/docs | API arayüzü |

Durdurmak için: `docker compose down`
Verileri de silmek için: `docker compose down -v` (**dikkat: veri silinir**)

---

## Sistemin parçaları

| Parça | Görevi |
|---|---|
| **api** | Web isteklerini karşılar (FastAPI) |
| **worker** | Arka plandaki uzun işleri yapar (veri çekme, rapor üretme) |
| **beat** | İşleri zamanında başlatır (günlük rapor gibi) |
| **postgres** | Tüm veriler burada saklanır |
| **redis** | İş kuyruğu |
| **caddy** | Dış dünyaya açılan kapı; HTTPS sertifikasını kendi alır ve yeniler |
| **n8n** | Otomasyon motoru: iş akışlarını zamanında çalıştırır |

### n8n neden "ikinci bir uygulama" değil?

n8n **yalnızca** zamanlama, sıralama, tekrar deneme ve dış servis
çağrılarından sorumludur. Veritabanına **doğrudan yazmaz**; her şey
Agency Cortex API'sinden geçer.

| Kimin işi | Ne |
|---|---|
| **Agency Cortex** | Kimlik, yetki, müşteri izolasyonu, AI bütçesi, onay sistemi, iş kuralları |
| **n8n** | Zamanlama, sıra, tekrar deneme, dış servis çağrıları |

n8n'e ait bir kimlik vardır (makine kimliği) ve bu kimlik **yalnızca
izin verilen müşterilerde** iş yapabilir. n8n'den gelen `workspace_id`
tek başına hiçbir yetki sağlamaz — her istekte ayrıca doğrulanır.

Gerekçesi: DECISIONS.md **K-032** ve **K-033**.

---

## Güvenlik kuralları

Bunlar koda gömülüdür, isteğe bağlı değildir:

- Her müşterinin verisi ayrıdır; bir müşteri diğerinin verisini göremez.
- Şifreler, token'lar ve API anahtarları koda yazılmaz; yalnızca `.env` içinde
  tutulur ve `.env` asla Git'e gönderilmez.
- Loglarda token, şifre ve kişisel bilgiler otomatik maskelenir.
- Üretim ortamı şablon şifrelerle **açılmaz**; uygulama hata verip durur.
- Yayın, yorum ve mesaj gönderimi ilk sürümde kapalıdır. Yayın takvimi
  **planlama** yapar; paylaşımı siz yaparsınız ve takvimde işaretlersiniz.
- Yetki kontrolü sunucu tarafındadır. Menüde bir bağlantıyı gizlemek
  güvenlik sayılmaz: adres elle yazıldığında da reddedilir.
- Panelde açılıp kapatılan her izin gerçekten uygulanır; bunu bir test
  sürekli denetler.

---

## Diğer belgeler

| Dosya | İçeriği |
|---|---|
| `DISCOVERY.md` | Sunucu ve ortam keşfi, ağ kısıtları |
| `DECISIONS.md` | Alınan teknik kararlar ve gerekçeleri |
| `CHANGELOG.md` | Neyin ne zaman değiştiği |
| `CREDENTIALS.md` | Hangi gizli bilginin nereye yazılacağı |
| `INSTALLATION.md` | Sizin yapacağınız adımlar (Meta hesap kurulumu) |
| `docs/platforms/meta.md` | Meta entegrasyonunda doğrulanacaklar |
| `docs/otomasyon-plani.md` | Kaç iş akışı var, her müşteride nasıl çalışıyor |
| `OPERATIONS.md` | Günlük işletme: yedek, günlük, sorun giderme |
| `DEPLOYMENT.md` | Sunucuya kurulum ve güncelleme |
