import os
import json
import logging
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BASE_URL = "https://lofficielshop.tn/fr/1002-black-friday"
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
        logging.warning("Telegram credentials not configured. Notification skipped.")
        return

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
        logging.info(f"Telegram alert sent for: {product['title']} (ID: {product['id']})")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")

def scrape_all_black_friday_products():
    """
    Scrapes the Black Friday category sorted by newest additions (date_add.desc),
    automatically following pagination across all available pages.
    """
    all_products = {}
    page = 1
    max_pages = 10 # Safety limit

    while page <= max_pages:
        # Sort by newest additions first: order=product.date_add.desc
        url = f"{BASE_URL}?order=product.date_add.desc&page={page}"
        logging.info(f"Scanning page {page}: {url}")

        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
        except Exception as e:
            logging.error(f"Failed to fetch page {page}: {e}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        articles = soup.select("article.product-miniature, [data-id-product]")

        if not articles:
            logging.info(f"No products found on page {page}. Stopping pagination.")
            break

        page_count = 0
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

            url_prod = title_elem.get("href", "").strip()
            title = title_elem.get("title") or title_elem.get_text(strip=True)
            price = price_elem.get_text(strip=True).replace("\xa0", " ") if price_elem else "N/A"
            regular_price = reg_price_elem.get_text(strip=True).replace("\xa0", " ") if reg_price_elem else None
            discount = discount_elem.get_text(strip=True).replace("\xa0", " ") if discount_elem else None
            stock = stock_elem.get_text(strip=True) if stock_elem else None
            image_url = img_elem.get("data-full-size-image-url") or img_elem.get("data-src") if img_elem else None

            # Unique key: primary PrestaShop product ID
            key = str(prod_id) if prod_id else url_prod

            if key and url_prod and key not in all_products:
                all_products[key] = {
                    "id": key,
                    "title": title,
                    "price": price,
                    "regular_price": regular_price,
                    "discount": discount,
                    "stock": stock,
                    "url": url_prod,
                    "image_url": image_url
                }
                page_count += 1

        logging.info(f"Found {page_count} products on page {page}.")

        # Check if there is a next page link
        has_next = soup.select_one('a[rel="next"], .pagination .next')
        if not has_next:
            logging.info("Reached last page.")
            break

        page += 1

    return all_products

def main():
    seen = load_seen_products()
    current = scrape_all_black_friday_products()
    logging.info(f"Total products found across all pages: {len(current)}.")

    # First run initialization (avoids spamming all products initially)
    if not seen:
        logging.info("Initializing database with existing products (first run).")
        save_seen_products(current)
        return

    # Check strictly for uncataloged products
    new_items_found = False
    for prod_id, info in current.items():
        if prod_id not in seen:
            logging.info(f"🚨 BRAND NEW PRODUCT DETECTED: {info['title']} (ID: {prod_id})")
            send_telegram_alert(info)
            # Add to seen immediately so it can NEVER trigger again
            seen[prod_id] = info
            new_items_found = True

    if new_items_found:
        save_seen_products(seen)
        logging.info(f"Database updated. Total seen products: {len(seen)}.")
    else:
        logging.info("Scan completed: No new products detected. Zero spam sent.")

if __name__ == "__main__":
    main()
