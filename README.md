# DipFiyat

Ürünlerin (kulaklık, RAM, vb.) fiyatlarını Akakçe, Cimri, Tebilon gibi sitelerden
düzenli olarak takip eden, tüm zamanların dip fiyatını ya da sizin belirlediğiniz
hedef fiyatı yakalayınca Telegram'a haber veren bağımsız bir bot. Uçuş radar
botunuzdan tamamen ayrı çalışır, GitHub Actions üzerinde otomatik tetiklenir.

## Kurulum (adım adım)

### 1. GitHub'da boş bir repo açın
GitHub'da sağ üstten **New repository** → isim: `DipFiyat` (veya istediğiniz isim)
→ **README, .gitignore, license eklemeyin** (hepsi zaten bu pakette var, çakışma
olmasın) → **Create repository**.

### 2. Bu paketi push'layın
Bu klasör zaten bir Git deposu olarak hazırlandı (`git init` + ilk commit yapıldı).
Sadece GitHub'daki boş reponuzu "remote" olarak bağlayıp push etmeniz yeterli:

```bash
cd DipFiyat
git remote add origin https://github.com/KULLANICI_ADINIZ/DipFiyat.git
git branch -M main
git push -u origin main
```

(`KULLANICI_ADINIZ` kısmını kendi GitHub kullanıcı adınızla değiştirin.)

### 3. Telegram Secrets'ları ekleyin
`config.json` içine bot token/chat_id **yazmayın** — repo ayarlarından secret
olarak ekleyeceğiz:

1. Repo sayfasında **Settings → Secrets and variables → Actions**
2. **New repository secret** ile iki tane ekleyin:
   - `TELEGRAM_BOT_TOKEN` → BotFather'dan aldığınız token
   - `TELEGRAM_CHAT_ID` → kendi chat id'niz
     (öğrenmek için botunuza bir mesaj atıp
     `https://api.telegram.org/bot<TOKEN>/getUpdates` adresini açın,
     dönen JSON'daki `"chat":{"id": ...}` değeri)

Flight radar botunuzla aynı Telegram bot'unu kullanmak isterseniz aynı token'ı
girebilirsiniz — tek bot birden fazla işlevi aynı anda yürütebilir.

### 4. Workflow'u kontrol edin
- Repo → **Actions** sekmesi → "DipFiyat - Fiyat Takip Botu" workflow'u görünür.
- Beklemeden test etmek için **Run workflow** butonuna basın.
- Varsayılan olarak her 2 saatte bir otomatik çalışır
  (`.github/workflows/price_tracker.yml` içindeki `cron` satırından değiştirilebilir).

### 5. İlk çalıştırma
İlk çalıştırmada her ürün için sadece "başlangıç fiyatı" kaydedilir, henüz
karşılaştıracak geçmiş olmadığından bildirim gelmez — bu normal. İkinci
çalıştırmadan itibaren dip fiyat/hedef fiyat karşılaştırması devreye girer.

## Ürün Ekleme / Düzenleme

`config.json` içindeki `urunler` listesine yeni bir obje ekleyin, sonra
`git add config.json && git commit -m "yeni ürün" && git push` ile gönderin:

```json
{
  "id": "benzersiz_bir_id",
  "ad": "Görünen ürün adı",
  "hedef_fiyat": 15000,
  "kaynaklar": [
    { "site": "akakce", "tip": "liste_min", "url": "..." },
    { "site": "tebilon", "tip": "tek_urun", "url": "..." }
  ]
}
```

- **liste_min**: Akakçe/Cimri gibi "birden çok satıcı" gösteren sayfalar — sayfadaki
  en düşük fiyatı alır.
- **tek_urun**: Tek bir ürün/mağaza sayfası (örn. Tebilon) — mümkünse arama sayfası
  yerine doğrudan ürün URL'i verin, daha güvenilir sonuç verir.

`hedef_fiyat` opsiyoneldir; sadece dip fiyat takibi istiyorsanız bu alanı silin.

## Fiyat Geçmişinin Kalıcılığı

GitHub Actions her çalıştırmada temiz bir ortamda başlar; script bu yüzden
`price_history.json` dosyasını her turun sonunda otomatik olarak repoya geri
commit'ler (workflow'un son adımı). Geçmiş veri böylece kaybolmaz.

## Bilinen Sınırlamalar

- Akakçe/Cimri gibi siteler sık istek atılırsa bot korumasına takılabilir —
  2 saatte bir gibi makul bir sıklık önerilir.
- "DFS Bilgisayar" sitesinin tam adresi henüz eklenmedi — URL'i verirseniz
  `config.json`'a hemen ekleyebiliriz.
- Fiyat çıkarma mantığı regex tabanlı; bazı sayfalarda kargo/taksit tutarı gibi
  başka bir sayı yanlışlıkla yakalanabilir. Böyle bir durum görürseniz bildirin,
  o siteye özel bir düzeltme ekleyelim.
