#!/usr/bin/env python3
"""
Fiyat Takip Botu
-----------------
config.json içindeki ürünleri, tanımlı kaynaklardan (Vatan, Akakçe, Cimri, ...)
periyodik olarak çeker, en ucuz fiyatı bulur, geçmişle karşılaştırır ve:
  - fiyat tüm-zamanların dibine (yeni "dip fiyat") inerse
  - veya hedef fiyatın altına inerse
Telegram'a bildirim gönderir.

Kullanım:
  python price_tracker.py                 -> tek seferlik kontrol
  (cron ile örn. her 3 saatte bir çalıştırılması önerilir)

Not: SCRAPER_API_KEY ortam değişkeni tanımlıysa istekler ScraperAPI proxy'si
üzerinden yapılır (veri merkezi IP engelini aşmak için). Site yapıları zaman
zaman değişebilir; fiyat bulunamazsa script hatayı loglar ve diğer kaynaklara
devam eder.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
HISTORY_PATH = os.path.join(BASE_DIR, "price_history.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

PRICE_REGEX = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*TL")


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def parse_tl_to_float(raw: str) -> float:
    raw = raw.strip()
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(".", "")
    return float(raw)


def fetch_html(url: str) -> str | None:
    try:
        if SCRAPER_API_KEY:
            proxy_url = f"http://api.scraperapi.com/?api_key={SCRAPER_API_KEY}&url={quote(url, safe='')}"
            resp = requests.get(proxy_url, timeout=60)
        else:
            resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        log(f"HATA: {url} çekilemedi -> {e}")
        return None


def extract_prices(html: str) -> list[float]:
    matches = PRICE_REGEX.findall(html)
    prices = []
    for m in matches:
        try:
            val = parse_tl_to_float(m)
            if 50 <= val <= 1_000_000:
                prices.append(val)
        except ValueError:
            continue
    return prices


def get_price_liste_min(url: str, min_gecerli: float = 0) -> float | None:
    """Akakçe/Cimri gibi sayfalarda en düşük fiyatı bulur.
    min_gecerli altındaki değerler (kargo bedeli, indirim rozeti vb.) elenir."""
    html = fetch_html(url)
    if not html:
        return None
    prices = [p for p in extract_prices(html) if p >= min_gecerli]
    if not prices:
        log(f"UYARI: {url} içinde geçerli aralıkta fiyat bulunamadı.")
        return None
    return min(prices)


def get_price_tek_urun(url: str, min_gecerli: float = 0) -> float | None:
    """Tek ürün sayfasında, min_gecerli üzerindeki ilk fiyatı döner."""
    html = fetch_html(url)
    if not html:
        return None
    prices = [p for p in extract_prices(html) if p >= min_gecerli]
    if not prices:
        log(f"UYARI: {url} içinde geçerli aralıkta fiyat bulunamadı.")
        return None
    return prices[0]


FETCHERS = {
    "liste_min": get_price_liste_min,
    "tek_urun": get_price_tek_urun,
}


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    if not bot_token or bot_token.startswith("BURAYA"):
        log("Telegram bilgileri girilmemiş, bildirim gönderilmedi. (config.json'u doldurun)")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        r = requests.post(
            url,
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        log(f"HATA: Telegram mesajı gönderilemedi -> {e}")


def check_product(product: dict, history: dict) -> list[str]:
    product_id = product["id"]
    name = product["ad"]
    target = product.get("hedef_fiyat")

    # Kargo bedeli/indirim rozeti gibi anlamsız küçük sayıları elemek için:
    # hedef fiyat varsa onun 1/4'ünü, yoksa sabit 300 TL'yi alt sınır kabul et.
    min_gecerli = (target / 4) if target else 300

    results = []  # (site, price)
    for kaynak in product.get("kaynaklar", []):
        site = kaynak["site"]
        tip = kaynak.get("tip", "liste_min")
        url = kaynak["url"]
        fetcher = FETCHERS.get(tip)
        if not fetcher:
            log(f"UYARI: Bilinmeyen kaynak tipi '{tip}' ({site})")
            continue
        price = fetcher(url, min_gecerli=min_gecerli)
        if price is not None:
            log(f"{name} - {site}: {price:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", "."))
            results.append((site, price, url))
        time.sleep(1)

    if not results:
        log(f"UYARI: {name} için hiçbir kaynaktan fiyat alınamadı.")
        return []

    best_site, best_price, best_url = min(results, key=lambda r: r[1])

    product_history = history.setdefault(product_id, [])
    all_time_min_before = min((h["fiyat"] for h in product_history), default=None)

    product_history.append({
        "tarih": datetime.now(timezone.utc).isoformat(),
        "fiyat": best_price,
        "site": best_site,
    })

    messages = []

    is_new_dip = all_time_min_before is not None and best_price < all_time_min_before
    is_below_target = target is not None and best_price <= target

    if all_time_min_before is None:
        log(f"{name}: ilk kayıt oluşturuldu ({best_price:,.2f} TL)")
    elif is_new_dip:
        messages.append(
            f"📉 <b>Yeni dip fiyat!</b>\n{name}\n"
            f"{best_price:,.2f} TL ({best_site})\n"
            f"Önceki en düşük: {all_time_min_before:,.2f} TL\n"
            f"{best_url}"
        )
    elif is_below_target:
        messages.append(
            f"🎯 <b>Hedef fiyat yakalandı!</b>\n{name}\n"
            f"{best_price:,.2f} TL ({best_site}) — hedef: {target:,.2f} TL\n"
            f"{best_url}"
        )

    return messages


def main():
    config = load_json(CONFIG_PATH, None)
    if config is None:
        log("HATA: config.json bulunamadı.")
        sys.exit(1)

    history = load_json(HISTORY_PATH, {})

    tg = config.get("telegram", {})
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", tg.get("bot_token", ""))
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", tg.get("chat_id", ""))

    all_messages = []
    for product in config.get("urunler", []):
        try:
            msgs = check_product(product, history)
            all_messages.extend(msgs)
        except Exception as e:
            log(f"HATA: {product.get('ad')} işlenirken sorun oluştu -> {e}")

    save_json(HISTORY_PATH, history)

    for msg in all_messages:
        send_telegram(bot_token, chat_id, msg)

    if not all_messages:
        log("Bu turda yeni dip fiyat ya da hedef fiyat yakalanmadı.")


if __name__ == "__main__":
    main()
