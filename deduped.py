import json

INPUT_FILE = "all_products_normalized(28-01-26).json"
OUTPUT_FILE = "all_products_normalized_deduped.json"


def dedupe_by_asin():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        groups = json.load(f)

    # 🔹 Split groups so All_Snacks is processed LAST
    non_all_snacks = []
    all_snacks = []

    for g in groups:
        if g.get("category") == "All_Snacks":
            all_snacks.append(g)
        else:
            non_all_snacks.append(g)

    ordered_groups = non_all_snacks + all_snacks

    seen_asins = set()
    deduped_groups = []

    for group in ordered_groups:
        variants = group.get("variants", [])
        seller_market = group.get("seller_market", [])

        kept_variants = []
        kept_asins = set()

        # --- Deduplicate variants by ASIN ---
        for v in variants:
            asin = v.get("asin")
            if not asin:
                continue

            if asin not in seen_asins:
                seen_asins.add(asin)
                kept_asins.add(asin)
                kept_variants.append(v)

        # --- Filter seller_market to only kept ASINs ---
        kept_sellers = [
            s for s in seller_market
            if s.get("asin") in kept_asins
        ]

        # Keep group only if at least one variant survives
        if kept_variants:
            group["variants"] = kept_variants
            group["seller_market"] = kept_sellers
            deduped_groups.append(group)

    # Write output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(deduped_groups, out, indent=2, ensure_ascii=False)

    print("✅ Deduplication complete")
    print("Unique ASINs:", len(seen_asins))
    print("Output file:", OUTPUT_FILE)


if __name__ == "__main__":
    dedupe_by_asin()
