# app.py
import json
from pathlib import Path
import pandas as pd
import streamlit as st
import math
from collections import defaultdict

# ----------------------------------------------------
# CONFIG
# ----------------------------------------------------
st.set_page_config(
    page_title="KIND Marketplace Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------------------------------
# PREMIUM SIDEBAR STYLING (LATEST WORKING VERSION)
# ----------------------------------------------------
sidebar_css = """
<style>

/* Sidebar Background */
[data-testid="stSidebar"] {
    background-color: #f4f6fa !important;
    padding-top: 22px !important;
}

/* Remove the default 'app' title completely */
[data-testid="stSidebar"] [data-testid="stSidebarNav"] > div:nth-child(1),
[data-testid="stSidebarNav"] div[role="heading"] {
    display: none !important;
}

/* Page link styling */
[data-testid="stSidebar"] ul {
    margin-top: 5px !important;
    padding-left: 4px !important;
}

[data-testid="stSidebar"] ul li {
    margin-bottom: 3px !important;
}

[data-testid="stSidebar"] ul li a {
    font-size: 0.96rem !important;
    color: #34495e !important;
    border-radius: 8px !important;
    padding: 10px 14px !important;
    transition: 0.2s;
    display: block !important;
}

/* Hover effect */
[data-testid="stSidebar"] ul li a:hover {
    background-color: #e6edfa !important;
    color: #003e8c !important;
}

/* Active Page */
[data-testid="stSidebar"] ul li a[data-selected="true"] {
    background-color: #dce6ff !important;
    color: #003e8c !important;
    font-weight: 600 !important;
    border-left: 4px solid #003e8c !important;
    padding-left: 10px !important;
}

</style>
"""
st.markdown(sidebar_css, unsafe_allow_html=True)

# ----------------------------------------------------
# LOAD DATA
# ----------------------------------------------------
BASE = Path(".")
NORMALIZED_FILE = BASE / "normalized_all_products.json"
METADATA_SUMMARY_FILE = BASE / "normalized_metadata_summary.json"
CAPACITY_FILE = BASE / "capacity_bins.json"

def load_json(path: Path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def load_json_null(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

# Load Data
data_families = load_json(NORMALIZED_FILE) or []
meta = load_json(METADATA_SUMMARY_FILE) or {}
capacity = load_json_null(CAPACITY_FILE) or {}

kind_total_products = capacity.get("total_products", 184)

# Flatten products (ASIN level)
flat_products = []
for fam in data_families:
    product_name = fam.get("product_name")
    category = fam.get("category")
    mp_all = fam.get("seller_market", [])
    for v in fam.get("variants", []):
        asin = v.get("asin")
        if not asin:
            continue
        mp = [s for s in mp_all if s.get("asin") == asin]
        flat_products.append({
            "asin": asin,
            "product_name": product_name,
            "category": category,
            "variant_title": v.get("title"),
            "amazon_price": v.get("price"),   # Amazon unit price
            "seller_market": mp
        })

# Dashboard Numbers
total_skus = meta.get("total_skus") or len(flat_products)
unique_sellers_excl = sorted(meta.get("unique_sellers_excluding_amazon_and_kind") or [])
sku_per_category = meta.get("skus_per_category") or {}

PRIMARY = "#0057b8"

# ----------------------------------------------------
# HEADER
# ----------------------------------------------------
st.markdown(
    f"""
    <h1 style="text-align:center;color:{PRIMARY};margin-bottom:5px;">
        KIND Marketplace Dashboard
    </h1>
    """,
    unsafe_allow_html=True
)

st.markdown("---")

# ----------------------------------------------------
# KPI CARDS
# ----------------------------------------------------
kpi_css = """
<style>
.kpi-card {
    background: #ffffff;
    padding: 25px;
    border-radius: 14px;
    text-align: center;
    box-shadow: 0px 3px 12px rgba(0,0,0,0.10);
    border: 1px solid #e3e3e3;
}
.kpi-title {
    font-size: 15px;
    font-weight: 600;
    color: #555;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 32px;
    font-weight: 700;
    color: #0057b8;
}
</style>
"""
st.markdown(kpi_css, unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)

c1.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">Total Products (KIND)</div>
    <div class="kpi-value">{kind_total_products}</div>
</div>
""", unsafe_allow_html=True)

c2.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">Total SKUs</div>
    <div class="kpi-value">{total_skus}</div>
</div>
""", unsafe_allow_html=True)

c3.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">Unique Sellers (Excl Amazon & KIND)</div>
    <div class="kpi-value">{len(unique_sellers_excl)}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ----------------------------------------------------
# CATEGORY + SELLER SUMMARY
# ----------------------------------------------------
left, right = st.columns([2,1])

with left:
    st.subheader("📦 SKUs Per Category (ascending)")
    if sku_per_category:
        df_cat = pd.DataFrame(
            list(sku_per_category.items()),
            columns=["category", "sku_count"]
        ).sort_values("sku_count").reset_index(drop=True)
        st.dataframe(df_cat, use_container_width=True)
    else:
        st.info("No category data available.")

with right:
    st.subheader("🛒 Sellers (Excl Amazon/KIND)")
    if unique_sellers_excl:
        st.dataframe(pd.DataFrame({"seller_name": unique_sellers_excl}),
                     use_container_width=True)
    else:
        st.info("No seller list found.")

st.markdown("---")

# ----------------------------------------------------
# ADDITIONAL INSIGHTS
# ----------------------------------------------------
st.header("Additional Insights")

# ----------------------------------------------------
# TOP 10 GOUGED SKUs — UPDATED FOR NEW METADATA FIELDS
# ----------------------------------------------------
st.subheader("🔥 Top 10 Most Gouged SKUs")

top_g_meta = meta.get("top_gouged_skus") or []
top_g_list = []

for t in top_g_meta:
    top_g_list.append({
        "asin": t.get("asin"),
        "product_name": t.get("product_name"),
        "title": t.get("title") or t.get("product_name"),
        "category": t.get("category"),

        # UPDATED for new unit-price structure
        "amazon_price": t.get("amazon_price_unit"),
        "seller_price": t.get("seller_price_unit"),

        "price_delta_abs": t.get("price_delta_abs"),
        "price_delta_percent": t.get("price_delta_percent"),

        "seller_name": t.get("seller_name"),
        "detected_as_gouging": t.get("detected_as_gouging"),
        "upstream_price_flag": t.get("upstream_price_flag")
    })

# Sort
top_g_sorted = sorted(
    [t for t in top_g_list if t.get("price_delta_percent") is not None],
    key=lambda x: x["price_delta_percent"],
    reverse=True
)[:10]

if top_g_sorted:
    df_topg = pd.DataFrame(top_g_sorted)

    df_topg["amazon_price"] = df_topg["amazon_price"].map(
        lambda x: f"${x:.2f}" if isinstance(x,(int,float)) else "-"
    )
    df_topg["seller_price"] = df_topg["seller_price"].map(
        lambda x: f"${x:.2f}" if isinstance(x,(int,float)) else "-"
    )
    df_topg["price_delta_abs"] = df_topg["price_delta_abs"].map(
        lambda x: f"${x:.2f}" if isinstance(x,(int,float)) else "-"
    )
    df_topg["price_delta_percent"] = df_topg["price_delta_percent"].map(
        lambda x: f"{x:.1f}%" if isinstance(x,(int,float)) else "-"
    )

    df_topg = df_topg[[
        "asin", "product_name", "title", "category",
        "amazon_price", "seller_price",
        "price_delta_abs", "price_delta_percent",
        "seller_name", "detected_as_gouging", "upstream_price_flag"
    ]]

    st.dataframe(df_topg, use_container_width=True)
else:
    st.info("No gouging detected.")

st.markdown("---")

# ----------------------------------------------------
# SELLER INSIGHTS (No field-change required)
# ----------------------------------------------------
st.subheader("Additional Seller Insights")

left_col, right_col = st.columns([2, 1])

def compute_seller_tables(products):
    seller_asins = defaultdict(set)
    seller_price_deltas_abs = defaultdict(list)
    seller_price_deltas_pct = defaultdict(list)
    seller_overpriced_asins = defaultdict(set)

    for s in products:
        asin = s.get("asin")
        for mk in s.get("seller_market") or []:
            name = mk.get("seller_name")
            if not name:
                continue

            seller_asins[name].add(asin)

            pct = mk.get("price_delta_percent")
            absd = mk.get("price_delta_abs")

            if pct is not None and pct > 0:
                seller_price_deltas_abs[name].append(absd or 0.0)
                seller_price_deltas_pct[name].append(pct)
                seller_overpriced_asins[name].add(asin)

    analysis_rows = []
    for seller, asins in seller_asins.items():
        total_skus = len(asins)
        overpriced_skus = len(seller_overpriced_asins.get(seller, set()))
        rate_high = (overpriced_skus / total_skus * 100) if total_skus else 0.0

        abs_list = seller_price_deltas_abs.get(seller, [])
        pct_list = seller_price_deltas_pct.get(seller, [])

        avg_delta_abs = sum(abs_list) / len(abs_list) if abs_list else 0.0
        avg_delta_pct = sum(pct_list) / len(pct_list) if pct_list else 0.0

        analysis_rows.append({
            "seller_name": seller,
            "total_skus": total_skus,
            "overpriced_skus": overpriced_skus,
            "rate_high": rate_high,
            "avg_delta_abs": avg_delta_abs,
            "avg_delta_percent": avg_delta_pct
        })

    analysis_sorted = sorted(
        analysis_rows,
        key=lambda r: (r["rate_high"], r["avg_delta_percent"]),
        reverse=True
    )

    impact = [{"seller": s, "sku_count": len(asins)} for s, asins in seller_asins.items()]
    impact_sorted = sorted(impact, key=lambda r: r["sku_count"], reverse=True)

    return analysis_sorted, impact_sorted

analysis_rows_sorted, impact_rows_sorted = compute_seller_tables(flat_products)

with left_col:
    st.markdown("### 📊 High Price Seller Analysis")

    if analysis_rows_sorted:
        df_hp = pd.DataFrame(analysis_rows_sorted)
        df_hp_display = pd.DataFrame({
            "seller_name": df_hp["seller_name"],
            "total_skus": df_hp["total_skus"].astype(int),
            "overpriced_skus": df_hp["overpriced_skus"].astype(int),
            "rate_high": df_hp["rate_high"].map(lambda x: f"{x:.0f}%"),
            "avg_delta_abs": df_hp["avg_delta_abs"].map(lambda x: f"${x:.2f}"),
            "avg_delta_percent": df_hp["avg_delta_percent"].map(lambda x: f"{x:.0f}%")
        })
        st.dataframe(df_hp_display.fillna("-"), use_container_width=True)
    else:
        st.info("No seller overpricing data available.")

with right_col:
    st.markdown("### 🏬 Seller SKU Impact")
    if impact_rows_sorted:
        df_impact = pd.DataFrame(impact_rows_sorted)
        df_impact = df_impact.rename(columns={"seller": "seller_name"})
        st.dataframe(df_impact.fillna("-"), use_container_width=True)
    else:
        st.info("No seller impact data.")

st.markdown("---")
st.caption("Dashboard view — Top gouged full-width, followed by High Price Seller Analysis and Seller SKU Impact.")
