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

## 2. Panele giriş

**https://agencycortex.tech/panel**

E-posta ve şifrenizi girin. Şifrenizi ilk girişten sonra mutlaka değiştirin:
üstteki menüden **"Şifre değiştir"**. Şifreyi değiştirdikten sonra bana
haber verin; GitHub'daki geçici şifre kaydını sildireceğim.

Şifrenizi unuttuysanız bana söyleyin — sunucudan sıfırlayabiliyorum.
Şifrenizi bana **sohbette yazmayın.**

---

## 3. Müşteri ekleme

Her müşteri ayrı bir **çalışma alanıdır.** Bir müşterinin verisi diğerine
asla görünmez.

Panelde **Müşteriler** sayfasındaki forma müşteri adını yazıp
**"Müşteri ekle"** düğmesine basın. Eklediğiniz müşterinin otomatik olarak
sahibi (en yetkili kişi) olursunuz.

Sonraki adımlar:
1. ~~Çalışma alanı oluşturulur~~ ✅ panelden yapılabiliyor
2. ~~Ekibinizden kişiler yetkiyle eklenir~~ ✅ panelden yapılabiliyor
3. ~~Marka bilgileri girilir~~ ✅ panelden yapılabiliyor
4. Müşterinin Instagram hesabı bağlanır — **henüz bağlanamıyor**, nedeni
   panelde yazıyor (aşağıya bakın)

### Marka bilgileri
Müşteri ekranında **"Marka bilgileri"** bağlantısı. Buraya girdikleriniz
yapay zekânın içerik üretirken uyacağı kurallardır:

| Alan | Ne işe yarar |
|---|---|
| Konuşma tonu | Üretilen metnin üslubunu belirler |
| Hedef kitle | Kime seslenileceğini belirler |
| **Yasaklı ifadeler** | Her üretilen içerikte aranır ve işaretlenir |
| Tercih edilen ifadeler | Kullanılması istenen sözler |

Yasaklı ifadeleri **her satıra bir tane** yazın. Örnek: reklam mevzuatı
açısından riskli olan *"dünyanın en iyisi"*, *"şifalı"* gibi sözler.

Değiştirmek için en az **stratejist** yetkisi gerekir.

### Ekip
Müşteri ekranında **"Ekip"** bağlantısı. Kişi eklemek için en az
**yönetici** yetkisi gerekir.

İki kural var:
- Eklenecek kişinin sistemde **zaten hesabı olmalı.** Yoksa bana söyleyin,
  açayım — sonra siz ekleyebilirsiniz.
- **Kendi yetkinizden yüksek bir yetki veremezsiniz.** Yönetici birini sahip
  yapamaz. Aynı şekilde kendinizden yüksek yetkilideki birini çıkaramazsınız.

---

## 4. Yetkiler

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

### Bir kişinin yetkisini değiştirmek
Müşteri ekranı &rsaquo; **Ekip** &rsaquo; kişinin satırındaki listeden yeni
yetkiyi seçin, **Değiştir**'e basın.

İki şeyi sistem **kabul etmez**, gerekçesiyle birlikte:
- **Kendi yetkinizi değiştiremezsiniz.** Aksi halde bir yönetici kendini
  sahip yapabilirdi.
- **Kendinizden yüksek yetkiliye dokunamazsınız.** Bir yönetici, sahibin
  yetkisini alamaz.

---

## 4b. Kullanıcılar (sistem hesapları)

Sol menüde **Kullanıcılar** — yalnızca size görünür.

Burası ile *Ekip* karıştırılmasın:

| | Kullanıcılar | Ekip |
|---|---|---|
| Kapsamı | **Tüm sistem** | **Tek müşteri** |
| Ne belirler | Kim giriş yapabilir | Kim hangi müşteride ne yapabilir |
| Kim yönetir | Sistem yöneticisi | O müşterinin yöneticisi |

### Yeni kişi eklemek — 3 adım
1. **Kullanıcılar** &rsaquo; *Yeni kullanıcı*: ad soyad ve e-posta girin,
   **Hesabı aç**.
2. Ekranda bir **bağ (link)** çıkar. Bunu kişiye iletin (WhatsApp, e-posta,
   fark etmez).
3. Kişi bağa tıklar, **şifresini kendisi belirler** ve giriş yapar.

Sonra o kişiyi ilgili müşterinin **Ekip** sayfasından ekleyin — yoksa giriş
yapar ama hiçbir müşteri göremez.

### Şifreyi siz belirlemiyorsunuz — neden?
Şifre sizden kişiye giderken her durakta bozulabilir: kopyalarken kaçan bir
boşluk, Türkçe harflerin farklı yazılışı, otomatik düzeltme. **21 Eylül'de
tam olarak bu oldu ve sisteme günlerce girilemedi.** Bu akışta şifre hiç
aktarılmıyor; kişi doğrudan kendi tarayıcısında belirliyor.

> **Bağ 24 saat geçerlidir ve yalnızca bir kez kullanılır.** Süresi geçerse
> veya kaybolursa listeden **Şifre bağı** düğmesiyle yenisini üretin; eski
> bağ o anda geçersiz olur.

### Bir hesabı kapatmak
İki seçenek var:

- **Pasif yapmak** (önerilen): *Düzenle* &rsaquo; "Giriş yapabilir"
  işaretini kaldırın. Kişi giremez ama geçmiş kayıtlarında adı durur.
- **Silmek**: geri alınamaz. Kişinin müşteri yetkileri de silinir.

### Sistemin kilitlenmesini engelleyen kurallar
Sistem şunlara **izin vermez** ve nedenini ekranda yazar:

- Kendi hesabınızı silemez, kendinizi pasifleştiremezsiniz.
- Kendi yönetici yetkinizi alamazsınız.
- **Son etkin yöneticiyi** silemez, pasifleştiremez, yetkisini alamazsınız.

Bu kurallar olmasaydı tek bir yanlış tıklama panele girişi tamamen
kapatırdı ve düzeltmek için sunucuya komut girmek gerekirdi.

> **Öneri:** Kendinizden başka **ikinci bir sistem yöneticisi** tanımlayın.
> Hesabınıza erişemediğiniz bir durumda ikinci yönetici sizi kurtarır.
> Tek yönetici varken panel bunu uyarı olarak gösterir.

---

### API anahtarlarını girmek
Sol menüde **Sistem ayarları** (yalnızca size görünür).

**Anahtarı asla sohbete yazmayın.** Sohbete yazılan bir anahtar geçmişte
kalıcı olarak durur ve yanmış sayılır — yenisini üretmeniz gerekir.
Doğru yer burasıdır: değer şifrelenerek saklanır, size bir daha gösterilmez.

**Girdikten sonra "Bağlantıyı sına" düğmesine basın.** Sistem anahtarı
gerçekten deneyip sonucu söyler:

| Sağlayıcı | Sınama ne yapar |
|---|---|
| Manus | Gerçek bir API çağrısı yapar, kredi durumunuzu gösterir. **Kredi harcamaz.** |
| Meta | Yalnızca **biçim** denetler. Canlı sınama değildir — bunu ekranda da yazar. |
| Claude | Yalnızca kayıtlı mı diye bakar. Canlı sınama ücret doğurur; haberiniz olmadan harcama yapmıyoruz. |

Sınama sonucu anahtarınızı **hiçbir zaman** ekrana yazmaz.

---

### Kampanyalar
Müşteri ekranında **"Kampanyalar"** bağlantısı. Belirli bir döneme ve hedefe
yönelik çalışmalar burada tutulur (örn: *Ramazan 2026 — iftar menüsü
rezervasyonlarını artırmak*).

- Kampanya bir markaya bağlıdır; **önce marka bilgilerini girmelisiniz.**
- Tarihler isteğe bağlı; boş bırakabilirsiniz.
- **Bitiş tarihi başlangıçtan önce olamaz** — sistem kabul etmez. Yanlış
  tarih aralığı, sonradan üretilen raporu anlamsız hale getirirdi.
- Eklemek/silmek için en az **stratejist** yetkisi gerekir.

---

### Bağlı hesaplar
Müşteri ekranında **"Bağlı hesaplar"** bağlantısı. Hangi hesapların bağlı
olduğunu, en son ne zaman veri çekildiğini ve varsa hatayı gösterir.

**Şu an hesap bağlanamıyor** ve sayfa bunu açıkça yazıyor: hangi ayarların
eksik olduğu tek tek listeleniyor. Çalışmayan bir "Bağla" düğmesi bilerek
gösterilmiyor — basıldığında hiçbir şey olmayacak bir düğme, olmayan bir
yeteneği varmış gibi göstermek olurdu.

Sistem şu an **sahte sağlayıcı** ile çalışıyor; bu da sayfada yazıyor.
Gerçek veri değil, örnek veri üretiliyor.

---

## 5. Instagram hesabı bağlama

**Ön koşul:** Hesap **profesyonel** (Business/Creator) olmalı. Kişisel
hesaplarda içgörü verisi yoktur.

Bağlama adımları `INSTALLATION.md` dosyasında.

**Bağladıktan sonra kontrol edin:** Hesap listesinde `profesyonel: true`
yazıyor mu? `false` ise içgörü verisi gelmeyecektir.

---

## 6. Sık sorulan sorunlar

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

## 7. Yapay zekâ maliyetleri

Her AI çağrısı kaydedilir: hangi model, kaç kelime, tahmini maliyet.

Her müşteri için **aylık bütçe sınırı** vardır. Sınır aşılırsa yeni AI işi
başlamaz — beklenmedik fatura gelmez.

Bütçe değişikliği isterseniz bana söyleyin.

---

## 8. Güvenlik kuralları

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

## 9. Bir sorun olduğunda bana ne göndermeliyim?

1. **Ne yapmaya çalıştınız?** ("Müşteri X'in raporunu açtım")
2. **Ne oldu?** ("Sayfa boş geldi")
3. **Ekran görüntüsü** veya hata yazısının tamamı
4. **Ne zaman oldu?** (yaklaşık saat)

Bu dördü ile sorunu genelde doğrudan bulabilirim.


---

## 10. Otomasyon (n8n)

Sol menüde **Otomasyon**.

### Ne yapar, ne yapmaz
Arka planda çalışan 4 iş akışı vardır: günlük sosyal zekâ, trend
araştırması, içerik zekâsı ve haftalık rapor. Bunlar **araştırır, analiz
eder, önerir ve panele yazar**.

**Hiçbiri paylaşım yapmaz, yoruma cevap vermez, DM göndermez.** Üretilen
her şey taslaktır ve sizin onayınızı bekler. Bu, v1'de bilinçli bir
sınırdır.

### Açıp kapatmak
Her iş akışı her müşteri için **ayrı ayrı** açılır ve **varsayılan olarak
kapalıdır**. Panelden açmadan hiçbir şey çalışmaz.

Tabloda her akış için şunları görürsünüz:
- açık mı kapalı mı
- ne zaman çalışması beklendiği
- **en son ne zaman çalıştığı ve başarılı olup olmadığı**
- hata verdiyse **hata mesajının kendisi**

Hata gizlenmez. "Bir şeyler ters gitti" yazmaz; ne olduğunu yazar.

### n8n'e girmeniz gerekiyor mu?
**Normal kullanımda hayır.** Yukarıdaki tablo her şeyi gösterir.
İş akışlarının kendisini düzenlemek gerekirse adres ve giriş bilgisi
Otomasyon sayfasının altında, yalnızca size görünür.

> **Orada iki ayrı giriş var:**
> 1. Tarayıcının sorduğu **kullanıcı adı/şifre** — bu, n8n'i internetten
>    gelen yabancılara kapatan kapıdır.
> 2. Geçtikten sonra **n8n'in kendi hesabı** — ilk açılışta siz
>    oluşturacaksınız.
>
> İkisi farklı şeydir. Birincisi olmasaydı, adresi bulan ilk yabancı n8n'in
> sahibi olur ve otomasyonu ele geçirirdi.

### n8n bağlantı anahtarları
n8n sizin hesabınızı kullanmaz; kendi **makine kimliği** vardır.

- Bir anahtar **yalnızca işaretlediğiniz müşterilerde** çalışabilir.
  İşaretlemediğiniz müşteriye n8n **ulaşamaz** — n8n'de yanlış bir ayar
  olsa bile.
- Anahtar **bir kez** gösterilir. Kaybederseniz yenisini üretin;
  eskisi geri getirilemez.
- Bir anahtardan şüphelenirseniz **İptal et**. O anda çalışmaz hale gelir.
- Anahtarın tamamı hiçbir yerde saklanmaz; listede yalnızca tanıtıcı
  baş kısmı (`acx_...`) görünür.

### Sık sorulan
**"Akış açık ama hiç çalışmadı" yazıyor.**
İş akışının n8n tarafında da kurulu olması gerekir. Panelde açmak "bu
müşteride çalışmasına izin veriyorum" demektir; çalıştıran taraf n8n'dir.

**"Hata" görüyorum.**
Hata mesajı satırın altında yazar. Bana o mesajı iletin — hangi akış,
hangi müşteri, ne zaman.

---

## 11. Panelin görünümünü doğrulama (geliştirici aracı)

Bu bölüm **sizin için değil**, sistemi geliştirenler içindir. Burada
durmasının sebebi şu: testlerin geçmesi panelin **doğru göründüğünü**
kanıtlamaz. 23 Eylül'de panel baştan yazıldığında 19 CSS sınıfı tanımsız
kaldı; bütün sayfalar HTTP 200 dönüyor ve testlerin tamamı geçiyordu, ama
ekranda başlıklar hizasız, ölçü kutuları düz metindi.

`ops/panel_goruntule.py` bu hata sınıfını görünür kılar: ayrı bir
veritabanında uygulamayı ayağa kaldırır, örnek veri yazar ve 14 sayfayı
koyu ve açık temada gerçek bir tarayıcıda çizdirip resimlerini alır.

```
pip install playwright && playwright install chromium
python ops/panel_goruntule.py ./gorsel-cikti
```

Sonunda `SORUNLU: yok` yazması beklenir. Giriş ekranına düşen veya
"Not Found" dönen her sayfa adıyla birlikte listelenir ve betik sıfırdan
farklı bir çıkış kodu döndürür.

**Güvenlik:** Betik veritabanını sıfırdan kurar, yani içindeki her şeyi
siler. Bu yüzden veritabanı adının `_gorsel` ile bitmesi zorunludur ve
kontrol edilir. Üretim sunucusunda çalıştırılmaz.
