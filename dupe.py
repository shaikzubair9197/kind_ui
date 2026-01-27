import json
from typing import Any, Dict, List

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
INPUT_FILE = "trufru_norm.json"
OUTPUT_FILE = "deduped.json"
DUPES_LOG_FILE = "duplicates_log.json"
MISSING_ASIN_LOG_FILE = "missing_asin_log.json"

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def item_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    """Readable summary for logs (not full payload)."""
    return {
        "asin": item.get("asin"),
        "title": item.get("title"),
        "category": item.get("category"),
        "url": item.get("final_url") or item.get("product_url"),
        "brand": item.get("brand"),
        "source": item.get("source"),
        "price": item.get("price"),
    }

# --------------------------------------------------
# DEDUPLICATOR
# --------------------------------------------------
def normalize_json():
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to read {INPUT_FILE}: {e}")

    if not isinstance(items, list):
        raise RuntimeError("Input JSON must be a LIST of objects")

    merged: Dict[str, Dict[str, Any]] = {}
    first_index: Dict[str, int] = {}

    duplicates_log: List[Dict[str, Any]] = []
    missing_asin_log: List[Dict[str, Any]] = []

    print(f"\n📦 Total input records: {len(items)}")

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        asin = item.get("asin")
        if not asin:
            missing_asin_log.append({
                "index": idx,
                "item_summary": item_summary(item),
                "raw_item": item,
            })
            continue

        # First ASIN wins
        if asin not in merged:
            merged[asin] = item
            first_index[asin] = idx
        else:
            duplicates_log.append({
                "asin": asin,
                "kept_index": first_index[asin],
                "dupe_index": idx,
                "kept_summary": item_summary(merged[asin]),
                "dupe_summary": item_summary(item),
                "kept_raw": merged[asin],
                "dupe_raw": item,
            })

    # --------------------------------------------------
    # WRITE OUTPUTS
    # --------------------------------------------------
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(list(merged.values()), out, indent=2, ensure_ascii=False)

    with open(DUPES_LOG_FILE, "w", encoding="utf-8") as out:
        json.dump(duplicates_log, out, indent=2, ensure_ascii=False)

    with open(MISSING_ASIN_LOG_FILE, "w", encoding="utf-8") as out:
        json.dump(missing_asin_log, out, indent=2, ensure_ascii=False)

    print("\n🎉 Deduplication complete")
    print("✔ Unique ASINs:", len(merged))
    print("⚠ Duplicates logged:", len(duplicates_log), "→", DUPES_LOG_FILE)
    print("⚠ Missing ASIN logged:", len(missing_asin_log), "→", MISSING_ASIN_LOG_FILE)
    print("📄 Output file:", OUTPUT_FILE)


# --------------------------------------------------
# ENTRY
# --------------------------------------------------
if __name__ == "__main__":
    normalize_json()
