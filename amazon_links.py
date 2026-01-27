from playwright.sync_api import sync_playwright, TimeoutError
from urllib.parse import urljoin
import json
import time
import random


SEARCH_URL = "https://www.amazon.com/s?k=trufru&rh=p_123%3A686917"
ZIP_CODE = "60601"
OUTPUT_FILE = "trufru_amazon_links.json"

# Remove TARGET_COUNT - we scrape everything available
MAX_PAGES = 100            # safety cap (increased for full scraping)
HEADLESS = False
SLOW_MO = 120              # slowdown (helps with Amazon)
NAV_TIMEOUT = 90000


def human_pause(a=0.8, b=1.8):
    time.sleep(random.uniform(a, b))


def wait_network(page, ms=30000):
    # networkidle can be flaky on Amazon; use best-effort
    try:
        page.wait_for_load_state("domcontentloaded", timeout=ms)
    except:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except:
        pass


def get_delivery_text(page) -> str:
    # This is the top header "Deliver to ..."
    try:
        t = page.locator("#glow-ingress-line2").inner_text(timeout=3000)
        return (t or "").strip()
    except:
        return ""


def set_zip_60601_verified(page, zip_code: str, max_attempts: int = 2) -> bool:
    """
    Attempts to set ZIP and verifies it by checking header delivery text contains the zip.
    Returns True if verified.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            # Open location popover
            page.click("#nav-global-location-popover-link", timeout=20000)
            human_pause(0.8, 1.5)

            # ZIP input variants
            zip_inputs = [
                "input#GLUXZipUpdateInput",
                "input[name='zipCode']",
            ]

            filled = False
            for sel in zip_inputs:
                try:
                    page.wait_for_selector(sel, timeout=8000)
                    page.fill(sel, zip_code)
                    filled = True
                    break
                except:
                    continue

            if not filled:
                # Sometimes Amazon shows "Sign in to see your address" — just give up
                try:
                    page.click("button:has-text('Continue')", timeout=3000)
                except:
                    pass

            human_pause(0.8, 1.4)

            # Apply / Update / Done variants
            apply_buttons = [
                "input#GLUXZipUpdate",
                "button:has-text('Apply')",
                "button:has-text('Done')",
            ]
            clicked = False
            for sel in apply_buttons:
                try:
                    page.click(sel, timeout=8000)
                    clicked = True
                    break
                except:
                    continue

            if clicked:
                human_pause(1.0, 2.0)

            # Close confirm if exists
            for sel in ["button#GLUXConfirmClose", "button:has-text('Continue')", "button:has-text('Done')"]:
                try:
                    page.click(sel, timeout=5000)
                    break
                except:
                    pass

            human_pause(1.0, 2.0)
            wait_network(page, 20000)

            # ✅ Verify delivery header reflects ZIP
            delivery = get_delivery_text(page)
            if zip_code in delivery:
                print(f"✅ ZIP applied: {delivery}")
                return True

            print(f"⚠️ ZIP not verified on attempt {attempt}. Delivery text: '{delivery}'")

        except Exception as e:
            print(f"⚠️ ZIP set attempt {attempt} failed: {e}")

        # Retry by re-opening the popover
        human_pause(1.5, 2.5)

    return False


def extract_cards(page) -> dict:
    """
    Extract product cards on the current page.
    Returns dict keyed by ASIN.
    """
    data = {}

    # Most stable selector for Amazon search results
    cards = page.query_selector_all("div[data-component-type='s-search-result'][data-asin]")
    # Sometimes Amazon puts results without that attribute; fallback:
    if not cards:
        cards = page.query_selector_all("div.s-result-item[data-asin]")

    for card in cards:
        asin = (card.get_attribute("data-asin") or "").strip()
        if not asin:
            continue
        if asin in data:
            continue

        # title (brand line in your output was "Tru Fru"; we want product title)
        title_el = card.query_selector("h2 span")
        title = title_el.inner_text().strip() if title_el else None

        # product url
        link_el = card.query_selector("a.a-link-normal.s-no-outline")
        rel = link_el.get_attribute("href") if link_el else None
        product_url = urljoin("https://www.amazon.com", rel) if rel else None

        # price (can be null on some listings)
        price_el = card.query_selector("span.a-price > span.a-offscreen")
        price = price_el.inner_text().strip() if price_el else None

        # rating / reviews
        rating_el = card.query_selector("span.a-icon-alt")
        rating = rating_el.inner_text().strip() if rating_el else None

        reviews_el = card.query_selector("a[href*='#customerReviews'] span.a-size-base, span.a-size-mini")
        reviews_count = None
        if reviews_el:
            txt = reviews_el.inner_text().strip()
            reviews_count = txt.strip("()") if txt else None

        img_el = card.query_selector("img.s-image")
        image = img_el.get_attribute("src") if img_el else None

        data[asin] = {
            "asin": asin,
            "title": title,
            "product_url": product_url,
            "price": price,
            "rating": rating,
            "reviews_count": reviews_count,
            "image": image,
        }

    return data


def slow_scroll_a_bit(page):
    # Helps trigger any lazy content without relying on infinite scroll
    for _ in range(3):
        page.mouse.wheel(0, random.randint(1200, 2200))
        human_pause(0.8, 1.6)


def goto_and_wait_results(page, url: str):
    page.goto(url, timeout=NAV_TIMEOUT)
    wait_network(page, 30000)

    # Wait for any results marker
    selectors = [
        "div[data-component-type='s-search-result'][data-asin]",
        "div.s-result-item[data-asin]",
        "span:has-text('results')",
    ]
    ok = False
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=20000)
            ok = True
            break
        except:
            continue
    if not ok:
        # Save screenshot for debugging if blocked/captcha
        page.screenshot(path="amazon_no_results.png")
        raise RuntimeError("Amazon results not visible. Saved screenshot: amazon_no_results.png")


def click_next_page(page) -> bool:
    """
    Clicks next page if available.
    Returns True if navigated, False if no next.
    """
    # Amazon next button selectors
    next_sel = "a.s-pagination-next"
    try:
        next_btn = page.locator(next_sel)
        if next_btn.count() == 0:
            return False

        # If disabled, it has 's-pagination-disabled'
        class_attr = next_btn.get_attribute("class") or ""
        if "s-pagination-disabled" in class_attr:
            return False

        # Click and wait
        next_btn.click(timeout=15000)
        wait_network(page, 30000)
        human_pause(1.0, 2.0)
        return True
    except:
        return False


def scrape_amazon_search():
    collected = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        context = browser.new_context(
            locale="en-US",
            timezone_id="America/Chicago",
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # 1) Open Amazon home
        page.goto("https://www.amazon.com", timeout=NAV_TIMEOUT)
        wait_network(page, 20000)
        human_pause(1.0, 2.0)

        # 2) Set ZIP and VERIFY
        ok_zip = set_zip_60601_verified(page, ZIP_CODE, max_attempts=3)
        if not ok_zip:
            print("⚠️ ZIP could not be verified. Continuing anyway (scrape may still work).")

        # 3) Go to search
        goto_and_wait_results(page, SEARCH_URL)

        # 4) Collect across ALL pages until Next button disappears
        page_idx = 1
        while True:
            human_pause(1.2, 2.2)
            slow_scroll_a_bit(page)

            page_data = extract_cards(page)
            for asin, item in page_data.items():
                if asin not in collected:
                    collected[asin] = item

            print(f"📄 Page {page_idx}: collected total {len(collected)}")

            # Safety check to prevent infinite loops
            if page_idx >= MAX_PAGES:
                print(f"⚠️ Reached MAX_PAGES safety limit ({MAX_PAGES}). Stopping.")
                break

            page_idx += 1

            # Stop ONLY when Next is not available
            if not click_next_page(page):
                print("🛑 No more pages. Scraping complete.")
                break

        browser.close()

    # Return ALL collected products (no slicing)
    return list(collected.values())


if __name__ == "__main__":
    data = scrape_amazon_search()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Scraped {len(data)} products")
    print(f"📁 Saved to {OUTPUT_FILE}")
