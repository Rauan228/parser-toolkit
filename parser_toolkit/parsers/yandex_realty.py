#!/usr/bin/env python3
"""
Yandex Realty parser — RU real-estate listings via Direct HTTP.

No Apify. No official API key. No captcha solving.

Data path
---------
``realty.yandex.ru`` is SmartCaptcha-walled from typical datacenter IPs.
The same listings are rendered on the Yandex Search realty vertical:

    https://yandex.ru/realty/{city}/{deal}/{type}/

Offer cards are embedded as JSON objects (``{"id":"…","type":"offer",…}``)
with price, address, rooms, area, floor, metro, coordinates.

Phones
------
Not present in the public SERP JSON. The dedicated card host
(``realty.yandex.ru/offer/{id}``) is captcha-gated. We do **not** click
«Показать телефон» or solve captcha. Metadata is collected; ``phone`` stays
empty unless a future public field appears.

Usage:
    parser-toolkit yandex-realty --city moscow --deal snyat --type kvartira --max 30
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from html import unescape
from typing import Any, Dict, Iterable, List, Optional, Tuple

from parser_toolkit.core.cli import add_output_args, resolve_cities
from parser_toolkit.core.exitcodes import EXIT_BLOCKED
from parser_toolkit.core.http import HttpClient, HttpError

SOURCE = "yandex-realty"

DEFAULT_DOMAINS = [
    d.strip()
    for d in os.environ.get("YANDEX_REALTY_DOMAINS", "yandex.ru,ya.ru").split(",")
    if d.strip()
]

# URL slug + geo id (lr) + display name.
CITY_META: Dict[str, Tuple[str, str, str]] = {
    "moscow": ("moskva", "213", "Москва"),
    "москва": ("moskva", "213", "Москва"),
    "msk": ("moskva", "213", "Москва"),
    "moskva": ("moskva", "213", "Москва"),
    "spb": ("sankt-peterburg", "2", "Санкт-Петербург"),
    "saint-petersburg": ("sankt-peterburg", "2", "Санкт-Петербург"),
    "sankt-peterburg": ("sankt-peterburg", "2", "Санкт-Петербург"),
    "санкт-петербург": ("sankt-peterburg", "2", "Санкт-Петербург"),
    "piter": ("sankt-peterburg", "2", "Санкт-Петербург"),
    "novosibirsk": ("novosibirsk", "65", "Новосибирск"),
    "новосибирск": ("novosibirsk", "65", "Новосибирск"),
    "ekaterinburg": ("ekaterinburg", "54", "Екатеринбург"),
    "yekaterinburg": ("ekaterinburg", "54", "Екатеринбург"),
    "екатеринбург": ("ekaterinburg", "54", "Екатеринбург"),
    "ekb": ("ekaterinburg", "54", "Екатеринбург"),
    "kazan": ("kazan", "43", "Казань"),
    "казань": ("kazan", "43", "Казань"),
    "nizhny-novgorod": ("nizhniy-novgorod", "47", "Нижний Новгород"),
    "nizhniy-novgorod": ("nizhniy-novgorod", "47", "Нижний Новгород"),
    "нижний новгород": ("nizhniy-novgorod", "47", "Нижний Новгород"),
    "nn": ("nizhniy-novgorod", "47", "Нижний Новгород"),
    "chelyabinsk": ("chelyabinsk", "56", "Челябинск"),
    "челябинск": ("chelyabinsk", "56", "Челябинск"),
    "samara": ("samara", "51", "Самара"),
    "самара": ("samara", "51", "Самара"),
    "omsk": ("omsk", "66", "Омск"),
    "омск": ("omsk", "66", "Омск"),
    "rostov": ("rostov-na-donu", "39", "Ростов-на-Дону"),
    "rostov-na-donu": ("rostov-na-donu", "39", "Ростов-на-Дону"),
    "ростов-на-дону": ("rostov-na-donu", "39", "Ростов-на-Дону"),
    "ufa": ("ufa", "172", "Уфа"),
    "уфа": ("ufa", "172", "Уфа"),
    "krasnoyarsk": ("krasnoyarsk", "62", "Красноярск"),
    "красноярск": ("krasnoyarsk", "62", "Красноярск"),
    "voronezh": ("voronezh", "193", "Воронеж"),
    "воронеж": ("voronezh", "193", "Воронеж"),
    "perm": ("perm", "50", "Пермь"),
    "пермь": ("perm", "50", "Пермь"),
    "volgograd": ("volgograd", "38", "Волгоград"),
    "волгоград": ("volgograd", "38", "Волгоград"),
    "krasnodar": ("krasnodar", "35", "Краснодар"),
    "краснодар": ("krasnodar", "35", "Краснодар"),
    "sochi": ("sochi", "239", "Сочи"),
    "сочи": ("sochi", "239", "Сочи"),
    "tyumen": ("tyumen", "55", "Тюмень"),
    "тюмень": ("tyumen", "55", "Тюмень"),
    "kaliningrad": ("kaliningrad", "22", "Калининград"),
    "калининград": ("kaliningrad", "22", "Калининград"),
}

DEFAULT_CITIES = ["moscow", "spb", "kazan", "krasnodar", "sochi"]

DEALS = {
    "snyat": "snyat",
    "rent": "snyat",
    "arenda": "snyat",
    "аренда": "snyat",
    "kupit": "kupit",
    "buy": "kupit",
    "sale": "kupit",
    "продажа": "kupit",
    "prodazha": "kupit",
}

PTYPES = {
    "kvartira": "kvartira",
    "kvartiry": "kvartira",
    "apartment": "kvartira",
    "квартира": "kvartira",
    "komnata": "komnata",
    "room": "komnata",
    "комната": "komnata",
    "dom": "dom",
    "house": "dom",
    "дом": "dom",
    "uchastok": "uchastok",
    "plot": "uchastok",
}

# Extra listing views used as "pages" (query ?page=N is ignored by the SERP).
PAGE_VARIANTS = (
    "",
    "?sort=date",
    "?sort=price",
    "?sort=area",
)

CSV_FIELDS = [
    "source",
    "phone",
    "title",
    "city",
    "address",
    "metro",
    "price_rub",
    "rooms",
    "area_m2",
    "floor",
    "floors_total",
    "deal_type",
    "property_type",
    "sale_type",
    "latitude",
    "longitude",
    "listing_id",
    "url",
]

_OFFER_START = re.compile(r'\{"id":"(\d+)","type":"offer"')
_ROOMS_RE = re.compile(r"(\d+)\s*-?\s*комн", re.I)
_STUDIO_RE = re.compile(r"студ", re.I)
_FLOOR_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
_AREA_RE = re.compile(r"([\d\s]+(?:[.,]\d+)?)\s*м")


def is_captcha(html: str) -> bool:
    if not html:
        return True
    head = html[:4000].lower()
    if "вы не робот" in html[:2000].lower() or '"type": "captcha"' in html[:800]:
        return True
    if "captcha_smart" in head:
        return True
    return False


def resolve_city(raw: str) -> Tuple[str, str, str]:
    key = (raw or "").strip().lower()
    if key in CITY_META:
        return CITY_META[key]
    slug = re.sub(r"\s+", "-", key) or "moskva"
    return slug, "", raw.strip() or slug


def resolve_deal(raw: str) -> str:
    return DEALS.get((raw or "").strip().lower(), "snyat")


def resolve_ptype(raw: str) -> str:
    return PTYPES.get((raw or "").strip().lower(), "kvartira")


def listing_url(domain: str, slug: str, deal: str, ptype: str, suffix: str = "") -> str:
    return f"https://{domain}/realty/{slug}/{deal}/{ptype}/{suffix}"


def search_url(domain: str, text: str, lr: str) -> str:
    from urllib.parse import urlencode

    q = urlencode({"text": text, "lr": lr})
    return f"https://{domain}/realty/search?{q}"


def extract_offers(html: str) -> List[Dict[str, Any]]:
    """Parse embedded ``type=offer`` JSON objects from SERP HTML."""
    if not html:
        return []
    blobs = [html]
    if "&quot;type&quot;:&quot;offer&quot;" in html:
        blobs.append(unescape(html))

    dec = json.JSONDecoder()
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for blob in blobs:
        for m in _OFFER_START.finditer(blob):
            try:
                obj, _end = dec.raw_decode(blob[m.start() :])
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or obj.get("type") != "offer":
                continue
            oid = str(obj.get("id") or "")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            out.append(obj)
    return out


def _spec_map(offer: Dict[str, Any]) -> Dict[str, str]:
    specs = (offer.get("specs") or {}).get("primarySpecs") or []
    mapped: Dict[str, str] = {}
    if isinstance(specs, list):
        for item in specs:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            val = item.get("children")
            if key and val not in (None, ""):
                mapped[key] = str(val)
    return mapped


def parse_rooms(text: str) -> Any:
    if _STUDIO_RE.search(text or ""):
        return 0
    m = _ROOMS_RE.search(text or "")
    return int(m.group(1)) if m else ""


def parse_area(text: str) -> Any:
    m = _AREA_RE.search(text or "")
    if not m:
        return ""
    raw = m.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return ""


def parse_floor_pair(text: str) -> Tuple[Any, Any]:
    m = _FLOOR_RE.search(text or "")
    if not m:
        return "", ""
    return int(m.group(1)), int(m.group(2))


def normalize_offer(
    offer: Dict[str, Any],
    *,
    fallback_city: str = "",
    deal_type: str = "",
    property_type: str = "",
    keep_raw: bool = True,
) -> Dict[str, Any]:
    attrs = offer.get("logNodeAttrs") or {}
    if not isinstance(attrs, dict):
        attrs = {}
    specs = _spec_map(offer)
    listing_id = str(offer.get("id") or attrs.get("offer-id") or "")
    address = offer.get("address") or attrs.get("address") or ""
    city = fallback_city
    if address and "," in address:
        city = address.split(",", 1)[0].strip() or city

    rooms_text = specs.get("roomCountTypeShort") or offer.get("title") or ""
    area_text = specs.get("apartmentArea") or ""
    floor_text = specs.get("floorOutOfTotal") or ""
    area = attrs.get("apartment_area_sq_m") or parse_area(area_text)
    if isinstance(area, str) and area:
        try:
            area = float(str(area).replace(",", "."))
        except ValueError:
            pass
    floor, floors_total = parse_floor_pair(floor_text)

    metro = offer.get("metro") or {}
    geo = metro.get("geoPoint") or {}
    price = attrs.get("price")
    if price in (None, ""):
        m = re.search(r"(\d[\d\s]{2,})", str(offer.get("title") or ""))
        price = int(re.sub(r"\D", "", m.group(1))) if m else ""

    url = offer.get("url") or (f"https://yandex.ru/realty/offer/{listing_id}" if listing_id else "")
    deal = (attrs.get("offer-type") or deal_type or "").lower()
    ptype = (attrs.get("category-type") or property_type or "").lower()

    row: Dict[str, Any] = {
        "source": SOURCE,
        "id": listing_id,
        "listing_id": listing_id,
        "place_id": listing_id,
        "phone": "",
        "phones": [],
        "title": offer.get("title") or "",
        "name": offer.get("title") or "",
        "city": city,
        "address": address,
        "metro": metro.get("name") or "",
        "price_rub": price if price not in (None, "") else "",
        "price": price if price not in (None, "") else "",
        "currency": "RUB" if price not in (None, "") else "",
        "rooms": parse_rooms(rooms_text),
        "area_m2": area if area not in (None, "") else parse_area(area_text),
        "floor": floor,
        "floors_total": floors_total,
        "deal_type": deal,
        "property_type": ptype,
        "sale_type": attrs.get("sale-type") or "",
        "category": f"{deal}/{ptype}".strip("/"),
        "latitude": geo.get("latitude") or "",
        "longitude": geo.get("longitude") or "",
        "url": url,
        "classified": attrs.get("main-classified-name") or "",
    }
    if keep_raw:
        raw = dict(offer)
        raw.pop("mediaCarouselProps", None)
        raw.pop("feedbackButtonProps", None)
        raw.pop("favoritesButtonProps", None)
        row["raw"] = raw
    return row


def pick_domain(client: HttpClient, domains: Iterable[str], probe_path: str) -> str:
    last_err: Optional[BaseException] = None
    for domain in domains:
        url = f"https://{domain}{probe_path}"
        try:
            html = client.get(url)
        except HttpError as e:
            last_err = e
            continue
        if is_captcha(html):
            last_err = RuntimeError(f"{domain} returned captcha")
            continue
        if extract_offers(html) or "searchResultsCount" in html:
            return domain
        last_err = RuntimeError(f"{domain} had no offers")
    print(
        "ERROR: all Yandex Realty hosts are captcha-blocked or empty.\n"
        f"  last: {last_err}\n"
        "  realty.yandex.ru is SmartCaptcha-walled; this parser uses yandex.ru/realty.\n"
        "  Try later, another network, or --proxy.",
        file=sys.stderr,
    )
    raise SystemExit(EXIT_BLOCKED)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Yandex Realty listings (yandex.ru/realty SERP JSON; phones not public)",
    )
    p.add_argument(
        "-c",
        "--city",
        action="append",
        dest="cities",
        default=None,
        help="city slug (moscow, spb, kazan…). Also CITIES=moscow,spb",
    )
    p.add_argument("--deal", default=os.environ.get("DEAL", "snyat"), help="snyat | kupit")
    p.add_argument("--type", dest="property_type", default=os.environ.get("TYPE", "kvartira"))
    p.add_argument("--pages", type=int, default=int(os.environ.get("PAGES", "1")), help="listing views per city (sort variants)")
    p.add_argument("--max", type=int, default=int(os.environ.get("MAX", "50")))
    p.add_argument("--out", default=os.environ.get("OUT", "output/yandex_realty_listings"))
    p.add_argument("--proxy", default=os.environ.get("PROXY", ""))
    p.add_argument("--timeout", type=float, default=float(os.environ.get("TIMEOUT", "30")))
    p.add_argument("--retries", type=int, default=int(os.environ.get("RETRIES", "4")))
    p.add_argument("--sleep", type=float, default=float(os.environ.get("SLEEP", "0.6")))
    p.add_argument(
        "--domains",
        default=",".join(DEFAULT_DOMAINS),
        help="comma-separated hosts (default yandex.ru,ya.ru)",
    )
    p.add_argument("--raw", dest="keep_raw", action="store_true", default=True)
    p.add_argument("--no-raw", dest="keep_raw", action="store_false")
    add_output_args(p)
    return p.parse_args(argv)


def scrape(
    *,
    cities: Optional[List[str]] = None,
    deal: str = "snyat",
    property_type: str = "kvartira",
    pages: int = 1,
    max_per_city: int = 50,
    proxy: str = "",
    timeout: float = 30.0,
    retries: int = 4,
    sleep: float = 0.6,
    keep_raw: bool = True,
    domains: Optional[List[str]] = None,
    out: Optional[str] = None,
    formats: str = "csv,json",
    resume: bool = False,
    write: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Collect Yandex Realty listings. Writes files only when ``out`` is set."""
    from parser_toolkit.core.report import RunReport, persist_run
    from parser_toolkit.core.resume import load_checkpoint, seed_rows
    from parser_toolkit.core.schema import phone_metrics

    city_list = resolve_cities(cities) or list(DEFAULT_CITIES)
    deal = resolve_deal(deal)
    ptype = resolve_ptype(property_type)
    host_list = domains or list(DEFAULT_DOMAINS)
    should_write = write if write is not None else bool(out)
    report = RunReport(source=SOURCE)
    report.extra["phones"] = "not_public_on_serp"

    print("Yandex Realty parser — yandex.ru/realty (not realty.yandex.ru)")
    print(f"deal={deal} type={ptype} cities={city_list} views/city={pages} max/city={max_per_city}")
    print("phones: not in public SERP; realty.yandex.ru/offer is captcha-walled")
    if proxy:
        print(f"proxy={proxy.split('@')[-1] if '@' in proxy else proxy}")

    client = HttpClient(
        timeout=timeout,
        retries=retries,
        proxy=proxy,
        sleep_base=max(sleep, 0.3),
    )
    first = resolve_city(city_list[0])
    domain = pick_domain(client, host_list, f"/realty/{first[0]}/{deal}/{ptype}/")

    rows: Dict[str, Dict[str, Any]] = {}
    if resume and out:
        n = seed_rows(rows, load_checkpoint(out))
        report.resumed = True
        report.resumed_from = n
        if n:
            print(f"resume: loaded {n} existing listings from {out}.*")

    for city_raw in city_list:
        slug, lr, display = resolve_city(city_raw)
        print(f"[{display} / {slug}] …")
        variants = list(PAGE_VARIANTS[: max(1, pages)])
        if pages >= 2 and lr:
            variants.append(("__search__", lr, display))
        city_new = 0
        for variant in variants:
            if len(rows) >= max_per_city and city_new > 0:
                # max is per city: count only this city's new + existing for this city is hard;
                # we cap by how many we add this city via city_new vs max
                pass
            if isinstance(variant, tuple):
                url = search_url(domain, f"{deal} {ptype} {display}", variant[1])
            else:
                url = listing_url(domain, slug, deal, ptype, variant)
            try:
                html = client.get(url, referer=f"https://{domain}/realty/")
            except HttpError as e:
                print(f"    list error: {e}")
                report.add_error(f"{slug}: {e}")
                break
            if is_captcha(html):
                print(f"    captcha on {url}")
                report.add_error(f"captcha: {url}")
                raise SystemExit(EXIT_BLOCKED)
            offers = extract_offers(html)
            added = 0
            for offer in offers:
                row = normalize_offer(
                    offer,
                    fallback_city=display,
                    deal_type=deal,
                    property_type=ptype,
                    keep_raw=keep_raw,
                )
                lid = row.get("listing_id") or ""
                if not lid or lid in rows:
                    continue
                rows[lid] = row
                added += 1
                city_new += 1
                if city_new >= max_per_city:
                    break
            print(f"    {url.split(domain, 1)[-1]}: +{added} (city={city_new} total={len(rows)})")
            if city_new >= max_per_city:
                break
            time.sleep(sleep)

        print(f"[{display}] +{city_new} | total={len(rows)}")
        if should_write and out:
            persist_run(
                list(rows.values()),
                out,
                fields=CSV_FIELDS,
                formats=formats,
                keep_raw=keep_raw,
                source=SOURCE,
                report=report,
                echo=False,
            )

    records = list(rows.values())
    extra = phone_metrics(records)
    extra["note"] = "phones are not public on yandex.ru/realty SERP"
    if should_write and out:
        persist_run(
            records,
            out,
            fields=CSV_FIELDS,
            formats=formats,
            keep_raw=keep_raw,
            source=SOURCE,
            report=report,
            extra_phones=extra,
        )
    else:
        report.finish(records=records, extra_phones=extra)
    print(
        f"  records={len(records)} phones={extra.get('with_phone', 0)} "
        f"(expected 0 — not public)"
    )
    return records


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    domains = [d.strip() for d in (args.domains or "").split(",") if d.strip()]
    scrape(
        cities=args.cities,
        deal=args.deal,
        property_type=args.property_type,
        pages=args.pages,
        max_per_city=args.max,
        proxy=args.proxy or "",
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
        keep_raw=args.keep_raw,
        domains=domains,
        out=args.out,
        formats=getattr(args, "formats", "csv,json"),
        resume=getattr(args, "resume", False),
        write=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
