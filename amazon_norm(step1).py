import os
import json

BASE_DIR = "kind_results"
OUTPUT_FILE = "all_products_merged.json"


def normalize_json():
    merged = {}

    # Traverse each category folder
    for category in os.listdir(BASE_DIR):
        path = os.path.join(BASE_DIR, category, "results.json")
        if not os.path.exists(path):
            continue

        print(f"Processing: {path}")

        with open(path, "r", encoding="utf-8") as f:
            variants = json.load(f)

        for item in variants:
            asin = item.get("asin")
            if not asin:
                continue

            # Add category to the item
            item["category"] = category

            # Only store first entry of this ASIN
            if asin not in merged:
                merged[asin] = item

    # Save merged JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(list(merged.values()), out, indent=2, ensure_ascii=False)

    print("\n🎉 Finished Normalizing with Category!")
    print("Unique ASINs:", len(merged))
    print("Output:", OUTPUT_FILE)


if __name__ == "__main__":
    normalize_json()
