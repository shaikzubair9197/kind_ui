import os
import json
import re
from urllib.parse import urlparse


# =========================
# CONFIG
# =========================
INPUT_ROOT = "kind_results"
OUTPUT_ROOT = "normalized_products(28-01-26)"
COMBINED_OUTPUT_FILE = "all_products_normalized(28-01-26).json"


AUTHORIZED_KEYWORDS = [
    "amazon.com",
    "amazonfresh",
    "whole foods",
    "kind snacks",
    "friend of brand",
]



EXTRA_AUTHORIZED = []


# =========================
# HELPERS
# =========================


def prettify_category_name(cat: str) -> str:
    return cat.replace("_", " ").strip().title()


def parse_money(m: str):
    if not m:
        return None
    m = m.replace(",", "")
    match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", m)
    return float(match.group(1)) if match else None


def parse_unit_price(s: str):
    if not s:
        return None
    s = s.replace(",", "")
    m = re.search(r"\$([0-9]+(?:\.[0-9]+)?)\s*/", s)
    return float(m.group(1)) if m else parse_money(s)


def parse_rating_stars(text: str):
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s+out of\s+5", text)
    return float(m.group(1)) if m else None


def parse_rating_meta(text: str):
    if not text:
        return None, None
    count = None
    positive = None
    m1 = re.search(r"\((\d[\d,]*)\s+ratings?\)", text)
    if m1:
        count = int(m1.group(1).replace(",", ""))
    m2 = re.search(r"(\d+)%\s+positive", text)
    if m2:
        positive = float(m2.group(1))
    return count, positive


def is_authorized_seller(name: str):
    if not name:
        return False
    n = name.lower()
    for v in EXTRA_AUTHORIZED:
        if v.lower() in n:
            return True
    return any(kw in n for kw in AUTHORIZED_KEYWORDS)


def classify_price_flag(delta_pct):
    if delta_pct is None:
        return None
    if delta_pct <= 0:
        return "at_or_below"
    if delta_pct <= 50:
        return "elevated"
    return "gouging"


def classify_rating_flag(positive_pct):
    if positive_pct is None:
        return None
    if positive_pct >= 90:
        return "excellent"
    if positive_pct >= 75:
        return "good"
    if positive_pct >= 50:
        return "mixed"
    return "poor"


def extract_product_family(url: str):
    """
    /products/healthy-grains-energy-bars/... -> Healthy Grains Energy Bars
    """
    if not url:
        return None
    try:
        parts = urlparse(url).path.split("/")
        idx = parts.index("products") + 1
        return parts[idx].replace("-", " ").title()
    except Exception:
        return None


def extract_slug_flavor(url: str):
    """Fallback if no Amazon flavor fields available"""
    if not url:
        return None
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return slug.replace("-", " ").title()


def fix_variant_names(variants):
    mapping = {}

    # Build mapping: Best known flavor for each ASIN
    for v in variants:
        flav = (v.get("variant_dimensions") or {}).get("flavor_name") \
               or v.get("flavor")
        title = (v.get("title") or "").lower()
        # If title contains flavor text → high confidence mapping
        if flav and flav.lower() in title:
            mapping[v["asin"]] = flav

    # Second pass: Fill missing or wrong flavors
    for v in variants:
        if v["asin"] in mapping:
            v["variant_name"] = mapping[v["asin"]]
            v["flavor"] = mapping[v["asin"]]
        else:
            # fallback: slug or flavor field
            v["variant_name"] = v.get("flavor") or extract_slug_flavor(v.get("final_url"))

    return variants


def dedupe_sellers(sellers):
    seen = {}
    for s in sellers:
        key = (s.get("asin"), s.get("seller_name"))
        current_price = s.get("price") or 0
        if key not in seen:
            seen[key] = s
        else:
            prev_price = seen[key].get("price") or 1e9
            if current_price < prev_price:
                seen[key] = s
    return list(seen.values())


# =========================
# NORMALIZATION
# =========================


def normalize_category(category_name, input_root):
    category_dir = os.path.join(input_root, category_name)
    if not os.path.isdir(category_dir):
        return []

    products = []

    # 🔹 Load ALL json files inside category folder
    for fname in os.listdir(category_dir):
        if not fname.lower().endswith(".json"):
            continue

        fpath = os.path.join(category_dir, fname)
        try:
            with open(fpath, "r") as f:
                data = json.load(f)

                # file may contain a list OR a single object
                if isinstance(data, list):
                    products.extend(data)
                elif isinstance(data, dict):
                    products.append(data)

        except Exception as e:
            print(f"⚠ Skipping {fpath}: {e}")

    if not products:
        return []

    groups = {}
    cat_display = prettify_category_name(category_name)

    for p in products:
        asin = p.get("asin")
        source_url = p.get("source_product_url") or asin
        if not source_url:
            continue

        product_family = extract_product_family(source_url)
        slug_flavor = extract_slug_flavor(source_url)
        if not product_family:
            product_family = slug_flavor

        if source_url not in groups:
            groups[source_url] = {
                "category": category_name,
                "category_display": cat_display,
                "source_product_url": p.get("source_product_url"),
                "product_name": product_family,
                "variants": [],
                "main_seller": [],
                "seller_market": [],
            }

        base_price = parse_money(p.get("price"))
        unit_price = parse_unit_price(p.get("price_per_unit"))

        # Amazon baseline set once per variant row
        amazon_price = base_price
        amazon_unit_price = unit_price

        # ---------- VARIANTS ----------
        variant_flavor = (
            p.get("flavor")
            or (p.get("variant_dimensions") or {}).get("flavor_name")
            or slug_flavor
        )

        groups[source_url]["variants"].append({
            "asin": asin,
            "variant_name": variant_flavor,
            "title": p.get("title"),
            "price": base_price,
            "unit_price": unit_price,
            "prime": p.get("prime"),
            "flavor": variant_flavor,
            "size": p.get("size"),
            "variant_dimensions": p.get("variant_dimensions") or {},
            "final_url": p.get("final_url"),
            "original_amazon_link": p.get("original_amazon_link"),
        })

        # ---------- MAIN SELLER (AMAZON / AUTHORIZED) ----------
        if p.get("main_seller"):
            groups[source_url]["main_seller"].append({
                "asin": asin,
                "seller_name": p.get("main_seller"),
                "ships_from": p.get("ships_from"),
                "is_authorized": True,
                "price": amazon_price,
                "unit_price": amazon_unit_price,
                "price_currency": "USD",
                "prime": p.get("prime"),
            })
        elif p.get("sold_by") and is_authorized_seller(p.get("sold_by")):
            # fallback: authorized but not explicitly main_seller
            groups[source_url]["main_seller"].append({
                "asin": asin,
                "seller_name": p.get("sold_by"),
                "ships_from": p.get("ships_from"),
                "is_authorized": True,
                "price": amazon_price,
                "unit_price": amazon_unit_price,
                "price_currency": "USD",
                "prime": p.get("prime"),
            })

        # ---------- OTHER SELLERS (NON-AUTHORIZED ONLY) ----------
        for oseller in p.get("other_sellers", []):
            seller_name = oseller.get("sold_by")

            # skip Amazon / authorized / missing
            if not seller_name or is_authorized_seller(seller_name):
                continue

            s_price = parse_money(oseller.get("price"))
            stars = parse_rating_stars(oseller.get("seller_rating"))
            rcount, pos = parse_rating_meta(oseller.get("seller_rating_count"))

            delta = (s_price - amazon_price) if amazon_price and s_price else None
            pct = (delta / amazon_price * 100) if delta is not None else None

            groups[source_url]["seller_market"].append({
                "asin": asin,
                "seller_name": seller_name,
                "ships_from": oseller.get("ships_from"),
                "is_authorized": False,
                "price": s_price,
                "unit_price": parse_unit_price(oseller.get("price_per_unit")),
                "price_currency": "USD",
                "price_delta_abs": delta,
                "price_delta_percent": pct,
                "price_flag": classify_price_flag(pct),
                "amazon_price_listing": amazon_price,
                "amazon_unit_price": amazon_unit_price,
                "prime": None,
                "rating_stars": stars,
                "rating_count": rcount,
                "positive_rating_percent": pos,
                "rating_flag": classify_rating_flag(pos),
            })

    # ---------- POST-PROCESSING: VARIANTS FIX + DEDUPE ----------
    final_groups = []
    for g in groups.values():
        g["variants"] = fix_variant_names(g["variants"])
        g["main_seller"] = dedupe_sellers(g["main_seller"])
        g["seller_market"] = dedupe_sellers(g["seller_market"])
        final_groups.append(g)

    return final_groups


def main():
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    all_groups = []

    for category in os.listdir(INPUT_ROOT):
        if os.path.isdir(os.path.join(INPUT_ROOT, category)):
            groups = normalize_category(category, INPUT_ROOT)
            if groups:
                with open(os.path.join(OUTPUT_ROOT, f"{category}.json"), "w") as f:
                    json.dump(groups, f, indent=2)
                all_groups.extend(groups)

    with open(COMBINED_OUTPUT_FILE, "w") as f:
        json.dump(all_groups, f, indent=2)

    print("Done ✔ Normalization complete.")


if __name__ == "__main__":
    main()
