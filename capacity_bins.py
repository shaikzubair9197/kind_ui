import os
import json

BASE_DIR = "products_kind"
OUTPUT_FILE = "capacity_bins1.json"
ALL_SNACKS_FILE = "All_Snacks.json"


def is_amazon_available(product):
    return (
        isinstance(product.get("amazon_link"), dict)
        and product["amazon_link"].get("amazon")
    )


def generate_metadata():
    categories_output = []

    # -----------------------------------
    # STEP 1: Collect product_urls
    #         from NON-All_Snacks categories
    # -----------------------------------
    non_all_snacks_products = set()

    for file_name in os.listdir(BASE_DIR):
        if not file_name.endswith(".json"):
            continue
        if file_name == ALL_SNACKS_FILE:
            continue

        with open(os.path.join(BASE_DIR, file_name), "r", encoding="utf-8") as f:
            items = json.load(f)

        if not isinstance(items, list):
            continue

        for p in items:
            if p.get("product_url"):
                non_all_snacks_products.add(p["product_url"])

    # -----------------------------------
    # STEP 2: Process each category
    # -----------------------------------
    total_products = 0
    products_available_on_amazon = 0

    for file_name in os.listdir(BASE_DIR):
        if not file_name.endswith(".json"):
            continue

        category_name = file_name.replace(".json", "")
        file_path = os.path.join(BASE_DIR, file_name)

        with open(file_path, "r", encoding="utf-8") as f:
            items = json.load(f)

        if not isinstance(items, list):
            continue

        filtered_items = []

        for p in items:
            product_url = p.get("product_url")
            if not product_url:
                continue

            # 👇 FILTER All_Snacks duplicates
            if file_name == ALL_SNACKS_FILE and product_url in non_all_snacks_products:
                continue

            filtered_items.append(p)

        total = len(filtered_items)
        available = sum(1 for p in filtered_items if is_amazon_available(p))

        categories_output.append({
            "name": category_name,
            "total_products": total,
            "available_on_amazon": available,
            "availability_percent": round((available / total) * 100, 2) if total else 0
        })

        total_products += total
        products_available_on_amazon += available

    # -----------------------------------
    # FINAL OUTPUT
    # -----------------------------------
    output = {
        "categories": categories_output,
        "total_categories": len(categories_output),
        "total_products": total_products,
        "products_available_on_amazon": products_available_on_amazon
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(output, out, indent=4)

    print("✔ Metadata created:", OUTPUT_FILE)
    print("✔ Total categories:", output["total_categories"])
    print("✔ Total products (All_Snacks filtered):", total_products)
    print("✔ Products available on Amazon:", products_available_on_amazon)


if __name__ == "__main__":
    generate_metadata()
import os
import json

BASE_DIR = "products_kind"
OUTPUT_FILE = "kind_products_metadata_filtered.json"
ALL_SNACKS_FILE = "All_Snacks.json"


def is_amazon_available(product):
    return (
        isinstance(product.get("amazon_link"), dict)
        and product["amazon_link"].get("amazon")
    )


def generate_metadata():
    categories_output = []

    # -----------------------------------
    # STEP 1: Collect product_urls
    #         from NON-All_Snacks categories
    # -----------------------------------
    non_all_snacks_products = set()

    for file_name in os.listdir(BASE_DIR):
        if not file_name.endswith(".json"):
            continue
        if file_name == ALL_SNACKS_FILE:
            continue

        with open(os.path.join(BASE_DIR, file_name), "r", encoding="utf-8") as f:
            items = json.load(f)

        if not isinstance(items, list):
            continue

        for p in items:
            if p.get("product_url"):
                non_all_snacks_products.add(p["product_url"])

    # -----------------------------------
    # STEP 2: Process each category
    # -----------------------------------
    total_products = 0
    products_available_on_amazon = 0

    for file_name in os.listdir(BASE_DIR):
        if not file_name.endswith(".json"):
            continue

        category_name = file_name.replace(".json", "")
        file_path = os.path.join(BASE_DIR, file_name)

        with open(file_path, "r", encoding="utf-8") as f:
            items = json.load(f)

        if not isinstance(items, list):
            continue

        filtered_items = []

        for p in items:
            product_url = p.get("product_url")
            if not product_url:
                continue

            # 👇 FILTER All_Snacks duplicates
            if file_name == ALL_SNACKS_FILE and product_url in non_all_snacks_products:
                continue

            filtered_items.append(p)

        total = len(filtered_items)
        available = sum(1 for p in filtered_items if is_amazon_available(p))

        categories_output.append({
            "name": category_name,
            "total_products": total,
            "available_on_amazon": available,
            "availability_percent": round((available / total) * 100, 2) if total else 0
        })

        total_products += total
        products_available_on_amazon += available

    # -----------------------------------
    # FINAL OUTPUT
    # -----------------------------------
    output = {
        "categories": categories_output,
        "total_categories": len(categories_output),
        "total_products": total_products,
        "products_available_on_amazon": products_available_on_amazon
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(output, out, indent=4)

    print("✔ Metadata created:", OUTPUT_FILE)
    print("✔ Total categories:", output["total_categories"])
    print("✔ Total products (All_Snacks filtered):", total_products)
    print("✔ Products available on Amazon:", products_available_on_amazon)


if __name__ == "__main__":
    generate_metadata()
