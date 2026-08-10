#!/usr/bin/env python3
"""
2GIS places parser — collects organizations of ANY category from 2GIS with their
OPEN public phone numbers, via the same Catalog web API that 2gis.ru itself uses.

No Apify. No personal 2GIS API key. The client talks to
`catalog.api.2gis.ru` with the public `webApiOutsourceKey` embedded in the
2GIS Online frontend (refreshed automatically if the hardcoded fallback stops
working).

Search by any free-text query ("рестораны", "автосервис", "стоматология",
"квартиры посуточно", ...) across any set of cities, or point at exact 2GIS
search/rubric URLs via START_URLS.

Output: CSV + JSON with phone, name, city, address, category, url, plus
coordinates, rating, website and other useful fields. Full raw item is kept
in the JSON under `raw` for later use.

Usage:
    QUERY="кофейни" CITIES="moscow,spb" python twogis_parser.py
    START_URLS="https://2gis.ru/moscow/search/рестораны" python twogis_parser.py
    QUERY="стоматология" CITIES="almaty,astana" MAX=200 python twogis_parser.py
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --- config (env-overridable; CLI in main() can override module globals) -----
OUT = os.environ.get("OUT", "output/twogis_places")
MAX = int(os.environ.get("MAX", "500"))
PAGE_SIZE = min(50, max(1, int(os.environ.get("PAGE_SIZE", "50"))))  # API max = 50
TIMEOUT = float(os.environ.get("TIMEOUT", "30"))
RETRIES = int(os.environ.get("RETRIES", "4"))
SLEEP = float(os.environ.get("SLEEP", "0.35"))
PROXY = os.environ.get("PROXY", "").strip()  # optional http://user:pass@host:port
QUERY = os.environ.get("QUERY", "рестораны")
START_URLS = [u.strip() for u in os.environ.get("START_URLS", "").split(",") if u.strip()]
# Keep full API objects in JSON under `raw` (set RAW=0 to drop them).
KEEP_RAW = os.environ.get("RAW", "1").strip() not in ("0", "false", "no")

# Public key used by 2gis.ru frontend (`webApiOutsourceKey` in page config).
# Overridable via TWOGIS_KEY; auto-refreshed from the site if blocked.
DEFAULT_WEB_KEY = "292d0592-6e9a-4882-b2c6-5979d678ddea"
WEB_KEY = os.environ.get("TWOGIS_KEY", DEFAULT_WEB_KEY).strip() or DEFAULT_WEB_KEY

CATALOG_ITEMS = "https://catalog.api.2gis.ru/3.0/items"
CATALOG_REGIONS = "https://catalog.api.2gis.ru/2.0/region/list"
SITE_ORIGIN = "https://2gis.ru"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
# App UA bypasses 2gis.ru /museum bot gate when we need to scrape page config.
APP_UA = "2GIS/6.0.0 Android/13"

# Common 2GIS city slugs → display name (region id resolved at runtime).
DEFAULT_CITIES = [
    ("moscow", "Москва"),
    ("spb", "Санкт-Петербург"),
    ("sochi", "Сочи"),
    ("kazan", "Казань"),
    ("krasnodar", "Краснодар"),
    ("ekaterinburg", "Екатеринбург"),
    ("novosibirsk", "Новосибирск"),
    ("nizhny_novgorod", "Нижний Новгород"),
    ("kaliningrad", "Калининград"),
    ("rostov", "Ростов-на-Дону"),
    ("tyumen", "Тюмень"),
    ("ufa", "Уфа"),
    ("samara", "Самара"),
    ("chelyabinsk", "Челябинск"),
    ("krasnoyarsk", "Красноярск"),
    ("perm", "Пермь"),
    ("volgograd", "Волгоград"),
]

# Fields requested from Catalog API (same family as the website).
ITEM_FIELDS = (
    "items.adm_div,items.address,items.address_name,items.full_address_name,"
    "items.contact_groups,items.point,items.rubrics,items.schedule,"
    "items.reviews,items.org,items.name_ex,items.links,items.external_content,"
    "items.flags,items.region_id,items.segment_id,items.attribute_groups,"
    "items.purpose_name"
)

# CSV columns. Unified `source` first; original fields preserved for consumers.
FIELDS = [
    "source",
    "phone",
    "phone2",
    "name",
    "city",
    "address",
    "category",
    "url",
    "website",
    "email",
    "rating",
    "reviews_count",
    "latitude",
    "longitude",
    "org_name",
    "firm_id",
    "org_id",
    "rubric_ids",
    "schedule",
    "postcode",
]

# --- helpers -----------------------------------------------------------------
_ssl_ctx = ssl.create_default_context()


def _cities() -> List[Tuple[str, str]]:
    env = os.environ.get("CITIES")
    if not env:
        return list(DEFAULT_CITIES)
    by = {s: n for s, n in DEFAULT_CITIES}
    out = []
    for part in env.split(","):
        slug = part.strip()
        if not slug:
            continue
        out.append((slug, by.get(slug, slug)))
    return out


def _build_opener() -> urllib.request.OpenerDirector:
    handlers: List[Any] = []
    if PROXY:
        handlers.append(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    handlers.append(urllib.request.HTTPSHandler(context=_ssl_ctx))
    return urllib.request.build_opener(*handlers)


def http_get(url: str, *, accept: str = "application/json", ua: str = UA) -> str:
    """GET with timeout + retries. Raises last error if all attempts fail."""
    last_err: Optional[BaseException] = None
    opener = _build_opener()
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": ua,
                    "Accept": accept,
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                    "Referer": f"{SITE_ORIGIN}/",
                    "Origin": SITE_ORIGIN,
                },
            )
            with opener.open(req, timeout=TIMEOUT) as resp:
                return resp.read().decode("utf-8", "ignore")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            # Don't burn retries on hard client errors except 429/5xx.
            if isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403, 404):
                body = ""
                try:
                    body = e.read().decode("utf-8", "ignore")
                except Exception:
                    pass
                # Re-raise with body for callers that inspect meta JSON.
                e._body = body  # type: ignore[attr-defined]
                raise
            time.sleep(min(2.0 * attempt, 8.0))
    assert last_err is not None
    raise last_err


def http_get_json(url: str) -> Dict[str, Any]:
    return json.loads(http_get(url, accept="application/json"))


def _norm_phone(p: Any) -> Optional[str]:
    d = re.sub(r"\D", "", str(p or ""))
    if not d:
        return None
    if len(d) == 11 and d[0] in "78":
        return "+7" + d[1:]
    if len(d) == 10:
        return "+7" + d
    # keep non-RU numbers as-is (2GIS covers KZ, BY, AE, …)
    return "+" + d if not str(p).strip().startswith("+") else ("+" + d)


def _unwrap_2gis_link(url: str) -> str:
    """Extract real destination from link.2gis.ru redirect wrappers."""
    if not url:
        return ""
    if "link.2gis." in url and "?" in url:
        return url.split("?", 1)[1]
    return url


def _schedule_str(schedule: Any) -> str:
    if not isinstance(schedule, dict):
        return ""
    # Prefer human comment if present; else compact Mon–Sun ranges.
    comment = schedule.get("comment")
    if comment:
        return str(comment)[:120]
    parts = []
    for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        slots = schedule.get(day) or schedule.get(day.lower())
        if not slots:
            continue
        if isinstance(slots, dict):
            working = slots.get("working_hours") or slots.get("work_hours") or []
            if working and isinstance(working, list):
                wh = working[0]
                parts.append(f"{day}:{wh.get('from', '')}-{wh.get('to', '')}")
        elif isinstance(slots, list) and slots:
            wh = slots[0]
            if isinstance(wh, dict):
                parts.append(f"{day}:{wh.get('from', '')}-{wh.get('to', '')}")
    return "; ".join(parts)[:120]


def _city_from_item(item: Dict[str, Any], fallback: str = "") -> str:
    for div in item.get("adm_div") or []:
        if div.get("type") == "city" and div.get("name"):
            return div["name"]
    for div in item.get("adm_div") or []:
        if div.get("type") in ("settlement", "region") and div.get("name"):
            return div["name"]
    return fallback


def _city_alias(item: Dict[str, Any], fallback: str = "moscow") -> str:
    for div in item.get("adm_div") or []:
        if div.get("city_alias"):
            return div["city_alias"]
        if div.get("type") == "city" and div.get("name"):
            # best-effort
            return fallback
    return fallback


def _contacts(item: Dict[str, Any]) -> Tuple[List[str], List[str], List[str]]:
    phones: List[str] = []
    websites: List[str] = []
    emails: List[str] = []
    for group in item.get("contact_groups") or []:
        for c in group.get("contacts") or []:
            if not isinstance(c, dict):
                continue
            ctype = (c.get("type") or "").lower()
            val = c.get("value") or c.get("text") or ""
            if ctype == "phone":
                n = _norm_phone(val)
                if n and n not in phones:
                    phones.append(n)
            elif ctype in ("website", "twitter", "facebook", "vkontakte", "instagram",
                           "telegram", "whatsapp", "viber", "youtube", "odnoklassniki"):
                url = _unwrap_2gis_link(c.get("url") or val)
                # Prefer real http(s) sites over social for `website`.
                if url and url not in websites:
                    websites.append(url)
            elif ctype == "email":
                em = (c.get("value") or c.get("text") or "").strip()
                if em and em not in emails:
                    emails.append(em)
    return phones, websites, emails


def _primary_website(websites: List[str]) -> str:
    for w in websites:
        low = w.lower()
        if any(s in low for s in ("vk.com", "t.me", "telegram", "instagram", "facebook",
                                  "whatsapp", "ok.ru", "youtube", "twitter", "x.com")):
            continue
        return w
    return websites[0] if websites else ""


def normalize_item(item: Dict[str, Any], fallback_city: str = "",
                   city_slug: str = "") -> Optional[Dict[str, Any]]:
    """Map a Catalog API branch object to a flat row. Requires at least one phone."""
    phones, websites, emails = _contacts(item)
    if not phones:
        return None

    rubrics = item.get("rubrics") or []
    category = ", ".join(r.get("name", "") for r in rubrics if r.get("name"))[:80]
    rubric_ids = ",".join(str(r.get("id")) for r in rubrics if r.get("id"))

    reviews = item.get("reviews") or {}
    rating = reviews.get("general_rating")
    if rating is None:
        rating = reviews.get("org_rating") or ""
    reviews_count = reviews.get("general_review_count")
    if reviews_count is None:
        reviews_count = reviews.get("org_review_count") or ""

    point = item.get("point") or {}
    lat = point.get("lat", "")
    lon = point.get("lon", "")

    org = item.get("org") or {}
    firm_id = str(item.get("id") or "")
    org_id = str(org.get("id") or "")
    name = item.get("name") or item.get("full_name") or org.get("name") or ""

    address = (
        item.get("full_address_name")
        or item.get("address_name")
        or ""
    )
    postcode = ""
    addr_obj = item.get("address") or {}
    if isinstance(addr_obj, dict):
        postcode = addr_obj.get("postcode") or ""

    city = _city_from_item(item, fallback_city)
    slug = city_slug or _city_alias(item, "moscow")
    url = f"{SITE_ORIGIN}/{slug}/firm/{firm_id}" if firm_id else ""

    row: Dict[str, Any] = {
        "source": "2gis",
        "phone": phones[0],
        "phone2": phones[1] if len(phones) > 1 else "",
        "phones": phones,
        "name": name,
        "city": city,
        "address": address,
        "category": category,
        "url": url,
        "website": _primary_website(websites),
        "email": emails[0] if emails else "",
        "rating": rating,
        "reviews_count": reviews_count,
        "latitude": lat,
        "longitude": lon,
        "org_name": org.get("name") or org.get("primary") or "",
        "firm_id": firm_id,
        "org_id": org_id,
        "place_id": firm_id,
        "rubric_ids": rubric_ids,
        "schedule": _schedule_str(item.get("schedule")),
        "postcode": postcode,
    }
    if KEEP_RAW:
        # Compact raw: drop huge nested blobs that aren't useful for re-use.
        raw = {k: v for k, v in item.items() if k not in ("geometry", "links")}
        row["raw"] = raw
    return row


# --- region resolution -------------------------------------------------------
_region_cache: Optional[List[Dict[str, Any]]] = None


def _meta_auth_error(meta: Dict[str, Any]) -> bool:
    err = meta.get("error") or {}
    if not isinstance(err, dict):
        return False
    etype = (err.get("type") or "").lower()
    msg = (err.get("message") or "").lower()
    return etype in ("apikeyisblocked", "forbidden", "unauthorized") or "blocked" in msg


def load_regions(key: str, *, force: bool = False) -> List[Dict[str, Any]]:
    global _region_cache
    if _region_cache is not None and not force:
        return _region_cache
    regions: List[Dict[str, Any]] = []
    page = 1
    while page <= 10:
        qs = urllib.parse.urlencode(
            {
                "key": key,
                "page": page,
                "page_size": 150,
                "fields": "items.code,items.country_code,items.default_pos,items.name",
            }
        )
        data = http_get_json(f"{CATALOG_REGIONS}?{qs}")
        meta = data.get("meta") or {}
        if meta.get("code") not in (None, 200):
            err = meta.get("error") or meta
            if _meta_auth_error(meta):
                raise PermissionError(f"region/list auth failed: {err}")
            raise RuntimeError(f"region/list failed: {err}")
        items = (data.get("result") or {}).get("items") or []
        if not items:
            break
        regions.extend(items)
        total = (data.get("result") or {}).get("total") or 0
        if total and len(regions) >= total:
            break
        page += 1
    _region_cache = regions
    return regions


def resolve_region(slug_or_name: str, key: str) -> Optional[Dict[str, Any]]:
    """Resolve a 2GIS city slug or display name to a region object."""
    regions = load_regions(key)
    needle = slug_or_name.strip().lower()
    # aliases used in this repo / common speech
    aliases = {
        "msk": "moscow",
        "spb": "spb",
        "peterburg": "spb",
        "piter": "spb",
        "sankt-peterburg": "spb",
        "санкт-петербург": "spb",
        "москва": "moscow",
        "ekb": "ekaterinburg",
        "екатеринбург": "ekaterinburg",
        "nsk": "novosibirsk",
        "новосибирск": "novosibirsk",
        "nn": "nizhny_novgorod",
        "nizhniy_novgorod": "nizhny_novgorod",
        "нижний новгород": "nizhny_novgorod",
        "astana": "nur_sultan",
        "астана": "nur_sultan",
        "nur-sultan": "nur_sultan",
        "алматы": "almaty",
        "almaty": "almaty",
    }
    needle = aliases.get(needle, needle)

    for r in regions:
        code = (r.get("code") or "").lower()
        name = (r.get("name") or "").lower()
        if needle == code or needle == name:
            return r
    # substring fallback
    for r in regions:
        code = (r.get("code") or "").lower()
        name = (r.get("name") or "").lower()
        if needle in code or needle in name or code in needle or name in needle:
            return r
    return None


# --- key refresh -------------------------------------------------------------
def refresh_web_key() -> Optional[str]:
    """Pull current webApiOutsourceKey from a 2GIS page (app UA avoids /museum)."""
    try:
        html = http_get(
            f"{SITE_ORIGIN}/moscow",
            accept="text/html,application/xhtml+xml",
            ua=APP_UA,
        )
    except Exception as e:
        print(f"    key refresh failed: {e}")
        return None
    m = re.search(r'"webApiOutsourceKey"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'"webApiKey"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1)
    return None


# --- catalog search ----------------------------------------------------------
def search_page(
    *,
    key: str,
    query: str = "",
    region_id: Optional[int] = None,
    rubric_id: Optional[str] = None,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    location: Optional[str] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "locale": "ru_RU",
        "fields": ITEM_FIELDS,
        "key": key,
        "type": "branch",
    }
    if query:
        params["q"] = query
    if region_id is not None:
        params["region_id"] = region_id
    if rubric_id:
        params["rubric_id"] = rubric_id
    if location:
        params["location"] = location

    url = f"{CATALOG_ITEMS}?{urllib.parse.urlencode(params)}"
    return http_get_json(url)


def search_all(
    *,
    key: str,
    query: str = "",
    region_id: Optional[int] = None,
    rubric_id: Optional[str] = None,
    max_results: int = MAX,
    location: Optional[str] = None,
    label: str = "",
) -> List[Dict[str, Any]]:
    """Paginate Catalog API until max_results or exhaustion."""
    items: List[Dict[str, Any]] = []
    page = 1
    total = None
    while len(items) < max_results:
        try:
            data = search_page(
                key=key,
                query=query,
                region_id=region_id,
                rubric_id=rubric_id,
                page=page,
                page_size=PAGE_SIZE,
                location=location,
            )
        except urllib.error.HTTPError as e:
            body = getattr(e, "_body", "") or ""
            print(f"    HTTP {e.code} on page {page} ({label}): {body[:200]}")
            break
        except Exception as e:
            print(f"    error on page {page} ({label}): {e}")
            break

        meta = data.get("meta") or {}
        code = meta.get("code")
        if code == 404:
            # empty result set
            break
        if code not in (None, 200):
            err = meta.get("error") or {}
            etype = err.get("type") if isinstance(err, dict) else ""
            print(f"    API error page {page} ({label}): {err}")
            if etype in ("apiKeyIsBlocked", "forbidden", "unauthorized"):
                raise PermissionError(str(err))
            break

        result = data.get("result") or {}
        batch = result.get("items") or []
        if total is None:
            total = result.get("total")
            if label:
                print(f"    total available: {total}")
        if not batch:
            break
        items.extend(batch)
        if total is not None and len(items) >= total:
            break
        # 2GIS typically serves a large page window; stop when a short page arrives
        if len(batch) < PAGE_SIZE:
            break
        page += 1
        time.sleep(SLEEP)

    return items[:max_results]


# --- START_URLS parsing ------------------------------------------------------
_URL_CITY_RE = re.compile(
    r"https?://(?:[a-z]+\.)?2gis\.[a-z.]+/(?P<city>[a-z0-9_\-]+)/",
    re.I,
)
_URL_SEARCH_RE = re.compile(r"/search/([^/?#]+)", re.I)
_URL_RUBRIC_RE = re.compile(r"rubricId/(\d+)", re.I)


def parse_start_url(url: str) -> Dict[str, Any]:
    """Extract city slug, query and/or rubric_id from a 2GIS URL."""
    info: Dict[str, Any] = {"url": url, "city_slug": "", "query": "", "rubric_id": ""}
    m = _URL_CITY_RE.search(url)
    if m:
        info["city_slug"] = m.group("city")
    m = _URL_SEARCH_RE.search(url)
    if m:
        info["query"] = urllib.parse.unquote(m.group(1))
    m = _URL_RUBRIC_RE.search(url)
    if m:
        info["rubric_id"] = m.group(1)
    return info


# --- output ------------------------------------------------------------------
def dump(rows: Dict[str, Dict[str, Any]]) -> None:
    data = list(rows.values())
    out_json = OUT + ".json"
    out_csv = OUT + ".csv"
    parent = os.path.dirname(os.path.abspath(out_json))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    # JSON keeps everything including raw
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    # CSV: flat FIELDS only
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in data:
            w.writerow([r.get(k, "") for k in FIELDS])


def collect(items: Iterable[Dict[str, Any]], city_name: str, city_slug: str,
            rows: Dict[str, Dict[str, Any]]) -> int:
    new = 0
    for it in items:
        row = normalize_item(it, fallback_city=city_name, city_slug=city_slug)
        if not row:
            continue
        phone = row["phone"]
        if phone in rows:
            continue
        rows[phone] = row
        new += 1
    return new


# --- main --------------------------------------------------------------------
def ensure_key(key: str, *, force_refresh: bool = False) -> str:
    """Validate key with a tiny request; refresh from site on block."""
    global _region_cache

    def _refresh() -> str:
        global _region_cache
        print("    refreshing web key from 2gis.ru …")
        fresh = refresh_web_key()
        if not fresh:
            raise SystemExit(
                "ERROR: 2GIS web key is blocked and could not be refreshed.\n"
                "Set TWOGIS_KEY to a working Catalog key, or retry later."
            )
        print(f"    refreshed key: {fresh[:8]}…")
        _region_cache = None
        try:
            load_regions(fresh, force=True)
        except PermissionError:
            raise SystemExit(
                "ERROR: 2GIS web key is blocked (site key also rejected).\n"
                "Set TWOGIS_KEY to a working Catalog key from https://platform.2gis.ru "
                "if you need one, or retry later."
            )
        return fresh

    if force_refresh or not key:
        return _refresh()

    try:
        # Cheap call — region list also warms the city cache.
        load_regions(key, force=True)
        return key
    except PermissionError:
        return _refresh()
    except Exception as e:
        # If region list fails for non-auth reasons, still try search later.
        msg = str(e).lower()
        if "blocked" in msg or "forbidden" in msg:
            return _refresh()
        return key


def run_for_city(key: str, slug: str, city_name: str, query: str,
                 rubric_id: str, rows: Dict[str, Dict[str, Any]]) -> int:
    region = resolve_region(slug, key)
    if not region and city_name:
        region = resolve_region(city_name, key)
    if not region:
        print(f"    WARN: unknown city '{slug}' — searching by query text only")
        region_id = None
        location = None
        display = city_name or slug
        q = query
        if city_name and city_name.lower() not in (query or "").lower():
            q = f"{query} {city_name}".strip()
    else:
        region_id = region.get("id")
        display = region.get("name") or city_name or slug
        pos = region.get("default_pos") or {}
        location = None
        if pos.get("lon") is not None and pos.get("lat") is not None:
            location = f"{pos['lon']},{pos['lat']}"
        q = query
        # Prefer resolved slug/code for firm URLs
        slug = region.get("code") or slug

    items = search_all(
        key=key,
        query=q,
        region_id=region_id,
        rubric_id=rubric_id or None,
        max_results=MAX,
        location=location,
        label=display,
    )
    return collect(items, display, slug, rows)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="2GIS places parser (Direct HTTP / internal Catalog web API, no Apify)",
    )
    p.add_argument("-q", "--query", default=QUERY, help="search text / category")
    p.add_argument(
        "-c",
        "--city",
        action="append",
        dest="cities",
        default=None,
        help="city slug (repeatable), e.g. moscow. Also: CITIES=moscow,spb",
    )
    p.add_argument("--max", type=int, default=MAX, help="max results per city")
    p.add_argument("--out", default=OUT, help="output path prefix without extension")
    p.add_argument("--proxy", default=PROXY, help="optional http://user:pass@host:port")
    p.add_argument("--timeout", type=float, default=TIMEOUT)
    p.add_argument("--retries", type=int, default=RETRIES)
    p.add_argument("--sleep", type=float, default=SLEEP)
    p.add_argument("--page-size", type=int, default=PAGE_SIZE)
    p.add_argument(
        "--start-url",
        action="append",
        dest="start_urls",
        default=None,
        help="exact 2GIS URL (repeatable); also START_URLS=a,b",
    )
    p.add_argument("--raw", dest="keep_raw", action="store_true", default=KEEP_RAW)
    p.add_argument("--no-raw", dest="keep_raw", action="store_false")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    global OUT, MAX, PAGE_SIZE, TIMEOUT, RETRIES, SLEEP, PROXY, QUERY, START_URLS, KEEP_RAW

    args = parse_args(argv)
    OUT = args.out
    MAX = args.max
    PAGE_SIZE = min(50, max(1, args.page_size))
    TIMEOUT = args.timeout
    RETRIES = args.retries
    SLEEP = args.sleep
    PROXY = (args.proxy or "").strip()
    QUERY = args.query
    KEEP_RAW = args.keep_raw
    if args.start_urls:
        START_URLS = args.start_urls
    if args.cities:
        os.environ["CITIES"] = ",".join(args.cities)

    print("2GIS parser — direct Catalog web API (no Apify)")
    if PROXY:
        print(f"proxy: {PROXY.split('@')[-1] if '@' in PROXY else PROXY}")

    key = WEB_KEY
    try:
        key = ensure_key(key)
    except SystemExit:
        raise
    except Exception as e:
        print(f"WARNING: region warmup failed ({e}); continuing with key as-is")

    rows: Dict[str, Dict[str, Any]] = {}

    if START_URLS:
        for url in START_URLS:
            info = parse_start_url(url)
            slug = info["city_slug"] or "moscow"
            city_name = dict(DEFAULT_CITIES).get(slug, slug)
            query = info["query"] or QUERY
            rubric_id = info["rubric_id"]
            print(f"[{slug}] url query={query!r} rubric={rubric_id or '-'} …")
            try:
                new = run_for_city(key, slug, city_name, query, rubric_id, rows)
            except PermissionError as e:
                print(f"    auth error: {e}")
                key = ensure_key(key, force_refresh=True)
                new = run_for_city(key, slug, city_name, query, rubric_id, rows)
            print(f"[{slug}] +{new} | total={len(rows)}")
            dump(rows)
    else:
        for slug, city_name in _cities():
            print(f"[{city_name}] query={QUERY!r} …")
            try:
                new = run_for_city(key, slug, city_name, QUERY, "", rows)
            except PermissionError as e:
                print(f"    auth error: {e}")
                key = ensure_key(key, force_refresh=True)
                new = run_for_city(key, slug, city_name, QUERY, "", rows)
            print(f"[{city_name}] +{new} | total={len(rows)}")
            dump(rows)

    dump(rows)
    print(f"\nDone: {len(rows)} unique phones -> {OUT}.csv / {OUT}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
