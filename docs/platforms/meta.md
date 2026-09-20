# Meta (Instagram / Facebook) Entegrasyonu

**Durum: KOD HAZIR — 4 sabit doğrulanmayı bekliyor.**

| Ne | Durum |
|---|---|
| Giriş modeli seçimi | ✅ Instagram Login (bkz. `DECISIONS.md` K-012) |
| OAuth akışı (state, kod değişimi, hata yönetimi) | ✅ Yazıldı ve test edildi |
| Token şifreli saklama | ✅ Yazıldı ve test edildi |
| Webhook imza + tekrar koruma | ✅ Yazıldı ve test edildi |
| Redirect / webhook adresleri | ✅ Üretildi (aşağıda) |
| **API sürümü, izin adları, uç adresleri** | ❌ **Doğrulanmadı** |
| Gerçek hesapla uçtan uca test | ❌ Yapılmadı |

---

## Üretilen adresler

Meta App Dashboard'a **birebir aynı** girilmelidir:

```
Redirect URI    : https://agencycortex.tech/api/v1/oauth/meta/callback
Deauthorize     : https://agencycortex.tech/api/v1/oauth/meta/deauthorize
Data deletion   : https://agencycortex.tech/api/v1/oauth/meta/data-deletion
Webhook         : https://agencycortex.tech/api/v1/webhooks/meta
```

---

## Doğrulanması gereken 4 değer

Bunlar `.env` içinde **boş** bırakıldı. Boşken sistem canlı moda geçmez.

| Ayar | Ne olacağı | Kaynak |
|---|---|---|
| `META_API_VERSION` | Kullanılacak Graph API sürümü | Meta API sürüm sayfası |
| `META_AUTHORIZE_URL` | İzin ekranının tam adresi | Business Login for Instagram |
| `META_TOKEN_URL` | Kodu anahtara çeviren uç | Business Login for Instagram |
| `META_SCOPES` | İstenecek izin adları (`instagram_business_*` ailesi) | Instagram Login izin listesi |
| `META_GRAPH_BASE_URL` | Veri uçlarının kök adresi | Instagram Platform overview |

> Rehbere göre Instagram Login izin ailesi `instagram_business_*` biçimindedir.
> Kesin adlar Meta panelinde ve resmî dokümanda gösterilenlerle
> doğrulanacaktır.

---

## Bu belgenin geri kalanı: ilk tespit

---

## Neden henüz yazılmadı?

Meta'nın API adresleri, izin (permission) adları, metrik adları ve token
yenileme akışı **tahminle yazılamaz.** Yanlış yazılmış bir entegrasyon
çökmez — sessizce **yanlış veri** üretir. O yanlış veri normalize edilir,
rapora girer ve müşteriye sunulur. Bu, hiç çalışmamasından daha kötüdür.

Bu yüzden `MetaAdapter` sınıfı bilerek **hiçbir yetenek bildirmiyor**.
Çağrılan her iş açık hata veriyor.

### Engel

Geliştirme ortamından resmî dokümantasyona erişim ağ politikası tarafından
engellendi:

```
developers.facebook.com:443 -> 403 (policy denial)
graph.facebook.com:443      -> 403 (policy denial)
```

Ortam belgesi bu durumda "raporla, etrafından dolaşma" diyor. Bu yüzden
ezberden endpoint yazmak yerine durumu belgeliyorum.

### Engeli kaldırmanın iki yolu

1. **Ağ izni:** Claude Code ortam ayarlarında `developers.facebook.com`
   adresinin erişim listesine eklenmesi. Sonrasında dokümanı okuyup
   adaptörü yazabilirim.
2. **Elle aktarım:** İlgili doküman sayfalarının içeriğini bana iletmeniz.

---

## Tamamlanmadan önce doğrulanması gerekenler

Aşağıdaki her satır, resmî dokümandan **doğrulanacak** ve kaynağı bu
belgeye yazılacaktır. Şu an hiçbiri doğrulanmamıştır.

### 1. Hesap türü
- [ ] Instagram **profesyonel** (işletme/içerik üreticisi) hesap şartı
- [ ] Hesabın bir Facebook Sayfası ile bağlı olma zorunluluğu
- [ ] Kişisel hesaplarda hangi verilerin **bulunmadığı**

> Sistem kuralı: Kişisel hesaba profesyonel hesap içgörüsü varmış gibi
> davranılmayacak. `SocialAccount.is_professional` alanı bunun için var.

### 2. İzinler (permissions)
- [ ] Hesap bilgisi okumak için gereken izin adları
- [ ] İçerik listelemek için gereken izin adları
- [ ] İçgörü (insights) okumak için gereken izin adları
- [ ] Yorum okumak için gereken izin adları
- [ ] Hangi izinlerin **uygulama incelemesi** gerektirdiği

### 3. OAuth akışı
- [ ] Yetkilendirme adresi ve parametreleri
- [ ] Kodun anahtara çevrilme adresi
- [ ] Kısa ömürlü → uzun ömürlü anahtar dönüşümü
- [ ] Anahtar geçerlilik süresi ve yenileme yöntemi
- [ ] Callback adresinin uygulama ayarlarında tanımlanma şekli

### 4. Veri uçları
- [ ] İçerik listeleme ucu ve alan adları
- [ ] İçerik içgörü ucu ve **gerçek metrik adları**
- [ ] Hesap içgörü ucu ve gerçek metrik adları
- [ ] Sayfalama (pagination) yöntemi
- [ ] Metriklerin hangi dönemler için geçerli olduğu

> Şu an sahte adaptör `impressions`, `reach`, `likes`, `comments`, `saves`,
> `shares` adlarını kullanıyor. Bunlar **yer tutucudur**, Meta'nın gerçek
> metrik adları doğrulandığında değiştirilecektir.

### 5. Sınırlar ve hatalar
- [ ] İstek sınırı (rate limit) kuralları
- [ ] Sınıra takılınca dönen hata kodu ve bekleme süresi
- [ ] Anahtarın geçersizleşme durumundaki hata kodu
- [ ] Geçici hataların kalıcı hatalardan nasıl ayrılacağı

### 6. Webhook
- [ ] Webhook doğrulama akışı
- [ ] İmza doğrulama yöntemi
- [ ] Tekrar gönderim (retry) davranışı

---

## Sizin yapmanız gerekecek işler (hesap sahipliği gerektirir)

Bunlar teknik değil, hesap işlemleridir. Sırası geldiğinde adım adım
anlatacağım.

1. Meta geliştirici hesabı açmak
2. Bir uygulama oluşturmak
3. Müşteri Instagram hesaplarının **profesyonel** hesaba çevrilmesi ve bir
   Facebook Sayfası ile ilişkilendirilmesi
4. **Uygulama incelemesi** başvurusu — içgörü izinleri için gereklidir ve
   günler ile haftalar sürebilir
5. İzin ekranında onay vermek

> ⚠️ 4. madde zaman alır. Erken başlatmak isteyebilirsiniz.

---

## Şu an ne çalışıyor?

`PLATFORM_MODE=fake` ayarıyla, gerçek hesap olmadan tüm sistem çalışıyor:

- İçerik listeleme
- İçerik ve hesap metrikleri
- Ham veri saklama ve normalize etme
- Tekrar çalıştırmaya dayanıklı (idempotent) senkronizasyon
- Şifreli anahtar saklama

Gerçek adaptör yazıldığında bu katmanların hiçbiri değişmeyecek; yalnızca
`MetaAdapter` doldurulacak.
