#!/usr/bin/env python3
"""
Kolesa.kz listings parser — Kazakhstan auto marketplace.

No Apify. No official API key.

Data path
---------
1) Search HTML:
      https://kolesa.kz/cars/{city}/?page=N
   → advert ids (/a/show/{id})

2) Detail HTML:
      https://kolesa.kz/a/show/{id}
   → title, price, params table, phonePrefix

3) Phones (required by default):
      Browser (Playwright) opens the detail page with session cookies,
      clicks «Показать телефон», intercepts:

        GET https://app.kolesa.kz/adverts/{id}/phones?captchaTokenV3=…&source=advert

      reCAPTCHA v3 is executed by the real browser (not bypassed).
      Requires: pip install playwright && playwright install chromium
      Optional: KOLESA_COOKIE for a logged-in session (recommended).

Usage:
    python kolesa_parser.py --city almaty --pages 1 --max 10
    KOLESA_COOKIE="klssid=…; kumd=…" python kolesa_parser.py --city astana --max 20
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from html import unescape
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.http import HttpClient, HttpError  # noqa: E402
from core.models import normalize_phone  # noqa: E402

SOURCE = "kolesa"
ORIGIN = "https://kolesa.kz"
APP_ORIGIN = "https://app.kolesa.kz"

DEFAULT_CITIES = ["almaty", "astana", "shymkent", "karaganda", "aktobe"]

CITY_NAMES = {
    "almaty": "Алматы",
    "astana": "Астана",
    "nur-sultan": "Астана",
    "shymkent": "Шымкент",
    "karaganda": "Караганда",
    "aktobe": "Актобе",
    "atyrau": "Атырау",
    "pavlodar": "Павлодар",
    "semey": "Семей",
    "ust-kamenogorsk": "Усть-Каменогорск",
    "kostanay": "Костанай",
    "kyzylorda": "Кызылорда",
    "taraz": "Тараз",
    "uralsk": "Уральск",
    "aktau": "Актау",
    "petropavlovsk": "Петропавловск",
    "kokshetau": "Кокшетау",
    "taldykorgan": "Талдыкорган",
}

CSV_FIELDS = [
    "source",
    "phone",
    "phone2",
    "phone_preview",
    "title",
    "city",
    "price_kzt",
    "year",
    "mileage_km",
    "body",
    "engine",
    "transmission",
    "drive",
    "steering",
    "color",
    "customs_kz",
    "generation",
    "listing_id",
    "url",
    "description",
    "owner_id",
]


def _clean(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_cookie_header(cookie: str) -> List[Dict[str, Any]]:
    """Convert Cookie request header into Playwright cookie dicts."""
    out: List[Dict[str, Any]] = []
    if not cookie:
        return out
    for part in cookie.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "value": value,
                "domain": ".kolesa.kz",
                "path": "/",
            }
        )
    return out


# --- list / detail HTTP ------------------------------------------------------
def extract_list_ids(html: str) -> List[str]:
    ids = re.findall(r'data-id=["\'](\d+)["\']', html)
    ids += re.findall(r"/a/show/(\d+)", html)
    # drop tiny non-listing ids if any
    return list(dict.fromkeys(i for i in ids if len(i) >= 6))


def build_list_url(section: str, city: str, page: int) -> str:
    base = f"{ORIGIN}/{section.strip('/')}/{city.strip('/')}/"
    if page <= 1:
        return base
    return base + f"?page={page}"


def fetch_list_ids(
    client: HttpClient, section: str, city: str, page: int
) -> List[str]:
    url = build_list_url(section, city, page)
    html = client.get(url, accept="text/html", referer=f"{ORIGIN}/")
    return extract_list_ids(html)


def extract_var_data(html: str) -> Optional[Dict[str, Any]]:
    m = re.search(r"var data\s*=\s*(\{)", html)
    if not m:
        return None
    start = m.start(1)
    depth = 0
    instr = False
    esc = False
    for i in range(start, len(html)):
        c = html[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            instr = not instr
            continue
        if instr:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def extract_params_table(html: str) -> Dict[str, str]:
    pairs = re.findall(
        r'<dt[^>]*class="value-title"[^>]*>\s*(.*?)\s*</dt>\s*<dd[^>]*>\s*(.*?)\s*</dd>',
        html,
        re.S | re.I,
    )
    out: Dict[str, str] = {}
    for k, v in pairs:
        key = _clean(k).rstrip(":").replace("\xa0", " ").strip()
        # strip trailing nbsp artifacts
        key = key.replace("&nbsp;", " ").strip()
        out[key] = _clean(v)
    return out


def extract_price(html: str) -> Any:
    m = re.search(r'class="offer__price"[^>]*>(.*?)</div>', html, re.S | re.I)
    if not m:
        return ""
    digits = re.sub(r"\D", "", _clean(m.group(1)))
    return int(digits) if digits else ""


def extract_title(html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    return _clean(m.group(1)) if m else ""


def extract_description(html: str) -> str:
    m = re.search(
        r'class="[^"]*offer__description[^"]*"[^>]*>(.*?)</div>',
        html,
        re.S | re.I,
    )
    if not m:
        m = re.search(r'itemprop="description"[^>]*>(.*?)<', html, re.S | re.I)
    return _clean(m.group(1))[:600] if m else ""


def parse_mileage(val: str) -> Any:
    digits = re.sub(r"\D", "", val or "")
    return int(digits) if digits else ""


def parse_year_from_title(title: str) -> Any:
    m = re.search(r"(19|20)\d{2}", title or "")
    return int(m.group(0)) if m else ""


def normalize_listing(
    *,
    listing_id: str,
    html: str,
    var_data: Optional[Dict[str, Any]] = None,
    phones: Optional[List[str]] = None,
    fallback_city: str = "",
    keep_raw: bool = True,
) -> Dict[str, Any]:
    params = extract_params_table(html)
    title = extract_title(html)
    price = extract_price(html)
    desc = extract_description(html)

    advert = (var_data or {}).get("advert") or {}
    if not title:
        title = advert.get("title") or ""
    phone_preview = advert.get("phonePrefix") or ""
    owner_id = advert.get("userId") or ""

    city = params.get("Город") or fallback_city
    # "Алматы, Алматинская область" → city first part
    if city and "," in city:
        city = city.split(",", 1)[0].strip()

    year = parse_year_from_title(title)
    gen = params.get("Поколение") or ""
    if not year and gen:
        m = re.search(r"(19|20)\d{2}", gen)
        if m:
            year = int(m.group(0))

    nums = [n for n in (normalize_phone(p) for p in (phones or [])) if n]
    seen = set()
    uniq: List[str] = []
    for n in nums:
        if n not in seen:
            seen.add(n)
            uniq.append(n)

    row: Dict[str, Any] = {
        "source": SOURCE,
        "phone": uniq[0] if uniq else "",
        "phone2": uniq[1] if len(uniq) > 1 else "",
        "phones": uniq,
        "phone_preview": phone_preview,
        "title": title,
        "name": title,
        "city": city,
        "price_kzt": price,
        "year": year,
        "mileage_km": parse_mileage(params.get("Пробег", "")),
        "body": params.get("Кузов") or "",
        "engine": params.get("Объем двигателя, л") or params.get("Объём двигателя, л") or "",
        "transmission": params.get("Коробка передач") or "",
        "drive": params.get("Привод") or "",
        "steering": params.get("Руль") or "",
        "color": params.get("Цвет") or "",
        "customs_kz": params.get("Растаможен в Казахстане") or "",
        "generation": gen,
        "listing_id": str(listing_id),
        "place_id": str(listing_id),
        "url": f"{ORIGIN}/a/show/{listing_id}",
        "description": desc,
        "owner_id": owner_id,
        "category": "cars",
        "params": params,
    }
    if keep_raw:
        row["raw"] = {
            "advert": advert,
            "params": params,
            "phones_api": phones,
        }
    return row


def fetch_detail(client: HttpClient, listing_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    url = f"{ORIGIN}/a/show/{listing_id}"
    html = client.get(url, accept="text/html", referer=f"{ORIGIN}/")
    return html, extract_var_data(html)


# --- phones via Playwright ---------------------------------------------------
def fetch_phones_playwright(
    listing_id: str,
    *,
    cookie: str = "",
    headless: bool = True,
    timeout_ms: int = 45000,
) -> List[str]:
    """Open detail page, click show-phones, intercept app.kolesa.kz phones API.

    reCAPTCHA v3 is handled inside Chromium (normal site flow), not bypassed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is required for Kolesa phones.\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from e

    url = f"{ORIGIN}/a/show/{listing_id}"
    phones: List[str] = []

    def _add_phones(raw_list: Any) -> None:
        if not isinstance(raw_list, list):
            return
        for ph in raw_list:
            n = normalize_phone(ph)
            if n and len(re.sub(r"\D", "", n)) >= 11 and n not in phones:
                phones.append(n)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
            ),
        )
        cookies = parse_cookie_header(cookie)
        if cookies:
            context.add_cookies(cookies)

        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_selector(
                '[data-test="show-seller-phones-button"], .seller-phones__show-button, .js__seller-phones',
                timeout=20000,
            )
        except Exception:
            pass

        def _click_show() -> bool:
            for sel in (
                '[data-test="show-seller-phones-button"]',
                "button.seller-phones__show-button",
                ".seller-phones__show-button",
                "text=Показать телефон",
                "text=Показать телефоны",
            ):
                try:
                    loc = page.locator(sel).first
                    if loc.count() == 0:
                        continue
                    loc.click(timeout=5000, force=True)
                    return True
                except Exception:
                    continue
            try:
                page.evaluate(
                    """() => {
                    const b = document.querySelector('[data-test="show-seller-phones-button"]')
                        || document.querySelector('.seller-phones__show-button');
                    if (b) { b.click(); return true; }
                    return false;
                }"""
                )
                return True
            except Exception:
                return False

        # Prefer waiting on the real phones API (includes captchaTokenV3 from page JS).
        try:
            with page.expect_response(
                lambda r: f"/adverts/{listing_id}/phones" in r.url and r.request.method == "GET",
                timeout=timeout_ms,
            ) as resp_info:
                _click_show()
            resp = resp_info.value
            if resp.status == 200:
                try:
                    data = resp.json()
                    _add_phones(data.get("phones") if isinstance(data, dict) else None)
                except Exception:
                    pass
        except Exception:
            _click_show()
            page.wait_for_timeout(4000)

        # DOM fallback if network intercept missed the payload
        if not phones:
            deadline = time.time() + 12
            while time.time() < deadline and not phones:
                try:
                    tels = page.eval_on_selector_all(
                        'a[href^="tel:"], .seller-phones__phones-list li, [data-test="seller-phones"] li',
                        "els => els.map(e => e.getAttribute('href') || e.textContent || '')",
                    )
                    for t in tels or []:
                        t = (t or "").replace("tel:", "").strip()
                        n = normalize_phone(t)
                        if n and len(re.sub(r"\D", "", n)) >= 11 and n not in phones:
                            phones.append(n)
                except Exception:
                    pass
                if phones:
                    break
                page.wait_for_timeout(500)

        browser.close()

    return phones


# --- output ------------------------------------------------------------------
def dump_rows(rows: Dict[str, Dict[str, Any]], out_base: str, keep_raw: bool) -> None:
    data = list(rows.values())
    if not keep_raw:
        for r in data:
            r.pop("raw", None)
            r.pop("params", None)

    parent = os.path.dirname(os.path.abspath(out_base + ".json"))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    with open(out_base + ".json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    with open(out_base + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CSV_FIELDS)
        for r in data:
            w.writerow([r.get(k, "") for k in CSV_FIELDS])


# --- CLI ---------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kolesa.kz auto listings parser (HTTP metadata + Playwright phones)",
    )
    p.add_argument(
        "--section",
        default=os.environ.get("SECTION", "cars"),
        help="URL section (default: cars)",
    )
    p.add_argument(
        "-c",
        "--city",
        action="append",
        dest="cities",
        default=None,
        help="city slug (repeatable). Also CITIES=almaty,astana",
    )
    p.add_argument("--pages", type=int, default=int(os.environ.get("PAGES", "2")))
    p.add_argument("--max", type=int, default=int(os.environ.get("MAX", "50")))
    p.add_argument("--out", default=os.environ.get("OUT", "output/kolesa_listings"))
    p.add_argument("--proxy", default=os.environ.get("PROXY", ""))
    p.add_argument("--timeout", type=float, default=float(os.environ.get("TIMEOUT", "30")))
    p.add_argument("--retries", type=int, default=int(os.environ.get("RETRIES", "4")))
    p.add_argument("--sleep", type=float, default=float(os.environ.get("SLEEP", "0.5")))
    p.add_argument(
        "--cookie",
        default=os.environ.get("KOLESA_COOKIE", ""),
        help="browser Cookie header (klssid + kumd recommended)",
    )
    p.add_argument(
        "--no-phones",
        action="store_true",
        help="metadata only (phones are required by default)",
    )
    p.add_argument(
        "--headed",
        action="store_true",
        help="show browser window while fetching phones",
    )
    p.add_argument("--raw", dest="keep_raw", action="store_true", default=True)
    p.add_argument("--no-raw", dest="keep_raw", action="store_false")
    return p.parse_args(argv)


def resolve_cities(cli: Optional[List[str]]) -> List[str]:
    if cli:
        return [c.strip().lower() for c in cli if c.strip()]
    env = os.environ.get("CITIES", "")
    if env:
        return [c.strip().lower() for c in env.split(",") if c.strip()]
    return list(DEFAULT_CITIES)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    cities = resolve_cities(args.cities)
    cookie = (args.cookie or "").strip()
    want_phones = not args.no_phones

    print("Kolesa.kz parser — HTTP metadata + Playwright phones")
    print(f"section={args.section} cities={cities} pages={args.pages} max/city={args.max}")
    if want_phones:
        print("phones: ON (Playwright + app.kolesa.kz /adverts/{id}/phones + reCAPTCHA v3 in browser)")
        if cookie:
            print("session: KOLESA_COOKIE set")
        else:
            print("session: no cookie (browser guest; login cookie recommended)")
    else:
        print("phones: OFF (--no-phones)")

    if want_phones:
        try:
            import playwright  # noqa: F401
        except ImportError:
            print(
                "\nERROR: phones are required but Playwright is not installed.\n"
                "  pip install playwright\n"
                "  playwright install chromium\n"
                "Or pass --no-phones for metadata-only."
            )
            raise SystemExit(2)

    client = HttpClient(
        timeout=args.timeout,
        retries=args.retries,
        proxy=args.proxy,
        sleep_base=max(args.sleep, 0.2),
        cookie=cookie,
    )

    rows: Dict[str, Dict[str, Any]] = {}
    phones_ok = 0
    phones_fail = 0

    for city in cities:
        display = CITY_NAMES.get(city, city)
        print(f"[{display} / {city}] …")
        ids: List[str] = []
        for page in range(1, args.pages + 1):
            try:
                batch = fetch_list_ids(client, args.section, city, page)
            except HttpError as e:
                print(f"    list page {page} error: {e}")
                break
            if not batch:
                print(f"    page {page}: empty")
                break
            new = [i for i in batch if i not in ids]
            ids.extend(new)
            print(f"    page {page}: +{len(new)} ids (bag={len(ids)})")
            if len(ids) >= args.max:
                ids = ids[: args.max]
                break
            time.sleep(args.sleep)

        city_new = 0
        for n, lid in enumerate(ids, 1):
            if lid in rows:
                continue
            try:
                html, var_data = fetch_detail(client, lid)
            except HttpError as e:
                print(f"    detail {lid} error: {e}")
                time.sleep(args.sleep)
                continue

            phone_list: List[str] = []
            if want_phones:
                try:
                    phone_list = fetch_phones_playwright(
                        lid,
                        cookie=cookie,
                        headless=not args.headed,
                    )
                    if phone_list:
                        phones_ok += 1
                    else:
                        phones_fail += 1
                        print(f"    {lid}: phones empty")
                except Exception as e:
                    phones_fail += 1
                    print(f"    {lid}: phones error: {e}")

            row = normalize_listing(
                listing_id=lid,
                html=html,
                var_data=var_data,
                phones=phone_list,
                fallback_city=display,
                keep_raw=args.keep_raw,
            )
            # skip listings without phone when phones required
            if want_phones and not row.get("phone"):
                print(f"    {lid}: skipped (no phone)")
                time.sleep(args.sleep)
                continue

            rows[lid] = row
            city_new += 1
            print(
                f"    {lid}: phone={row.get('phone')!r} | {row.get('price_kzt')} ₸ | "
                f"{row.get('title')}"
            )
            if n % 5 == 0:
                dump_rows(rows, args.out, args.keep_raw)
            time.sleep(args.sleep)

        print(f"[{display}] +{city_new} | total={len(rows)}")
        dump_rows(rows, args.out, args.keep_raw)

    dump_rows(rows, args.out, args.keep_raw)
    print(
        f"\nDone: {len(rows)} listings -> {args.out}.csv / {args.out}.json"
        f"\n  phones ok={phones_ok} fail={phones_fail}"
    )


if __name__ == "__main__":
    main()
