# app.py (redesigned layout: Option C - Mixed) - FULL (grouping integrated)
import json
from pathlib import Path
import pandas as pd
import streamlit as st
import math

# --------------------------------------------------------
# Original sidebar CSS
# --------------------------------------------------------
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
        stars = "★" * full + "⯪" + "☆" * (5 - full - 1)
    else:
        stars = "★" * full + "☆" * (5 - full)
    return f"<span class='gold-stars'>{stars}</span>"


def price_flag_label(flag):
    if flag == "Fair Price":
        return ("Fair Price", "#4caf50")
    if flag == "Slightly High":
        return ("Slightly High", "#ffb84d")
    if flag == "High Price":
        return ("High Price", "#ff9900")
    if flag == "Price Gouging":
        return ("Price Gouging", "#ff4d4d")
    return ("-", "#9e9e9e")


def seller_count_badge(count):
    if count == 0:
        return ("0 sellers", "#4caf50")
    if 1 <= count <= 3:
        return (f"{count} sellers", "#ffd400")
    if 4 <= count <= 10:
        return (f"{count} sellers", "#ff8c00")
    return (f"{count} sellers", "#ff4d4d")


# --------------------------------------------------------
# Fuzzy Grouping for Same Product (Different Pack Sizes)
# (Inserted here as requested; does not change other logic)
# --------------------------------------------------------
import re
from difflib import SequenceMatcher


def normalize_title_for_grouping(title: str) -> str:
    """
    Normalize title to remove pack size, counts, weights, numbers,
    so different sizes of the same product group together.
    """
    if not title:
        return ""

    t = title.lower()

    # Remove specific pack phrases
    t = re.sub(r"pack\s*of\s*\d+", "", t)

    # Remove count indicators (ct, pcs, count, pieces, pack)
    t = re.sub(r"\b\d+\s*(ct|count|pcs|pieces|pack)\b", "", t)

    # Remove weights (oz, g, lb)
    t = re.sub(r"\b\d+\.?\d*\s*(oz|ounce|g|gram|lb|lbs)\b", "", t)

    # Remove any remaining isolated number (e.g., 12, 24)
    t = re.sub(r"\b\d+\b", "", t)

    # Remove any leftover non-alpha characters
    t = re.sub(r"[^a-z]+", " ", t)

    # Final cleanup
    t = " ".join(t.split())

    return t.strip()


def fuzzy_ratio(a: str, b: str) -> float:
    """Compute fuzzy similarity between two normalized titles."""
    return SequenceMatcher(None, a, b).ratio()


def extract_identity(title: str) -> str:
    """
    Extracts a dynamic identity for a product based on the first few meaningful words.
    No hardcoded brand rules. Pure text-based identity.
    """
    if not title:
        return ""

    t = title.lower()

    # Remove pack size, weights, numbers
    t = re.sub(r"pack\s*of\s*\d+", "", t)
    t = re.sub(r"\b\d+\s*(ct|count|pcs|pieces|pack)\b", "", t)
    t = re.sub(r"\b\d+\.?\d*\s*(oz|ounce|g|gram|lb|lbs)\b", "", t)
    t = re.sub(r"\b\d+\b", "", t)

    # Split into words
    words = re.findall(r"[a-z]+", t)

    # Identity = first 3 meaningful words
    # Example:
    #   KIND ZERO Added Sugar Bars → ["kind", "zero", "added"]
    #   KIND Nut Bars → ["kind", "nut", "bars"]
    identity = " ".join(words[:3])

    return identity


def group_same_products(product_list, threshold=0.80):
    groups = []
    used = set()

    for p in product_list:
        asin_p = p.get("asin")
        if asin_p in used:
            continue

        title_p = p.get("title") or ""
        flavor_p = (p.get("flavor") or "").lower().strip()
        id_p = extract_identity(title_p)

        norm_p = normalize_title_for_grouping(title_p)

        group = {
            "identity": id_p,
            "normalized_title": norm_p,
            "group_title": p.get("product_name"),
            "items": [p],
        }
        used.add(asin_p)

        for q in product_list:
            asin_q = q.get("asin")
            if asin_q in used:
                continue

            title_q = q.get("title") or ""
            flavor_q = (q.get("flavor") or "").lower().strip()
            id_q = extract_identity(title_q)

            # 1️⃣ Same product identity (self-learned, no hardcoding)
            if id_p != id_q:
                continue

            # 2️⃣ Same flavor
            if flavor_p != flavor_q:
                continue

            # 3️⃣ Fuzzy title similarity
            norm_q = normalize_title_for_grouping(title_q)
            score = fuzzy_ratio(norm_p, norm_q)

            if score >= threshold:
                group["items"].append(q)
                used.add(asin_q)

        groups.append(group)

    return groups


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

        main_seller = next(
            (ms for ms in fam.get("main_seller", []) if ms.get("asin") == asin), None
        )
        mp_sellers = [s for s in mp_all if s.get("asin") == asin]

        flat_products.append(
            {
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
            }
        )

# --------------------------------------------------------
# PAGE UI + CSS
# --------------------------------------------------------
PRIMARY = "#0057b8"

st.set_page_config(page_title="Product Explorer — Redesigned", layout="wide")
st.markdown(
    """
<style>
  body { background-color: #f7f9fc; }
  .gold-stars { color: #d4af37; font-weight:700; }
  .badge { padding:6px 10px; border-radius:8px; color:#fff; font-weight:700; display:inline-block; }
  .small-muted { color:#666; font-size:13px; }

  /* KPI card */
  .kpi-card {
      background: #ffffff;
      padding: 26px;
      border-radius: 16px;
      text-align: center;
      box-shadow: 0px 4px 14px rgba(0,0,0,0.08);
      border: 1px solid #e5e5e5;
      height: 160px;
      display: flex;
      flex-direction: column;
      justify-content: center;
  }
  .kpi-title { font-size: 15px; font-weight: 600; color: #444; margin-bottom: 8px; }
  .kpi-value { font-size: 34px; font-weight: 800; color: #0057b8; margin-bottom: 6px; }
  .kpi-sub { font-size:13px;color:#777;margin-top:4px; }

  /* small table tweaks */
  .small-table th, .small-table td { padding:6px 8px; font-size:13px; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("Product Explorer — Redesigned")
st.markdown("Use filters, search, and sorting to refine results.")
st.markdown("")


# --------------------------------------------------------
# KPI fallbacks (scan flat_products if meta missing)
# --------------------------------------------------------
def compute_fallback_kpis(flat_products):
    total_listings = 0
    total_gouged_listings = 0
    pct_list = []
    abs_list = []
    sku_gouged_set = set()
    seller_gouged_counts = {}
    max_pct = None
    max_abs = None
    unique_sellers_set = set()

    for p in flat_products:
        for s in p["seller_market"]:
            total_listings += 1
            unique_sellers_set.add(s.get("seller_name"))
            pct = s.get("price_delta_percent")
            absd = s.get("price_delta_abs")
            if pct is not None:
                try:
                    pf = float(pct)
                except:
                    pf = None
            else:
                pf = None
            if absd is not None:
                try:
                    af = float(absd)
                except:
                    af = None
            else:
                af = None

            if pf is not None:
                pct_list.append(pf)
                if max_pct is None or pf > max_pct:
                    max_pct = pf
            if af is not None:
                abs_list.append(af)
                if max_abs is None or af > max_abs:
                    max_abs = af

            upstream_flag = (s.get("price_flag") or "").strip().lower()
            if upstream_flag == "price gouging":
                total_gouged_listings += 1
                sku_gouged_set.add(p["asin"])
                seller_gouged_counts[s.get("seller_name")] = (
                    seller_gouged_counts.get(s.get("seller_name"), 0) + 1
                )
            elif pf is not None and af is not None:
                if pf >= 20.0 and af >= 2.0:
                    total_gouged_listings += 1
                    sku_gouged_set.add(p["asin"])
                    seller_gouged_counts[s.get("seller_name")] = (
                        seller_gouged_counts.get(s.get("seller_name"), 0) + 1
                    )

    avg_pct = (sum(pct_list) / len(pct_list)) if pct_list else 0.0
    avg_abs = (sum(abs_list) / len(abs_list)) if abs_list else 0.0
    gouging_rate = (
        (total_gouged_listings / total_listings * 100) if total_listings else 0.0
    )
    skus_impacted = len(sku_gouged_set)
    total_skus = len(flat_products)
    return {
        "total_listings": total_listings,
        "total_gouged_listings": total_gouged_listings,
        "gouging_rate": gouging_rate,
        "avg_overprice_pct": avg_pct,
        "avg_overprice_abs": avg_abs,
        "max_overprice_pct": (max_pct if max_pct is not None else 0.0),
        "max_overprice_abs": (max_abs if max_abs is not None else 0.0),
        "skus_impacted": skus_impacted,
        "total_skus": total_skus,
        "unique_marketplace_sellers": len(unique_sellers_set),
        "seller_gouged_counts": seller_gouged_counts,
    }


fallback = compute_fallback_kpis(flat_products)

# --------------------------------------------------------
# KPI values: prefer meta if available, otherwise fallback
# --------------------------------------------------------
marketplace_health_score = meta.get(
    "marketplace_health_score", fallback.get("marketplace_health_score", "-")
)
skus_impacted = meta.get("skus_impacted", fallback.get("skus_impacted", 0))
gouging_rate = meta.get("gouging_rate", fallback.get("gouging_rate", 0.0))
avg_overprice_pct = meta.get(
    "avg_overprice_pct", fallback.get("avg_overprice_pct", 0.0)
)
max_overprice_pct = meta.get(
    "max_overprice_pct",
    fallback.get("max_overprice_pct", fallback.get("max_overprice_pct", 0.0)),
)
total_listings = meta.get("total_listings", fallback.get("total_listings", 0))
total_gouged_listings = meta.get(
    "total_gouged_listings", fallback.get("total_gouged_listings", 0)
)
fair_price_listings = meta.get("fair_price_listings", 0)
total_skus = meta.get("total_skus", fallback.get("total_skus", len(flat_products)))
unique_marketplace_sellers = meta.get(
    "total_unique_sellers_excluding_amazon_and_kind",
    fallback.get("unique_marketplace_sellers", 0),
)

# Outlier absolute markup fallback
max_abs_markup = meta.get("avg_overprice_abs", fallback.get("avg_overprice_abs", 0.0))
if meta.get("max_overprice_abs") is not None:
    max_abs_markup = meta.get("max_overprice_abs")

# Seller summaries (top violators)
seller_summary = meta.get("seller_gouging_summary", [])
if not seller_summary:
    seller_counts = fallback.get("seller_gouged_counts", {})
    seller_summary = sorted(
        [
            {"seller_name": k, "gouged_listings": v, "avg_overprice_pct": 0.0}
            for k, v in seller_counts.items()
        ],
        key=lambda x: x["gouged_listings"],
        reverse=True,
    )

top_violator = (
    seller_summary[0]
    if seller_summary
    else {"seller_name": "-", "gouged_listings": 0, "avg_overprice_pct": 0.0}
)

# Category summary table (prefer meta)
category_rows = meta.get("category_gouging_summary", [])
if not category_rows:
    cat_map = {}
    for p in flat_products:
        cat = p.get("category") or "Unknown"
        if cat not in cat_map:
            cat_map[cat] = {"total": 0, "gouged": 0, "pct_list": [], "abs_list": []}
        for s in p["seller_market"]:
            cat_map[cat]["total"] += 1
            upstream_flag = (s.get("price_flag") or "").strip().lower()
            if upstream_flag == "price gouging":
                cat_map[cat]["gouged"] += 1
            pct = s.get("price_delta_percent")
            absd = s.get("price_delta_abs")
            if pct is not None:
                try:
                    cat_map[cat]["pct_list"].append(float(pct))
                except:
                    pass
            if absd is not None:
                try:
                    cat_map[cat]["abs_list"].append(float(absd))
                except:
                    pass
    category_rows = []
    for cat, stt in cat_map.items():
        t = stt["total"]
        g = stt["gouged"]
        avg_pct = (
            (sum(stt["pct_list"]) / len(stt["pct_list"])) if stt["pct_list"] else 0.0
        )
        avg_abs = (
            (sum(stt["abs_list"]) / len(stt["abs_list"])) if stt["abs_list"] else 0.0
        )
        category_rows.append(
            {
                "category": cat,
                "total_listings": t,
                "gouged_listings": g,
                "gouging_rate": (g / t * 100) if t else 0.0,
                "avg_overprice_pct": avg_pct,
                "avg_overprice_abs": avg_abs,
            }
        )
    category_rows = sorted(category_rows, key=lambda x: x["gouging_rate"], reverse=True)


# --------------------------------------------------------
# KPI CARD HTML helper
# --------------------------------------------------------
def kpi_card(title, value, tooltip, subtitle=""):
    return f"""
    <div class="kpi-card" title="{tooltip}">
        <div class="kpi-title">{title}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub">{subtitle}</div>
    </div>
    """


# part2
# --------------------------------------------------------
# TOP: Operational KPIs (6 cards)
# --------------------------------------------------------
st.markdown("### Top: Operational KPIs")

c1, c2, c3, c4, c5, c6 = st.columns(6)

c1.markdown(
    kpi_card(
        "Marketplace Health Score",
        marketplace_health_score if marketplace_health_score is not None else "-",
        "Composite 0–100 risk score.",
    ),
    unsafe_allow_html=True,
)

c2.markdown(
    kpi_card(
        "Gouging Rate",
        f"{gouging_rate:.1f}%",
        "Gouged listings ÷ total listings × 100.",
        subtitle=f"{total_gouged_listings} / {total_listings}",
    ),
    unsafe_allow_html=True,
)

c3.markdown(
    kpi_card(
        "Avg Overprice (%)",
        f"+{avg_overprice_pct:.1f}%",
        "Average % markup across all marketplace listings.",
    ),
    unsafe_allow_html=True,
)

c4.markdown(
    kpi_card(
        "SKUs Impacted",
        skus_impacted,
        "SKUs with ≥1 detected gouged seller.",
        subtitle=f"{total_skus} total SKUs",
    ),
    unsafe_allow_html=True,
)

c5.markdown(
    kpi_card(
        "Total Listings",
        total_listings,
        "Total seller-ASIN offers scanned.",
        subtitle=f"{unique_marketplace_sellers} unique sellers",
    ),
    unsafe_allow_html=True,
)

# 🔥 NEW KPI CARD ADDED TO TOP ROW
c6.markdown(
    kpi_card(
        "Top Violator",
        top_violator.get("seller_name", "-"),
        "Seller with the highest gouged-listing count.",
        subtitle=f"{top_violator.get('gouged_listings', 0)} listings",
    ),
    unsafe_allow_html=True,
)

st.markdown("---")

# --------------------------------------------------------
# MIDDLE: Seller / Category Analytics (Side-By-Side)
# --------------------------------------------------------
st.markdown("### Middle: Seller & Category Analytics")

left, right = st.columns([1.2, 2])

# ---------------- LEFT: Top Violators Table ----------------
with left:
    st.markdown("#### Top Violators (table)")

    top_df = (
        pd.DataFrame(seller_summary[:15])
        if seller_summary
        else pd.DataFrame(
            columns=["seller_name", "gouged_listings", "avg_overprice_pct"]
        )
    )

    if not top_df.empty:
        top_df = top_df.sort_values("gouged_listings", ascending=False)
        st.dataframe(top_df, use_container_width=True)
    else:
        st.info("No violators detected in dataset.")

# ---------------- RIGHT: Category Gouging Table ----------------
with right:
    st.markdown("#### Category Gouging Rates")

    cat_df = pd.DataFrame(category_rows)

    if not cat_df.empty:
        cat_df = cat_df.sort_values("gouging_rate", ascending=False)
        st.dataframe(
            cat_df[
                [
                    "category",
                    "total_listings",
                    "gouged_listings",
                    "gouging_rate",
                    "avg_overprice_pct",
                ]
            ],
            use_container_width=True,
        )
    else:
        st.info("No category data available.")

st.markdown("---")
# --------------------------------------------------------
# BOTTOM: Outlier Risk (extremes & single-worst cases)
# --------------------------------------------------------
st.markdown("### Bottom: Outlier Risk (extremes & single-worst cases)")
o1, o2, o3 = st.columns(3)

o1.markdown(
    kpi_card(
        "Worst Overprice (%)",
        f"+{max_overprice_pct:.1f}%",
        "Maximum single listing % overprice across dataset.",
    ),
    unsafe_allow_html=True,
)

o2.markdown(
    kpi_card(
        "Max Absolute Markup ($)",
        (
            f"${max_abs_markup:.2f}"
            if isinstance(max_abs_markup, (int, float))
            else max_abs_markup
        ),
        "Max absolute markup (dataset or fallback).",
    ),
    unsafe_allow_html=True,
)


# function to find single worst listing by percent delta
def find_worst_listing(flat_products):
    worst = None
    for p in flat_products:
        for s in p.get("seller_market", []):
            pct = s.get("price_delta_percent")
            try:
                pctv = float(pct) if pct is not None else None
            except:
                pctv = None
            if pctv is not None:
                if worst is None or pctv > worst["pct"]:
                    worst = {
                        "pct": pctv,
                        "seller_name": s.get("seller_name"),
                        "asin": p.get("asin"),
                        "product_name": p.get("product_name"),
                        "seller_price": s.get("price"),
                        "amazon_price": (
                            s.get("amazon_price_listing")
                            if s.get("amazon_price_listing")
                            else None
                        ),
                    }
    return worst


worst_listing = find_worst_listing(flat_products)
if worst_listing:
    worst_sub = f"{worst_listing['seller_name']} — ASIN {worst_listing['asin']} (+{worst_listing['pct']:.1f}%)"
else:
    worst_sub = "No per-listing pct found in dataset."

o3.markdown(
    kpi_card(
        "Worst Seller Outlier",
        worst_listing["seller_name"] if worst_listing else "-",
        "Seller with the single highest percent overprice listing (if present).",
        subtitle=worst_sub,
    ),
    unsafe_allow_html=True,
)

st.markdown("---")

# --------------------------------------------------------
# KEEP the rest of your original UI (search/sort/pagination/product accordions)
# --------------------------------------------------------
# --------------------------------------------------------
# Search + Sort
# --------------------------------------------------------
col_search, col_sort = st.columns([3, 1])

with col_search:
    search_query = (
        st.text_input(
            "Search products by name / flavor / ASIN",
            placeholder="Type to search...",
        )
        .lower()
        .strip()
    )
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
            "Rating Count (High → Low)",
            "Rating Count (Low → High)",
            "Name (A → Z)",
            "Name (Z → A)",
        ],
    )


st.markdown("")

# --------------------------------------------------------
# Sidebar Filters
# --------------------------------------------------------
st.sidebar.header("Filters & Controls")

all_categories = sorted({p.get("category") or "Unknown" for p in flat_products})
category_choice = st.sidebar.selectbox(
    "Filter by Category", ["All Categories"] + all_categories
)

mp_filter = st.sidebar.radio(
    "Marketplace filter",
    ("All SKUs", "Only with marketplace sellers", "Only without marketplace sellers"),
)

max_seller_count = max(
    (len(s.get("seller_market") or []) for s in flat_products), default=0
)
seller_min, seller_max = st.sidebar.slider(
    "Marketplace seller count",
    0,
    max(20, max_seller_count),
    (0, max(20, max_seller_count)),
)

all_price_flags = sorted(
    {
        s.get("price_flag")
        for fam in data_families
        for s in (fam.get("seller_market") or [])
        if s.get("price_flag")
    }
)
pf_choice = st.sidebar.multiselect("Price flags", all_price_flags)

uniq_sellers = sorted(meta.get("unique_sellers_excluding_amazon_and_kind") or [])
seller_filter = st.sidebar.selectbox("Filter by seller", ["All Sellers"] + uniq_sellers)

rating_filter = st.sidebar.selectbox(
    "Filter by rating",
    ("All", "Excellent (>=90%)", "Good (75-89%)", "Mixed (50-74%)", "Poor (<50%)"),
)


# --------------------------------------------------------
# Filtering Logic
# --------------------------------------------------------
def get_tier(pct):
    if pct is None:
        return None
    try:
        pct = float(pct)
    except:
        return None
    if pct >= 90:
        return "Excellent (>=90%)"
    if pct >= 75:
        return "Good (75-89%)"
    if pct >= 50:
        return "Mixed (50-74%)"
    return "Poor (<50%)"


def sku_matches(sku):
    if category_choice != "All Categories" and sku.get("category") != category_choice:
        return False

    sku_has_mp = bool(sku.get("seller_market"))
    if mp_filter == "Only with marketplace sellers" and not sku_has_mp:
        return False
    if mp_filter == "Only without marketplace sellers" and sku_has_mp:
        return False

    if not (seller_min <= len(sku.get("seller_market") or []) <= seller_max):
        return False

    if pf_choice:
        flags = [s.get("price_flag") for s in (sku.get("seller_market") or [])]
        if not any(f in pf_choice for f in flags if f):
            return False

    if seller_filter != "All Sellers":
        sf = seller_filter.strip().lower()

        ms = sku.get("main_seller")
        main_name = (ms.get("seller_name") or "").strip().lower() if ms else ""

        mp_names = [
            (s.get("seller_name") or "").strip().lower()
            for s in (sku.get("seller_market") or [])
        ]

        if sf != main_name and sf not in mp_names:
            return False

    if rating_filter != "All":
        match = False
        for s in sku.get("seller_market") or []:
            if get_tier(s.get("positive_rating_percent")) == rating_filter:
                match = True
                break
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
        s
        for s in filtered
        if search_query in (s.get("product_name") or "").lower()
        or search_query in (s.get("flavor") or "").lower()
        or search_query in (s.get("asin") or "").lower()
    ]

# Sorting choices remain same
if sort_choice == "Price (Low → High)":
    filtered = sorted(filtered, key=lambda x: x.get("price") or 9999)

elif sort_choice == "Price (High → Low)":
    filtered = sorted(filtered, key=lambda x: -(x.get("price") or 0))

elif sort_choice == "Marketplace Sellers (High → Low)":
    filtered = sorted(
        filtered, key=lambda x: len(x.get("seller_market") or []), reverse=True
    )

elif sort_choice == "Marketplace Sellers (Low → High)":
    filtered = sorted(filtered, key=lambda x: len(x.get("seller_market") or []))

elif sort_choice == "Gouging (High → Low)":

    def worst_pct(p):
        vals = [
            s.get("price_delta_percent")
            for s in (p.get("seller_market") or [])
            if s.get("price_delta_percent") is not None
        ]
        try:
            return max([float(v) for v in vals]) if vals else -999
        except:
            return -999

    filtered = sorted(filtered, key=worst_pct, reverse=True)

elif sort_choice == "Name (A → Z)":
    filtered = sorted(filtered, key=lambda x: x.get("product_name") or "")

elif sort_choice == "Name (Z → A)":
    filtered = sorted(filtered, key=lambda x: x.get("product_name") or "", reverse=True)
elif sort_choice == "Rating Count (High → Low)":

    def max_rating_count(p):
        vals = [
            s.get("rating_count")
            for s in (p.get("seller_market") or [])
            if s.get("rating_count") is not None
        ]
        try:
            return max([int(v) for v in vals]) if vals else -1
        except:
            return -1

    filtered = sorted(filtered, key=max_rating_count, reverse=True)
elif sort_choice == "Rating Count (Low → High)":

    def min_rating_count(p):
        vals = [
            s.get("rating_count")
            for s in (p.get("seller_market") or [])
            if s.get("rating_count") is not None
        ]
        try:
            return min([int(v) for v in vals]) if vals else 9999999
        except:
            return 9999999

    filtered = sorted(filtered, key=min_rating_count)

# --------------------------------------------------------
# GROUP PRODUCTS BY TITLE (same product, different pack sizes)
# --------------------------------------------------------
grouped_products = group_same_products(filtered)

# --------------------------------------------------------
# Summary Display & Pagination
# --------------------------------------------------------
st.markdown(f"### Showing {len(filtered)} SKUs (after filters)")
st.markdown("")

# NOTE: pagination now applies to groups
page_size = st.selectbox("Items per page", [10, 20, 50, 100], index=0)
total_groups = max(1, len(grouped_products))
total_pages = max(1, (total_groups + page_size - 1) // page_size)

if "page" not in st.session_state:
    st.session_state.page = 1

if st.session_state.page > total_pages:
    st.session_state.page = total_pages

start = (st.session_state.page - 1) * page_size
end = start + page_size
page_groups = grouped_products[start:end]

st.markdown(f"**Page {st.session_state.page} of {total_pages}**")
st.markdown("---")

# --------------------------------------------------------
# Product Accordions (rendering grouped products)
# Each group becomes one accordion; pack-size SKUs shown inside
# --------------------------------------------------------
for group in page_groups:
    items = group.get("items", [])
    # derive combined header info from first item
    first = items[0] if items else {}
    mp_list_all = []
    for it in items:
        mp_list_all.extend(it.get("seller_market") or [])
    mp_count = len(mp_list_all)
    seller_badge_text, seller_badge_color = seller_count_badge(mp_count)

    # compute worst flag across all items
    flags = []
    for it in items:
        flags.extend(
            [
                s.get("price_flag")
                for s in (it.get("seller_market") or [])
                if s.get("price_flag")
            ]
        )
    flag_priority = {
        "Price Gouging": 4,
        "High Price": 3,
        "Slightly High": 2,
        "Fair Price": 1,
    }
    worst_flag = (
        sorted(flags, key=lambda f: flag_priority.get(f, 0), reverse=True)[0]
        if flags
        else None
    )
    pf_label, pf_color = price_flag_label(worst_flag)

    # header shows product_name and number of pack-size options
    header_title = f"{group.get('group_title') or first.get('product_name')} — {len(items)} pack(s)"
    # also show list of ASINs in small text
    asin_list = ", ".join([it.get("asin") for it in items if it.get("asin")])
    exp_title = f"{header_title} (ASINs: {asin_list})"

    header_html = f"""
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
      <div style="font-weight:700;color:{PRIMARY};">{header_title}</div>
      <div>
        <span class='badge' style='background:{seller_badge_color};margin-right:6px'>{seller_badge_text}</span>
        <span class='badge' style='background:{pf_color};'>{pf_label}</span>
      </div>
    </div>
    """

    with st.expander(exp_title, expanded=False):
        st.markdown(header_html, unsafe_allow_html=True)

        # show grouped product-level summary (first item's fields used as representative)
        st.markdown("### Product Summary")
        pd_summary = pd.DataFrame(
            [
                {
                    "product_name": group.get("group_title")
                    or first.get("product_name"),
                    "category": first.get("category"),
                    "representative_asin": first.get("asin"),
                    "pack_options": len(items),
                    "amazon_url": first.get("final_url") or "-",
                }
            ]
        )
        st.dataframe(pd_summary, use_container_width=True)

        # --------------------------------------------------------
        # NEW LOGIC: Split group into matching + missing items
        # --------------------------------------------------------
        matching_items = []
        missing_items = []

        for it in items:
            if sku_matches(it):
                matching_items.append(it)
            else:
                missing_items.append(it)

        # --------------------------------------------------------
        # Show ONLY matching SKUs (normal behavior)
        # --------------------------------------------------------
        for p in matching_items:
            st.markdown(f"#### Pack Option — ASIN: {p.get('asin')}")
            pd_details = pd.DataFrame(
                [
                    {
                        "asin": p.get("asin"),
                        "title": p.get("title"),
                        "price": format_price(p.get("price")),
                        "unit_price": format_price(p.get("unit_price")),
                        "prime": "Yes" if p.get("prime") else "No",
                        "flavor": p.get("flavor"),
                        "amazon_url": p.get("final_url") or "-",
                    }
                ]
            )
            st.dataframe(pd_details, use_container_width=True)

            # ---------- Main Seller ----------
            if p.get("main_seller"):
                st.markdown("**Main Seller**")
                ms = p.get("main_seller")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "seller_name": ms.get("seller_name"),
                                "ships_from": ms.get("ships_from"),
                                "authorized": (
                                    "Yes" if ms.get("is_authorized") else "No"
                                ),
                                "price": format_price(ms.get("price")),
                                "unit_price": format_price(ms.get("unit_price")),
                                "prime": "Yes" if ms.get("prime") else "No",
                            }
                        ]
                    ),
                    use_container_width=True,
                )
            else:
                st.info("No main seller found for this pack option.")

            # ---------- Marketplace Sellers ----------
            mp_list = p.get("seller_market") or []
            if mp_list:
                st.markdown("**Marketplace Sellers**")
                sellers_table = [
                    {
                        "seller_name": s.get("seller_name"),
                        "ships_from": s.get("ships_from"),
                        "authorized": "Yes" if s.get("is_authorized") else "No",
                        "price": format_price(s.get("price")),
                        "unit_price": format_price(s.get("unit_price")),
                        "price_delta": (
                            f"${float(s['price_delta_abs']):.2f}"
                            if s.get("price_delta_abs") is not None
                            else "-"
                        ),
                        "price_flag": s.get("price_flag"),
                        "rating_stars": s.get("rating_stars") or "-",
                        "rating_count": s.get("rating_count") or "-",
                        "positive_rating_percent": s.get("positive_rating_percent")
                        or "-",
                    }
                    for s in mp_list
                ]
                st.dataframe(pd.DataFrame(sellers_table), use_container_width=True)

                st.markdown("**Seller ratings (visual)**")
                for s in mp_list:
                    stars_html = rating_to_stars(s.get("rating_stars"))
                    st.markdown(
                        f"<div><b>{s.get('seller_name')}</b> — {stars_html} "
                        f"<span class='small-muted'>({s.get('rating_count') or '-'} ratings, "
                        f"{s.get('positive_rating_percent') or '-'}% positive)</span></div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No marketplace sellers found for this pack option.")

            st.markdown("---")

        # --------------------------------------------------------
        # SHOW MISSING VARIANTS (Option A1)
        # --------------------------------------------------------
        if missing_items:
            missing_asins = ", ".join(
                [m.get("asin") for m in missing_items if m.get("asin")]
            )

            if mp_filter == "Only with marketplace sellers":
                st.markdown(
                    f"🔸 This product has **{len(missing_items)} variants WITHOUT marketplace sellers**: {missing_asins}"
                )

            elif mp_filter == "Only without marketplace sellers":
                st.markdown(
                    f"🔸 This product has **{len(missing_items)} variants SOLD BY marketplace sellers**: {missing_asins}"
                )

# --------------------------------------------------------
# Bottom pagination buttons (works with group pagination)
# --------------------------------------------------------
st.markdown("---")
col_prev, col_mid, col_next = st.columns([1, 8, 1])

with col_prev:
    if st.button("⬅️ Previous") and st.session_state.page > 1:
        st.session_state.page -= 1

with col_next:
    if st.button("Next ➡️") and st.session_state.page < total_pages:
        st.session_state.page += 1
