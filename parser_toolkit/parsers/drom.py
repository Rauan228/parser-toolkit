#!/usr/bin/env python3
"""
Drom.ru auto listings parser — Russian used-car classifieds via Direct HTTP.

No Apify. No official API key. No captcha solving.

Data path
---------
1) Search HTML (windows-1251):
      https://auto.drom.ru/{city}/all/
      https://auto.drom.ru/{city}/all/page{N}/
   → ``<script data-drom-module="bulls-list-auto">`` JSON
      ``bullList.bullsData[].bulls[]`` → bullId, title, price, url, attrs

2) Optional detail (``--phones``):
      https://auto.drom.ru/.../{id}.html
   → ``data-drom-module="bull-page"``
   → GET https://www.drom.ru/api/sales/bulls/{id}/contacts?contactToken=…

   Without a logged-in session the contacts API returns ``{"type":4}``
   (no number). We do not solve Drom captcha / reCAPTCHA.

Usage:
    parser-toolkit drom --city moscow --pages 2 --max 40
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from parser_toolkit.core.cli import add_cookie_args, add_output_args, resolve_cities
from parser_toolkit.core.http import HttpClient, HttpError
from parser_toolkit.core.models import normalize_phone

SOURCE = "drom"
ORIGIN = "https://auto.drom.ru"

DEFAULT_CITIES = ["moscow", "spb", "novosibirsk", "ekaterinburg", "kazan"]

CITY_SLUGS: Dict[str, str] = {
    "moscow": "moscow",
    "москва": "moscow",
    "msk": "moscow",
    "spb": "spb",
    "питер": "spb",
    "санкт-петербург": "spb",
    "saint-petersburg": "spb",
    "sankt-peterburg": "spb",
    "novosibirsk": "novosibirsk",
    "новосибирск": "novosibirsk",
    "ekaterinburg": "ekaterinburg",
    "yekaterinburg": "ekaterinburg",
    "екатеринбург": "ekaterinburg",
    "ekb": "ekaterinburg",
    "kazan": "kazan",
    "казань": "kazan",
    "nizhny-novgorod": "nizhniy-novgorod",
    "nizhniy-novgorod": "nizhniy-novgorod",
    "нижний новгород": "nizhniy-novgorod",
    "nn": "nizhniy-novgorod",
    "chelyabinsk": "chelyabinsk",
    "челябинск": "chelyabinsk",
    "samara": "samara",
    "самара": "samara",
    "omsk": "omsk",
    "омск": "omsk",
    "rostov": "rostov-na-donu",
    "rostov-na-donu": "rostov-na-donu",
    "ростов-на-дону": "rostov-na-donu",
    "ufa": "ufa",
    "уфа": "ufa",
    "krasnoyarsk": "krasnoyarsk",
    "красноярск": "krasnoyarsk",
    "voronezh": "voronezh",
    "воронеж": "voronezh",
    "perm": "perm",
    "пермь": "perm",
    "volgograd": "volgograd",
    "волгоград": "volgograd",
    "krasnodar": "krasnodar",
    "краснодар": "krasnodar",
    "sochi": "sochi",
    "сочи": "sochi",
    "tyumen": "tyumen",
    "тюмень": "tyumen",
    "kaliningrad": "kaliningrad",
    "калининград": "kaliningrad",
}

CITY_NAMES = {
    "moscow": "Москва",
    "spb": "Санкт-Петербург",
    "novosibirsk": "Новосибирск",
    "ekaterinburg": "Екатеринбург",
    "kazan": "Казань",
    "nizhniy-novgorod": "Нижний Новгород",
    "chelyabinsk": "Челябинск",
    "samara": "Самара",
    "omsk": "Омск",
    "rostov-na-donu": "Ростов-на-Дону",
    "ufa": "Уфа",
    "krasnoyarsk": "Красноярск",
    "voronezh": "Воронеж",
    "perm": "Пермь",
    "volgograd": "Волгоград",
    "krasnodar": "Краснодар",
    "sochi": "Сочи",
    "tyumen": "Тюмень",
    "kaliningrad": "Калининград",
}

CSV_FIELDS = [
    "source",
    "phone",
    "title",
    "city",
    "price_rub",
    "year",
    "mileage_km",
    "engine",
    "fuel",
    "transmission",
    "drive",
    "complectation",
    "listing_id",
    "url",
    "posted",
    "dealer_name",
]

_MODULE_RE = re.compile(
    r'<script[^>]*data-drom-module="bulls-list-auto"[^>]*>(.*?)</script>',
    re.S | re.I,
)
_DETAIL_MODULE_RE = re.compile(
    r'<script[^>]*data-drom-module="bull-page"[^>]*>(.*?)</script>',
    re.S | re.I,
)
_YEAR_RE = re.compile(r"(19|20)\d{2}")
_MILEAGE_RE = re.compile(r"([\d\s]{2,})\s*км", re.I)
_ENGINE_RE = re.compile(r"[\d.,]+\s*л")


def resolve_city_slug(raw: str) -> str:
    key = (raw or "").strip().lower()
    return CITY_SLUGS.get(key, re.sub(r"\s+", "-", key) or "moscow")


def list_url(city: str, page: int) -> str:
    slug = resolve_city_slug(city)
    if page <= 1:
        return f"{ORIGIN}/{slug}/all/"
    return f"{ORIGIN}/{slug}/all/page{page}/"


def find_bulls(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, dict):
        bulls = obj.get("bulls")
        if (
            isinstance(bulls, list)
            and bulls
            and isinstance(bulls[0], dict)
            and ("bullId" in bulls[0] or "url" in bulls[0])
        ):
            return [b for b in bulls if isinstance(b, dict)]
        for v in obj.values():
            found = find_bulls(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_bulls(v)
            if found:
                return found
    return []


def extract_bulls(html: str) -> List[Dict[str, Any]]:
    if not html:
        return []
    m = _MODULE_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    return find_bulls(data)


def extract_detail_module(html: str) -> Optional[Dict[str, Any]]:
    if not html:
        return None
    m = _DETAIL_MODULE_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _attr_payloads(bull: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for item in bull.get("attributes") or []:
        if isinstance(item, dict) and item.get("payload") not in (None, ""):
            out.append(str(item["payload"]))
        elif isinstance(item, str):
            out.append(item)
    return out


def parse_mileage(text: str) -> Any:
    m = _MILEAGE_RE.search(text or "")
    if not m:
        return ""
    digits = re.sub(r"\D", "", m.group(1))
    return int(digits) if digits else ""


def parse_year(title: str) -> Any:
    m = _YEAR_RE.search(title or "")
    return int(m.group(0)) if m else ""


def split_attrs(payloads: List[str]) -> Dict[str, str]:
    engine = fuel = transmission = drive = mileage_s = ""
    for p in payloads:
        if _ENGINE_RE.search(p) and not engine:
            engine = p
        elif any(x in p.lower() for x in ("бензин", "дизель", "гибрид", "электро", "газ")):
            fuel = p
        elif any(x in p.upper() for x in ("АКПП", "МКПП", "ВАРИАТОР", "РОБОТ")) or "вариатор" in p.lower():
            transmission = p
        elif any(x in p.lower() for x in ("передний", "задний", "полный")):
            drive = p
        elif "км" in p.lower() and not mileage_s:
            mileage_s = p
    return {
        "engine": engine,
        "fuel": fuel,
        "transmission": transmission,
        "drive": drive,
        "mileage_raw": mileage_s,
    }


def normalize_listing(
    bull: Dict[str, Any],
    *,
    fallback_city: str = "",
    phones: Optional[List[str]] = None,
    keep_raw: bool = True,
) -> Dict[str, Any]:
    listing_id = str(bull.get("bullId") or "")
    title = bull.get("title") or ""
    payloads = _attr_payloads(bull)
    attrs = split_attrs(payloads)
    nums = [n for n in (normalize_phone(p) for p in (phones or [])) if n]
    city = bull.get("location") or fallback_city
    price = bull.get("price")
    row: Dict[str, Any] = {
        "source": SOURCE,
        "id": listing_id,
        "listing_id": listing_id,
        "place_id": listing_id,
        "phone": nums[0] if nums else "",
        "phone2": nums[1] if len(nums) > 1 else "",
        "phones": nums,
        "title": title,
        "name": title,
        "city": city,
        "price_rub": price if price not in (None, "") else "",
        "price": price if price not in (None, "") else "",
        "currency": "RUB" if price not in (None, "") else "",
        "year": parse_year(title),
        "mileage_km": parse_mileage(attrs.get("mileage_raw") or ""),
        "engine": attrs.get("engine") or "",
        "fuel": attrs.get("fuel") or "",
        "transmission": attrs.get("transmission") or "",
        "drive": attrs.get("drive") or "",
        "complectation": bull.get("subtitle") or "",
        "url": bull.get("url") or "",
        "posted": bull.get("date") or "",
        "dealer_name": bull.get("dealerName") or "",
        "sold": bool(bull.get("sold")),
        "category": "cars",
    }
    if keep_raw:
        raw = {k: v for k, v in bull.items() if k != "images"}
        row["raw"] = raw
    return row


def parse_contacts_response(body: str) -> Tuple[List[str], str]:
    """Return (phones, status). status: ok | blocked | empty | error."""
    if not body:
        return [], "empty"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return [], "error"
    if not isinstance(data, dict):
        return [], "error"
    # type 4 = bad/incomplete request; type 5 + loginUrl = auth required
    # type 9 = success (phone is often an HTML snippet)
    if data.get("type") == 4:
        return [], "blocked"
    err = data.get("contactErrorNotification")
    if isinstance(err, dict) and (err.get("loginUrl") or data.get("type") == 5):
        return [], "auth_required"
    phones: List[str] = []
    for key in ("phone", "phones", "number", "numbers", "value"):
        val = data.get(key)
        if isinstance(val, str):
            n = normalize_phone(re.sub(r"<[^>]+>", " ", val))
            if n:
                phones.append(n)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    n = normalize_phone(item.get("phone") or item.get("number") or item)
                else:
                    n = normalize_phone(item)
                if n:
                    phones.append(n)
    # nested
    for key in ("contacts", "data", "result"):
        inner = data.get(key)
        if isinstance(inner, dict):
            extra, _st = parse_contacts_response(json.dumps(inner))
            phones.extend(extra)
        elif isinstance(inner, list):
            for item in inner:
                n = normalize_phone(item if not isinstance(item, dict) else item.get("phone") or item.get("number"))
                if n:
                    phones.append(n)
    # unique
    seen = set()
    uniq = []
    for n in phones:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq, ("ok" if uniq else "empty")


def fetch_phones(
    client: HttpClient,
    detail: Dict[str, Any],
    *,
    referer: str = "",
) -> Tuple[List[str], str]:
    contact = detail.get("contact") or {}
    if not isinstance(contact, dict):
        return [], "empty"
    bull_id = (detail.get("constants") or {}).get("bullId") or ""
    base = contact.get("baseUrl") or (
        f"https://www.drom.ru/api/sales/bulls/{bull_id}/contacts" if bull_id else ""
    )
    if not base:
        return [], "empty"
    # Browser click on [data-ftid=open-contacts] uses:
    #   contactData, regionIp, token, dust
    token = contact.get("contactToken") or contact.get("token") or ""
    cdata = contact.get("contactData") or ""
    region_ip = contact.get("regionIp") or ""
    query = {
        "contactData": cdata,
        "token": token,
        "dust": "VGQBwPQs",
    }
    if region_ip not in (None, ""):
        query["regionIp"] = str(region_ip)
    url = base + "?" + urlencode(query)
    try:
        body = client.get(
            url,
            accept="application/json,text/javascript,*/*;q=0.01",
            referer=referer or ORIGIN + "/",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
    except HttpError:
        return [], "error"
    return parse_contacts_response(body)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Drom.ru auto listings (HTTP list JSON; phones need session, often blocked)",
    )
    p.add_argument(
        "-c",
        "--city",
        action="append",
        dest="cities",
        default=None,
        help="city slug (moscow, spb, kazan…). Also CITIES=moscow,spb",
    )
    p.add_argument("--pages", type=int, default=int(os.environ.get("PAGES", "2")))
    p.add_argument("--max", type=int, default=int(os.environ.get("MAX", "40")))
    p.add_argument("--out", default=os.environ.get("OUT", "output/drom_listings"))
    p.add_argument("--proxy", default=os.environ.get("PROXY", ""))
    p.add_argument("--timeout", type=float, default=float(os.environ.get("TIMEOUT", "30")))
    p.add_argument("--retries", type=int, default=int(os.environ.get("RETRIES", "4")))
    p.add_argument("--sleep", type=float, default=float(os.environ.get("SLEEP", "0.5")))
    add_cookie_args(
        p,
        env_name="DROM_COOKIE",
        help_cookie="logged-in Drom Cookie header (required for phones)",
    )
    p.add_argument(
        "--phones",
        action="store_true",
        help="fetch detail + contacts API (needs DROM_COOKIE / --cookie-file)",
    )
    p.add_argument("--raw", dest="keep_raw", action="store_true", default=True)
    p.add_argument("--no-raw", dest="keep_raw", action="store_false")
    add_output_args(p)
    return p.parse_args(argv)


def scrape(
    *,
    cities: Optional[List[str]] = None,
    pages: int = 2,
    max_per_city: int = 40,
    proxy: str = "",
    timeout: float = 30.0,
    retries: int = 4,
    sleep: float = 0.5,
    keep_raw: bool = True,
    want_phones: bool = False,
    cookie: str = "",
    cookie_file: str = "",
    out: Optional[str] = None,
    formats: str = "csv,json",
    resume: bool = False,
    write: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Collect Drom listings. Writes files only when ``out`` is set."""
    from parser_toolkit.core.cookies import cookie_status, load_cookie
    from parser_toolkit.core.report import RunReport, persist_run
    from parser_toolkit.core.resume import load_checkpoint, seed_rows
    from parser_toolkit.core.schema import phone_metrics

    city_list = resolve_cities(cities) or list(DEFAULT_CITIES)
    cookie = load_cookie(cookie=cookie, cookie_file=cookie_file, env_names=("DROM_COOKIE",))
    should_write = write if write is not None else bool(out)
    report = RunReport(source=SOURCE)
    report.extra["phones"] = "contacts_api" if want_phones else "skipped"
    report.extra["cookie"] = cookie_status(cookie)

    print("Drom.ru parser — auto.drom.ru list JSON (Direct HTTP)")
    print(f"cities={city_list} pages={pages} max/city={max_per_city}")
    if want_phones:
        print(
            "phones: ON (click-equivalent GET /contacts?contactData&token&regionIp)"
            f" cookie={cookie_status(cookie)}"
        )
        if not cookie:
            print(
                "  NOTE: Drom returns type=5 / loginUrl without a logged-in session.\n"
                "  Export Cookie from my.drom.ru after sign-in → DROM_COOKIE or --cookie-file"
            )
    else:
        print("phones: OFF (default; pass --phones + DROM_COOKIE for numbers)")
    if proxy:
        print(f"proxy={proxy.split('@')[-1] if '@' in proxy else proxy}")

    client = HttpClient(
        timeout=timeout,
        retries=retries,
        proxy=proxy,
        sleep_base=max(sleep, 0.2),
        cookie=cookie,
    )

    rows: Dict[str, Dict[str, Any]] = {}
    if resume and out:
        n = seed_rows(rows, load_checkpoint(out))
        report.resumed = True
        report.resumed_from = n
        if n:
            print(f"resume: loaded {n} existing listings from {out}.*")

    phones_ok = 0
    phones_blocked = 0

    for city_raw in city_list:
        slug = resolve_city_slug(city_raw)
        display = CITY_NAMES.get(slug, city_raw)
        print(f"[{display} / {slug}] …")
        city_new = 0
        for page in range(1, max(1, pages) + 1):
            url = list_url(slug, page)
            try:
                html = client.get(url, referer=ORIGIN + "/")
            except HttpError as e:
                print(f"    page {page} error: {e}")
                report.add_error(f"{slug} p{page}: {e}")
                break
            bulls = extract_bulls(html)
            if not bulls:
                print(f"    page {page}: empty")
                break
            added = 0
            for bull in bulls:
                lid = str(bull.get("bullId") or "")
                if not lid or lid in rows:
                    continue
                phone_list: List[str] = []
                if want_phones:
                    detail_url = bull.get("url") or ""
                    if detail_url:
                        try:
                            dhtml = client.get(detail_url, referer=url)
                            detail = extract_detail_module(dhtml) or {}
                            phone_list, status = fetch_phones(
                                client, detail, referer=detail_url
                            )
                            if status == "ok" and phone_list:
                                phones_ok += 1
                            elif status in ("blocked", "auth_required"):
                                phones_blocked += 1
                        except HttpError as e:
                            report.add_error(f"detail {lid}: {e}")
                        time.sleep(sleep * 0.5)
                row = normalize_listing(
                    bull,
                    fallback_city=display,
                    phones=phone_list,
                    keep_raw=keep_raw,
                )
                rows[lid] = row
                added += 1
                city_new += 1
                if city_new >= max_per_city:
                    break
            print(f"    page {page}: +{added} (city={city_new} total={len(rows)})")
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
    extra.update({"phones_ok": phones_ok, "phones_blocked": phones_blocked})
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
        f"ok={phones_ok} blocked={phones_blocked}"
    )
    return records


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    scrape(
        cities=args.cities,
        pages=args.pages,
        max_per_city=args.max,
        proxy=args.proxy or "",
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
        keep_raw=args.keep_raw,
        want_phones=bool(args.phones),
        cookie=getattr(args, "cookie", "") or "",
        cookie_file=getattr(args, "cookie_file", "") or "",
        out=args.out,
        formats=getattr(args, "formats", "csv,json"),
        resume=getattr(args, "resume", False),
        write=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
