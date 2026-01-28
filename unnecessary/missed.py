
# import os
# import json

# KIND_DIR = "products_kind"
# SCRAPED_FILE = "normalized_all_products1.json"


# def load_json(path):
#     with open(path, "r", encoding="utf-8") as f:
#         return json.load(f)


# # -------------------------------------------------
# # 1) KIND product URLs that HAVE amazon_link
# # -------------------------------------------------
# kind_products = set()

# for file_name in os.listdir(KIND_DIR):
#     if not file_name.endswith(".json"):
#         continue

#     items = load_json(os.path.join(KIND_DIR, file_name))
#     if not isinstance(items, list):
#         continue

#     for p in items:
#         if (
#             isinstance(p.get("product_url"), str)
#             and isinstance(p.get("amazon_link"), dict)
#             and p["amazon_link"].get("amazon")
#         ):
#             kind_products.add(p["product_url"].strip())


# # -------------------------------------------------
# # 2) Scraped product URLs
# # -------------------------------------------------
# scraped_data = load_json(SCRAPED_FILE)
# scraped_products = set()


# def walk(x):
#     if isinstance(x, dict):
#         # 👇 THIS is the key you mentioned
#         src = x.get("source_product_url")
#         if isinstance(src, str) and "kindsnacks.com/products" in src:
#             scraped_products.add(src.strip())

#         for v in x.values():
#             walk(v)

#     elif isinstance(x, list):
#         for i in x:
#             walk(i)


# walk(scraped_data)


# # -------------------------------------------------
# # 3) DIFF
# # -------------------------------------------------
# missed = sorted(kind_products - scraped_products)
# extra = sorted(scraped_products - kind_products)

# print("KIND products with Amazon links:", len(kind_products))
# print("Scraped product URLs:", len(scraped_products))
# print("❌ Missed products:", len(missed))
# print("➕ Extra scraped products:", len(extra))

# if missed:
#     print("\n--- MISSED PRODUCT URLS ---")
#     for u in missed:
#         print(u)

# if extra:
#     print("\n--- EXTRA SCRAPED PRODUCT URLS ---")
#     for u in extra:
#         print(u)

# with open("product_url_diff.json", "w", encoding="utf-8") as f:
#     json.dump(
#         {
#             "missed_products": missed,
#             "extra_scraped_products": extra,
#         },
#         f,
#         indent=2,
#     )

# print("\n✔ wrote: product_url_diff.json")
import os
import json

BASE_DIR = "products_kind"

MISSED_PRODUCTS = [
    "https://www.kindsnacks.com/products/healthy-grains-clusters/vanilla-blueberry-granola-flax-seeds",
    "https://www.kindsnacks.com/products/minis/caramel-almond-sea-salt",
    "https://www.kindsnacks.com/products/nut-bar/dark-chocolate-almond-mint",
    "https://www.kindsnacks.com/products/nut-bar/dark-chocolate-cherry-cashew",
    "https://www.kindsnacks.com/products/nut-bar/dark-chocolate-mocha-almond",
    "https://www.kindsnacks.com/products/nut-bar/dark-chocolate-nuts-sea-salt",
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Map: product_url -> categories
product_categories = {u: [] for u in MISSED_PRODUCTS}

for file_name in os.listdir(BASE_DIR):
    if not file_name.endswith(".json"):
        continue

    category = file_name.replace(".json", "")
    items = load_json(os.path.join(BASE_DIR, file_name))

    if not isinstance(items, list):
        continue

    for p in items:
        url = p.get("product_url")
        if url in product_categories:
            product_categories[url].append(category)


# -------- PRINT RESULT --------
for url, cats in product_categories.items():
    print("\nPRODUCT:")
    print(url)

    if cats:
        print("Found in categories:")
        for c in cats:
            print("  -", c)
    else:
        print("⚠ Not found in ANY category (unexpected)")
