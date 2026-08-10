#!/usr/bin/env python3
"""
Yandex Maps places parser — collects organizations of ANY category with their
OPEN public phone numbers via Direct HTTP + embedded JSON state.

No Apify. No official Yandex API key. No browser automation.

How it works
------------
Yandex Maps SPA hydrates from a large `application/json` blob embedded in the
search HTML. That blob contains the same organization cards the UI shows:

    stack[0].results.items[]  →  title, phones, coordinates, ratingData, …

We request public search pages:

    https://{domain}/maps/{geoId}/{citySeo}/search/{query}/?page={n}

and parse the embedded state. Pagination uses the `page` query parameter
(observed: ~25 items per page; `totalResultCount` grows as further pages load).

Domain note
-----------
`yandex.ru/maps` may rate-limit datacenter IPs with HTTP 429 ("limited").
The same Maps product is served on regional hosts (`yandex.kz`, `yandex.by`,
…). The client tries a short domain fallback list and uses the first that
returns a usable page. This is still the Yandex Maps product, not a third-party
mirror.

Usage:
    python yandex_maps_parser.py --query "кофейни" --city "Москва" --max 50
    QUERY="стоматология" CITIES="Астана,Алматы" python yandex_maps_parser.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Allow `python yandex-maps/yandex_maps_parser.py` from repo root.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.cli import add_common_args, resolve_cities  # noqa: E402
from core.http import HttpClient, HttpError  # noqa: E402
from core.models import Place, normalize_phone  # noqa: E402
from core.output import dump_places  # noqa: E402

SOURCE = "yandex-maps"

# Prefer ru, then regional Maps hosts (same product / same JSON shape).
DEFAULT_DOMAINS = [
    d.strip()
    for d in os.environ.get(
        "YANDEX_DOMAINS",
        "yandex.ru,yandex.kz,yandex.by,yandex.com",
    ).split(",")
    if d.strip()
]

# Well-known Yandex geo ids + SEO slugs (not exhaustive; others resolved live).
CITY_GEO: Dict[str, Tuple[int, str]] = {
    # Russia
    "moscow": (213, "moscow"),
    "москва": (213, "moscow"),
    "msk": (213, "moscow"),
    "spb": (2, "saint-petersburg"),
    "saint-petersburg": (2, "saint-petersburg"),
    "sankt-peterburg": (2, "saint-petersburg"),
    "санкт-петербург": (2, "saint-petersburg"),
    "питер": (2, "saint-petersburg"),
    "piter": (2, "saint-petersburg"),
    "novosibirsk": (65, "novosibirsk"),
    "новосибирск": (65, "novosibirsk"),
    "ekaterinburg": (54, "yekaterinburg"),
    "yekaterinburg": (54, "yekaterinburg"),
    "екатеринбург": (54, "yekaterinburg"),
    "ekb": (54, "yekaterinburg"),
    "kazan": (43, "kazan"),
    "казань": (43, "kazan"),
    "nizhny_novgorod": (47, "nizhny-novgorod"),
    "nizhny-novgorod": (47, "nizhny-novgorod"),
    "нижний новгород": (47, "nizhny-novgorod"),
    "nn": (47, "nizhny-novgorod"),
    "chelyabinsk": (56, "chelyabinsk"),
    "челябинск": (56, "chelyabinsk"),
    "samara": (51, "samara"),
    "самара": (51, "samara"),
    "omsk": (66, "omsk"),
    "омск": (66, "omsk"),
    "rostov": (39, "rostov-on-don"),
    "rostov-on-don": (39, "rostov-on-don"),
    "ростов-на-дону": (39, "rostov-on-don"),
    "ufa": (172, "ufa"),
    "уфа": (172, "ufa"),
    "krasnoyarsk": (62, "krasnoyarsk"),
    "красноярск": (62, "krasnoyarsk"),
    "voronezh": (193, "voronezh"),
    "воронеж": (193, "voronezh"),
    "perm": (50, "perm"),
    "пермь": (50, "perm"),
    "volgograd": (38, "volgograd"),
    "волгоград": (38, "volgograd"),
    "krasnodar": (35, "krasnodar"),
    "краснодар": (35, "krasnodar"),
    "tyumen": (55, "tyumen"),
    "тюмень": (55, "tyumen"),
    "irkutsk": (63, "irkutsk"),
    "иркутск": (63, "irkutsk"),
    "khabarovsk": (76, "khabarovsk"),
    "хабаровск": (76, "khabarovsk"),
    "vladivostok": (75, "vladivostok"),
    "владивосток": (75, "vladivostok"),
    "kaliningrad": (22, "kaliningrad"),
    "калининград": (22, "kaliningrad"),
    "sochi": (239, "sochi"),
    "сочи": (239, "sochi"),
    "tomsk": (67, "tomsk"),
    "томск": (67, "tomsk"),
    # Kazakhstan
    "almaty": (162, "almaty"),
    "алматы": (162, "almaty"),
    "astana": (163, "astana"),
    "астана": (163, "astana"),
    "nur-sultan": (163, "astana"),
    "nur_sultan": (163, "astana"),
    "shymkent": (221, "shymkent"),
    "шымкент": (221, "shymkent"),
    # Belarus
    "minsk": (157, "minsk"),
    "минск": (157, "minsk"),
}

DEFAULT_CITIES = [
    "Москва",
    "Санкт-Петербург",
    "Сочи",
    "Казань",
    "Краснодар",
    "Екатеринбург",
    "Новосибирск",
    "Нижний Новгород",
    "Ростов-на-Дону",
    "Самара",
    "Уфа",
    "Красноярск",
    "Пермь",
    "Калининград",
]

# CSV stays close to historical Yandex output + unified extras.
CSV_FIELDS = [
    "source",
    "phone",
    "phone2",
    "name",
    "category",
    "city",
    "address",
    "rating",
    "reviews_count",
    "latitude",
    "longitude",
    "website",
    "url",
    "place_id",
]


# --- HTML / JSON extraction --------------------------------------------------
_APP_JSON_RE = re.compile(
    r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)


def extract_app_state(html: str) -> Optional[Dict[str, Any]]:
    """Pull the Maps SPA hydration state from search HTML."""
    if not html or html.strip() in ("limited", "captcha"):
        return None
    for m in _APP_JSON_RE.finditer(html):
        raw = m.group(1).strip()
        if not raw.startswith("{"):
            continue
        if '"stack"' not in raw or '"config"' not in raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("stack"), list):
            return obj
    return None


def extract_search_results(state: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    stack = state.get("stack") or []
    if not stack or not isinstance(stack[0], dict):
        return {}, []
    results = stack[0].get("results") or {}
    if not isinstance(results, dict):
        return {}, []
    items = results.get("items") or []
    if not isinstance(items, list):
        items = []
    # Keep only business cards
    businesses = [it for it in items if isinstance(it, dict) and it.get("type", "business") == "business"]
    if not businesses:
        businesses = [it for it in items if isinstance(it, dict) and (it.get("title") or it.get("id"))]
    return results, businesses


# --- city resolution ---------------------------------------------------------
def lookup_city(name: str) -> Optional[Tuple[int, str, str]]:
    """Return (geo_id, seo_slug, display_name) from static table."""
    key = name.strip().lower().replace("ё", "е")
    if key in CITY_GEO:
        geo_id, seo = CITY_GEO[key]
        display = name.strip()
        # nicer display for slugs
        if re.fullmatch(r"[a-z0-9_\-]+", display, re.I):
            display = seo.replace("-", " ").title()
        return geo_id, seo, display
    return None


def resolve_city_live(client: HttpClient, domain: str, name: str) -> Optional[Tuple[int, str, str]]:
    """Resolve unknown city via Maps `?text=` and read mapRegion from state."""
    url = f"https://{domain}/maps/?text={urllib.parse.quote(name.strip())}"
    try:
        html = client.get(url, accept="text/html", referer=f"https://{domain}/maps/")
    except HttpError:
        return None
    state = extract_app_state(html)
    if not state:
        return None
    region = state.get("mapRegion") or {}
    if not isinstance(region, dict) or not region.get("id"):
        # sometimes first result region
        results, items = extract_search_results(state)
        if items:
            region = items[0].get("region") or {}
    if not isinstance(region, dict) or not region.get("id"):
        return None
    geo_id = int(region["id"])
    seo = str(region.get("seoname") or name.strip().lower().replace(" ", "-"))
    names = region.get("names") or {}
    display = names.get("nominative") or name.strip()
    return geo_id, seo, display


# --- normalization -----------------------------------------------------------
def _clean_website(url: str) -> str:
    if not url:
        return ""
    # strip yclid / utm noise for readability
    try:
        parts = urllib.parse.urlsplit(url)
        q = [
            (k, v)
            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in ("yclid", "ysclid")
        ]
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(q), parts.fragment)
        )
    except Exception:
        return url


def normalize_yandex_item(
    item: Dict[str, Any],
    *,
    fallback_city: str = "",
    domain: str = "yandex.ru",
    keep_raw: bool = True,
) -> Optional[Place]:
    phones: List[str] = []
    for p in item.get("phones") or []:
        n = normalize_phone(p)
        if n and n not in phones:
            phones.append(n)
    if not phones:
        return None

    cats = item.get("categories") or []
    category = ", ".join(
        (c.get("name") or c.get("pluralName") or "") for c in cats if isinstance(c, dict)
    ).strip(", ")

    rating_data = item.get("ratingData") or {}
    rating = rating_data.get("ratingValue", "")
    if isinstance(rating, float):
        rating = round(rating, 2)
    reviews_count = rating_data.get("reviewCount")
    if reviews_count is None:
        reviews_count = rating_data.get("ratingCount", "")

    coords = item.get("coordinates") or item.get("displayCoordinates") or []
    lon = lat = ""
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        lon, lat = coords[0], coords[1]

    region = item.get("region") or {}
    city = ""
    if isinstance(region, dict):
        names = region.get("names") or {}
        city = names.get("nominative") or region.get("seoname") or ""
    city = city or fallback_city

    address = (
        item.get("fullAddress")
        or item.get("address")
        or item.get("description")
        or ""
    )
    if isinstance(item.get("compositeAddress"), dict):
        # sometimes structured
        ca = item["compositeAddress"]
        address = address or ca.get("address") or ""

    websites = item.get("urls") or []
    if isinstance(websites, str):
        websites = [websites]
    website = ""
    for w in websites:
        if isinstance(w, str) and w.startswith("http"):
            website = _clean_website(w)
            break

    place_id = str(item.get("id") or "")
    seoname = item.get("seoname") or ""
    url = ""
    if place_id:
        if seoname:
            url = f"https://{domain}/maps/org/{seoname}/{place_id}/"
        else:
            url = f"https://{domain}/maps/org/{place_id}/"

    meta = {
        "working_time": item.get("workingTimeText") or "",
        "country": item.get("country") or "",
        "seoname": seoname,
        "uri": item.get("uri") or "",
        "categories": cats,
    }

    place = Place(
        source=SOURCE,
        name=item.get("title") or item.get("shortTitle") or "",
        category=category[:120],
        phones=phones,
        address=address,
        city=city,
        latitude=lat,
        longitude=lon,
        rating=rating,
        reviews_count=reviews_count,
        website=website,
        url=url,
        place_id=place_id,
        metadata=meta,
        raw=item if keep_raw else None,
    )
    return place.finalize()


# --- fetching ----------------------------------------------------------------
def pick_domain(client: HttpClient, domains: List[str]) -> str:
    """Return first domain that serves Maps search HTML (not 429 limited)."""
    # Probe a lightweight real search page — bare /maps/ is often stricter.
    probe_path = "/maps/213/moscow/search/" + urllib.parse.quote("cafe")
    for domain in domains:
        url = f"https://{domain}{probe_path}"
        try:
            html = client.get(url, accept="text/html", referer=f"https://{domain}/maps/")
        except HttpError as e:
            print(f"    domain {domain}: HTTP {e.status} ({e})")
            continue
        if html.strip() in ("limited", "captcha"):
            print(f"    domain {domain}: blocked/limited body")
            continue
        if extract_app_state(html) or len(html) > 20000:
            print(f"    using domain: {domain}")
            return domain
        print(f"    domain {domain}: unexpected page (len={len(html)})")
    raise SystemExit(
        "ERROR: all Yandex Maps domains returned limited/blocked responses.\n"
        "Try later, another network, set YANDEX_DOMAINS, or --proxy."
    )


def build_search_url(domain: str, geo_id: int, seo: str, query: str, page: int) -> str:
    q = urllib.parse.quote(query)
    base = f"https://{domain}/maps/{geo_id}/{seo}/search/{q}/"
    if page <= 1:
        return base
    return base + f"?page={page}"


def fetch_search_page(
    client: HttpClient,
    domain: str,
    geo_id: int,
    seo: str,
    query: str,
    page: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    url = build_search_url(domain, geo_id, seo, query, page)
    referer = f"https://{domain}/maps/{geo_id}/{seo}/"
    html = client.get(url, accept="text/html,application/xhtml+xml", referer=referer)
    if html.strip() in ("limited", "captcha"):
        raise HttpError("Yandex Maps rate-limited this request", status=429, body=html)
    state = extract_app_state(html)
    if not state:
        return {}, []
    return extract_search_results(state)


def search_city(
    client: HttpClient,
    *,
    domain: str,
    city: str,
    query: str,
    max_results: int,
    sleep: float,
    keep_raw: bool,
) -> List[Place]:
    resolved = lookup_city(city)
    if not resolved:
        print(f"    resolving city {city!r} via Maps …")
        resolved = resolve_city_live(client, domain, city)
    if not resolved:
        # last resort: free-text "query city"
        print(f"    WARN: unknown city {city!r}, using text search")
        return search_text(client, domain=domain, text=f"{query} {city}", fallback_city=city,
                           max_results=max_results, sleep=sleep, keep_raw=keep_raw)

    geo_id, seo, display = resolved
    places: List[Place] = []
    seen_ids: set = set()
    page = 1
    empty_streak = 0

    while len(places) < max_results:
        try:
            results, items = fetch_search_page(client, domain, geo_id, seo, query, page)
        except HttpError as e:
            print(f"    page {page} error: {e}")
            break
        if page == 1:
            print(f"    totalResultCount≈{results.get('totalResultCount')} pageSize≈{results.get('resultsCount') or results.get('requestResults')}")
        if not items:
            empty_streak += 1
            if empty_streak >= 2:
                break
            page += 1
            time.sleep(sleep)
            continue
        empty_streak = 0
        new_on_page = 0
        for it in items:
            pid = str(it.get("id") or "")
            if pid and pid in seen_ids:
                continue
            if pid:
                seen_ids.add(pid)
            place = normalize_yandex_item(
                it, fallback_city=display, domain=domain, keep_raw=keep_raw
            )
            if not place:
                continue
            places.append(place)
            new_on_page += 1
            if len(places) >= max_results:
                break
        print(f"    page {page}: +{new_on_page} (unique with phone) | bag={len(places)}")
        if new_on_page == 0 and page > 1:
            # page returned only duplicates / phoneless cards
            empty_streak += 1
            if empty_streak >= 2:
                break
        page += 1
        time.sleep(sleep)
    return places[:max_results]


def search_text(
    client: HttpClient,
    *,
    domain: str,
    text: str,
    fallback_city: str,
    max_results: int,
    sleep: float,
    keep_raw: bool,
) -> List[Place]:
    """Fallback search via /maps/?text=…&page=N (no geo id)."""
    places: List[Place] = []
    seen_ids: set = set()
    page = 1
    while len(places) < max_results:
        url = f"https://{domain}/maps/?text={urllib.parse.quote(text)}"
        if page > 1:
            url += f"&page={page}"
        try:
            html = client.get(url, accept="text/html", referer=f"https://{domain}/maps/")
        except HttpError as e:
            print(f"    text search page {page} error: {e}")
            break
        state = extract_app_state(html)
        if not state:
            break
        results, items = extract_search_results(state)
        if not items:
            break
        for it in items:
            pid = str(it.get("id") or "")
            if pid and pid in seen_ids:
                continue
            if pid:
                seen_ids.add(pid)
            place = normalize_yandex_item(
                it, fallback_city=fallback_city, domain=domain, keep_raw=keep_raw
            )
            if place:
                places.append(place)
            if len(places) >= max_results:
                break
        page += 1
        time.sleep(sleep)
    return places[:max_results]


# --- main --------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Yandex Maps places parser (Direct HTTP / embedded JSON, no Apify)",
    )
    add_common_args(p, default_query="рестораны", default_out="output/yandex_maps_places", default_max=200)
    p.add_argument(
        "--domains",
        default=os.environ.get("YANDEX_DOMAINS", ",".join(DEFAULT_DOMAINS)),
        help="comma-separated Maps hosts to try (default: yandex.ru,yandex.kz,…)",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    cities = resolve_cities(args.cities) or list(DEFAULT_CITIES)
    domains = [d.strip() for d in args.domains.split(",") if d.strip()]

    print("Yandex Maps parser — Direct HTTP / embedded JSON (no Apify)")
    print(f"query={args.query!r} cities={cities} max/city={args.max}")
    if args.proxy:
        print(f"proxy={args.proxy.split('@')[-1] if '@' in args.proxy else args.proxy}")

    client = HttpClient(
        timeout=args.timeout,
        retries=args.retries,
        proxy=args.proxy,
        sleep_base=max(args.sleep, 0.3),
    )
    domain = pick_domain(client, domains)

    # Dedup across cities by phone
    by_phone: Dict[str, Place] = {}
    for city in cities:
        print(f"[{city}] …")
        found = search_city(
            client,
            domain=domain,
            city=city,
            query=args.query,
            max_results=args.max,
            sleep=args.sleep,
            keep_raw=args.keep_raw,
        )
        new = 0
        for place in found:
            if not place.phone or place.phone in by_phone:
                continue
            by_phone[place.phone] = place
            new += 1
        print(f"[{city}] +{new} | total={len(by_phone)}")
        dump_places(by_phone.values(), args.out, fields=CSV_FIELDS, keep_raw=args.keep_raw)

    dump_places(by_phone.values(), args.out, fields=CSV_FIELDS, keep_raw=args.keep_raw)
    print(f"\nDone: {len(by_phone)} unique phones -> {args.out}.csv / {args.out}.json")


if __name__ == "__main__":
    main()
