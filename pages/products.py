import json
from pathlib import Path
import pandas as pd
import streamlit as st
import math

# --------------------------------------------------------
# Load Data
# --------------------------------------------------------
BASE = Path(".")
NORMALIZED_FILE = BASE / "normalized_all_products.json"
METADATA_SUMMARY_FILE = BASE / "normalized_metadata_summary.json"

def load_json(path: Path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

data_families = load_json(NORMALIZED_FILE) or []
meta = load_json(METADATA_SUMMARY_FILE) or {}
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

# --------------------------------------------------------
# Helpers
# --------------------------------------------------------
def format_price(p):
    try:
        return f"${float(p):.2f}"
    except:
        return "-" if not p else str(p)

def rating_to_stars(r):
    if r is None:
        return "-"
    try:
        r = float(r)
    except:
        return "-"
    full = int(math.floor(r))
    half = (r - full) >= 0.5
    if half:
        stars = "★"*full + "⯪" + "☆"*(5 - full - 1)
    else:
        stars = "★"*full + "☆"*(5 - full)
    return f"<span class='gold-stars'>{stars}</span>"

def price_flag_label(flag):
    if flag == "Fair Price": return ("Fair Price", "#4caf50")
    if flag == "Slightly High": return ("Slightly High", "#ffb84d")
    if flag == "High Price": return ("High Price", "#ff9900")
    if flag == "Price Gouging": return ("Price Gouging", "#ff4d4d")
    return ("-", "#9e9e9e")

def seller_count_badge(count):
    if count == 0: return ("0 sellers", "#4caf50")
    if 1 <= count <= 3: return (f"{count} sellers", "#ffd400")
    if 4 <= count <= 10: return (f"{count} sellers", "#ff8c00")
    return (f"{count} sellers", "#ff4d4d")

# --------------------------------------------------------
# Flatten SKUs
# --------------------------------------------------------
flat_products = []
for fam in data_families:
    pname = fam.get("product_name")
    cat = fam.get("category")
    mp_all = fam.get("seller_market", [])

    for v in fam.get("variants", []):
        asin = v.get("asin")
        if not asin:
            continue

        main_seller = next((ms for ms in fam.get("main_seller", []) if ms.get("asin") == asin), None)
        mp_sellers = [s for s in mp_all if s.get("asin") == asin]

        flat_products.append({
            "asin": asin,
            "product_name": pname,
            "category": cat,
            "title": v.get("title") or v.get("variant_name") or asin,
            "flavor": v.get("variant_name") or v.get("flavor"),
            "price": v.get("price"),
            "unit_price": v.get("unit_price"),
            "prime": v.get("prime"),
            "final_url": v.get("final_url"),
            "main_seller": main_seller,
            "seller_market": mp_sellers,
        })

# --------------------------------------------------------
# PAGE UI
# --------------------------------------------------------
PRIMARY = "#0057b8"

st.markdown("""
<style>
  body { background-color: #f7f9fc; }
  .gold-stars { color: #d4af37; font-weight:700; }
  .badge { padding:6px 10px; border-radius:8px; color:#fff; font-weight:700; display:inline-block; }
  .small-muted { color:#666; font-size:13px; }
</style>
""", unsafe_allow_html=True)

st.title("📦 Product Explorer")
st.markdown("Use filters, search, and sorting to refine results.")
st.markdown("")

# --------------------------------------------------------
# KPIs at Top
# --------------------------------------------------------
gouging_count = sum(
    1 for s in flat_products
    for mk in s["seller_market"]
    if mk.get("price_flag") == "Price Gouging"
)

marketplace_skus = sum(1 for s in flat_products if s["seller_market"])

unique_sellers = {
    mk.get("seller_name")
    for s in flat_products
    for mk in s["seller_market"]
    if mk.get("seller_name")
}

# --------------------------------------------------------
# KPI CARD STYLE (INSERTED)
# --------------------------------------------------------
kpi_css = """
<style>
.kpi-card {
    background: #ffffff;
    padding: 24px;
    border-radius: 16px;
    text-align: center;
    box-shadow: 0px 4px 14px rgba(0,0,0,0.08);
    border: 1px solid #e5e5e5;
    transition: all 0.25s ease;
}
.kpi-card:hover {
    transform: translateY(-4px);
    box-shadow: 0px 6px 18px rgba(0,0,0,0.12);
}
.kpi-title {
    font-size: 15px;
    font-weight: 600;
    color: #444;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 34px;
    font-weight: 800;
    color: #0057b8;
    margin-top: 4px;
}
</style>
"""
st.markdown(kpi_css, unsafe_allow_html=True)

# --------------------------------------------------------
# KPI CARDS
# --------------------------------------------------------
kpi_css = """
<style>
.kpi-card {
    background: #ffffff;
    padding: 28px;
    border-radius: 16px;
    text-align: center;
    box-shadow: 0px 4px 14px rgba(0,0,0,0.08);
    border: 1px solid #e5e5e5;
    height: 150px; /* increased height */
    display: flex;
    flex-direction: column;
    justify-content: center;
}

.kpi-title {
    font-size: 15px;
    font-weight: 600;
    color: #444;
    margin-bottom: 8px;
}

.kpi-value {
    font-size: 36px;
    font-weight: 800;
    color: #0057b8;
    margin-bottom: 6px;
}
</style>
"""

st.markdown(kpi_css, unsafe_allow_html=True)
def kpi_card(title, value, tooltip, subtitle=""):
    return f"""
    <div class="kpi-card" title="{tooltip}">
        <div class="kpi-title">{title}</div>
        <div class="kpi-value">{value}</div>
        <div style="font-size:13px;color:#777;margin-top:4px;">{subtitle}</div>
    </div>
    """

st.markdown("### 📊 Marketplace Summary")

c1, c2, c3, c4, c5, c6 = st.columns(6)

c1.markdown(kpi_card(
    "Marketplace Health Score",
    meta.get("marketplace_health_score", "-"),
    "A 0–100 score.\nFormula: 100 - (0.5 × gouging rate) - (0.4 × avg overprice %) - (0.1 × % bad sellers).\nLower score = riskier marketplace."
), unsafe_allow_html=True)

c2.markdown(kpi_card(
    "SKUs Impacted",
    meta.get("skus_impacted", "-"),
    "Number of KIND SKUs with at least one gouged seller.\nExample: If SKU has 1 gouged seller → counted."
), unsafe_allow_html=True)

c3.markdown(kpi_card(
    "Gouging Rate",
    f"{meta.get('gouging_rate', 0):.1f}%",
    f"Gouged Listings / Total Listings.\nExample: {meta.get('total_gouged_listings')} / {meta.get('total_listings')} = {meta.get('gouging_rate'):.1f}%.",
    subtitle=f"{meta.get('total_gouged_listings')} / {meta.get('total_listings')} listings"
), unsafe_allow_html=True)

c4.markdown(kpi_card(
    "Avg Overprice (%)",
    f"+{meta.get('avg_overprice_pct', 0):.1f}%",
    "Average % markup of gouged listings.\nExample: (+30% + +80%) / 2 = +55%."
), unsafe_allow_html=True)

c5.markdown(kpi_card(
    "Worst Overprice (%)",
    f"+{meta.get('max_overprice_pct', 0):.0f}%",
    "Highest single price increase in all listings.\nExample: Seller price $15.99 vs Amazon $4.97 → +222%."
), unsafe_allow_html=True)

top_v = meta.get("seller_gouging_summary", [])
top_name = top_v[0]['seller_name'] if top_v else "-"
top_count = top_v[0]['gouged_listings'] if top_v else 0

c6.markdown(kpi_card(
    "Top Violator",
    top_name,
    "Seller with the highest number of gouged listings.\nExample: BirkenStar = 10 gouged listings.",
    subtitle=f"{top_count} listings"
), unsafe_allow_html=True)


st.markdown("<div style='height:35px;'></div>", unsafe_allow_html=True)

# --------------------------------------------------------
# Search + Sort
# --------------------------------------------------------
col_search, col_sort = st.columns([3, 1])

with col_search:
    search_query = st.text_input(
        "🔎 Search products by name / flavor / ASIN",
        placeholder="Type to search..."
    ).lower().strip()

with col_sort:
    sort_choice = st.selectbox(
        "Sort By",
        [
            "Default",
            "Price (Low → High)",
            "Price (High → Low)",
            "Marketplace Sellers (High → Low)",
            "Marketplace Sellers (Low → High)",
            "Gouging (High → Low)",
            "Name (A → Z)",
            "Name (Z → A)"
        ]
    )

st.markdown("")

# --------------------------------------------------------
# Sidebar Filters
# --------------------------------------------------------
st.sidebar.header("Filters & Controls")

all_categories = sorted({p["category"] for p in flat_products})
category_choice = st.sidebar.selectbox("Filter by Category", ["All Categories"] + all_categories)

mp_filter = st.sidebar.radio(
    "Marketplace filter",
    ("All SKUs", "Only with marketplace sellers", "Only without marketplace sellers")
)

max_seller_count = max((len(s["seller_market"]) for s in flat_products), default=0)
seller_min, seller_max = st.sidebar.slider(
    "Marketplace seller count",
    0, max(20, max_seller_count), (0, max(20, max_seller_count))
)

all_price_flags = sorted({
    s.get("price_flag")
    for fam in data_families
    for s in fam.get("seller_market") or []
    if s.get("price_flag")
})
pf_choice = st.sidebar.multiselect("Price flags", all_price_flags)

uniq_sellers = sorted(meta.get("unique_sellers_excluding_amazon_and_kind") or [])
seller_filter = st.sidebar.selectbox("Filter by seller", ["All Sellers"] + uniq_sellers)

rating_filter = st.sidebar.selectbox(
    "Filter by rating",
    ("All", "Excellent (>=90%)", "Good (75-89%)", "Mixed (50-74%)", "Poor (<50%)")
)

# --------------------------------------------------------
# Filtering Logic
# --------------------------------------------------------
def get_tier(pct):
    if pct is None: return None
    if pct >= 90: return "Excellent (>=90%)"
    if pct >= 75: return "Good (75-89%)"
    if pct >= 50: return "Mixed (50-74%)"
    return "Poor (<50%)"

def sku_matches(sku):
    if category_choice != "All Categories" and sku["category"] != category_choice:
        return False

    sku_has_mp = bool(sku["seller_market"])
    if mp_filter == "Only with marketplace sellers" and not sku_has_mp:
        return False
    if mp_filter == "Only without marketplace sellers" and sku_has_mp:
        return False

    if not (seller_min <= len(sku["seller_market"]) <= seller_max):
        return False

    if pf_choice:
        flags = [s.get("price_flag") for s in sku["seller_market"]]
        if not any(f in pf_choice for f in flags if f):
            return False

    if seller_filter != "All Sellers":
        ms = sku.get("main_seller")
        if ms and ms.get("seller_name") == seller_filter:
            pass
        elif any(s.get("seller_name") == seller_filter for s in sku["seller_market"]):
            pass
        else:
            return False

    if rating_filter != "All":
        match = False
        for s in sku["seller_market"]:
            if get_tier(s.get("positive_rating_percent")) == rating_filter:
                match = True
        ms = sku.get("main_seller")
        if ms and get_tier(ms.get("positive_rating_percent")) == rating_filter:
            match = True
        if not match:
            return False

    return True

# --------------------------------------------------------
# Apply Filters + Search + Sorting
# --------------------------------------------------------
filtered = [s for s in flat_products if sku_matches(s)]

if search_query:
    filtered = [
        s for s in filtered
        if search_query in (s["product_name"] or "").lower()
        or search_query in (s.get("flavor") or "").lower()
        or search_query in (s.get("asin") or "").lower()
    ]

# Sorting
if sort_choice == "Price (Low → High)":
    filtered = sorted(filtered, key=lambda x: x["price"] or 9999)

elif sort_choice == "Price (High → Low)":
    filtered = sorted(filtered, key=lambda x: -(x["price"] or 0))

elif sort_choice == "Marketplace Sellers (High → Low)":
    filtered = sorted(filtered, key=lambda x: len(x["seller_market"]), reverse=True)

elif sort_choice == "Marketplace Sellers (Low → High)":
    filtered = sorted(filtered, key=lambda x: len(x["seller_market"]))

elif sort_choice == "Gouging (High → Low)":
    def worst_pct(p):
        vals = [s.get("price_delta_percent") for s in p["seller_market"] if s.get("price_delta_percent")]
        return max(vals) if vals else -999
    filtered = sorted(filtered, key=worst_pct, reverse=True)

elif sort_choice == "Name (A → Z)":
    filtered = sorted(filtered, key=lambda x: x["product_name"])

elif sort_choice == "Name (Z → A)":
    filtered = sorted(filtered, key=lambda x: x["product_name"], reverse=True)

# --------------------------------------------------------
# Summary Display
# --------------------------------------------------------
st.markdown(f"### Showing {len(filtered)} SKUs (after filters)")
st.markdown("")

# --------------------------------------------------------
# Pagination (CLEAN VERSION)
# --------------------------------------------------------
page_size = st.selectbox("Items per page", [10, 20, 50, 100], index=0)

total_pages = max(1, (len(filtered) + page_size - 1) // page_size)

if "page" not in st.session_state:
    st.session_state.page = 1

# Fix page boundary when filters change
if st.session_state.page > total_pages:
    st.session_state.page = total_pages

start = (st.session_state.page - 1) * page_size
end = start + page_size
page_items = filtered[start:end]

st.markdown(f"**Page {st.session_state.page} of {total_pages}**")
st.markdown("---")

# --------------------------------------------------------
# Product Accordions
# --------------------------------------------------------
for p in page_items:

    mp_count = len(p["seller_market"])
    seller_badge_text, seller_badge_color = seller_count_badge(mp_count)

    flags = [s.get("price_flag") for s in p["seller_market"] if s.get("price_flag")]
    flag_priority = {"Price Gouging":4, "High Price":3, "Slightly High":2, "Fair Price":1}
    worst_flag = sorted(flags, key=lambda f: flag_priority.get(f,0), reverse=True)[0] if flags else None
    pf_label, pf_color = price_flag_label(worst_flag)

    exp_title = f"{p['product_name']} — {p.get('flavor') or ''} (ASIN: {p['asin']})"

    header_html = f"""
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
      <div style="font-weight:700;color:{PRIMARY};">{exp_title}</div>
      <div>
        <span class='badge' style='background:{seller_badge_color};margin-right:6px'>{seller_badge_text}</span>
        <span class='badge' style='background:{pf_color};'>{pf_label}</span>
      </div>
    </div>
    """

    with st.expander(exp_title, expanded=False):

        st.markdown(header_html, unsafe_allow_html=True)

        st.markdown("### Product Details")
        pd_details = pd.DataFrame([{
            "asin": p["asin"],
            "title": p["title"],
            "price": format_price(p["price"]),
            "unit_price": format_price(p["unit_price"]),
            "prime": "Yes" if p["prime"] else "No",
            "flavor": p.get("flavor"),
            "amazon_url": p.get("final_url") or "-"
        }])
        st.dataframe(pd_details, use_container_width=True)

        if p.get("main_seller"):
            st.markdown("### Main Seller")
            ms = p["main_seller"]
            st.dataframe(pd.DataFrame([{
                "seller_name": ms.get("seller_name"),
                "ships_from": ms.get("ships_from"),
                "authorized": "Yes" if ms.get("is_authorized") else "No",
                "price": format_price(ms.get("price")),
                "unit_price": format_price(ms.get("unit_price")),
                "prime": "Yes" if ms.get("prime") else "No"
            }]), use_container_width=True)
        else:
            st.info("No main seller found.")

        if p["seller_market"]:
            st.markdown("### Marketplace Sellers")
            sellers_table = [
                {
                    "seller_name": s.get("seller_name"),
                    "ships_from": s.get("ships_from"),
                    "authorized": "Yes" if s.get("is_authorized") else "No",
                    "price": format_price(s.get("price")),
                    "unit_price": format_price(s.get("unit_price")),
                    "price_delta": f"${s['price_delta_abs']:.2f}" if s.get("price_delta_abs") else "-",
                    "price_flag": s.get("price_flag"),
                    "rating_stars": s.get("rating_stars") or "-",
                    "rating_count": s.get("rating_count") or "-",
                    "positive_rating_percent": s.get("positive_rating_percent") or "-"
                }
                for s in p["seller_market"]
            ]
            st.dataframe(pd.DataFrame(sellers_table), use_container_width=True)

            st.markdown("**Seller ratings (visual)**")
            for s in p["seller_market"]:
                stars_html = rating_to_stars(s.get("rating_stars"))
                st.markdown(
                    f"<div><b>{s.get('seller_name')}</b> — {stars_html} "
                    f"<span class='small-muted'>({s.get('rating_count') or '-'} ratings, "
                    f"{s.get('positive_rating_percent') or '-'}% positive)</span></div>",
                    unsafe_allow_html=True
                )
        else:
            st.info("No marketplace sellers found.")

# --------------------------------------------------------
# BOTTOM PAGINATION BUTTONS ONLY
# --------------------------------------------------------
st.markdown("---")
col_prev, col_mid, col_next = st.columns([1, 8, 1])

with col_prev:
    if st.button("⬅️ Previous") and st.session_state.page > 1:
        st.session_state.page -= 1

with col_next:
    if st.button("Next ➡️") and st.session_state.page < total_pages:
        st.session_state.page += 1
