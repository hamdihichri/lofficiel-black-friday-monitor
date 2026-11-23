import os
import json
import logging
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

URL = "https://lofficielshop.tn/fr/1002-black-friday"
STATE_FILE = "seen_products.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
}

def load_seen_products():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error reading {STATE_FILE}: {e}")
    return {}

def save_seen_products(products):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

def send_telegram_alert(product):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram credentials not found. Notification skipped.")
        return

    # Format message with HTML
    text = (
        f"🔥 <b>Nouveau Produit Black Friday Détecté !</b>\n\n"
        f"🏷️ <b>Produit:</b> {product['title']}\n"
        f"💰 <b>Prix Promo:</b> {product['price']}\n"
    )
    if product.get("regular_price"):
        text += f"❌ <b>Ancien Prix:</b> <s>{product['regular_price']}</s>\n"
    if product.get("discount"):
        text += f"📉 <b>Remise:</b> {product['discount']}\n"
    if product.get("stock"):
        text += f"📦 <b>Disponibilité:</b> {product['stock']}\n"

    text += f"\n🔗 <a href='{product['url']}'>👉 Cliquez ici pour voir le produit</a>"

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        res = requests.post(api_url, json=payload, timeout=10)
        res.raise_for_status()
        logging.info(f"Telegram alert sent for: {product['title']}")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")

def scrape_products():
    response = requests.get(URL, headers=HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    products = {}

    articles = soup.select("article.product-miniature, [data-id-product]")

    for item in articles:
        prod_id = item.get("data-id-product")

        title_elem = item.select_one("a.product_name, .product-title a, h3 a")
        price_elem = item.select_one(".price, .price-sale")
        reg_price_elem = item.select_one(".regular-price")
        discount_elem = item.select_one(".discount-amount, .product-flag .discount")
        stock_elem = item.select_one(".availability span")
        img_elem = item.select_one(".product-thumbnail img")

        if not title_elem:
            continue

        url = title_elem.get("href", "").strip()
        title = title_elem.get("title") or title_elem.get_text(strip=True)
        price = price_elem.get_text(strip=True).replace("\xa0", " ") if price_elem else "N/A"
        regular_price = reg_price_elem.get_text(strip=True).replace("\xa0", " ") if reg_price_elem else None
        discount = discount_elem.get_text(strip=True).replace("\xa0", " ") if discount_elem else None
        stock = stock_elem.get_text(strip=True) if stock_elem else None
        image_url = img_elem.get("data-full-size-image-url") or img_elem.get("data-src") if img_elem else None

        key = prod_id if prod_id else url

        if key and url:
            products[key] = {
                "id": prod_id,
                "title": title,
                "price": price,
                "regular_price": regular_price,
                "discount": discount,
                "stock": stock,
                "url": url,
                "image_url": image_url
            }

    return products

def main():
    seen = load_seen_products()
    current = scrape_products()
    logging.info(f"Successfully scraped {len(current)} products from Black Friday page.")

    # On the very first run, seed database without spamming
    if not seen:
        logging.info("Initializing database with existing products (first run).")
        save_seen_products(current)
        return

    # Check for new products
    new_items_found = False
    for prod_id, info in current.items():
        if prod_id not in seen:
            logging.info(f"🚨 NEW PRODUCT DETECTED: {info['title']}")
            send_telegram_alert(info)
            seen[prod_id] = info
            new_items_found = True

    if new_items_found:
        save_seen_products(seen)
        logging.info("Saved updated products to database.")
    else:
        logging.info("Scan completed: No new products detected.")

if __name__ == "__main__":
    main()
