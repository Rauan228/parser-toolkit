#!/usr/bin/env python3
"""
CIAN listings parser — extracts real-estate listings with OPEN owner phone numbers
straight from CIAN's embedded JSON state. No API key, no CAPTCHA, no "reveal phone"
click: the phones are already in the page's server-rendered state.

Works on ANY CIAN section — set CIAN_PATH to the search path you want:
    snyat-kvartiru-posutochno   daily rent (default)
    snyat-kvartiru              long-term rent
    kupit-kvartiru              buy apartment
    kupit-dom                   buy house
    snyat-pomeshchenie          commercial rent
(the phones live in the same JSON state regardless of section).

Requires a Russian residential/mobile proxy (CIAN geo-blocks non-RU IPs and
throws automation to a decoy "/museum" page without a real browser fingerprint).
Set it via the PROXY env var.

Output: CSV + JSON with phone, address, price, rooms, area, floor, metro,
        furniture, posted date, description and the listing URL.

Usage:
    PROXY="http://user:pass@host:port" python cian_parser.py
    PROXY="..." CIAN_PATH="snyat-kvartiru" CITIES="www,spb" PAGES=5 python cian_parser.py
"""
import argparse
import csv
import gzip
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.request

# --- config (env-overridable; CLI can override) ------------------------------
PROXY = os.environ.get("PROXY", "")  # http://user:pass@host:port  (RU proxy required)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
OUT = os.environ.get("OUT", "output/cian_listings")
PAGES = int(os.environ.get("PAGES", "5"))
# CIAN search section (any listing type works). Default: daily rent.
CIAN_PATH = os.environ.get("CIAN_PATH", "snyat-kvartiru-posutochno").strip("/")
SORTS = ["", "?sort=creation_date_desc", "?sort=price_object_order",
         "?sort=price_square_order_desc"]

# CIAN city subdomains. "www" == Moscow. Override with CITIES="www,spb,kazan".
DEFAULT_CITIES = [
    ("www", "Москва"), ("spb", "Санкт-Петербург"), ("sochi", "Сочи"),
    ("kazan", "Казань"), ("krasnodar", "Краснодар"), ("ekb", "Екатеринбург"),
    ("nsk", "Новосибирск"), ("nn", "Нижний Новгород"), ("rostov", "Ростов-на-Дону"),
    ("samara", "Самара"), ("ufa", "Уфа"), ("krasnoyarsk", "Красноярск"),
    ("perm", "Пермь"), ("volgograd", "Волгоград"), ("voronezh", "Воронеж"),
    ("tyumen", "Тюмень"), ("chelyabinsk", "Челябинск"), ("kaliningrad", "Калининград"),
    ("vladivostok", "Владивосток"), ("irkutsk", "Иркутск"), ("tomsk", "Томск"),
    ("omsk", "Омск"), ("saratov", "Саратов"), ("stavropol", "Ставрополь"),
]

def _cities():
    env = os.environ.get("CITIES")
    if not env:
        return DEFAULT_CITIES
    by_slug = {s: n for s, n in DEFAULT_CITIES}
    return [(s.strip(), by_slug.get(s.strip(), s.strip())) for s in env.split(",")]

FIELDS = ["source", "phone", "phone2", "city", "price_rub", "rooms", "area_m2",
          "floor", "floors_total", "address", "metro", "build_year", "furniture",
          "deposit", "owner_id", "posted", "description", "url"]

# --- fetch with integrity retry ----------------------------------------------
def offers_complete(html):
    """True only if the "offers":[...] array is fully downloaded (balanced)."""
    key = '"offers":['
    pos = html.find(key)
    if pos < 0:
        return False
    depth = 0; instr = False; esc = False
    for i in range(pos + len(key) - 1, len(html)):
        c = html[i]
        if esc: esc = False; continue
        if c == "\\": esc = True; continue
        if c == '"': instr = not instr; continue
        if instr: continue
        if c == "[": depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return True
    return False

def fetch(url):
    """GET via proxy, gzip-aware, retrying until the offers array is intact.
    Proxies sometimes truncate long responses (IncompleteRead)."""
    for _ in range(5):
        try:
            handlers = []
            if PROXY:
                handlers.append(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
            ctx = ssl.create_default_context(); ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
            op = urllib.request.build_opener(*handlers)
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9",
                "Accept-Encoding": "gzip"})
            r = op.open(req, timeout=60)
            data = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                try: data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                except Exception: pass
            html = data.decode("utf-8", "ignore")
            if offers_complete(html):
                return html
        except Exception:
            pass
        time.sleep(2)
    return ""

# --- parse -------------------------------------------------------------------
def extract_offers(html):
    """Slice the balanced "offers":[...] array out of CIAN's JSON state and parse."""
    key = '"offers":['
    pos = html.find(key)
    if pos < 0:
        return []
    start = pos + len(key) - 1
    depth = 0; instr = False; esc = False; end = None
    for i in range(start, len(html)):
        c = html[i]
        if esc: esc = False; continue
        if c == "\\": esc = True; continue
        if c == '"': instr = not instr; continue
        if instr: continue
        if c == "[": depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = i + 1; break
    if end is None:
        return []
    try:
        return json.loads(html[start:end])
    except Exception:
        return []

def _geo_full(o):
    g = o.get("geo") or {}
    parts = [a.get("fullName") or a.get("name") for a in (g.get("address") or [])]
    return ", ".join(p for p in parts if p)

def _geo_city(o):
    g = o.get("geo") or {}
    addr = g.get("address") or []
    for a in addr:
        if a.get("type") in ("location", "city") and a.get("name"):
            return a["name"]
    names = [a.get("name") for a in addr if a.get("name")]
    return names[1] if len(names) > 1 else (names[0] if names else "")

def _metro(o):
    g = o.get("geo") or {}
    return "; ".join(u.get("name", "") for u in (g.get("undergrounds") or []) if u.get("name"))[:80]

def _norm(num, cc="7"):
    d = re.sub(r"\D", "", str(num))
    if len(d) == 11 and d[0] in "78": return "+7" + d[1:]
    if len(d) == 10: return "+7" + d
    if len(d) == 11 and d.startswith("7"): return "+" + d
    return None

def row_of(o, fallback_city):
    phones = []
    for p in (o.get("phones") or []):
        n = _norm(p.get("number"), p.get("countryCode", "7")) if isinstance(p, dict) else _norm(p)
        if n and n not in phones:
            phones.append(n)
    if not phones:
        return None
    addr = _geo_full(o)
    if not addr:  # incomplete parse — skip, we only want full cards
        return None
    bt = o.get("bargainTerms") or {}
    url = o.get("fullUrl") or ""
    oid = o.get("cianId") or o.get("id") or ""
    return {
        "source": "cian",
        "id": str(oid) if oid else "",
        "listing_id": str(oid) if oid else "",
        "title": o.get("formattedTitle") or o.get("title") or "",
        "phones": phones,
        "phone": phones[0], "phone2": phones[1] if len(phones) > 1 else "",
        "city": _geo_city(o) or fallback_city,
        "price_rub": bt.get("priceRur") or o.get("formattedFullPrice") or "",
        "rooms": o.get("roomsCount") or o.get("bedroomsCount") or "",
        "area_m2": o.get("totalArea") or "", "floor": o.get("floorNumber") or "",
        "floors_total": o.get("floorsCount") or "", "address": addr, "metro": _metro(o),
        "build_year": o.get("buildYear") or "",
        "furniture": "yes" if o.get("hasFurniture") else "",
        "deposit": (o.get("offerInfo") or {}).get("deposit", "") if isinstance(o.get("offerInfo"), dict) else "",
        "owner_id": o.get("cianUserId") or "", "posted": o.get("creationDate") or o.get("added") or "",
        "description": re.sub(r"\s+", " ", (o.get("description") or ""))[:400],
        "url": url,
    }

def dump(rows, *, formats="csv,json"):
    from parser_toolkit.core.output import dump_records

    dump_records(list(rows.values()), OUT, fields=FIELDS, formats=formats, keep_raw=True, source="cian")


def parse_args(argv=None):
    from parser_toolkit.core.cli import add_output_args

    p = argparse.ArgumentParser(description="CIAN listings parser (Direct HTTP / embedded JSON)")
    p.add_argument("--proxy", default=PROXY, help="RU proxy http://user:pass@host:port (required)")
    p.add_argument("--path", dest="cian_path", default=CIAN_PATH, help="CIAN section path")
    p.add_argument("-c", "--city", action="append", dest="cities", default=None,
                   help="CIAN subdomain (www=Moscow). Also CITIES=www,spb")
    p.add_argument("--pages", type=int, default=PAGES)
    p.add_argument("--out", default=OUT)
    add_output_args(p)
    return p.parse_args(argv)


def scrape(
    *,
    proxy="",
    cian_path="",
    cities=None,
    pages=None,
    out=None,
    formats="csv,json",
    resume=False,
    write=None,
    require_proxy=True,
):
    """Collect CIAN listings. RU proxy is required unless require_proxy=False."""
    global PROXY, OUT, PAGES, CIAN_PATH
    from parser_toolkit.core.exitcodes import EXIT_BLOCKED
    from parser_toolkit.core.report import RunReport, persist_run
    from parser_toolkit.core.resume import load_checkpoint, seed_rows

    PROXY = (proxy if proxy is not None else PROXY or "").strip()
    if cian_path:
        CIAN_PATH = cian_path.strip("/")
    if pages is not None:
        PAGES = pages
    if cities:
        os.environ["CITIES"] = ",".join(cities)
    if out:
        OUT = out
    should_write = write if write is not None else bool(out)

    if require_proxy and not PROXY:
        print(
            "ERROR: CIAN requires a Russian residential/mobile proxy.\n"
            "  parser-toolkit cian --proxy \"http://user:pass@host:port\"\n"
            "  or set PROXY=...",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_BLOCKED)

    report = RunReport(source="cian")
    rows = {}
    if resume and OUT:
        n = seed_rows(rows, load_checkpoint(OUT), key_fn=lambda r: r.get("phone") or "")
        report.resumed = True
        report.resumed_from = n
        if n:
            print(f"resume: loaded {n} existing phones from {OUT}.*")

    for slug, city in _cities():
        base = f"https://{slug}.cian.ru/{CIAN_PATH}/"
        new = 0
        for srt in SORTS:
            for pg in range(1, PAGES + 1):
                sep = "&" if srt else "?"
                url = base + srt + (f"{sep}p={pg}" if pg > 1 else "")
                html = fetch(url)
                if not html:
                    continue
                for o in extract_offers(html):
                    r = row_of(o, city)
                    if not r or r["phone"] in rows:
                        continue
                    rows[r["phone"]] = r
                    new += 1
                time.sleep(1.1)
        print(f"[{city}] +{new} | total={len(rows)}")
        if should_write:
            dump(rows, formats=formats)
    records = list(rows.values())
    if should_write:
        persist_run(
            records, OUT, fields=FIELDS, formats=formats, keep_raw=True, source="cian", report=report
        )
    else:
        report.finish(records=records)
    return records


def main(argv=None):
    args = parse_args(argv)
    scrape(
        proxy=args.proxy or "",
        cian_path=args.cian_path,
        cities=args.cities,
        pages=args.pages,
        out=args.out,
        formats=getattr(args, "formats", "csv,json"),
        resume=getattr(args, "resume", False),
        write=True,
        require_proxy=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
