#!/usr/bin/env python3
"""
Krisha.kz listings parser — Kazakhstan real-estate (sale / rent) via Direct HTTP.

No Apify. No official API key.

Data path
---------
1) Search HTML list pages:
      https://krisha.kz/{deal}/{type}/{city}/?page=N
   → product ids (`data-product-id`)

2) Detail pages:
      https://krisha.kz/a/show/{id}
   → embedded `window.data` (jsdata) with full listing metadata

3) Phones (logged-in session):
   The UI shows «Показать телефон», but with a real krisha.kz login the
   detail HTML already embeds full numbers:

      window.data.adverts[0].phones == ["+7 778 046 4438"]

   Set KRISHA_COOKIE to the Cookie header from a logged-in browser
   (must include krssid + kumd). Without cookie only phone_preview is public.

   Fallback GET /a/ajaxPhones?id= often returns reCAPTCHA even when logged in;
   we do not solve captchas.

Usage:
    python krisha_parser.py --deal arenda --type kvartiry --city almaty --pages 2
    KRISHA_COOKIE="krssid=...; kumd=..." python krisha_parser.py --city astana --max 50
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from html import unescape
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.http import HttpClient, HttpError  # noqa: E402
from core.models import normalize_phone  # noqa: E402

SOURCE = "krisha"
ORIGIN = "https://krisha.kz"

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
    "district",
    "address",
    "price_kzt",
    "rooms",
    "area_m2",
    "floor",
    "floors_total",
    "owner_name",
    "owner_type",
    "deal_type",
    "property_type",
    "latitude",
    "longitude",
    "listing_id",
    "url",
    "description",
]


# --- HTML / JSON helpers -----------------------------------------------------
def extract_window_data(html: str) -> Optional[Dict[str, Any]]:
    """Parse `window.data = {...}` from the show-page jsdata script."""
    m = re.search(r"window\.data\s*=\s*(\{)", html)
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


def extract_list_ids(html: str) -> List[str]:
    return list(dict.fromkeys(re.findall(r'data-product-id=["\'](\d+)["\']', html)))


def parse_floor_pair(title: str) -> Tuple[Any, Any]:
    """Parse '10/14 этаж' → (10, 14)."""
    m = re.search(r"(\d+)\s*/\s*(\d+)\s*этаж", title or "", re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    return "", ""


def _clean_text(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def address_from_advert(advert: Dict[str, Any], ad0: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return city, district, address line."""
    city = ""
    district = ""
    address = advert.get("addressTitle") or ""

    addr = advert.get("address") or {}
    if isinstance(addr, dict):
        # slugs → display if we can
        city_slug = (addr.get("city") or "").lower()
        city = CITY_NAMES.get(city_slug, addr.get("city") or "")
        district = addr.get("district") or ""

    if ad0.get("fullAddress"):
        address = _clean_text(str(ad0["fullAddress"])) or address
    if ad0.get("city"):
        c = ad0["city"]
        if isinstance(c, str) and c.strip():
            # Prefer human-readable city from listing card payload.
            city = c.strip()
        elif isinstance(c, dict):
            city = c.get("name") or city
    if ad0.get("address") and isinstance(ad0["address"], str):
        address = address or _clean_text(ad0["address"])

    # Prefer human district from fullAddress: "Алматы, Медеуский р-н, …"
    if address and "," in address:
        parts = [p.strip() for p in address.split(",") if p.strip()]
        if len(parts) >= 2 and ("р-н" in parts[1].lower() or "район" in parts[1].lower()):
            district = parts[1]
    # prettify leftover slugs
    if district and re.search(r"[_-]", district) and "р-н" not in district.lower():
        district = district.replace("_", " ").replace("-", " ")

    return city, district, address


def normalize_listing(
    data: Dict[str, Any],
    *,
    fallback_city: str = "",
    deal_type: str = "",
    property_type: str = "",
    phones: Optional[List[str]] = None,
    keep_raw: bool = True,
) -> Dict[str, Any]:
    advert = data.get("advert") or {}
    adverts = data.get("adverts") or []
    ad0 = adverts[0] if adverts and isinstance(adverts[0], dict) else {}

    listing_id = str(advert.get("id") or ad0.get("id") or "")
    title = advert.get("title") or ad0.get("title") or ""
    price = advert.get("price")
    if price is None:
        price = ad0.get("price")
    if isinstance(price, str):
        digits = re.sub(r"\D", "", _clean_text(price))
        price = int(digits) if digits else ""
    rooms = advert.get("rooms") if advert.get("rooms") is not None else ""
    area = advert.get("square") if advert.get("square") is not None else ""
    floor, floors_total = parse_floor_pair(title)

    city, district, address = address_from_advert(advert, ad0)
    if not city:
        city = fallback_city

    mp = advert.get("map") or {}
    lat = mp.get("lat", "")
    lon = mp.get("lon", "")

    contacts = ad0.get("contactsInfo") or {}
    phone_preview = contacts.get("phonePreview") or ""

    owner = ad0.get("owner") or {}
    owner_name = (advert.get("ownerName") or owner.get("title") or "").strip()
    owner_type = advert.get("userType") or ""
    if not owner_type and isinstance(owner.get("label"), dict):
        owner_type = owner["label"].get("name") or owner["label"].get("title") or ""

    desc = ad0.get("description") or ""
    if isinstance(desc, str):
        desc = _clean_text(desc)[:500]

    deal = deal_type or advert.get("sectionAlias") or ""
    ptype = property_type or advert.get("categoryAlias") or ""

    # Phones may already be present in SSR when the session is logged in
    # (UI still shows "Показать телефон", but window.data has adverts[].phones).
    page_phones: List[Any] = []
    for src in (ad0.get("phones"), advert.get("phones"), contacts.get("phones")):
        if isinstance(src, list):
            page_phones.extend(src)
        elif isinstance(src, str) and src.strip():
            page_phones.append(src)
    merged_phones: List[Any] = list(page_phones)
    if phones:
        merged_phones.extend(phones)

    nums = [n for n in (normalize_phone(p) for p in merged_phones) if n]
    # de-dup preserve order
    seen = set()
    uniq = []
    for n in nums:
        if n not in seen:
            seen.add(n)
            uniq.append(n)

    url = f"{ORIGIN}/a/show/{listing_id}" if listing_id else ""

    row: Dict[str, Any] = {
        "source": SOURCE,
        "phone": uniq[0] if uniq else "",
        "phone2": uniq[1] if len(uniq) > 1 else "",
        "phones": uniq,
        "phone_preview": phone_preview.strip(),
        "title": title,
        "name": title,  # alias for unified dumps that expect name
        "city": city,
        "district": district,
        "address": address,
        "price_kzt": price if price is not None else "",
        "rooms": rooms,
        "area_m2": area,
        "floor": floor,
        "floors_total": floors_total,
        "owner_name": owner_name,
        "owner_type": owner_type,
        "deal_type": deal,
        "property_type": ptype,
        "category": f"{deal}/{ptype}".strip("/"),
        "latitude": lat,
        "longitude": lon,
        "listing_id": listing_id,
        "place_id": listing_id,
        "url": url,
        "description": desc,
        "posted": ad0.get("addedAt") or ad0.get("createdAt") or "",
    }
    if keep_raw:
        # keep advert + contacts, drop huge paidServices trees if present
        raw_adv = dict(advert)
        raw_ad0 = {k: v for k, v in ad0.items() if k not in ("paidServices", "photo", "photos")}
        row["raw"] = {"advert": raw_adv, "listing": raw_ad0, "phones_response": phones}
    return row


def parse_phones_response(body: str) -> List[str]:
    """Normalize various ajaxPhones JSON shapes into phone strings."""
    if not body or not body.strip().startswith(("{", "[")):
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []

    found: List[str] = []

    def collect(obj: Any) -> None:
        if isinstance(obj, str):
            if any(ch.isdigit() for ch in obj) and len(re.sub(r"\D", "", obj)) >= 10:
                found.append(obj)
        elif isinstance(obj, dict):
            # common keys
            for k in ("phones", "phone", "numbers", "data", "items", "result"):
                if k in obj:
                    collect(obj[k])
            for k, v in obj.items():
                if k in ("error", "message", "status"):
                    continue
                if isinstance(v, (dict, list)):
                    collect(v)
                elif isinstance(v, str) and "phone" in k.lower():
                    collect(v)
        elif isinstance(obj, list):
            for it in obj:
                collect(it)

    collect(data)
    # unique normalized later by caller
    return found


# --- fetch layer -------------------------------------------------------------
def build_list_url(deal: str, ptype: str, city: str, page: int) -> str:
    base = f"{ORIGIN}/{deal.strip('/')}/{ptype.strip('/')}/{city.strip('/')}/"
    if page <= 1:
        return base
    return base + f"?page={page}"


def fetch_list_ids(client: HttpClient, deal: str, ptype: str, city: str, page: int) -> List[str]:
    url = build_list_url(deal, ptype, city, page)
    html = client.get(url, accept="text/html,application/xhtml+xml", referer=f"{ORIGIN}/")
    return extract_list_ids(html)


def fetch_detail(client: HttpClient, listing_id: str) -> Optional[Dict[str, Any]]:
    url = f"{ORIGIN}/a/show/{listing_id}"
    html = client.get(url, accept="text/html", referer=f"{ORIGIN}/")
    return extract_window_data(html)


def fetch_phones(client: HttpClient, listing_id: str) -> Tuple[List[str], str]:
    """Return (phones, status_note). status_note is 'ok'|'auth_required'|'error'|…"""
    url = f"{ORIGIN}/a/ajaxPhones?id={urllib.parse.quote(str(listing_id))}"
    try:
        body = client.get(
            url,
            accept="application/json, text/javascript, */*; q=0.01",
            referer=f"{ORIGIN}/a/show/{listing_id}",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
    except HttpError as e:
        if e.status == 403:
            return [], "auth_required"
        if e.status == 401:
            return [], "auth_required"
        return [], f"http_{e.status}"
    phones = parse_phones_response(body)
    if not phones and "автор" in body.lower():
        return [], "auth_required"
    if not phones and '"error"' in body:
        return [], "error"
    # Logged-in but captcha gate on the click endpoint.
    if not phones and ("gRecaptcha" in body or "recaptcha" in body.lower()):
        return [], "captcha_required"
    return phones, "ok" if phones else "empty"


# --- main loop ---------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Krisha.kz listings parser (Direct HTTP; phones need KRISHA_COOKIE)",
    )
    p.add_argument("--deal", default=os.environ.get("DEAL", "arenda"), help="arenda | prodazha")
    p.add_argument(
        "--type",
        dest="property_type",
        default=os.environ.get("TYPE", "kvartiry"),
        help="kvartiry | doma | …",
    )
    p.add_argument(
        "-c",
        "--city",
        action="append",
        dest="cities",
        default=None,
        help="city slug (repeatable). Also CITIES=almaty,astana",
    )
    p.add_argument("--pages", type=int, default=int(os.environ.get("PAGES", "3")), help="list pages per city")
    p.add_argument("--max", type=int, default=int(os.environ.get("MAX", "100")), help="max listings total per city")
    p.add_argument("--out", default=os.environ.get("OUT", "output/krisha_listings"))
    p.add_argument("--proxy", default=os.environ.get("PROXY", ""))
    p.add_argument("--timeout", type=float, default=float(os.environ.get("TIMEOUT", "30")))
    p.add_argument("--retries", type=int, default=int(os.environ.get("RETRIES", "4")))
    p.add_argument("--sleep", type=float, default=float(os.environ.get("SLEEP", "0.45")))
    p.add_argument(
        "--cookie",
        default=os.environ.get("KRISHA_COOKIE", ""),
        help="browser Cookie header after login (required for full phones)",
    )
    p.add_argument(
        "--skip-phones",
        action="store_true",
        help="do not call ajaxPhones (metadata + phone_preview only)",
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


def dump_rows(rows: Dict[str, Dict[str, Any]], out_base: str, keep_raw: bool) -> None:
    """Write CSV/JSON; adapt Place dump by writing dicts directly."""
    data = list(rows.values())
    if not keep_raw:
        for r in data:
            r.pop("raw", None)

    parent = os.path.dirname(os.path.abspath(out_base + ".json"))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    with open(out_base + ".json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    import csv

    with open(out_base + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CSV_FIELDS)
        for r in data:
            w.writerow([r.get(k, "") for k in CSV_FIELDS])


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    cities = resolve_cities(args.cities)
    cookie = (args.cookie or "").strip()

    print("Krisha.kz parser — Direct HTTP (list + detail + phones)")
    print(f"deal={args.deal} type={args.property_type} cities={cities} pages={args.pages} max/city={args.max}")
    if cookie:
        print("phones: KRISHA_COOKIE set (session mode B)")
    elif args.skip_phones:
        print("phones: skipped (--skip-phones)")
    else:
        print(
            "phones: no KRISHA_COOKIE — will try public ajaxPhones; "
            "if Krisha requires login, only phone_preview will be filled.\n"
            "         Set KRISHA_COOKIE from a logged-in browser for full numbers."
        )

    client = HttpClient(
        timeout=args.timeout,
        retries=args.retries,
        proxy=args.proxy,
        sleep_base=max(args.sleep, 0.2),
        cookie=cookie,
    )

    rows: Dict[str, Dict[str, Any]] = {}  # by listing_id
    auth_warned = False
    phones_ok = 0
    phones_blocked = 0

    for city in cities:
        display = CITY_NAMES.get(city, city)
        print(f"[{display} / {city}] …")
        ids: List[str] = []
        for page in range(1, args.pages + 1):
            try:
                batch = fetch_list_ids(client, args.deal, args.property_type, city, page)
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
                data = fetch_detail(client, lid)
            except HttpError as e:
                print(f"    detail {lid} error: {e}")
                time.sleep(args.sleep)
                continue
            if not data:
                print(f"    detail {lid}: no window.data")
                time.sleep(args.sleep)
                continue

            # Prefer phones already embedded in window.data (logged-in SSR).
            row = normalize_listing(
                data,
                fallback_city=display,
                deal_type=args.deal,
                property_type=args.property_type,
                phones=None,
                keep_raw=args.keep_raw,
            )

            # Fallback: ajaxPhones only if page did not embed full numbers.
            if not row.get("phone") and not args.skip_phones:
                phone_list, status = fetch_phones(client, lid)
                if status == "auth_required":
                    phones_blocked += 1
                    if not auth_warned:
                        print(
                            "    ! Full phones need a logged-in Krisha session.\n"
                            "      UI hides them behind «Показать телефон», but with KRISHA_COOKIE\n"
                            "      they usually already appear in window.data (adverts[].phones).\n"
                            "      Export Cookie from a krisha.kz request after sign-in."
                        )
                        auth_warned = True
                elif status == "ok" and phone_list:
                    phones_ok += 1
                    # re-normalize with ajax phones
                    row = normalize_listing(
                        data,
                        fallback_city=display,
                        deal_type=args.deal,
                        property_type=args.property_type,
                        phones=phone_list,
                        keep_raw=args.keep_raw,
                    )
                time.sleep(args.sleep * 0.5)
            elif row.get("phone"):
                phones_ok += 1
            # key: prefer phone if present else listing id
            key = row.get("phone") or f"id:{lid}"
            if key in rows and row.get("phone"):
                # already have this phone
                pass
            rows[str(lid)] = row
            city_new += 1
            if n % 10 == 0:
                print(f"    processed {n}/{len(ids)} | stored={len(rows)}")
            time.sleep(args.sleep)

        print(f"[{display}] +{city_new} | total={len(rows)}")
        dump_rows(rows, args.out, args.keep_raw)

    dump_rows(rows, args.out, args.keep_raw)
    with_phone = sum(1 for r in rows.values() if r.get("phone"))
    with_preview = sum(1 for r in rows.values() if r.get("phone_preview"))
    print(
        f"\nDone: {len(rows)} listings -> {args.out}.csv / {args.out}.json"
        f"\n  full phones: {with_phone} | phone_preview: {with_preview}"
        f" | ajaxPhones ok={phones_ok} blocked={phones_blocked}"
    )
    if with_phone == 0 and not cookie and not args.skip_phones:
        print(
            "\nNOTE: Full phones need a logged-in session.\n"
            "  1) Open krisha.kz in browser and sign in\n"
            "  2) DevTools → Network → any request → copy 'cookie' request header\n"
            "  3) KRISHA_COOKIE='…' python krisha/krisha_parser.py …\n"
        )


if __name__ == "__main__":
    main()
