# amazon_full_scraper.py
import os
import json
import time
import requests
import traceback
from urllib.parse import urljoin, urlparse, parse_qs
from playwright.sync_api import sync_playwright, TimeoutError as PLTimeout

# ---- CONFIG ----
INPUT_JSON = "trufru_amazon_links.json"
OUTPUT_DIR = "trufru_results"
CATEGORY_NAME = "trufru"
HEADLESS = False
CHICAGO_ZIP = "60601"
NAV_TIMEOUT = 60000
SWATCH_CLICK_WAIT = 1.0
ITEM_DELAY = 1.0
MAX_OTHER_SELLERS = None

# Characters to strip from scraped labels (RTL marks, NBSP, etc.)
INVISIBLE_CHAR_MAP = dict.fromkeys(map(ord, [
    "\u200f",  # RTL mark
    "\u200e",  # LTR mark
    "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",  # dir marks
    "\xa0",    # non-breaking space
]), None)

import re

def extract_product_family_from_url(url: str):
    if not url:
        return None
    try:
        parts = urlparse(url).path.split("/")
        idx = parts.index("products") + 1
        family = parts[idx].replace("-", " ").title()
        return family
    except:
        return None


def make_family_id(category: str, family: str):
    base = (category + "_" + family).lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return base

# ================================
# Basic utilities
# ================================
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def save_json(path, data):
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


# 🔥 NEW: Append to JSON file incrementally
def append_to_json(path, new_items):
    """
    Load existing JSON, append new items, and save back.
    """
    existing = load_json(path)
    existing.extend(new_items)
    save_json(path, existing)


def clean_text(value):
    if not value:
        return None
    cleaned = value.translate(INVISIBLE_CHAR_MAP)
    return " ".join((cleaned or "").strip().split())


def text_list_from_elements(elements):
    texts = []
    for el in elements or []:
        txt = inner_text_or_none(el)
        if txt:
            texts.append(clean_text(txt))
    return texts


def extract_amazon_entries(items):
    """
    Extract Amazon links from JSON array.
    Expects: [{"asin": "...", "product_url": "...amazon.com...", ...}, ...]
    """
    extracted = []
    for entry in items:
        if not isinstance(entry, dict):
            continue

        amazon_link = entry.get("product_url")
        
        if not amazon_link or "amazon" not in amazon_link.lower():
            continue

        extracted.append({
            "amazon_link": amazon_link,
            "product_url": amazon_link,
            "asin": entry.get("asin"),
            "title": entry.get("title"),
            "price": entry.get("price"),
            "rating": entry.get("rating"),
            "reviews_count": entry.get("reviews_count"),
        })

    return extracted


# ================================
# PriceSpider → Amazon API FIX
# ================================
def resolve_pricespider_to_amazon(url):
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        pmid = qs.get("pmid", [None])[0]

        if not pmid:
            return None

        api_url = f"https://api.pricespider.com/v2/redirects/{pmid}"
        r = requests.get(api_url, timeout=10)
        data = r.json()

        for r in data.get("retailers", []):
            if r.get("name", "").lower() == "amazon":
                return r.get("link")

    except Exception:
        pass

    return None


def resolve_pricespider_with_playwright(context, url):
    page = None
    try:
        page = context.new_page()
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)
        final_url = page.url
        if "amazon" in (urlparse(final_url).netloc or ""):
            return final_url
    except Exception:
        return None
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
    return None


def normalize_amazon_link(context, url):
    if not url:
        return None
    link = url
    if "pricespider" in link:
        resolved = resolve_pricespider_to_amazon(link)
        if not resolved:
            resolved = resolve_pricespider_with_playwright(context, link)
        link = resolved or link
    return link


# ================================
# Amazon helpers
# ================================
def inner_text_or_none(elem):
    try:
        if elem:
            return elem.inner_text().strip()
    except:
        pass
    return None


def safe_query_text(page, selector):
    try:
        el = page.query_selector(selector)
        return inner_text_or_none(el)
    except:
        return None


def get_current_asin(page):
    selectors = [
        "input#ASIN",
        "input#twister-plus-asin",
        "input#twister-plus-asin-dp",
        "input#twister-plus-asin-dp-inner",
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if not el:
                continue
            val = el.get_attribute("value")
            if val:
                return val.strip()
        except Exception:
            continue
    try:
        return page.get_attribute("div#twister", "data-dp-as")
    except Exception:
        return None


def extract_offer_display_value(page, feature_name):
    selector = f"[offer-display-feature-name='{feature_name}'] .offer-display-feature-text-message"
    return safe_query_text(page, selector)


def parse_fresh_ships_from_sold_by(page):
    result = {"ships_from": None, "sold_by": None}
    
    try:
        rows = page.query_selector_all("#fresh-merchant-info tr")
        for row in rows or []:
            cells = row.query_selector_all("td")
            if len(cells) != 2:
                continue
            
            label = inner_text_or_none(cells[0])
            value = inner_text_or_none(cells[1])
            
            if not label or not value:
                continue
            
            label_lower = label.lower()
            if "ships from" in label_lower:
                result["ships_from"] = clean_text(value)
            elif "sold by" in label_lower:
                result["sold_by"] = clean_text(value)
    
    except Exception:
        pass
    
    return result


def parse_detail_bullets(page):
    bullets = {}
    try:
        items = page.query_selector_all("#detailBullets_feature_div li")
        for item in items or []:
            bold = item.query_selector("span.a-text-bold")
            label = inner_text_or_none(bold)
            value_span = item.query_selector("span.a-text-bold ~ span") or item.query_selector("span.a-list-item")
            value = inner_text_or_none(value_span)
            if label and value:
                label_clean = clean_text(label)
                value_clean = clean_text(value)
                if label_clean and value_clean:
                    bullets[label_clean.rstrip(":")] = value_clean
    except Exception:
        pass
    return bullets


def parse_important_info(page):
    info = {}
    try:
        sections = page.query_selector_all("#important-information .a-section.content")
        for section in sections or []:
            label = inner_text_or_none(section.query_selector(".a-text-bold"))
            paragraphs = section.query_selector_all("p")
            values = text_list_from_elements(paragraphs)
            joined = " ".join(values).strip() if values else None
            if label and joined:
                info[label] = joined
    except Exception:
        pass
    return info


def parse_diet_types(page):
    try:
        nodes = page.query_selector_all("#nic-diet-type-logos-wrapper span.a-size-base")
        return text_list_from_elements(nodes)
    except Exception:
        return []


def parse_ingredients(page):
    try:
        ingredients_block = page.query_selector("#nic-ingredients-content")
        if ingredients_block:
            return clean_text(ingredients_block.inner_text())
    except Exception:
        pass

    try:
        sections = page.query_selector_all("#important-information .a-section.content")
        for section in sections or []:
            label = inner_text_or_none(section.query_selector(".a-text-bold"))
            if label and "ingredient" in label.lower():
                paragraphs = section.query_selector_all("p")
                text = " ".join(text_list_from_elements(paragraphs))
                if text:
                    return text
    except Exception:
        pass

    return None


def parse_other_sellers(context, page):
    link_el = page.query_selector("#aod-ingress-link")
    if not link_el:
        return []

    href = link_el.get_attribute("href")
    if not href:
        return []

    offer_url = urljoin("https://www.amazon.com", href)

    if "offer-listing" in offer_url:
        olp_page = None
        try:
            olp_page = context.new_page()
            raw = extract_offers_from_offer_listing(olp_page, offer_url) or []
        except Exception:
            raw = []
        finally:
            if olp_page:
                try:
                    olp_page.close()
                except Exception:
                    pass

        if MAX_OTHER_SELLERS:
            raw = raw[:MAX_OTHER_SELLERS]

        normalized = []
        for r in raw:
            normalized.append({
                "price": clean_text(r.get("price")),
                "price_per_unit": clean_text(r.get("price_per_unit")),
                "delivery": clean_text(r.get("delivery")),
                "ships_from": clean_text(r.get("ships_from")),
                "sold_by": clean_text(r.get("sold_by") or r.get("seller")),
                "seller_rating": clean_text(r.get("seller_rating")),
                "seller_rating_count": clean_text(r.get("seller_rating_count")),
            })

        return [x for x in normalized if any(v for v in x.values())]

    def first_text(node, selectors):
        for sel in selectors:
            try:
                el = node.query_selector(sel)
            except Exception:
                el = None
            if not el:
                continue
            txt = inner_text_or_none(el)
            if txt:
                return txt
        return None

    def combine_price(node):
        price = first_text(node, [
            ".aod-price .a-offscreen",
            ".a-price .a-offscreen",
            "[id^='aod-price'] .aok-offscreen",
            "[id^='aod-offer-price'] .aok-offscreen",
        ])
        if price:
            return price

        price_container = node.query_selector(".a-price")
        if not price_container:
            return None

        symbol = inner_text_or_none(price_container.query_selector(".a-price-symbol")) or "$"
        whole = inner_text_or_none(price_container.query_selector(".a-price-whole"))
        fraction = inner_text_or_none(price_container.query_selector(".a-price-fraction")) or "00"
        if not whole:
            return None

        whole_digits = "".join(ch for ch in whole if ch.isdigit())
        fraction_digits = "".join(ch for ch in fraction if ch.isdigit()) or "00"

        return f"{symbol}{whole_digits}.{fraction_digits}"

    def get_offer_identifier(node):
        try:
            form = node.query_selector("form.AodAddToCart")
            if not form:
                return None
            trigger = form.query_selector("[data-aod-atc-action]")
            if not trigger:
                return None
            payload = trigger.get_attribute("data-aod-atc-action")
            if not payload:
                return None
            data = json.loads(payload)
            return data.get("offerIndex") or data.get("oid")
        except Exception:
            return None

    def scroll_and_load_all_offers(offer_root):
        try:
            scroller = (
                offer_root.query_selector("#all-offers-display-scroller")
                or offer_root.query_selector("#aod-offer-list")
                or offer_root.query_selector("#all-offers-display")
            )

            if not scroller:
                print("⚠️ No scroll container found")
                return

            print("🧲 Activating AOD scroll virtualization...")

            prev_count = 0
            stable = 0

            for i in range(80):
                offers = offer_root.query_selector_all(
                    "div.aod-information-block[role='listitem'], div.aod-offer"
                )
                count = len(offers)

                scroller.evaluate("""
                    el => {
                        el.scrollBy(0, 350);
                        el.dispatchEvent(new WheelEvent('wheel', { deltaY: 350, bubbles: true }));
                    }
                """)

                time.sleep(0.7)

                if count == prev_count:
                    stable += 1
                    if stable >= 6:
                        print(f"✅ AOD stabilized at {count} offers")
                        break
                else:
                    stable = 0

                prev_count = count

                if i % 5 == 0:
                    print(f"🔄 Scroll {i+1}: {count} offers")

            print(f"🎯 Final offer count: {count}")

        except Exception as e:
            print("⚠️ AOD scroll failed:", e)

    def extract_offers(nodes, processed_ids, root):
        items = []

        for node in nodes or []:
            atc = node.query_selector("input[name='submit.addToCart']")
            if not atc:
                continue

            offer_key = get_offer_identifier(node)
            if offer_key and offer_key in processed_ids:
                continue

            price = combine_price(node)

            price_per_unit = first_text(node, [
                ".centralizedApexPricePerUnitCSS span.a-size-mini.aok-offscreen",
                ".centralizedApexPricePerUnitCSS span.aok-offscreen",
                ".centralizedApexPricePerUnitCSS span[aria-hidden='true']",
                ".centralizedApexPricePerUnitCSS span",
                ".aod-price-per-unit span",
                ".a-size-mini.a-color-base.aok-align-center",
                ".a-size-mini.a-color-base",
            ])

            if price_per_unit:
                price_per_unit = price_per_unit.replace("(", "").replace(")", "").strip()

            if not price_per_unit:
                price_per_unit = clean_text(
                    safe_query_text(root, ".centralizedApexPricePerUnitCSS span.a-size-mini.aok-offscreen")
                    or safe_query_text(root, ".centralizedApexPricePerUnitCSS span[aria-hidden='true']")
                    or safe_query_text(root, ".a-size-mini.a-color-base.aok-align-center")
                    or safe_query_text(root, ".a-size-mini.a-color-base")
                )

            delivery = first_text(node, [
                ".aod-delivery-promise span",
                ".a-row.aod-fulfillment-text",
                "#mir-layout-DELIVERY_BLOCK span",
            ])

            ships_from = first_text(node, [
                ".aod-ship-from-row span.a-color-base",
                "div[id*='shipsFrom'] span.a-size-small.a-color-base",
                "div[id*='shipsFrom'] span.a-color-base",
            ])

            sold_by = first_text(node, [
                ".aod-offer-soldBy a",
                ".aod-offer-soldBy span.a-color-base",
                "div[id*='soldBy'] a",
                "div[id*='soldBy'] span",
            ])

            seller_rating = first_text(node, [
                ".aod-offer-seller-rating .a-icon-alt",
                "#aod-offer-seller-rating .a-icon-alt",
                "div[id*='seller-rating'] .a-icon-alt",
            ])

            seller_rating_count = first_text(node, [
                ".aod-offer-seller-rating span.a-color-base",
                "#aod-offer-seller-rating span.a-color-base",
                "div[id*='seller-rating'] span.a-color-base",
            ])

            data = {
                "price": clean_text(price),
                "price_per_unit": clean_text(price_per_unit),
                "delivery": clean_text(delivery),
                "ships_from": clean_text(ships_from),
                "sold_by": clean_text(sold_by),
                "seller_rating": clean_text(seller_rating),
                "seller_rating_count": clean_text(seller_rating_count),
            }

            if any(v for v in data.values()):
                if offer_key:
                    processed_ids.add(offer_key)
                items.append(data)

        return items

    popup = None
    items = []

    try:
        popup = context.new_page()
        popup.goto(offer_url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        try:
            popup.wait_for_load_state("networkidle", timeout=10000)
        except PLTimeout:
            pass

        offer_root = popup

        try:
            popup.wait_for_selector("iframe#all-offers-display-iframe", timeout=5000)
            frame_el = popup.query_selector("iframe#all-offers-display-iframe")
            if frame_el:
                frame = frame_el.content_frame()
                if frame:
                    offer_root = frame
                    print("✅ Detected iframe-based AOD layout")
        except Exception:
            pass

        offer_root.wait_for_selector("div#aod-offer-list, div#all-offers-display", timeout=10000)

        print("🔥 Activating AOD...")
        offer_root.evaluate("""
            () => {
                document.body.dispatchEvent(new MouseEvent('mousemove', { bubbles: true }));
                document.body.dispatchEvent(new WheelEvent('wheel', { deltaY: 200, bubbles: true }));
            }
        """)
        time.sleep(0.5)

        scroll_and_load_all_offers(offer_root)

        container = offer_root.query_selector("div#aod-offer-list") or \
                    offer_root.query_selector("div#all-offers-display")

        offer_nodes = container.query_selector_all(
            "div.aod-information-block[role='listitem'], div.aod-offer"
        )

        print(f"📊 Extracted {len(offer_nodes)} offer nodes from DOM")

        if MAX_OTHER_SELLERS:
            offer_nodes = offer_nodes[:MAX_OTHER_SELLERS]

        processed_ids = set()
        items = extract_offers(offer_nodes, processed_ids, offer_root)

        print(f"✅ Successfully parsed {len(items)} sellers with data")

        try:
            olp_page = context.new_page()
            fallback = extract_offers_from_offer_listing(olp_page, offer_url) or []
            olp_page.close()

            for row in items:
                row_seller = row.get("sold_by")
                if not row_seller:
                    continue

                match = next(
                    (
                        f for f in fallback
                        if (f.get("sold_by") or f.get("seller"))
                        and (f.get("sold_by") or f.get("seller")) in row_seller
                    ),
                    None
                )
                if not match:
                    continue

                if not row.get("delivery"):
                    row["delivery"] = match.get("delivery")

                if not row.get("ships_from"):
                    row["ships_from"] = match.get("ships_from")

                if not row.get("seller_rating_count"):
                    row["seller_rating_count"] = match.get("seller_rating_count")

        except Exception:
            pass

        return items

    except Exception:
        return []

    finally:
        if popup:
            try:
                popup.close()
            except Exception:
                pass


def parse_other_sellers_summary(page):
    link_el = page.query_selector("#aod-ingress-link")
    summary = {
        "text": clean_text(inner_text_or_none(link_el)) if link_el else safe_query_text(page, "#aod-ingress-block"),
        "link": link_el.get_attribute("href") if link_el else None,
        "price": None,
        "price_per_unit": None,
    }

    try:
        price_text = safe_query_text(page, "#apex_dp_aod #aod-price-1 span.a-offscreen") or \
                     safe_query_text(page, "#apex_dp_aod .a-price span.a-offscreen")
        if not price_text and link_el:
            price_text = inner_text_or_none(link_el.query_selector(".a-price span.a-offscreen"))
        per_unit = safe_query_text(page, "#apex_dp_aod .centralizedApexPricePerUnitCSS span[aria-hidden='true']") or \
                   inner_text_or_none(link_el.query_selector(".centralizedApexPricePerUnitCSS span[aria-hidden='true']"))
        summary["price"] = clean_text(price_text)
        summary["price_per_unit"] = clean_text(per_unit)
    except Exception:
        pass

    return summary


def set_chicago_zip(page):
    try:
        page.goto("https://www.amazon.com/gp/delivery/ajax/address-change.html", timeout=15000)
        time.sleep(1)

        if page.query_selector("#GLUXZipUpdateInput"):
            page.fill("#GLUXZipUpdateInput", CHICAGO_ZIP)
            page.click("#GLUXZipUpdate")
            time.sleep(2)
            return True

        page.goto("https://www.amazon.com/", timeout=15000)
        time.sleep(1)

        btn = page.query_selector("#nav-global-location-popover-link")
        if btn:
            btn.click()
            time.sleep(1)
            if page.query_selector("#GLUXZipUpdateInput"):
                page.fill("#GLUXZipUpdateInput", CHICAGO_ZIP)
                page.click("#GLUXZipUpdate")
                time.sleep(2)
                return True

    except Exception:
        pass

    return False


def configure_zip_once(context):
    temp_page = None
    try:
        temp_page = context.new_page()
        success = set_chicago_zip(temp_page)
        return success
    except Exception:
        return False
    finally:
        if temp_page:
            try:
                temp_page.close()
            except Exception:
                pass


def is_chicago_location(page):
    text = safe_query_text(page, "#glow-ingress-line2")
    if not text:
        return False
    lower = text.lower()
    return "chicago" in lower or CHICAGO_ZIP in lower


def ensure_chicago_location(context, page):
    if not page:
        return False

    domain = (urlparse(page.url).netloc or "").lower()
    if "amazon" not in domain:
        return False

    if is_chicago_location(page):
        return True

    configured = configure_zip_once(context)
    if not configured:
        return False

    try:
        page.reload(wait_until="domcontentloaded")
    except Exception:
        pass

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except PLTimeout:
        pass

    return is_chicago_location(page)


def extract_offers_from_offer_listing(page, url):
    import re

    offers = []

    def first_text(node, selectors):
        for sel in selectors:
            try:
                el = node.query_selector(sel)
            except Exception:
                el = None
            if not el:
                continue
            txt = inner_text_or_none(el)
            if txt:
                return txt.strip()
        return None

    def clean_rating_count(text):
        if not text:
            return None
        m = re.search(r"\(([\d,]+)\s+ratings\)", text)
        return m.group(1) if m else None

    def combine_price(node):
        price = first_text(node, [
            "span[id^='aod-price'] span.a-offscreen",
            "div#aod-offer-price span.a-offscreen",
            "span[id^='aod-price'] span.aok-offscreen",
            "div#aod-offer-price span.aok-offscreen",
            ".aod-price .a-offscreen",
            ".a-price .a-offscreen",
        ])
        if price:
            return price

        price_container = node.query_selector(".a-price")
        if not price_container:
            return None

        symbol = inner_text_or_none(price_container.query_selector(".a-price-symbol")) or "$"
        whole = inner_text_or_none(price_container.query_selector(".a-price-whole"))
        fraction = inner_text_or_none(price_container.query_selector(".a-price-fraction")) or "00"

        if not whole:
            return None

        whole_digits = "".join(ch for ch in whole if ch.isdigit())
        fraction_digits = "".join(ch for ch in fraction if ch.isdigit()) or "00"

        return f"{symbol}{whole_digits}.{fraction_digits}"

    try:
        page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        try:
            page.wait_for_selector("div.aod-information-block[role='listitem']", timeout=9000)
        except Exception:
            pass

        aod_nodes = page.query_selector_all("div.aod-information-block[role='listitem']") or []

        if aod_nodes:

            for node in aod_nodes:

                price = combine_price(node)

                price_per_unit = first_text(node, [
                    ".aod-price-per-unit span",
                    ".centralizedApexPricePerUnitCSS span.a-color-base",
                    ".centralizedApexPricePerUnitCSS span.aok-offscreen",
                    ".centralizedApexPricePerUnitCSS span.a-size-mini",
                    "span.a-size-mini",
                ])

                ships_from = first_text(node, [
                    ".aod-ship-from-row span.a-color-base",
                    "div[id*='shipsFrom'] span.a-size-small.a-color-base",
                    "#aod-offer-shipsFrom span.a-size-small",
                    "div[id*='shipsFrom'] span.a-size-small",
                    "div[id*='shipsFrom'] span",
                ])

                sold_by = first_text(node, [
                    ".aod-offer-soldBy a",
                    ".aod-offer-soldBy span.a-color-base",
                    "div[id*='soldBy'] a",
                    "div[id*='soldBy'] span",
                    "a.a-link-normal",
                ])

                seller_rating = first_text(node, [
                    ".aod-offer-seller-rating .a-icon-alt",
                    "div[id*='seller-rating'] .a-icon-alt",
                    ".a-icon-alt",
                ])

                rating_block = node.query_selector("div#aod-offer-seller-rating") or \
                               node.query_selector("div[id*='seller-rating']")

                seller_rating_count = clean_rating_count(
                    inner_text_or_none(rating_block)
                ) if rating_block else None

                delivery = first_text(node, [
                    ".aod-delivery-promise span",
                    ".a-row.aod-fulfillment-text",
                    "[data-csa-c-delivery-time]",
                    "div.aod-delivery-promise",
                    "span",
                ])

                row = {
                    "price": clean_text(price),
                    "price_per_unit": clean_text(price_per_unit) or clean_text(
                        safe_query_text(page, ".centralizedApexPricePerUnitCSS span[aria-hidden='true']") or
                        safe_query_text(page, ".a-size-mini.a-color-base.aok-align-center") or
                        safe_query_text(page, ".a-size-mini.a-color-base")
                    ),
                    "delivery": clean_text(delivery),
                    "ships_from": clean_text(ships_from),
                    "sold_by": clean_text(sold_by),
                    "seller": clean_text(sold_by),
                    "seller_rating": clean_text(seller_rating),
                    "seller_rating_count": clean_text(seller_rating_count),
                }

                if row["price"] or row["sold_by"]:
                    offers.append(row)

            return offers

        try:
            page.wait_for_selector("div.olpOffer, div.a-row.a-spacing-mini", timeout=8000)
        except Exception:
            return []

        rows = page.query_selector_all("div.olpOffer, div.a-row.a-spacing-mini") or []

        for r in rows:

            price = (
                inner_text_or_none(r.query_selector(".a-offscreen"))
                or inner_text_or_none(r.query_selector(".a-price .a-offscreen"))
            )

            seller = (
                inner_text_or_none(r.query_selector(".olpSellerName"))
                or inner_text_or_none(r.query_selector("a[href*='seller']"))
                or inner_text_or_none(r.query_selector("span.a-size-small.a-color-base"))
            )

            seller_rating = inner_text_or_none(r.query_selector(".a-icon-alt"))

            rating_block = r.query_selector(".olpSellerColumn, .olpSellerName")

            seller_rating_count = clean_rating_count(
                inner_text_or_none(rating_block)
            ) if rating_block else None

            row = {
                "price": clean_text(price),
                "price_per_unit": None,
                "delivery": None,
                "ships_from": None,
                "sold_by": clean_text(seller),
                "seller": clean_text(seller),
                "seller_rating": clean_text(seller_rating),
                "seller_rating_count": clean_text(seller_rating_count),
            }

            if row["price"] or row["sold_by"]:
                offers.append(row)

        return offers

    except Exception:
        return []


def get_variant_swatches(page):
    swatch_lists = []
    try:
        containers = page.query_selector_all("ul.dimension-values-list")
    except Exception:
        containers = []

    seen_names = set()
    for idx, container in enumerate(containers or []):
        raw_group = container.get_attribute("data-a-button-group")
        group_name = None
        if raw_group:
            try:
                parsed = json.loads(raw_group)
                group_name = parsed.get("name")
            except Exception:
                pass

        if not group_name:
            group_name = container.get_attribute("aria-label")

        if not group_name:
            group_name = f"dimension_{idx+1}"

        if group_name in seen_names:
            group_name = f"{group_name}_{idx+1}"
        seen_names.add(group_name)

        options = []
        li_nodes = container.query_selector_all("li")
        for li in li_nodes or []:
            button = li.query_selector("span.a-button")
            if not button:
                continue
            option_label = inner_text_or_none(li.query_selector(".swatch-title-text-display")) or \
                           inner_text_or_none(li.query_selector(".a-button-text")) or \
                           inner_text_or_none(li)
            option_label = clean_text(option_label) if option_label else None
            classes = li.get_attribute("class") or ""
            available = "unavailable" not in classes
            options.append({
                "label": option_label,
                "button": button,
                "asin": li.get_attribute("data-asin"),
                "available": available
            })

        if options:
            swatch_lists.append({
                "name": group_name,
                "options": options
            })

    return swatch_lists


def click_variant(page, element):
    try:
        element.scroll_into_view_if_needed()
        element.click(force=True)
        time.sleep(1)
        return True
    except:
        return False


def extract_product_data(context, page):
    data = {}
    try:
        data["title"] = safe_query_text(page, "#productTitle")
        data["price"] = safe_query_text(page, "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen") \
            or safe_query_text(page, ".a-price .a-offscreen")
        data["price_per_unit"] = safe_query_text(page, ".pricePerUnit") or \
            safe_query_text(page, ".aok-relative .pricePerUnit") or \
            safe_query_text(page, ".a-size-mini.a-color-base.aok-align-center")

        data["flavor"] = safe_query_text(page, "#inline-twister-expanded-dimension-text-flavor_name")
        data["size"] = safe_query_text(page, "#inline-twister-expanded-dimension-text-size_name")

        data["prime"] = bool(page.query_selector("img[alt*='Prime'], i[class*='a-icon-prime']"))

        bullet_items = page.query_selector_all("#feature-bullets li span")
        data["about_this_item"] = [clean_text(inner_text_or_none(b)) for b in bullet_items if inner_text_or_none(b)] \
            if bullet_items else []

        data["diet_types"] = parse_diet_types(page)
        data["ingredients"] = parse_ingredients(page)

        data["product_description"] = safe_query_text(page, "#productDescription")
        data["product_details"] = parse_detail_bullets(page)
        data["important_information"] = parse_important_info(page)

        data["ships_from"] = extract_offer_display_value(page, "desktop-fulfiller-info")
        data["sold_by"] = extract_offer_display_value(page, "desktop-merchant-info")

        if not data["ships_from"] or not data["sold_by"]:
            fresh = parse_fresh_ships_from_sold_by(page)
            data["ships_from"] = data["ships_from"] or fresh["ships_from"]
            data["sold_by"] = data["sold_by"] or fresh["sold_by"]

        data["returns"] = extract_offer_display_value(page, "desktop-return-info")
        data["packaging"] = extract_offer_display_value(page, "desktop-package-info")
        data["payment"] = extract_offer_display_value(page, "desktop-dynamic-secure-transaction")

        data["other_sellers_summary"] = parse_other_sellers_summary(page)
        data["other_sellers"] = parse_other_sellers(context, page)
    except Exception:
        pass

    return data


def capture_variant_payload(context, page, base_meta, variant_selection, seen_asins, results):
    asin = get_current_asin(page)
    if asin and asin in seen_asins:
        return
    if asin:
        seen_asins.add(asin)

    pdata = extract_product_data(context, page) or {}
    pdata["source_product_url"] = base_meta.get("product_url")
    pdata["source_link"] = base_meta.get("source_link")
    pdata["original_amazon_link"] = base_meta.get("original_link")
    pdata["variant_dimensions"] = dict(variant_selection) if variant_selection else {}
    pdata["asin"] = asin
    pdata["final_url"] = page.url

    product_family = pdata.get("title") or "TruFru"
    pdata["variant_group_name"] = product_family
    pdata["variant_family_id"] = make_family_id("trufru", product_family)
    
    # 🔥 NEW: Add input metadata
    pdata["input_asin"] = base_meta.get("input_asin")
    pdata["input_title"] = base_meta.get("input_title")
    
    results.append(pdata)


def ensure_full_variant_root(page):
    try:
        first = page.query_selector(
            "ul[role='radiogroup'] li:first-child button, ul.dimension-values-list li:first-child button"
        )
        if first:
            first.click()
            page.wait_for_timeout(1500)
    except:
        pass


def reveal_all_swatches(page):
    for _ in range(20):
        try:
            page.evaluate("""
                const lists = document.querySelectorAll(
                    'ul[role="radiogroup"], ul.dimension-values-list'
                );
                lists.forEach(c => c.scrollLeft = c.scrollWidth);
            """)
            page.wait_for_timeout(200)
        except:
            break


def get_parent_data(page):
    meta = page.evaluate("""
        () => window.AmazonUIPageJS?.getState?.('twisterJsInitializeState') || null
    """) or {}

    return {
        "parent_asin": meta.get("parentASIN"),
        "variation_map": meta.get("asinVariationValues") or {}
    }


def collect_variants_for_product(context, page, base_meta):
    ensure_full_variant_root(page)
    reveal_all_swatches(page)

    pd = get_parent_data(page)
    parent_asin = pd["parent_asin"]
    backend_variants = set(pd["variation_map"].keys())

    if parent_asin:
        base_meta["parent_asin"] = parent_asin

    if backend_variants:
        print(f"📦 Backend variants detected: {len(backend_variants)}")

    swatch_groups = get_variant_swatches(page)
    results = []
    seen_asins = set()
    group_names = [g["name"] for g in swatch_groups]

    def recurse(idx, selection):
        if idx >= len(group_names):
            capture_variant_payload(context, page, base_meta, selection, seen_asins, results)
            return

        group = next((g for g in get_variant_swatches(page) if g["name"] == group_names[idx]), None)
        if not group:
            return

        for opt in group["options"]:
            if not opt.get("available"):
                continue
            if click_variant(page, opt["button"]):
                page.wait_for_timeout(1200)
                selection[group["name"]] = opt.get("label")
                capture_variant_payload(context, page, base_meta, selection, seen_asins, results)

        selection.pop(group["name"], None)

    if group_names:
        recurse(0, {})
    else:
        capture_variant_payload(context, page, base_meta, {}, seen_asins, results)

    missing = backend_variants - seen_asins
    if missing:
        print(f"⚠️ Fetching missing variants: {len(missing)}")

    for asin in missing:
        try:
            page.goto(f"https://www.amazon.com/dp/{asin}", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_load_state("networkidle")
            capture_variant_payload(context, page, base_meta, {}, seen_asins, results)
        except Exception:
            continue

    final_results = []
    seen = set()
    for item in results:
        a = item.get("asin")
        if a and a not in seen:
            seen.add(a)
            final_results.append(item)

    print(f"✔ Final unique variants: {len(final_results)}")
    return final_results


# ================================
# 🔥 NEW: SCRAPE WITH INCREMENTAL SAVING
# ================================
def scrape_category_amazons(context, page, cat, links):
    save_folder = os.path.join(OUTPUT_DIR, cat)
    ensure_dir(save_folder)

    results_path = os.path.join(save_folder, "results.json")
    failed_path = os.path.join(save_folder, "failed.json")
    missing_path = os.path.join(save_folder, "missing.json")
    all_products_path = os.path.join(OUTPUT_DIR, "all_products.json")
    failed_overall_path = os.path.join(OUTPUT_DIR, "failed_overall.json")

    # Initialize empty files if they don't exist
    if not os.path.exists(results_path):
        save_json(results_path, [])
    if not os.path.exists(all_products_path):
        save_json(all_products_path, [])
    if not os.path.exists(failed_overall_path):
        save_json(failed_overall_path, [])

    zip_configured = False

    for idx, item in enumerate(links, start=1):
        amazon_link = item.get("amazon_link")
        original_url = item.get("product_url")
        asin = item.get("asin")
        title = item.get("title")

        print(f"\n[{idx}/{len(links)}] ASIN: {asin} | Title: {title}")
        print(f"Amazon Link: {amazon_link}")

        if not amazon_link:
            append_to_json(missing_path, [item])
            continue

        resolved_link = normalize_amazon_link(context, amazon_link)
        if not resolved_link:
            print("❌ Could not resolve Amazon link, skipping.")
            fail_entry = {"item": item, "error": "amazon_link_missing"}
            append_to_json(failed_path, [fail_entry])
            append_to_json(failed_overall_path, [fail_entry])
            continue

        parsed_host = (urlparse(resolved_link).netloc or "").lower()
        if "amazon" not in parsed_host:
            print("❌ Resolved link is not an Amazon domain, skipping:", resolved_link)
            fail_entry = {"item": item, "error": "non_amazon_link"}
            append_to_json(failed_path, [fail_entry])
            append_to_json(failed_overall_path, [fail_entry])
            continue

        try:
            page.goto(resolved_link, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PLTimeout:
                pass
            time.sleep(2)
        except Exception:
            fail_entry = {"item": item, "error": "amazon_open_failed"}
            append_to_json(failed_path, [fail_entry])
            append_to_json(failed_overall_path, [fail_entry])
            continue

        current_domain = (urlparse(page.url).netloc or "").lower()
        if "amazon" in current_domain:
            if not zip_configured or not is_chicago_location(page):
                if ensure_chicago_location(context, page):
                    zip_configured = True
                    print("📍 Shipping ZIP confirmed as Chicago.")
                else:
                    print("⚠ Could not confirm Chicago ZIP on this page.")

        metadata = {
            "product_url": original_url,
            "source_link": resolved_link,
            "original_link": amazon_link,
            "input_asin": asin,
            "input_title": title,
        }

        try:
            variant_payloads = collect_variants_for_product(context, page, metadata)
        except Exception:
            traceback.print_exc()
            fail_entry = {"item": item, "error": "variant_extraction_failed"}
            append_to_json(failed_path, [fail_entry])
            append_to_json(failed_overall_path, [fail_entry])
            continue

        # 🔥 APPEND IMMEDIATELY after scraping each product
        if variant_payloads:
            append_to_json(results_path, variant_payloads)
            append_to_json(all_products_path, variant_payloads)
            print(f"✔ Scraped {len(variant_payloads)} variant(s) → Saved immediately!")

        time.sleep(ITEM_DELAY)

    print(f"\n✔ Finished category: {cat}")


# ================================
# DRIVER
# ================================
def run_scraper():
    ensure_dir(OUTPUT_DIR)

    raw_links = load_json(INPUT_JSON)
    
    if not raw_links:
        print(f"❌ No data found in {INPUT_JSON}")
        return

    links = extract_amazon_entries(raw_links)
    
    if not links:
        print(f"❌ No valid Amazon links found in {INPUT_JSON}")
        return

    print(f"\n✅ Loaded {len(links)} products from {INPUT_JSON}")
    print("="*60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(locale="en-US")
        page = context.new_page()
        page.set_default_navigation_timeout(NAV_TIMEOUT)

        configured = configure_zip_once(context)
        if configured:
            print("📍 Amazon ZIP set to Chicago once for the session.")
        else:
            print("⚠ Could not pre-set Chicago ZIP; continuing anyway.")

        print("\n" + "="*60)
        print(f"📂 CATEGORY: {CATEGORY_NAME}")
        print("="*60)

        scrape_category_amazons(context, page, CATEGORY_NAME, links)

        browser.close()

    # Final summary
    all_products = load_json(os.path.join(OUTPUT_DIR, "all_products.json"))
    all_failed = load_json(os.path.join(OUTPUT_DIR, "failed_overall.json"))

    print("\n🎉 DONE — All Amazon Pages Scraped!")
    print(f"Total products scraped: {len(all_products)}")
    print(f"Total failures: {len(all_failed)}")


if __name__ == "__main__":
    run_scraper()
