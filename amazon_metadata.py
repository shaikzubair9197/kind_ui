# Part 1: imports, constants, file paths
import json
import re
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

# Files
INPUT_FILE = "normalized_all_products.json"
OUTPUT_FILE = "normalized_metadata_summary.json"

# Configurable thresholds (industry-aligned defaults)
PCT_THRESHOLD = 20.0        # mark as gouging only if >= 20% markup
ABS_THRESHOLD = 2.0         # and absolute difference >= $2 (adjust to your currency/market)
TOP_N = 20

EXCLUDED_SELLERS = {
    "amazon.com", "amazon", "kind", "kind snacks", "kindsnacks"
}
# Part 2: helper functions
def safe_lower(x: Optional[str]) -> str:
    return (x or "").strip().lower()

def to_decimal(x: Any) -> Optional[Decimal]:
    """Safe Decimal conversion; returns None on failure."""
    try:
        if x is None:
            return None
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None

_pack_count_re1 = re.compile(r"pack\s*(?:of)?\s*(\d+)", flags=re.I)
_pack_count_re2 = re.compile(r"(\d+)\s*(?:count|ct|pieces|pcs)\b", flags=re.I)

def parse_pack_count(v: Dict[str, Any]) -> int:
    """
    Infer number_of_items / pack count from variant or seller fields.
    Return integer >=1 (defaults to 1).
    """
    if not isinstance(v, dict):
        return 1

    # 1) direct fields inside variant_dimensions
    dims = v.get("variant_dimensions") or {}
    for k in ("number_of_items", "number_of_items_string", "count", "items"):
        val = dims.get(k)
        if val:
            try:
                return max(1, int(re.sub(r"\D", "", str(val)) or 1))
            except Exception:
                pass

    # 2) attempt to find "Pack of X" or "(Pack of X)" in size/title/variant_name
    for text in (v.get("size") or "", v.get("title") or "", v.get("variant_name") or ""):
        if not text:
            continue
        m = _pack_count_re1.search(text)
        if m:
            try:
                return max(1, int(m.group(1)))
            except Exception:
                pass
        m2 = _pack_count_re2.search(text)
        if m2:
            try:
                return max(1, int(m2.group(1)))
            except Exception:
                pass

    # fallback
    return 1

def classify_rating_tier(pos: Optional[float]) -> Optional[str]:
    try:
        if pos is None:
            return None
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

def compute_unit_price_from_price(price: Any, pack_count: int) -> Optional[Decimal]:
    """Return unit price (Decimal) or None"""
    p = to_decimal(price)
    if p is None:
        return None
    try:
        return (p / Decimal(pack_count)).quantize(Decimal("0.0001"))
    except Exception:
        return None

def choose_amazon_baseline_for_asin(main_sellers_for_asin: List[Dict[str,Any]], variant_unit_price: Optional[Decimal]) -> Tuple[Optional[Decimal], str]:
    """
    Returns (amazon_unit_price, amazon_price_source).
    Priority:
      1) main seller named 'amazon'
      2) first main_seller
      3) variant_unit_price
    """
    for m in main_sellers_for_asin:
        name = (m.get("seller_name") or "").lower()
        if "amazon" in name:
            up = compute_unit_price_from_price(m.get("price"), parse_pack_count(m))
            if up is not None:
                return up, "main_seller_amazon"
            dp = to_decimal(m.get("price"))
            if dp is not None:
                return dp, "main_seller_amazon_raw"

    if main_sellers_for_asin:
        m = main_sellers_for_asin[0]
        up = compute_unit_price_from_price(m.get("price"), parse_pack_count(m))
        if up is not None:
            return up, "main_seller_first"
        dp = to_decimal(m.get("price"))
        if dp is not None:
            return dp, "main_seller_first_raw"

    if variant_unit_price is not None:
        return variant_unit_price, "variant_unit_price"

    return None, "none"
# Part 3: core scanning & per-variant logic
def generate_summary() -> None:
    # Load data
    with open(INPUT_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    total_products = len(data)
    total_categories = len({p.get("category") for p in data})

    # Counters / collectors (original ones you had)
    total_skus = 0
    products_per_category = defaultdict(int)
    skus_per_category = defaultdict(int)
    marketplace_skus_per_category = defaultdict(int)

    unique_sellers = set()
    unique_sellers_excl_main = set()

    seller_sku_impact = defaultdict(set)
    price_flag_counter = Counter()
    rating_tier_counter = Counter()

    top_gouged_candidates: List[Dict[str, Any]] = []
    product_variant_summary: List[Dict[str, Any]] = []

    # marketplace asins tracker
    marketplace_asins_seen = defaultdict(set)

    # We'll also collect listing-level info for KPI aggregation efficiently
    # These structures are for the add-on KPI block but we populate them inline for efficiency
    total_listings = 0
    total_gouged_listings = 0
    fair_price_count = 0

    all_pct_deltas: List[float] = []
    all_abs_deltas: List[float] = []
    seller_gouged_count = defaultdict(int)
    seller_gouged_pct_list = defaultdict(list)
    sku_gouged_map = defaultdict(set)
    category_gouge_stats = defaultdict(lambda: {"total": 0, "gouged": 0, "pct_list": [], "abs_list": []})
    unique_sellers_seen_for_kpi = set()

    # main loop: process each product (family)
    for item in data:
        category = item.get("category") or "Unknown"
        variants = item.get("variants", []) or []
        variant_count = len(variants)

        total_skus += variant_count
        products_per_category[category] += 1
        skus_per_category[category] += variant_count

        seller_market = item.get("seller_market", []) or []
        main_sellers = item.get("main_seller", []) or []

        # product-level summary
        product_variant_summary.append({
            "product_name": item.get("product_name"),
            "category": category,
            "variant_count": variant_count,
            "unique_sellers_in_product": sorted({(s.get("seller_name") or "").strip() for s in seller_market})
        })

        # index main sellers by asin for quick lookup
        main_by_asin = defaultdict(list)
        for m in main_sellers:
            main_by_asin[m.get("asin")].append(m)

        for v in variants:
            asin = v.get("asin")
            if not asin:
                continue
            title = v.get("title") or v.get("variant_name") or asin
            pack_count = parse_pack_count(v)

            variant_unit_price = compute_unit_price_from_price(v.get("price"), pack_count)

            sellers = [s for s in (seller_market or []) if s.get("asin") == asin]
            main_s = main_by_asin.get(asin, [])

            # marketplace SKUs per category - unique ASINs that have sellers
            if sellers and asin not in marketplace_asins_seen[category]:
                marketplace_asins_seen[category].add(asin)
                marketplace_skus_per_category[category] += 1

            # choose amazon baseline for ASIN
            amazon_unit_price, amazon_price_source = choose_amazon_baseline_for_asin(main_s, variant_unit_price)

            # process each seller entry (main + marketplace)
            for s in (main_s + sellers):
                name = (s.get("seller_name") or "").strip()
                if not name:
                    continue

                # basic sets / counters
                unique_sellers.add(name)
                unique_sellers_seen_for_kpi.add(name)
                if safe_lower(name) not in EXCLUDED_SELLERS:
                    unique_sellers_excl_main.add(name)

                seller_sku_impact[name].add(asin)

                pf = s.get("price_flag")
                if pf:
                    price_flag_counter[pf] += 1

                pos = s.get("positive_rating_percent")
                tier = classify_rating_tier(pos)
                if tier:
                    rating_tier_counter[tier] += 1

                # determine seller pack/unit price
                seller_pack_count = parse_pack_count(s if isinstance(s, dict) else {})
                su = to_decimal(s.get("unit_price"))
                seller_unit_price: Optional[Decimal] = None
                if su is not None and su > 0:
                    sp = to_decimal(s.get("price"))
                    if sp is not None and su * Decimal(seller_pack_count) < sp * Decimal("0.5"):
                        seller_unit_price = compute_unit_price_from_price(sp, seller_pack_count)
                    else:
                        seller_unit_price = su
                else:
                    seller_unit_price = compute_unit_price_from_price(s.get("price"), seller_pack_count)

                # if we can't compute seller or amazon unit price, skip delta logic (but still counted above)
                if seller_unit_price is None or amazon_unit_price is None:
                    # count listing-level for category (we'll still count this listing even if delta can't be computed)
                    category_gouge_stats[category]["total"] += 1
                    # Also count as a listing for KPI total_listings only if this is a seller entry
                    total_listings += 1
                    # price_flag fair?
                    if (pf or "").strip().lower() == "fair price":
                        fair_price_count += 1
                    continue

                # compute deltas (unit price)
                price_delta_abs = (seller_unit_price - amazon_unit_price)
                price_delta_pct = None
                try:
                    price_delta_pct = (price_delta_abs / amazon_unit_price) * Decimal(100)
                except Exception:
                    price_delta_pct = None

                abs_float = float(price_delta_abs) if price_delta_abs is not None else None
                pct_float = float(price_delta_pct) if price_delta_pct is not None else None

                # realistic gouging rule: both percent and absolute thresholds must be met
                is_gouging = False
                if pct_float is not None and abs_float is not None:
                    if pct_float >= float(PCT_THRESHOLD) and abs_float >= float(ABS_THRESHOLD):
                        is_gouging = True

                upstream_flag = (s.get("price_flag") or "").strip().lower()
                if upstream_flag == "price gouging":
                    is_gouging = True

                # append to top_gouged_candidates if detected (preserve original shape plus more fields)
                if is_gouging or upstream_flag == "price gouging":
                    top_gouged_candidates.append({
                        "asin": asin,
                        "product_name": item.get("product_name"),
                        "title": title,
                        "category": category,
                        "seller_name": name,
                        "amazon_price_unit": float(amazon_unit_price) if amazon_unit_price is not None else None,
                        "seller_price_unit": float(seller_unit_price) if seller_unit_price is not None else None,
                        "amazon_price_source": amazon_price_source,
                        "amazon_price_listing": float(v.get("price")) if v.get("price") is not None else None,
                        "seller_price_listing": float(s.get("price")) if s.get("price") is not None else None,
                        "price_delta_abs": abs_float,
                        "price_delta_percent": pct_float,
                        "detected_as_gouging": is_gouging,
                        "upstream_price_flag": s.get("price_flag")
                    })

                # --- populate KPI accumulators (every listing) ---
                total_listings += 1
                category_gouge_stats[category]["total"] += 1

                if (pf or "").strip().lower() == "fair price":
                    fair_price_count += 1

                if pct_float is not None:
                    all_pct_deltas.append(pct_float)
                    category_gouge_stats[category]["pct_list"].append(pct_float)
                    seller_gouged_pct_list[name].append(pct_float)

                if abs_float is not None:
                    all_abs_deltas.append(abs_float)
                    category_gouge_stats[category]["abs_list"].append(abs_float)

                if is_gouging:
                    total_gouged_listings += 1
                    category_gouge_stats[category]["gouged"] += 1
                    seller_gouged_count[name] += 1
                    sku_gouged_map[asin].add(name)

    # END main loop
# Part 4: KPI aggregation & final transforms

    # SKUs impacted
    skus_impacted = len([asin for asin, sellers in sku_gouged_map.items() if sellers])
    skus_impact_rate = (skus_impacted / total_skus * 100) if total_skus else 0.0

    # Global averages & max
    avg_overprice_pct = (sum(all_pct_deltas) / len(all_pct_deltas)) if all_pct_deltas else 0.0
    avg_overprice_abs = (sum(all_abs_deltas) / len(all_abs_deltas)) if all_abs_deltas else 0.0
    max_overprice_pct = max(all_pct_deltas) if all_pct_deltas else 0.0

    gouging_rate = (total_gouged_listings / total_listings * 100) if total_listings else 0.0

    # Seller summary (top violators)
    seller_summary_rows = []
    for seller, gcount in seller_gouged_count.items():
        avg_pct = (sum(seller_gouged_pct_list[seller]) / len(seller_gouged_pct_list[seller])) if seller_gouged_pct_list[seller] else 0.0
        seller_summary_rows.append({
            "seller_name": seller,
            "gouged_listings": gcount,
            "avg_overprice_pct": avg_pct
        })

    seller_summary_sorted = sorted(seller_summary_rows, key=lambda x: (x["gouged_listings"], x["avg_overprice_pct"]), reverse=True)

    # Category summary
    category_rows = []
    for cat, stats in category_gouge_stats.items():
        total = stats.get("total", 0)
        gouged = stats.get("gouged", 0)
        avg_pct = (sum(stats["pct_list"]) / len(stats["pct_list"])) if stats["pct_list"] else 0.0
        avg_abs = (sum(stats["abs_list"]) / len(stats["abs_list"])) if stats["abs_list"] else 0.0

        category_rows.append({
            "category": cat,
            "total_listings": total,
            "gouged_listings": gouged,
            "gouging_rate": (gouged / total * 100) if total else 0.0,
            "avg_overprice_pct": avg_pct,
            "avg_overprice_abs": avg_abs
        })

    category_rows_sorted = sorted(category_rows, key=lambda x: x["gouging_rate"], reverse=True)

    # proportion of sellers with bad ratings (simple heuristic)
    bad_seller_count = 0
    total_sellers_with_ratings = 0
    seen_sellers_for_ratings = set()
    for item in data:
        # check seller_market entries for rating
        for s in (item.get("seller_market") or []):
            name = s.get("seller_name")
            if not name or name in seen_sellers_for_ratings:
                continue
            seen_sellers_for_ratings.add(name)
            pr = s.get("positive_rating_percent")
            if pr is not None:
                total_sellers_with_ratings += 1
                try:
                    if float(pr) < 50:
                        bad_seller_count += 1
                except Exception:
                    pass

    prop_bad_sellers = (bad_seller_count / total_sellers_with_ratings * 100) if total_sellers_with_ratings else 0.0

    # Marketplace Health Score (weighted heuristic)
    # Score = 100 - (gouging_rate * 0.5) - (avg_overprice_pct * 0.4) - (prop_bad_sellers * 0.1)
    # clamp 0-100
    health_score = 100.0 - (gouging_rate * 0.5) - (avg_overprice_pct * 0.4) - (prop_bad_sellers * 0.1)
    health_score = max(0.0, min(100.0, round(health_score, 2)))
# Part 5: write output & runner (append to generate_summary function scope)
    # Original outputs + new KPI fields
    seller_impact_sorted = {
        k: len(v)
        for k, v in sorted(seller_sku_impact.items(), key=lambda x: len(x[1]), reverse=True)
    }

    top_gouged_sorted = sorted(
        top_gouged_candidates,
        key=lambda x: (x.get("price_delta_percent") or -999),
        reverse=True
    )[:TOP_N]

    out = {
        "total_products": total_products,
        "total_categories": total_categories,
        "total_skus": total_skus,

        "products_per_category": dict(products_per_category),
        "skus_per_category": dict(skus_per_category),
        "marketplace_skus_per_category": dict(marketplace_skus_per_category),

        "total_unique_sellers": len(unique_sellers),
        "unique_sellers": sorted(unique_sellers),

        "unique_sellers_excluding_amazon_and_kind": sorted(unique_sellers_excl_main),
        "total_unique_sellers_excluding_amazon_and_kind": len(unique_sellers_excl_main),

        "seller_sku_impact": seller_impact_sorted,

        "price_flag_summary": dict(price_flag_counter),
        "rating_tiers_summary": dict(rating_tier_counter),

        # note: top_gouged_skus entries now include unit price fields and a boolean detected_as_gouging
        "top_gouged_skus": top_gouged_sorted,

        "product_variant_summary": product_variant_summary,

        # --- NEW KPI FIELDS ---
        "total_listings": total_listings,
        "total_gouged_listings": total_gouged_listings,
        "fair_price_listings": fair_price_count,

        "avg_overprice_pct": avg_overprice_pct,
        "avg_overprice_abs": avg_overprice_abs,
        "max_overprice_pct": max_overprice_pct,
        "gouging_rate": gouging_rate,

        "sku_gouged_map": {asin: sorted(list(sellers)) for asin, sellers in sku_gouged_map.items()},
        "skus_impacted": skus_impacted,
        "skus_impact_rate": skus_impact_rate,

        "category_gouging_summary": category_rows_sorted,
        "seller_gouging_summary": seller_summary_sorted,

        "prop_bad_sellers": prop_bad_sellers,
        "marketplace_health_score": health_score
    }

    # Write output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=4)

    print("✔ Metadata generated:", OUTPUT_FILE)
    print("✔ Total products:", total_products)
    print("✔ Total SKUs:", total_skus)

# End of generate_summary function

if __name__ == "__main__":
    generate_summary()
