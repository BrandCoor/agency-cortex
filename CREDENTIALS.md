# Gizli Bilgiler Rehberi

> Bu dosya **hiçbir gerçek şifre içermez.** Hangi bilginin nereden alınacağını
> ve nereye yazılacağını anlatır.

Tüm gizli değerler sunucudaki `.env` dosyasında tutulur. Bu dosya Git'e
gönderilmez.

---

## 1. Sistemin kendi ürettiği şifreler

Bunları hiçbir yerden almanız gerekmez; kurulum sırasında ben üretirim.

| Ayar | Ne işe yarar |
|---|---|
| `SECRET_KEY` | Kullanıcı oturumlarını imzalar |
| `ENCRYPTION_KEY` | Sosyal medya token'larını şifreler |
| `POSTGRES_PASSWORD` | Veritabanı şifresi |

---

## 2. Sizin hesabınızdan almanız gerekenler

### Claude API anahtarı
- **Ne işe yarar:** İçerik senaryolarını ve stratejik raporları üretir.
- **Nereden alınır:** <https://console.anthropic.com> → API Keys → Create Key
- **Maliyet:** Kullandıkça ödenir. Aylık bütçe sınırı `.env` içinde
  `AI_MONTHLY_BUDGET_USD` ile belirlenir.
- **Yazılacağı yer:** `.env` → `ANTHROPIC_API_KEY`
- ⚠️ Anahtarı sohbete yapıştırmayın. Nasıl güvenle ileteceğinizi Aşama 5'te
  anlatacağım.

### Manus API anahtarı
- **Ne işe yarar:** Rakip ve trend araştırması yapar.
- **Nereden alınır:** Manus hesabınızın API ayarları bölümü.
- **Yazılacağı yer:** `.env` → `MANUS_API_KEY`

### Meta (Instagram/Facebook) uygulama bilgileri
- **Ne işe yarar:** Müşterilerinizin Instagram profesyonel hesaplarına
  izinli bağlantı kurar.
- **Nereden alınır:** <https://developers.facebook.com> → uygulamanız →
  Ayarlar → Temel
- **Yazılacağı yer:** `.env` → `META_APP_ID` ve `META_APP_SECRET`
- ⚠️ Instagram içgörü izinleri için Meta'nın **uygulama incelemesinden**
  geçmek gerekir. Bu süreç günler sürebilir; Aşama 3'te ayrıntısını
  anlatacağım.

---

## 3. Asla yapılmaması gerekenler

- Gizli değerleri sohbete yazmak
- `.env` dosyasını Git'e göndermek
- Anahtarları kod dosyalarının içine yazmak
- Aynı anahtarı test ve üretim ortamında birlikte kullanmak
