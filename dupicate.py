import json

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
INPUT_FILE = "trufru_norm.json"     # ✅ single JSON file
OUTPUT_FILE = "deduped.json"

# --------------------------------------------------
# DEDUPLICATOR
# --------------------------------------------------
def normalize_json():
    merged = {}
    skipped = 0

    # Load input
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to read {INPUT_FILE}: {e}")

    if not isinstance(items, list):
        raise RuntimeError("Input JSON must be a LIST of objects")

    print(f"\n📦 Total input records: {len(items)}")

    # Deduplicate by ASIN
    for item in items:
        asin = item.get("asin")
        if not asin:
            skipped += 1
            continue

        # RULE:
        # ✔ First ASIN wins
        # ✔ Do NOT override category / data
        if asin not in merged:
            merged[asin] = item

    # Save output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(list(merged.values()), out, indent=2, ensure_ascii=False)

    print("\n🎉 Deduplication complete")
    print("✔ Unique ASINs:", len(merged))
    print("⚠ Skipped records (missing ASIN):", skipped)
    print("📄 Output file:", OUTPUT_FILE)


# --------------------------------------------------
# ENTRY
# --------------------------------------------------
if __name__ == "__main__":
    normalize_json()
