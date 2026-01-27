###############################################
# TRU FRU Marketplace Metadata Normalizer
# FIXED: Health score clamping + gouged-only averaging
###############################################
import json
import re
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Tuple


# ---------------------------------------------------------
# CONFIG (TRU FRU)
# ---------------------------------------------------------
INPUT_FILE = "normalized_trufru.json"
OUTPUT_FILE = "normalized_trufru_metadata_summary.json"

PCT_THRESHOLD = 20.0
ABS_THRESHOLD = 2.0
TOP_N = 20

# 🔥 Brand-specific exclusions
EXCLUDED_SELLERS = {
    "amazon",
    "amazon.com",
    "amazonfresh",
    "whole foods market",
    "trufru"
}


# ---------------------------------------------------------
# HELPERS (UNCHANGED)
# ---------------------------------------------------------
def safe_lower(x: Optional[str]) -> str:
    return (x or "").strip().lower()


def to_decimal(x) -> Optional[Decimal]:
    try:
        if x is None:
            return None
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


_pack1 = re.compile(r"pack\s*(?:of)?\s*(\d+)", re.I)
_pack2 = re.compile(r"(\d+)\s*(?:count|ct|pieces|pcs)\b", re.I)


def parse_pack_count(v: dict) -> int:
    if not isinstance(v, dict):
        return 1
    dims = v.get("variant_dimensions") or {}
    for key in ("number_of_items", "count", "items"):
        val = dims.get(key)
        if val:
            cleaned = re.sub(r"\D", "", str(val))
            if cleaned:
                return max(1, int(cleaned))
    for txt in (v.get("size"), v.get("title"), v.get("variant_name")):
        if txt:
            m = _pack1.search(txt) or _pack2.search(txt)
            if m:
                return max(1, int(m.group(1)))
    return 1


def compute_unit_price(price, pack: int) -> Optional[Decimal]:
    p = to_decimal(price)
    if p is None or not pack or pack <= 0:
        return None
    try:
        return (p / Decimal(pack)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
    except Exception:
        return None


def rating_tier(pos) -> Optional[str]:
    try:
        posf = float(pos)
    except Exception:
        return None
    if posf >= 90:
        return "excellent"
    if posf >= 75:
        return "good"
    if posf >= 50:
        return "mixed"
    return "poor"


def choose_amazon_baseline(main_sellers, variant_unit) -> Tuple[Optional[Decimal], str]:
    for m in main_sellers:
        if "amazon" in safe_lower(m.get("seller_name")):
            up = to_decimal(m.get("unit_price"))
            if up and up > 0:
                return up, "amazon_main_unit"
            fallback = compute_unit_price(m.get("price"), parse_pack_count(m))
            if fallback:
                return fallback, "amazon_main_fallback"
    if variant_unit:
        return variant_unit, "variant_unit"
    return None, "none"


# ---------------------------------------------------------
# METADATA NORMALIZER
# ---------------------------------------------------------
def generate_trufru_metadata():
    with open(INPUT_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    total_products = len(data)
    total_skus = 0
    total_listings = 0
    total_gouged = 0
    fair_price_count = 0

    pct_deltas, abs_deltas = [], []
    pct_deltas_gouged_only = []  # 🔧 NEW: Track positive deltas only
    sku_gouged_map = defaultdict(set)
    seller_gouged_count = defaultdict(int)
    seller_pct_records = defaultdict(list)

    unique_sellers = set()
    unique_marketplace_sellers = set()

    price_flag_counter = Counter()
    rating_tier_counter = Counter()
    category_stats = defaultdict(lambda: {"total": 0, "gouged": 0})

    top_gouged_candidates = []

    # ---------------------------------------------------------
    # MAIN LOOP
    # ---------------------------------------------------------
    for item in data:
        category = item.get("category") or "Unknown"
        variants = item.get("variants") or []
        main_sellers = item.get("main_seller") or []
        seller_market = item.get("seller_market") or []

        # Normalize seller names
        for s in main_sellers + seller_market:
            s["seller_name"] = safe_lower(s.get("seller_name"))

        main_by_asin = defaultdict(list)
        for m in main_sellers:
            main_by_asin[m.get("asin")].append(m)

        for v in variants:
            asin = v.get("asin")
            if not asin:
                continue

            total_skus += 1
            pack = parse_pack_count(v)
            variant_unit = compute_unit_price(v.get("price"), pack)
            amazon_unit, amazon_source = choose_amazon_baseline(
                main_by_asin.get(asin, []), variant_unit
            )

            sellers = [
                s for s in seller_market
                if s.get("asin") == asin
            ]

            for s in sellers:
                total_listings += 1
                name = s.get("seller_name")

                unique_sellers.add(name)
                if name not in EXCLUDED_SELLERS:
                    unique_marketplace_sellers.add(name)

                sp = to_decimal(s.get("price"))
                seller_pack = parse_pack_count(s)
                seller_unit = to_decimal(s.get("unit_price")) or compute_unit_price(sp, seller_pack)

                category_stats[category]["total"] += 1

                if not seller_unit or not amazon_unit:
                    continue

                delta_abs = seller_unit - amazon_unit
                delta_pct = (delta_abs / amazon_unit) * 100 if amazon_unit else None

                pct_deltas.append(float(delta_pct))
                abs_deltas.append(float(delta_abs))

                is_gouging = (
                    delta_pct >= PCT_THRESHOLD and
                    delta_abs >= Decimal(str(ABS_THRESHOLD))
                )

                if is_gouging:
                    total_gouged += 1
                    category_stats[category]["gouged"] += 1
                    seller_gouged_count[name] += 1
                    seller_pct_records[name].append(float(delta_pct))
                    sku_gouged_map[asin].add(name)
                    pct_deltas_gouged_only.append(float(delta_pct))  # 🔧 NEW

                    top_gouged_candidates.append({
                        "asin": asin,
                        "product_name": item.get("product_name"),
                        "seller_name": name,
                        "category": category,
                        "amazon_unit": float(amazon_unit),
                        "seller_unit": float(seller_unit),
                        "price_delta_abs": float(delta_abs),
                        "price_delta_pct": float(delta_pct),
                        "amazon_price_source": amazon_source
                    })
                else:
                    fair_price_count += 1

    # ---------------------------------------------------------
    # AGGREGATION
    # ---------------------------------------------------------
    gouging_rate = (total_gouged / total_listings * 100) if total_listings else 0.0
    avg_pct = sum(pct_deltas) / len(pct_deltas) if pct_deltas else 0.0
    avg_abs = sum(abs_deltas) / len(abs_deltas) if abs_deltas else 0.0
    
    # 🔧 NEW: Gouged-only average for health calculation
    avg_pct_gouged_only = (
        sum(pct_deltas_gouged_only) / len(pct_deltas_gouged_only) 
        if pct_deltas_gouged_only else 0.0
    )

    seller_summary = sorted([
        {
            "seller_name": s,
            "gouged_listings": cnt,
            "avg_overprice_pct": sum(seller_pct_records[s]) / len(seller_pct_records[s])
        }
        for s, cnt in seller_gouged_count.items()
    ], key=lambda x: (x["gouged_listings"], x["avg_overprice_pct"]), reverse=True)

    # 🔧 FIX #1 & #2: Use gouged-only average and clamp to 0-100
    health = 100 - (gouging_rate * 0.5) - (avg_pct_gouged_only * 0.4)
    health = max(0.0, min(100.0, round(health, 2)))  # 🔧 MANDATORY CLAMP

    out = {
        "brand": "Tru Fru",
        "total_products": total_products,
        "total_skus": total_skus,
        "total_listings": total_listings,
        "total_gouged_listings": total_gouged,
        "fair_price_listings": fair_price_count,
        "gouging_rate": round(gouging_rate, 2),
        "avg_overprice_pct": round(avg_pct, 2),  # All deltas (can be negative)
        "avg_overprice_pct_gouged_only": round(avg_pct_gouged_only, 2),  # 🔧 NEW metric
        "avg_overprice_abs": round(avg_abs, 2),
        "unique_sellers": sorted(unique_sellers),
        "unique_marketplace_sellers": sorted(unique_marketplace_sellers),
        "seller_gouging_summary": seller_summary,
        "category_gouging_summary": dict(category_stats),
        "top_gouged_skus": sorted(
            top_gouged_candidates, 
            key=lambda x: (x["price_delta_pct"], x["price_delta_abs"]), 
            reverse=True
        )[:TOP_N],
        "marketplace_health_score": health
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    print("✔ Tru Fru metadata generated:", OUTPUT_FILE)


# ---------------------------------------------------------
if __name__ == "__main__":
    generate_trufru_metadata()
