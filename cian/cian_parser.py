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
import re, json, time, os, csv, urllib.request, ssl, gzip, io

# --- config (env-overridable) ------------------------------------------------
PROXY = os.environ.get("PROXY", "")  # http://user:pass@host:port  (RU proxy required)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
OUT = os.environ.get("OUT", "cian_listings")
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

FIELDS = ["phone", "phone2", "city", "price_rub", "rooms", "area_m2",
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
    return {
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
        "url": o.get("fullUrl") or "",
    }

def dump(rows):
    data = list(rows.values())
    json.dump(data, open(OUT + ".json", "w"), ensure_ascii=False, indent=1)
    with open(OUT + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(FIELDS)
        for r in data:
            w.writerow([r.get(k, "") for k in FIELDS])

def main():
    if not PROXY:
        print("WARNING: no PROXY set. CIAN geo-blocks non-RU IPs — set a Russian "
              "residential/mobile proxy via the PROXY env var, e.g.\n"
              '  PROXY="http://user:pass@host:port" python cian_parser.py')
    rows = {}
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
                    rows[r["phone"]] = r; new += 1
                time.sleep(1.1)
        print(f"[{city}] +{new} | total={len(rows)}")
        dump(rows)
    dump(rows)
    print(f"\nDone: {len(rows)} unique listings -> {OUT}.csv / {OUT}.json")

if __name__ == "__main__":
    main()
