import json
import re
from urllib.parse import urlparse


INPUT_FILE = "all_products_merged.json"
OUTPUT_FILE = "normalized_all_products1.json"


# =========================
# HELPERS
# =========================


def parse_money(m):
    if m is None:
        return None
    if isinstance(m, (int, float)):
        return float(m)
    m = str(m).replace(",", "")
    m = re.search(r"\$?([0-9]+(?:\.[0-9]+)?)", m)
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

    # plain number like "1228"
    if t.isdigit():
        return int(t), None

    c = re.search(r"([\d,]+)", t)
    count = int(c.group(1).replace(",", "")) if c else None

    p = re.search(r"(\d+)%\s+positive", t)
    positive = float(p.group(1)) if p else None

    return count, positive


def extract_slug(url):
    if not url:
        return None
    part = urlparse(url).path.rstrip("/").split("/")[-1]
    return part.replace("-", " ").title()


def extract_product_family(url):
    try:
        parts = urlparse(url).path.split("/")
        idx = parts.index("products") + 1
        return parts[idx].replace("-", " ").title()
    except:
        return None


def classify_price_flag(pct):
    """
    Returns a business-friendly price classification based on
    how much higher the seller's price is compared to Amazon.
    """

    if pct is None:
        return None

    # 0% or cheaper → fair
    if pct <= 0:
        return "Fair Price"

    # Up to +20% → slightly high
    if pct <= 20:
        return "Slightly High"

    # +20% to +50% → high price
    if pct <= 50:
        return "High Price"

    # Above +50% → price gouging
    return "Price Gouging"


# =========================
# NORMALIZER
# =========================


def normalize():
    with open(INPUT_FILE, "r") as f:
        items = json.load(f)

    groups = {}

    for p in items:
        asin = p.get("asin")
        src = p.get("source_product_url")
        if not asin or not src:
            continue

        # Group Key
        if src not in groups:
            groups[src] = {
                "category": p.get("category"),
                # Change C: derive display from category by removing underscores
                "category_display": (p.get("category") or "").replace("_", " ") or None,
                "source_product_url": src,
                "product_name": extract_product_family(src) or extract_slug(src),
                "variants": [],
            }

        # ---------------------------------------
        # VARIANT PROCESSING
        # ---------------------------------------
        variant_name = (
            p.get("flavor")
            or (p.get("variant_dimensions") or {}).get("flavor_name")
            or extract_slug(src)
        )

        base_price = parse_money(p.get("price"))
        unit_price = parse_unit_price(p.get("price_per_unit"))

        variant_obj = {
            "asin": asin,
            "variant_name": variant_name,
            "title": p.get("title"),
            "price": base_price,
            "unit_price": unit_price,
            "prime": p.get("prime"),
            "flavor": variant_name,
            "size": p.get("size"),
            "variant_dimensions": p.get("variant_dimensions") or {},
            "final_url": p.get("final_url"),
            "original_amazon_link": p.get("original_amazon_link"),
        }

        groups[src]["variants"].append(variant_obj)

        # ---------------------------------------
        # MAIN SELLER (per variant)
        # ---------------------------------------
        raw_main = p.get("main_seller")

        # Change A: Normalize to a dict, including string case
        if isinstance(raw_main, list) and raw_main:
            existing_main = raw_main[0]
        elif isinstance(raw_main, dict):
            existing_main = raw_main
        elif isinstance(raw_main, str):
            existing_main = {
                "seller_name": raw_main,
                "ships_from": p.get("ships_from"),
            }
        else:
            existing_main = {}

        seller_name = (
            existing_main.get("seller_name")
            or existing_main.get("ships_from")
            or p.get("main_seller")   # fallback when input is a string
            or p.get("ships_from")
        )

        main_seller = {
            "asin": asin,
            "seller_name": seller_name,
            "ships_from": existing_main.get("ships_from") or p.get("ships_from"),
            # Change B: force explicit boolean
            "is_authorized": bool(
                seller_name
                and seller_name.lower() in {
                    "amazon",
                    "amazon.com",
                    "amazonfresh",
                    "whole foods market",
                }
            ),
            "price": base_price,
            "unit_price": unit_price,
            "price_currency": "USD",
            "prime": p.get("prime"),
        }

        # Store as list (one per variant)
        if "main_seller" not in groups[src]:
            groups[src]["main_seller"] = []

        groups[src]["main_seller"].append(main_seller)

        # ---------------------------------------
        # OTHER SELLERS
        # ---------------------------------------
        if "seller_market" not in groups[src]:
            groups[src]["seller_market"] = []

        for osel in p.get("other_sellers", []):
            osp = parse_money(osel.get("price"))
            stars = parse_rating_stars(osel.get("seller_rating"))
            rcount, pos = parse_rating_meta(osel.get("seller_rating_count"))

            delta = (
                (osp - base_price)
                if (osp is not None and base_price is not None)
                else None
            )

            if delta is not None and base_price:
                pct = (delta / base_price) * 100
            else:
                pct = None

            seller_name = osel.get("sold_by")

            groups[src]["seller_market"].append(
                {
                    "asin": asin,
                    "seller_name": seller_name,
                    "ships_from": osel.get("ships_from"),
                    "is_authorized": seller_name
                    and seller_name.lower() in {
                        "amazon",
                        "amazon.com",
                        "amazonfresh",
                        "whole foods market",
                    },
                    "price": osp,
                    "unit_price": parse_unit_price(osel.get("price_per_unit")),
                    "price_currency": "USD",
                    "price_delta_abs": delta,
                    "price_delta_percent": pct,
                    "price_flag": classify_price_flag(pct),
                    "rating_stars": stars,
                    "rating_count": rcount,
                    "positive_rating_percent": pos,
                    "rating_flag": None
                    if pos is None
                    else (
                        "excellent"
                        if pos >= 90
                        else "good"
                        if pos >= 75
                        else "mixed"
                        if pos >= 50
                        else "poor"
                    ),
                }
            )

    # convert dict → list
    result = list(groups.values())

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2)

    print("✔ FINAL Normalization Complete")
    print("✔ Output:", OUTPUT_FILE)
    print("✔ Product Families:", len(result))


if __name__ == "__main__":
    normalize()
