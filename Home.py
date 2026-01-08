# app.py
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from collections import defaultdict
import sys

# ----------------------------------------------------
# CONFIG / PAGE
# ----------------------------------------------------
st.set_page_config(
    page_title="KIND Marketplace Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRIMARY = "#0057b8"

# ----------------------------------------------------
# STYLES (sidebar + KPI)
# ----------------------------------------------------
sidebar_css = """
<style>
[data-testid="stSidebar"] { background-color: #f4f6fa !important; padding-top: 22px !important; }
[data-testid="stSidebar"] [data-testid="stSidebarNav"] > div:nth-child(1),
[data-testid="stSidebarNav"] div[role="heading"] { display: none !important; }
[data-testid="stSidebar"] ul { margin-top:5px !important; padding-left:4px !important; }
[data-testid="stSidebar"] ul li { margin-bottom:3px !important; }
[data-testid="stSidebar"] ul li a { font-size:0.96rem !important; color:#34495e !important; border-radius:8px !important; padding:10px 14px !important; transition:0.2s; display:block !important; }
[data-testid="stSidebar"] ul li a:hover { background-color:#e6edfa !important; color:#003e8c !important; }
[data-testid="stSidebar"] ul li a[data-selected="true"] { background-color:#dce6ff !important; color:#003e8c !important; font-weight:600 !important; border-left:4px solid #003e8c !important; padding-left:10px !important; }
</style>
"""
st.markdown(sidebar_css, unsafe_allow_html=True)

kpi_css = """
<style>
.kpi-card { background:#fff;padding:25px;border-radius:14px;text-align:center;box-shadow:0 3px 12px rgba(0,0,0,0.10);border:1px solid #e3e3e3; }
.kpi-title { font-size:15px;font-weight:600;color:#555;margin-bottom:6px; }
.kpi-value { font-size:32px;font-weight:700;color:#0057b8; }
</style>
"""
st.markdown(kpi_css, unsafe_allow_html=True)

# ----------------------------------------------------
# LOAD JSONS
# ----------------------------------------------------
BASE = Path(".")
NORMALIZED_FILE = BASE / "normalized_all_products.json"
META_FILE = BASE / "normalized_metadata_summary.json"
CAPACITY_FILE = BASE / "capacity_bins.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


data_families = load_json(NORMALIZED_FILE) or []
meta = load_json(META_FILE) or {}
capacity = load_json(CAPACITY_FILE) or {}

# ----------------------------------------------------
# BUILD LOOKUPS
# ----------------------------------------------------
asin_title_map = {}
for fam in data_families:
    for v in fam.get("variants", []):
        asin = v.get("asin")
        title = v.get("title") or v.get("variant_name") or fam.get("product_name")
        if asin:
            asin_title_map[asin] = title


def safe_num(v):
    try:
        return float(v) if v is not None else None
    except:
        return None


# ----------------------------------------------------
# KPI VALUES
# ----------------------------------------------------
kind_total_products = capacity.get("total_products", 184)
total_skus = meta.get("total_skus")
unique_sellers_list = meta.get("unique_sellers_excluding_amazon_and_kind", [])
unique_sellers_count = len(unique_sellers_list)
sku_per_category = meta.get("skus_per_category", {})

marketplace_health_score = meta.get("marketplace_health_score")
gouging_rate = meta.get("gouging_rate")
avg_overprice_pct = meta.get("avg_overprice_pct")
max_overprice_pct = meta.get("max_overprice_pct")
max_overprice_abs = meta.get("max_overprice_abs")
total_listings = meta.get("total_listings")
total_gouged_listings = meta.get("total_gouged_listings")
fair_price_listings = meta.get("fair_price_listings")
skus_impacted = meta.get("skus_impacted")

# ----------------------------------------------------
# HEADER (UI)
# ----------------------------------------------------
col1, col2 = st.columns([0.1, 1])
with col1:
    try:
        st.image("kind.png", width="content")
    except Exception:
        pass  # Silently fail if logo not found
with col2:
    pass
st.markdown(
    f"""<h1 style="text-align:center;color:{PRIMARY};margin-bottom:5px;">
    KIND Marketplace Dashboard
    </h1>""",
    unsafe_allow_html=True,
)
st.markdown("---")

# KPI ROW
c1, c2, c3 = st.columns(3)

c1.markdown(
    f"""
<div class="kpi-card">
  <div class="kpi-title">Total Products (KIND)</div>
  <div class="kpi-value">{kind_total_products}</div>
</div>
""",
    unsafe_allow_html=True,
)

c2.markdown(
    f"""
<div class="kpi-card">
  <div class="kpi-title">Total SKUs</div>
  <div class="kpi-value">{total_skus}</div>
</div>
""",
    unsafe_allow_html=True,
)

c3.markdown(
    f"""
<div class="kpi-card">
  <div class="kpi-title">Unique Sellers (Excl Amazon & KIND)</div>
  <div class="kpi-value">{unique_sellers_count}</div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("---")

# ----------------------------------------------------
# CATEGORY + SELLERS LIST
# ----------------------------------------------------
left, right = st.columns([2, 1])

with left:
    st.subheader("SKUs Per Category (ascending)")

    df_cat = pd.DataFrame(
        list(sku_per_category.items()), columns=["category", "sku_count"]
    )

    # Sort ascending
    df_cat = df_cat.sort_values("sku_count", ascending=True).reset_index(drop=True)

    # Add row numbers to make order visible
    df_cat.index = df_cat.index + 1
    df_cat.index.name = "S.No"

    st.dataframe(df_cat, width="stretch")


with right:
    st.subheader("Sellers (Excl Amazon/KIND)")
    st.dataframe(pd.DataFrame({"seller_name": unique_sellers_list}), width="stretch")

st.markdown("---")

# ----------------------------------------------------
# TOP GOUGED SKUS
# ----------------------------------------------------
st.header("Additional Insights")
st.subheader("Top 10 Most Gouged SKUs")

meta_top = meta.get("top_gouged_skus", [])
rows = []

for t in meta_top:
    asin = t.get("asin")
    rows.append(
        {
            "asin": asin,
            "title": asin_title_map.get(asin, t.get("product_name")),
            "category": t.get("category"),
            "amazon_price": safe_num(t.get("amazon_unit")),
            "seller_price": safe_num(t.get("seller_unit")),
            "price_delta_abs": safe_num(t.get("price_delta_abs")),
            "price_delta_percent": safe_num(t.get("price_delta_pct")),
            "seller_name": t.get("seller_name"),
            "upstream_price_flag": t.get("upstream_price_flag"),
        }
    )

# Sort descending by % or abs
rows_sorted = sorted(rows, key=lambda x: (x["price_delta_percent"] or 0), reverse=True)[
    :10
]
df_top = pd.DataFrame(rows_sorted)

df_top["amazon_price"] = df_top["amazon_price"].apply(
    lambda x: f"${x:.2f}" if x else "-"
)
df_top["seller_price"] = df_top["seller_price"].apply(
    lambda x: f"${x:.2f}" if x else "-"
)
df_top["price_delta_abs"] = df_top["price_delta_abs"].apply(
    lambda x: f"${x:.2f}" if x else "-"
)
df_top["price_delta_percent"] = df_top["price_delta_percent"].apply(
    lambda x: f"{x:.1f}%" if x else "-"
)

st.dataframe(df_top, width="stretch")

st.markdown("---")

# ----------------------------------------------------
# SELLER INSIGHTS
# ----------------------------------------------------
st.subheader("Additional Seller Insights")

left_col, right_col = st.columns([2, 1])

# ---- LEFT: High Price Seller Analysis ----
meta_seller_summary = meta.get("seller_gouging_summary", [])

# Build seller → total_skus from normalized_all_products.json
seller_total_skus = defaultdict(int)

for fam in data_families:
    for listing in fam.get("seller_market", []):
        seller = listing.get("seller_name", "").strip().lower()
        if seller:
            seller_total_skus[seller] += 1

with left_col:
    st.markdown("### High Price Seller Analysis")

    df_hp = pd.DataFrame(meta_seller_summary)

    # Add total_skus column (case-insensitive match)
    df_hp["total_skus"] = df_hp["seller_name"].str.lower().map(seller_total_skus)

    # Build final display
    df_hp_display = pd.DataFrame(
        {
            "seller_name": df_hp["seller_name"],
            "total_skus": df_hp["total_skus"],
            "overpriced_skus": df_hp["gouged_listings"],
            "avg_delta_percent": df_hp["avg_overprice_pct"].map(lambda x: f"{x:.0f}%"),
        }
    )

    st.dataframe(df_hp_display, width="stretch")


# ---- RIGHT: Seller SKU Impact (Ranked, Amazon Removed) ----
with right_col:
    st.markdown("### Seller SKU Impact")

    meta_sku_impact = meta.get("seller_sku_impact", {})

    df_imp = pd.DataFrame(
        [(seller, count) for seller, count in meta_sku_impact.items()],
        columns=["seller_name", "sku_count"],
    )

    # Remove Amazon.com (case-insensitive)
    df_imp = df_imp[df_imp["seller_name"].str.lower() != "amazon.com"]

    # Sort high → low
    df_imp = df_imp.sort_values("sku_count", ascending=False).reset_index(drop=True)

    st.dataframe(df_imp, width="stretch")

# st.markdown("---")
# st.caption(
#     "Dashboard view — All insights sourced from normalized_metadata_summary.json (meta) with titles from normalized_all_products.json."
# )
