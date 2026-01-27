import json
import re
from urllib.parse import urlparse

INPUT_FILE = "unique_trufru.json"        # Tru Fru merged scrape
OUTPUT_FILE = "normalized_trufru.json"

# =========================
# HELPERS (REUSED)
# =========================

def parse_money(m):
    if not m:
        return None
    m = m.replace(",", "")
    m = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", m)
    return float(m.group(1)) if m else None


def parse_unit_price(text):
    if not text:
        return None
    text = text.replace(",", "")
    m = re.search(r"\$([0-9]+(?:\.[0-9]+)?)\s*/", text)
    return float(m.group(1)) if m else parse_money(text)


def parse_rating_stars(t):
    if not t:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s+out of\s+5", t)
    return float(m.group(1)) if m else None


def parse_rating_meta(t):
    if not t:
        return None, None
    c = re.search(r"\(([\d,]+)\s+ratings?\)", t)
    count = int(c.group(1).replace(",", "")) if c else None
    p = re.search(r"(\d+)%\s+positive", t)
    positive = float(p.group(1)) if p else None
    return count, positive


def classify_price_flag(pct):
    if pct is None:
        return None
    if pct <= 0:
        return "Fair Price"
    if pct <= 20:
        return "Slightly High"
    if pct <= 50:
        return "High Price"
    return "Price Gouging"


# =========================
# TRU FRU–SPECIFIC CONFIG
# =========================

AUTHORIZED_TRUFRU_SELLERS = {
    "Amazon.com",
    "AmazonFresh",
    "Whole Foods Market"
}


# =========================
# NORMALIZER
# =========================

def normalize_trufru():
    with open(INPUT_FILE, "r") as f:
        items = json.load(f)

    groups = {}

    for p in items:
        family_id = p.get("variant_family_id")
        asin = p.get("asin")

        if not family_id or not asin:
            continue

        # -------------------------------
        # GROUPING (Tru Fru canonical)
        # -------------------------------
        if family_id not in groups:
            groups[family_id] = {
                "product_family_id": family_id,
                "product_name": p.get("variant_group_name") or p.get("title"),
                "variants": [],
                "main_seller": [],
                "seller_market": [],
            }

        # -------------------------------
        # VARIANT
        # -------------------------------
        base_price = parse_money(p.get("price"))
        unit_price = parse_unit_price(p.get("price_per_unit"))

        variant_name = (
            p.get("title")
            or (p.get("variant_dimensions") or {}).get("flavor_name")
            or asin
        )

        variant_obj = {
            "asin": asin,
            "variant_name": variant_name,
            "title": p.get("title"),
            "price": base_price,
            "unit_price": unit_price,
            "prime": p.get("prime"),
            "variant_dimensions": p.get("variant_dimensions") or {},
            "final_url": p.get("final_url"),
        }

        groups[family_id]["variants"].append(variant_obj)

        # -------------------------------
        # MAIN SELLER (Amazon baseline)
        # -------------------------------
        seller_name = p.get("sold_by")

        main_seller = {
            "asin": asin,
            "seller_name": seller_name,
            "ships_from": p.get("ships_from"),
            "is_authorized": seller_name in AUTHORIZED_TRUFRU_SELLERS,
            "price": base_price,
            "unit_price": unit_price,
            "price_currency": "USD",
            "prime": p.get("prime"),
        }

        groups[family_id]["main_seller"].append(main_seller)

        # -------------------------------
        # OTHER SELLERS (Marketplace)
        # -------------------------------
        for osel in p.get("other_sellers", []):
            seller_price = parse_money(osel.get("price"))
            seller_unit = parse_unit_price(osel.get("price_per_unit"))

            amazon_unit = unit_price

            if seller_unit is not None and amazon_unit is not None:
                delta = seller_unit - amazon_unit
                pct = (delta / amazon_unit) * 100
            else:
                delta = None
                pct = None

            stars = parse_rating_stars(osel.get("seller_rating"))
            rcount, pos = parse_rating_meta(osel.get("seller_rating_count"))

            groups[family_id]["seller_market"].append({
                "asin": asin,
                "seller_name": osel.get("sold_by"),
                "ships_from": osel.get("ships_from"),
                "is_authorized": osel.get("sold_by") in AUTHORIZED_TRUFRU_SELLERS,

                # Prices
                "price": seller_price,
                "unit_price": seller_unit,
                "price_currency": "USD",

                # Canonical deltas (UNIT PRICE)
                "price_delta_abs": delta,
                "price_delta_percent": pct,
                "price_flag": classify_price_flag(pct),

                # Amazon reference
                "amazon_price_listing": base_price,
                "amazon_unit_price": amazon_unit,

                # Ratings
                "rating_stars": stars,
                "rating_count": rcount,
                "positive_rating_percent": pos,
                "rating_flag": None if pos is None else (
                    "excellent" if pos >= 90 else
                    "good" if pos >= 75 else
                    "mixed" if pos >= 50 else
                    "poor"
                )
            })

    result = list(groups.values())

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2)

    print("✔ Tru Fru normalization complete")
    print("✔ Output:", OUTPUT_FILE)
    print("✔ Product families:", len(result))


if __name__ == "__main__":
    normalize_trufru()
