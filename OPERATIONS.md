# Günlük Kullanım ve Sorun Çözme

Bu dosya teknik olmayan kullanım içindir. Terminal bilgisi gerektirmez.

---

## 1. Sistem çalışıyor mu?

Tarayıcınızdan açın:

**https://agencycortex.tech/readyz**

| Gördüğünüz | Anlamı | Ne yapmalı |
|---|---|---|
| `"status":"ready"` | Her şey yolunda ✅ | Bir şey yapmayın |
| `"status":"not_ready"` | Sistem ayakta ama bir parçası çalışmıyor | Bana söyleyin, hangi parça olduğu yanıtta yazıyor |
| Sayfa açılmıyor | Sistem kapalı veya sunucu sorunu | Bana söyleyin |
| Sertifika uyarısı | HTTPS sorunu | Bana söyleyin |

Bana bildirirken **ekrandaki yazının tamamını** kopyalayıp gönderin.

---

## 2. Müşteri ekleme

Her müşteri ayrı bir **çalışma alanıdır.** Bir müşterinin verisi diğerine
asla görünmez.

Sıralama:
1. Çalışma alanı oluşturulur (müşteri adı)
2. Ekibinizden kişiler yetkiyle eklenir
3. Müşterinin Instagram hesabı bağlanır
4. Marka bilgileri girilir (dil, hedef kitle, yasaklı ifadeler)

Panel Aşama 7'de gelecek. O zamana kadar bu işlemleri ben yaparım.

---

## 3. Yetkiler

| Rol | Ne yapabilir |
|---|---|
| **Sahip** | Her şey + çalışma alanını silme |
| **Yönetici** | Her şey + ekip yönetimi + hesap bağlama |
| **Stratejist** | İçerik ve rapor üretir, onaya sunar |
| **Editör** | İçerik düzenler, onaya sunamaz |
| **İzleyici** | Sadece okur |

**Öneri:** Müşteri temsilcilerine **İzleyici** verin. Raporları görürler,
hiçbir şeyi değiştiremezler.

> Son sahip çalışma alanından çıkarılamaz — yönetilemez hale gelmesin diye.

---

## 4. Instagram hesabı bağlama

**Ön koşul:** Hesap **profesyonel** (Business/Creator) olmalı. Kişisel
hesaplarda içgörü verisi yoktur.

Bağlama adımları `INSTALLATION.md` dosyasında.

**Bağladıktan sonra kontrol edin:** Hesap listesinde `profesyonel: true`
yazıyor mu? `false` ise içgörü verisi gelmeyecektir.

---

## 5. Sık sorulan sorunlar

### "Rapor boş geldi / veri yok"
Sırayla kontrol edin:
1. Hesap gerçekten bağlı mı?
2. Hesap profesyonel mi?
3. Son senkronizasyon ne zaman yapılmış?
4. Hesap listesinde bir hata mesajı var mı?

> Sistem, veri çekemediğinde **sıfır yazmaz** — açıkça hata bildirir.
> "0 erişim" görüyorsanız bu gerçek bir sıfırdır.

### "İçerik yayınlanmadı"
Bu **beklenen davranıştır.** İlk sürümde otomatik yayın **kapalıdır.**
Sistem içerik hazırlar, insan onayına sunar. Yayını siz yaparsınız.

### "Müşteri kendi verisini göremiyor"
O kullanıcı ilgili çalışma alanına üye olarak eklenmemiştir.

### "Giriş yapamıyorum"
Şifre yanlış mı, hesap pasif mi kontrol edin. Sistem güvenlik gereği
hangisi olduğunu söylemez — ikisinde de aynı mesajı verir.

---

## 6. Yapay zekâ maliyetleri

Her AI çağrısı kaydedilir: hangi model, kaç kelime, tahmini maliyet.

Her müşteri için **aylık bütçe sınırı** vardır. Sınır aşılırsa yeni AI işi
başlamaz — beklenmedik fatura gelmez.

Bütçe değişikliği isterseniz bana söyleyin.

---

## 7. Güvenlik kuralları

**Asla yapmayın:**
- Şifre, API anahtarı veya token'ı sohbete yazmak
- Aynı şifreyi birden fazla serviste kullanmak
- Müşteri Instagram şifresini istemek *(gerek yok — izinli bağlantı kullanıyoruz)*

**Sistem otomatik yapıyor:**
- Şifreleri geri çevrilemez şekilde saklamak
- Sosyal medya anahtarlarını şifrelemek
- Loglarda kişisel bilgiyi maskelemek
- Kim ne yaptı kaydını tutmak

---

## 8. Bir sorun olduğunda bana ne göndermeliyim?

1. **Ne yapmaya çalıştınız?** ("Müşteri X'in raporunu açtım")
2. **Ne oldu?** ("Sayfa boş geldi")
3. **Ekran görüntüsü** veya hata yazısının tamamı
4. **Ne zaman oldu?** (yaklaşık saat)

Bu dördü ile sorunu genelde doğrudan bulabilirim.
