import os
import json

BASE_DIR = "kind_results"
OUTPUT_FILE = "all_products_merged.json"


def normalize_json():
    merged = {}
    category_order = []

    # Collect categories and ensure All_Snacks comes LAST
    for c in os.listdir(BASE_DIR):
        if not os.path.isdir(os.path.join(BASE_DIR, c)):
            continue
        if c == "All_Snacks":
            continue
        category_order.append(c)

    if "All_Snacks" in os.listdir(BASE_DIR):
        category_order.append("All_Snacks")

    print("\nProcessing categories in order:")
    print(category_order)

    for category in category_order:
        category_dir = os.path.join(BASE_DIR, category)
        if not os.path.isdir(category_dir):
            continue

        print(f"\nProcessing category: {category}")

        # 🔹 Read ALL json files inside category folder
        for fname in os.listdir(category_dir):
            if not fname.lower().endswith(".json"):
                continue

            fpath = os.path.join(category_dir, fname)
            print(f"  → Loading {fname}")

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Handle list or single object
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = [data]
                else:
                    continue

            except Exception as e:
                print(f"  ⚠ Skipping {fname}: {e}")
                continue

            for item in items:
                asin = item.get("asin")
                if not asin:
                    continue

                # Tag category
                item["category"] = category

                # RULE:
                # ✔ Keep first occurrence (real category wins)
                if asin not in merged:
                    merged[asin] = item

    # Save merged unique items
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(list(merged.values()), out, indent=2, ensure_ascii=False)

    print("\n🎉 Finished Normalizing!")
    print("Unique ASINs:", len(merged))
    print("Output:", OUTPUT_FILE)


if __name__ == "__main__":
    normalize_json()
