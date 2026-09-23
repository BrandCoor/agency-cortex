# Otomasyon planı — kaç iş akışı, ne yapıyor, nasıl çalışıyor

## Kaç tane?

**Altı.** Her biri farklı bir işi yapıyor; sayı bilerek küçük tutuldu.
Veri kaynağı olmayan bir akış eklemek, panelde sürekli "yapacak iş yoktu"
yazan bir satır üretmekten başka işe yaramaz.

| # | Akış | Ne yapar | Ne zaman | Neye bağlı |
|---|---|---|---|---|
| WF-05 | **Bağlantı sağlığı** | Erişim anahtarlarını süresi dolmadan yeniler | Her gün 06:00 | — |
| WF-01 | **Günlük sosyal zekâ** | Bağlı hesapların içerik ve metriklerini çeker | Her gün 07:00 | WF-05 (geçerli anahtar) |
| WF-02 | **Trend araştırması** | Sektör trendlerini araştırır, bulguları kaydeder | Her gün 09:00 | Marka bilgisi |
| WF-03 | **İçerik zekâsı** | Bulgulardan içerik senaryosu önerir | Pzt/Çar/Cum 10:00 | WF-02'nin bulguları |
| WF-04 | **Haftalık zekâ raporu** | Haftanın raporunu üretir | Her pazartesi 08:00 | WF-01'in verisi |
| WF-06 | **Rakip araştırması** | İzlenen rakip hesapları araştırır | Salı/Perşembe 11:00 | İzlenen rakip hesap |

**Sıra tesadüf değil.** WF-05 önce çalışır ki WF-01 geçerli bir anahtarla
veri çekebilsin. WF-02 sabah araştırır, WF-03 bir saat sonra o bulgulardan
içerik önerir. WF-06, WF-02'den iki saat sonra çalışır: aynı anda çalışsalardı
ikisi de AI bütçesinden aynı dakikada düşerdi.
WF-01 hafta boyunca veri toplar, WF-04 pazartesi sabahı
onu rapora çevirir.

### WF-05 neden var?

Instagram'ın erişim anahtarı yaklaşık **60 gün** geçerli. Yenilenmezse
hesap sessizce çalışmaz hale gelir: veri gelmez, kimse nedenini bilmez.
Bu akış anahtarı **25 gün kala** yeniler. Bu kadar erken olmasının sebebi,
son güne bırakmanın riskli olması: o gün n8n kapalıysa veya Meta hata
veriyorsa hesap ölür. 25 günlük pay, iki haftalık bir kesintiyi bile
tolere eder.

Yenilenemeyen anahtar **gizlenmez**: hesap işaretlenir, sebebi Bağlı
hesaplar sayfasında yazar.

---

## Her müşteri için nasıl çalışıyor?

n8n her akışı **zamanı geldiğinde bir kez** çalıştırır — müşteri başına
ayrı ayrı değil. Akış şöyle ilerler:

```
n8n zamanlayıcı  →  Agency Cortex API  →  yetkili müşterileri gez
                                           ├─ akış kapalı  → atla (kayıt yok)
                                           ├─ açık         → işi yap, sonucu yaz
                                           └─ hata çıktı   → o müşteriye yaz, DEVAM ET
```

Üç sonuç var ve üçü de panelde görünür:

- **Tamam** — iş yapıldı, özeti yazıldı.
- **Çalıştı ama yapacak iş yoktu** — örneğin bağlı hesap yok. Hata değil.
- **Hata** — nedeni yazılı; diğer müşteriler etkilenmez.

### Müşteri sayısı artınca ne değişir?

**n8n tarafında hiçbir şey.** İş akışı dosyaları müşteriden bağımsızdır.
Yeni müşteri eklediğinizde:

1. n8n anahtarı "tüm müşteriler" kapsamında olduğu için müşteri
   **otomatik** kapsama girer.
2. Akışlar o müşteride **kapalı** başlar.
3. Siz Otomasyon sayfasından hangilerini açacağınızı seçersiniz.

Varsayılanın kapalı olması bilinçli: bir müşteri panele eklendiği anda
onun adına araştırma yapıp para harcamak doğru olmaz.

---

## Neden her akış iki düğümden ibaret?

n8n'deki her iş akışı yalnızca **Zamanlayıcı → HTTP çağrısı**.

Alternatif, müşteri listesini n8n'de çekip orada döngü kurmaktı. O zaman
her akış 6-8 düğüm olurdu ve **müşteri izolasyonu n8n'in düğüm ayarlarına
bağlı** hale gelirdi — yanlış yazılmış bir ifade başka bir müşterinin
verisine yazabilirdi.

Bu haliyle n8n yalnızca kendi işini yapıyor: zamanlama, tekrar deneme,
çalışma geçmişi. Kim ne yapabilir sorusu Agency Cortex'te kalıyor.

---

## Zamanlamanın sahibi kim?

İş akışlarının tek zamanlayıcısı **n8n**. Agency Cortex'in kendi
zamanlayıcısında (Celery beat) yalnızca n8n'de karşılığı olmayan işler
kalır: sistem nabzı, günlük rapor, aylık rapor.

Daha önce veri senkronu hem Celery'de (6 saatte bir) hem WF-01'de vardı;
haftalık rapor ise ikisinde de **pazartesi 08:00** idi. Aynı iş iki kez
çalışıyordu ve Celery tarafındaki çalışmalar panelde **hiç görünmüyordu**.
Bu yüzden çift zamanlamalar kaldırıldı.

---

## Bir akış çalışmıyorsa nereye bakılır?

1. **Otomasyon sayfası** — akış açık mı? Kapalıysa n8n onu atlıyordur.
2. Aynı sayfadaki **n8n bağlantı durumu** — "son bağlantı" saati güncel
   mi? Değilse n8n çalışmıyor olabilir.
3. **Son çalışmalar** listesi — hata mesajı orada yazar.
4. Beklemek istemiyorsanız **"Şimdi çalıştır"** ile elle tetikleyin.

Hiçbir aşamada n8n arayüzüne girmeniz gerekmez.
