import os
import json

# -----------------------------
# CONFIG
# -----------------------------
BASE_DIR = "products_kind"
OUTPUT_FILE = "kind_products_metadata1.json"


def generate_metadata():
    output = {
        "total_categories": 0,

        # 👇 GLOBAL (DEDUPED BY product_url)
        "total_products": 0,
        "products_available_on_amazon": 0,
        "products_missing_on_amazon": 0,
        "availability_percent_overall": 0,

        # 👇 CATEGORY-LEVEL (NOT DEDUPED)
        "category_breakdown": []
    }

    # -----------------------------
    # DEDUP TRACKERS
    # -----------------------------
    seen_products = set()          # unique product_url
    available_products = set()     # product_url with Amazon availability

    # -----------------------------
    # PROCESS EACH CATEGORY FILE
    # -----------------------------
    for file_name in os.listdir(BASE_DIR):
        if not file_name.endswith(".json"):
            continue

        category_path = os.path.join(BASE_DIR, file_name)

        with open(category_path, "r", encoding="utf-8") as f:
            items = json.load(f)

        if not isinstance(items, list):
            continue

        # -----------------------------
        # CATEGORY-LEVEL COUNTS
        # -----------------------------
        total = len(items)

        available = sum(
            1 for p in items
            if isinstance(p.get("amazon_link"), dict)
            and p["amazon_link"].get("amazon")
        )

        missing = total - available

        category = file_name.replace(".json", "")
        cat_display = category.replace("_", " ").title()

        output["category_breakdown"].append({
            "category": category,
            "category_display": cat_display,
            "total_products": total,
            "available_on_amazon": available,
            "missing_on_amazon": missing,
            "availability_percent": round((available / total) * 100, 2) if total else 0
        })

        output["total_categories"] += 1

        # -----------------------------
        # GLOBAL UNIQUE COUNTS
        # -----------------------------
        for p in items:
            product_url = p.get("product_url")
            if not product_url:
                continue

            # 👇 DEDUPLICATION KEY
            if product_url in seen_products:
                continue

            seen_products.add(product_url)

            if (
                isinstance(p.get("amazon_link"), dict)
                and p["amazon_link"].get("amazon")
            ):
                available_products.add(product_url)

    # -----------------------------
    # FINAL GLOBAL TOTALS
    # -----------------------------
    output["total_products"] = len(seen_products)
    output["products_available_on_amazon"] = len(available_products)
    output["products_missing_on_amazon"] = (
        output["total_products"] - output["products_available_on_amazon"]
    )

    if output["total_products"] > 0:
        output["availability_percent_overall"] = round(
            (output["products_available_on_amazon"] / output["total_products"]) * 100,
            2
        )

    # -----------------------------
    # WRITE OUTPUT
    # -----------------------------
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(output, out, indent=4)

    # -----------------------------
    # CONSOLE SUMMARY
    # -----------------------------
    print("✔ Metadata created:", OUTPUT_FILE)
    print("✔ Total categories:", output["total_categories"])
    print("✔ UNIQUE products:", output["total_products"])
    print("✔ UNIQUE available on Amazon:", output["products_available_on_amazon"])


# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    generate_metadata()
