###############################################
# KIND Marketplace Normalizer (Fixed & Improved)
###############################################
import json
import re
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
INPUT_FILE = "normalized_all_products.json"
OUTPUT_FILE = "normalized_metadata_summary.json"

PCT_THRESHOLD = 20.0
ABS_THRESHOLD = 2.0
TOP_N = 20

EXCLUDED_SELLERS = {
    "amazon", "amazon.com", "kind", "kindsnacks", "kind snacks"
}

# ---------------------------------------------------------
# HELPERS
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
    for key in ("number_of_items", "number_of_items_string", "count", "items"):
        val = dims.get(key)
        if val:
            cleaned = re.sub(r"\D", "", str(val))
            if cleaned:
                return max(1, int(cleaned))
    for txt in (v.get("size"), v.get("title"), v.get("variant_name"), v.get("seller_name")):
        if not txt:
            continue
        m = _pack1.search(txt) or _pack2.search(txt)
        if m:
            return max(1, int(m.group(1)))
    return 1

def compute_unit_price(price, pack: int) -> Optional[Decimal]:
    p = to_decimal(price)
    if p is None:
        return None
    if not isinstance(pack, int) or pack <= 0:
        return None
    try:
        return (p / Decimal(pack)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
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

def choose_amazon_baseline(main_sellers: List[dict], variant_unit: Optional[Decimal]) -> Tuple[Optional[Decimal], str]:
    for m in main_sellers:
        if "amazon" in safe_lower(m.get("seller_name")):
            up_decl = to_decimal(m.get("unit_price"))
            if up_decl is not None and up_decl > 0:
                return up_decl, "main_seller_amazon"
            up = compute_unit_price(m.get("price"), parse_pack_count(m))
            if up is not None:
                return up, "main_seller_amazon"
            dp = to_decimal(m.get("price"))
            if dp is not None:
                return dp, "main_seller_amazon_raw"

    if main_sellers:
        m = main_sellers[0]
        up_decl = to_decimal(m.get("unit_price"))
        if up_decl is not None and up_decl > 0:
            return up_decl, "main_seller_first_unit"
        up = compute_unit_price(m.get("price"), parse_pack_count(m))
        if up is not None:
            return up, "main_seller_first"
        dp = to_decimal(m.get("price"))
        if dp is not None:
            return dp, "main_seller_first_raw"

    if variant_unit is not None:
        return variant_unit, "variant_unit_price"

    return None, "none"

# ---------------------------------------------------------
# MAIN NORMALIZER
# ---------------------------------------------------------
def generate_summary():
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        print("Error reading input file:", e)
        data = []

    total_products = len(data)
    categories = {p.get("category") for p in data if p.get("category")}
    total_categories = len(categories)

    total_skus = 0
    products_per_category = defaultdict(int)
    skus_per_category = defaultdict(int)
    marketplace_skus_per_category = defaultdict(int)

    unique_sellers = set()
    unique_marketplace_sellers = set()

    seller_sku_impact = defaultdict(set)
    price_flag_counter = Counter()
    rating_tier_counter = Counter()

    top_gouged_candidates = []
    product_variant_summary = []
    marketplace_seen = defaultdict(set)

    total_listings = 0
    total_gouged_listings = 0
    fair_price_count = 0

    pct_deltas = []
    abs_deltas = []
    seller_gouged_count = defaultdict(int)
    seller_pct_records = defaultdict(list)
    sku_gouged_map = defaultdict(set)
    category_stats = defaultdict(lambda: {"total": 0, "gouged": 0, "pct_list": [], "abs_list": []})
    category_marketplace_stats = defaultdict(lambda: {"total": 0, "gouged": 0, "pct_list": [], "abs_list": []})

    # ---------------------------------------------------------
    # MAIN LOOP
    # ---------------------------------------------------------
    for item in data:
        category = item.get("category") or "Unknown"
        variants = item.get("variants") or []
        seller_market = item.get("seller_market") or []
        main_sellers = item.get("main_seller") or []

        # 🔥 NORMALIZE MAIN SELLER NAMES
        for ms in main_sellers:
            ms["seller_name"] = safe_lower(ms.get("seller_name"))

        # 🔥 NORMALIZE MARKETPLACE SELLER NAMES
        for sm in seller_market:
            sm["seller_name"] = safe_lower(sm.get("seller_name"))

        total_skus += len(variants)
        products_per_category[category] += 1
        skus_per_category[category] += len(variants)

        product_variant_summary.append({
            "product_name": item.get("product_name"),
            "category": category,
            "variant_count": len(variants),
            "unique_sellers_in_product": sorted({safe_lower(s.get("seller_name")) for s in seller_market if s.get("seller_name")})
        })

        main_by_asin = defaultdict(list)
        for m in main_sellers:
            main_by_asin[m.get("asin")].append(m)

        for v in variants:
            asin = v.get("asin")
            if not asin:
                continue

            pack = parse_pack_count(v)
            variant_unit = compute_unit_price(v.get("price"), pack)

            sellers = [s for s in seller_market if s.get("asin") == asin]

            if sellers and asin not in marketplace_seen[category]:
                marketplace_skus_per_category[category] += 1
                marketplace_seen[category].add(asin)

            main_for_asin = main_by_asin.get(asin, [])
            amazon_unit, amazon_source = choose_amazon_baseline(main_for_asin, variant_unit)

            combined = main_for_asin + sellers
            seen_seller_keys = set()
            deduped_offers = []
            for s in combined:
                seller_canon = safe_lower(s.get("seller_name"))
                seller_id = s.get("seller_id") or s.get("seller_sku") or ""
                key = (seller_canon, str(seller_id))
                if key in seen_seller_keys:
                    continue
                seen_seller_keys.add(key)
                deduped_offers.append(s)

            for s in deduped_offers:
                total_listings += 1

                name = safe_lower(s.get("seller_name"))
                if not name:
                    continue

                unique_sellers.add(name)
                if name not in EXCLUDED_SELLERS:
                    unique_marketplace_sellers.add(name)

                seller_sku_impact[name].add(asin)

                pf_raw = s.get("price_flag")
                pf = safe_lower(pf_raw)

                if pf:
                    price_flag_counter[pf] += 1

                tier = rating_tier(s.get("positive_rating_percent"))
                if tier:
                    rating_tier_counter[tier] += 1

                sp = to_decimal(s.get("price"))
                seller_pack = parse_pack_count(s)
                up_declared = to_decimal(s.get("unit_price"))
                seller_unit = up_declared if (up_declared and up_declared > 0) else compute_unit_price(sp, seller_pack)

                category_stats[category]["total"] += 1
                if name not in EXCLUDED_SELLERS:
                    category_marketplace_stats[category]["total"] += 1

                if seller_unit is None or amazon_unit is None:
                    if pf == "fair price":
                        fair_price_count += 1
                    continue

                try:
                    delta_abs_dec = (seller_unit - amazon_unit)
                except Exception:
                    delta_abs_dec = None

                try:
                    delta_pct_dec = (delta_abs_dec / amazon_unit * Decimal("100")) if (delta_abs_dec is not None and amazon_unit != 0) else None
                except Exception:
                    delta_pct_dec = None

                if delta_abs_dec is not None:
                    delta_abs = float(delta_abs_dec)
                    abs_deltas.append(delta_abs)
                    category_stats[category]["abs_list"].append(delta_abs)
                    if name not in EXCLUDED_SELLERS:
                        category_marketplace_stats[category]["abs_list"].append(delta_abs)
                else:
                    delta_abs = None

                if delta_pct_dec is not None:
                    delta_pct = float(delta_pct_dec)
                    pct_deltas.append(delta_pct)
                    category_stats[category]["pct_list"].append(delta_pct)
                    if name not in EXCLUDED_SELLERS:
                        category_marketplace_stats[category]["pct_list"].append(delta_pct)
                else:
                    delta_pct = None

                is_gouging = False
                if (delta_pct is not None and delta_abs is not None):
                    if delta_pct >= PCT_THRESHOLD and delta_abs >= ABS_THRESHOLD:
                        is_gouging = True

                if pf == "price gouging":
                    is_gouging = True
                if pf == "fair price":
                    is_gouging = False
                    fair_price_count += 1

                if is_gouging:
                    total_gouged_listings += 1
                    category_stats[category]["gouged"] += 1
                    if name not in EXCLUDED_SELLERS:
                        category_marketplace_stats[category]["gouged"] += 1

                    seller_gouged_count[name] += 1
                    if delta_pct is not None:
                        seller_pct_records[name].append(delta_pct)
                    sku_gouged_map[asin].add(name)

                    top_gouged_candidates.append({
                        "asin": asin,
                        "product_name": item.get("product_name"),
                        "seller_name": s.get("seller_name"),
                        "category": category,
                        "amazon_unit": float(amazon_unit) if amazon_unit is not None else None,
                        "seller_unit": float(seller_unit) if seller_unit is not None else None,
                        "price_delta_abs": delta_abs,
                        "price_delta_pct": delta_pct,
                        "amazon_price_source": amazon_source,
                        "seller_price_listing": float(s.get("price")) if s.get("price") is not None else None,
                        "upstream_price_flag": pf_raw
                    })
                else:
                    if (delta_pct is not None and delta_abs is not None) and (delta_pct < PCT_THRESHOLD and delta_abs < ABS_THRESHOLD):
                        fair_price_count += 1

    # ---------------------------------------------------------
    # KPI AGGREGATION
    # ---------------------------------------------------------
    skus_impacted = sum(1 for a, ss in sku_gouged_map.items() if ss)
    avg_pct = (sum(pct_deltas) / len(pct_deltas)) if pct_deltas else 0.0
    avg_abs = (sum(abs_deltas) / len(abs_deltas)) if abs_deltas else 0.0
    max_pct = max(pct_deltas) if pct_deltas else 0.0
    max_abs = max(abs_deltas) if abs_deltas else 0.0

    gouging_rate = (total_gouged_listings / total_listings * 100) if total_listings else 0.0
    impact_rate = (skus_impacted / total_skus * 100) if total_skus else 0.0

    seller_rows = []
    for seller, cnt in seller_gouged_count.items():
        avg_seller_pct = (sum(seller_pct_records[seller]) / len(seller_pct_records[seller])) if seller_pct_records[seller] else 0.0
        seller_rows.append({
            "seller_name": seller,
            "gouged_listings": cnt,
            "avg_overprice_pct": avg_seller_pct
        })
    seller_summary_sorted = sorted(seller_rows, key=lambda x: (x["gouged_listings"], x["avg_overprice_pct"]), reverse=True)

    category_rows = []
    for cat, st in category_stats.items():
        total = st.get("total", 0)
        gouged = st.get("gouged", 0)
        avgp = (sum(st.get("pct_list", [])) / len(st.get("pct_list", []))) if st.get("pct_list") else 0.0
        avga = (sum(st.get("abs_list", [])) / len(st.get("abs_list", []))) if st.get("abs_list") else 0.0
        category_rows.append({
            "category": cat,
            "total_listings": total,
            "gouged_listings": gouged,
            "gouging_rate": (gouged / total * 100) if total else 0.0,
            "avg_overprice_pct": avgp,
            "avg_overprice_abs": avga
        })
    category_rows_sorted = sorted(category_rows, key=lambda x: x["gouging_rate"], reverse=True)

    bad_sellers = rating_tier_counter.get("poor", 0)
    total_rated = sum(rating_tier_counter.values())
    prop_bad = (bad_sellers / total_rated * 100) if total_rated else 0.0

    health = 100.0 - (gouging_rate * 0.5) - (avg_pct * 0.4) - (prop_bad * 0.1)
    health = max(0.0, min(100.0, round(health, 2)))

    unique_top = {}
    for t in top_gouged_candidates:
        key = (t.get("asin"), safe_lower(t.get("seller_name")))
        existing = unique_top.get(key)
        if existing is None or (t.get("price_delta_pct") or 0) > (existing.get("price_delta_pct") or 0):
            unique_top[key] = t
    sorted_top = sorted(unique_top.values(), key=lambda x: (x.get("price_delta_pct") or -999), reverse=True)[:TOP_N]

    out = {
        "total_products": total_products,
        "total_categories": total_categories,
        "total_skus": total_skus,
        "products_per_category": dict(products_per_category),
        "skus_per_category": dict(skus_per_category),
        "marketplace_skus_per_category": dict(marketplace_skus_per_category),
        "total_unique_sellers": len(unique_sellers),
        "unique_sellers": sorted(unique_sellers),
        "unique_sellers_excluding_amazon_and_kind": sorted(unique_marketplace_sellers),
        "total_unique_sellers_excluding_amazon_and_kind": len(unique_marketplace_sellers),
        "seller_sku_impact": {k: len(v) for k, v in seller_sku_impact.items()},
        "price_flag_summary": dict(price_flag_counter),
        "rating_tiers_summary": dict(rating_tier_counter),
        "top_gouged_skus": sorted_top,
        "product_variant_summary": product_variant_summary,
        "total_listings": total_listings,
        "total_gouged_listings": total_gouged_listings,
        "fair_price_listings": fair_price_count,
        "avg_overprice_pct": avg_pct,
        "avg_overprice_abs": avg_abs,
        "max_overprice_pct": max_pct,
        "max_overprice_abs": max_abs,
        "gouging_rate": gouging_rate,
        "sku_gouged_map": {asin: sorted(list(sellers)) for asin, sellers in sku_gouged_map.items()},
        "skus_impacted": skus_impacted,
        "skus_impact_rate": impact_rate,
        "category_gouging_summary": category_rows_sorted,
        "seller_gouging_summary": seller_summary_sorted,
        "prop_bad_sellers": prop_bad,
        "marketplace_health_score": health,
        "_internal_debug": {
            "pct_sample_count": len(pct_deltas),
            "abs_sample_count": len(abs_deltas),
        }
    }

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=4)
        print("✔ Metadata generated successfully:", OUTPUT_FILE)
        print("✔ Total products:", total_products)
        print("✔ Total SKUs:", total_skus)
    except Exception as e:
        print("Error writing output:", e)



if __name__ == "__main__":
    generate_summary()
