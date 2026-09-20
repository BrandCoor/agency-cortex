# Kurulum Rehberi

Bu dosyada **sizin yapacağınız işler** ile **benim yapacağım işler** kesin
olarak ayrılmıştır.

> **Altın kural:** Gerçek şifre, API anahtarı veya token'ı **sohbete
> yazmayın.** Bunları yalnızca aşağıda gösterilen güvenli alanlara girin.

---

## Bölüm 1 — Sizin yapacağınız işler (Meta / Instagram)

Bunlar hesap sahipliği gerektirir; ben yapamam.

### Adım 1: Instagram hesabını profesyonele çevirin

Pilot olarak kullanacağınız Instagram hesabı **Business** veya **Creator**
türünde olmalı.

1. Instagram uygulamasını açın
2. Profil → ☰ → **Ayarlar**
3. **Hesap türü ve araçlar** → **Profesyonel hesaba geç**
4. **İşletme** (Business) veya **İçerik Üreticisi** (Creator) seçin

**Neden gerekli?** Kişisel hesaplarda içgörü (erişim, kaydetme, demografi)
verisi **yoktur.** Kişisel hesabı bağlarsak sistem boş veri çeker ve raporlar
anlamsız olur.

**Beklenen sonuç:** Instagram profilinizde "Profesyonel Kontrol Paneli"
görünür hale gelir.

---

### Adım 2: Meta geliştirici hesabı açın

1. <https://developers.facebook.com> adresine gidin
2. Sağ üstten **Başlayın** / **Get Started**
3. Facebook hesabınızla giriş yapın
4. Telefon ve e-posta doğrulamasını tamamlayın

> ⚠️ İki aşamalı doğrulama kodunu **yalnızca Meta ekranına** girin.

---

### Adım 3: Meta uygulamasını oluşturun

1. **My Apps** → **Create App**
2. Uygulama türü: **Business**
3. Uygulama adı: `Agency Cortex` (istediğiniz adı verebilirsiniz)
4. İletişim e-postası: kendi e-postanız
5. **Create App**

---

### Adım 4: Instagram ürününü ekleyin

1. Uygulama panelinde **Add Product** listesinden **Instagram** → **Set up**
2. Giriş modeli olarak **Instagram Login** (Business Login for Instagram) seçin

**Neden Instagram Login?** Bu modeli seçtim çünkü bağlı bir Facebook Sayfası
gerektirmiyor ve ilk sürümümüz yalnızca okuma yapacak. Gerekçesi
`DECISIONS.md` → K-012'de yazılı.

> ⚠️ Meta, bir uygulamanın Instagram Login **veya** Facebook Login'den
> **yalnızca birini** seçmesini istiyor. İkisini birden kurmaya çalışmayın.

---

### Adım 5: Adresleri Meta paneline girin

Bu adresleri **ben ürettim.** Meta paneline **birebir aynı** şekilde
yapıştırın — tek harf veya sondaki `/` farkı bile OAuth hatası verir.

| Meta panelindeki alan | Yapıştırılacak adres |
|---|---|
| **Valid OAuth Redirect URI** | `https://agencycortex.tech/api/v1/oauth/meta/callback` |
| **Deauthorize Callback URL** | `https://agencycortex.tech/api/v1/oauth/meta/deauthorize` |
| **Data Deletion Request URL** | `https://agencycortex.tech/api/v1/oauth/meta/data-deletion` |
| **Webhook Callback URL** | `https://agencycortex.tech/api/v1/webhooks/meta` |

> Bu adreslerin çalışması için sistemin sunucuya kurulmuş ve HTTPS'in aktif
> olması gerekir. Kurulumu ben yapacağım; siz bu adımı **kurulumdan sonra**
> tamamlayın.

---

### Adım 6: Pilot hesabı test kullanıcısı olarak ekleyin

1. Uygulama panelinde **App Roles** / **Roles** bölümü
2. Instagram profesyonel hesabınızı **test kullanıcısı** veya **yönetici**
   olarak ekleyin

**Neden gerekli?** Uygulama incelemesinden geçmeden önce yalnızca kendi
eklediğiniz hesaplarla test yapabilirsiniz.

---

### Adım 7: Bana şu bilgileri iletin

| Bilgi | Nerede yazıyor | Sohbete yazılır mı? |
|---|---|---|
| **App ID** | Meta panel → Ayarlar → Temel | ✅ Evet, yazabilirsiniz |
| **App Secret** | Meta panel → Ayarlar → Temel → Göster | ❌ **HAYIR** |

**App Secret'ı nasıl ileteceksiniz?** Kurulum tamamlandığında size sunucuda
çalıştıracağınız tek satırlık bir komut vereceğim. Değer doğrudan sunucudaki
korumalı dosyaya yazılacak, sohbetten geçmeyecek.

---

### Adım 8: Uygulama incelemesi (sonraki aşama — şimdi değil)

Kendi hesabınızla test ederken buna gerek yok. Ama **müşterilerinizin**
hesaplarını bağlayacağınız için Meta **App Review** ve **Business
Verification** isteyecektir.

Gerekecekler (ben hazırlayacağım, siz onaylayacaksınız):
- Dışarıdan açılabilen HTTPS adresi ✅ (kurulumda hazır olacak)
- Çalışan OAuth akışı ✅ (kod hazır)
- Gizlilik politikası adresi — *sizin onaylamanız gerekecek*
- Uygulama simgesi — *sizin seçmeniz gerekecek*
- Her izin için ekran kaydı — *ben çekip size göstereceğim*
- İnceleme ekibi için kullanım talimatı — *ben yazacağım*

> ⏰ **Bu süreç günler-haftalar sürebilir.** Pilot testi bitirir bitirmez
> başlatmanızı öneririm.

---

## Bölüm 2 — Benim yapacağım işler

Bunlar için sizden bir şey istemiyorum:

- [x] Sunucu ve depo keşfi
- [x] Docker altyapısı, veritabanı, kuyruk sistemi
- [x] Kullanıcı, müşteri izolasyonu, roller
- [x] Platform adaptör mimarisi
- [x] OAuth akışı (state üretimi, tek kullanımlık kod, hata yönetimi)
- [x] Token'ların şifreli saklanması
- [x] Webhook imza doğrulama ve tekrar koruma
- [x] Redirect ve webhook adreslerinin üretilmesi
- [ ] Sunucuya kurulum ve HTTPS *(onayınızı bekliyorum)*
- [ ] Meta doküman değerlerinin doğrulanması *(erişim engeli — Bölüm 3)*
- [ ] Rapor motoru ve içerik üretimi
- [ ] Uygulama incelemesi hazırlıkları

---

## Bölüm 3 — Çözülmesi gereken engel

Meta'nın resmî dokümanlarına geliştirme ortamımdan erişemiyorum:

```
developers.facebook.com -> 403 (ağ politikası reddi)
graph.facebook.com      -> 403 (ağ politikası reddi)
```

Bu yüzden şu 4 değeri **boş bıraktım** ve tahminle doldurmadım:

- `META_API_VERSION` — kullanılacak API sürümü
- `META_AUTHORIZE_URL` — izin ekranının tam adresi
- `META_TOKEN_URL` — kodu anahtara çeviren adres
- `META_SCOPES` — istenecek izinlerin tam adları

Bunlar boşken sistem **canlı moda geçmez** ve açık hata verir.

### Çözüm seçenekleri

**Seçenek A (önerim):** Claude Code ortam ayarlarınızda erişim listesine
`developers.facebook.com` ve `graph.facebook.com` ekleyin. Ben dokümanı
okuyup değerleri doğrularım, siz bir şey yapmazsınız.

**Seçenek B:** Meta panelinde Instagram → Business Login ayarları sayfasında
gösterilen izin adlarını ve API sürümünü bana iletirsiniz. Bunlar gizli
bilgi değildir.

---

## Sık karşılaşılan hatalar

| Hata | Sebebi | Çözümü |
|---|---|---|
| `redirect_uri_mismatch` | Adres Meta panelindekiyle birebir aynı değil | Adım 5'teki adresi tekrar kopyalayın; sondaki `/` farkına dikkat |
| İçgörü verisi boş geliyor | Hesap profesyonel değil | Adım 1'i tekrarlayın |
| `Invalid Verify Token` | Webhook token'ı eşleşmiyor | Aynı değerin hem `.env` hem Meta panelinde olduğunu kontrol edin |
| İzin ekranı açılmıyor | `META_*` ayarları boş | Bölüm 3'e bakın |

---

## Bölüm 4 — Sunucu kurulumu için sizden gereken (3 adım)

Kodunuz ve uygulama paketi **gizli kalacak.** Bunun için GitHub'ın
sunucunuza güvenli bağlanabilmesi gerekiyor. Bir kerelik işlem.

### Adım 1: Erişim anahtarı oluşturun

Kendi bilgisayarınızda terminal/komut istemi açın ve şunu yapıştırın:

```bash
ssh-keygen -t ed25519 -C "agency-cortex-deploy" -f ~/.ssh/agency_cortex_deploy -N ""
```

**Ne yapar?** Birbirine eşlenmiş iki anahtar üretir:
- `agency_cortex_deploy.pub` → **açık** anahtar (paylaşılabilir, kilit gibi)
- `agency_cortex_deploy` → **gizli** anahtar (asla paylaşılmaz, anahtar gibi)

**Beklenen sonuç:** "Your identification has been saved" yazısı.

---

### Adım 2: Açık anahtarı bana gönderin

```bash
cat ~/.ssh/agency_cortex_deploy.pub
```

Çıkan tek satırı (`ssh-ed25519 AAAA...` ile başlar) **sohbete yapıştırın.**

> ✅ Bu anahtarı paylaşmak **güvenlidir.** Kilidin kendisidir, anahtarı değil.
> Ben bunu Hostinger üzerinden sunucunuza tanıtacağım.

---

### Adım 3: Gizli anahtarı GitHub'a ekleyin

> ⛔ **Bu anahtarı sohbete YAPIŞTIRMAYIN.** Doğrudan GitHub'a girin.

1. <https://github.com/BrandCoor/agency-cortex/settings/secrets/actions>
   adresine gidin
2. **New repository secret**
3. **Name** kutusuna tam olarak şunu yazın: `VPS_SSH_KEY`
4. **Secret** kutusuna gizli anahtarın **tamamını** yapıştırın.
   İçeriği görmek için:
   ```bash
   cat ~/.ssh/agency_cortex_deploy
   ```
   `-----BEGIN` satırından `-----END` satırına kadar **her şeyi** kopyalayın.
5. **Add secret**

**Beklenen sonuç:** Listede `VPS_SSH_KEY` görünür. Değeri bir daha
görüntülenemez — bu normaldir ve güvenlik içindir.

---

### Sonra ne olacak?

Ben kurulumu başlatacağım. Sistem sırayla:

1. Sunucuda Docker'ı hazırlar
2. Yapılandırmayı gönderir
3. **Gizli anahtarları sunucuda üretir** (hiçbiri bana veya GitHub'a geçmez)
4. Uygulama paketini indirir ve başlatır
5. Veritabanı şemasını kurar
6. HTTPS sertifikasını otomatik alır
7. Sağlık kontrolü yapar ve sonucu bildirir

Sorun çıkarsa log'ları okuyup düzeltirim. Geri dönüş yolu açık:
sunucu yedeği 20 Eylül'de alındı.
