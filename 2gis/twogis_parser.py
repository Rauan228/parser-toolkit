#!/usr/bin/env python3
"""
2GIS places parser — collects organizations of ANY category from 2GIS with their
OPEN public phone numbers, via the Apify actor `zen-studio/2gis-places-scraper-api`.

2GIS is a business directory, so phones are public by design — no "reveal" step.
Search by any free-text query ("рестораны", "автосервис", "стоматология",
"квартиры посуточно", ...) across any set of cities, or point it at exact 2GIS
rubric/category URLs via START_URLS.

Requires an Apify API token (free tier available). Set it via APIFY_TOKEN.
The actor uses Apify's own proxies, so you do NOT need your own proxy here.

Output: CSV + JSON with phone, name, city, address, category, url.

Usage:
    APIFY_TOKEN="apify_api_..." QUERY="кофейни" CITIES="moscow,spb" python twogis_parser.py
    APIFY_TOKEN="..." START_URLS="https://2gis.ru/moscow/search/..." python twogis_parser.py
"""
import re, json, time, os, csv, urllib.request, urllib.error

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ACTOR = "zen-studio~2gis-places-scraper-api"
OUT = os.environ.get("OUT", "twogis_places")
MAX = int(os.environ.get("MAX", "500"))

# What to search for. Any 2GIS category works: "рестораны", "автосервис",
# "стоматология", "фитнес", "квартиры посуточно", etc.
QUERY = os.environ.get("QUERY", "рестораны")

# Optional: target exact 2GIS URLs (rubric pages, precise categories). If set,
# START_URLS overrides QUERY+CITIES. Comma-separated.
START_URLS = [u.strip() for u in os.environ.get("START_URLS", "").split(",") if u.strip()]

# 2GIS city slugs. Override with CITIES="moscow,spb,kazan,...".
DEFAULT_CITIES = [
    ("moscow", "Москва"), ("spb", "Санкт-Петербург"), ("sochi", "Сочи"),
    ("kazan", "Казань"), ("krasnodar", "Краснодар"), ("ekaterinburg", "Екатеринбург"),
    ("novosibirsk", "Новосибирск"), ("nizhny_novgorod", "Нижний Новгород"),
    ("kaliningrad", "Калининград"), ("rostov", "Ростов-на-Дону"), ("tyumen", "Тюмень"),
    ("ufa", "Уфа"), ("samara", "Самара"), ("chelyabinsk", "Челябинск"),
    ("krasnoyarsk", "Красноярск"), ("perm", "Пермь"), ("volgograd", "Волгоград"),
]

def _cities():
    env = os.environ.get("CITIES")
    if not env:
        return DEFAULT_CITIES
    by = {s: n for s, n in DEFAULT_CITIES}
    return [(s.strip(), by.get(s.strip(), s.strip())) for s in env.split(",")]

def api(method, path, body=None, timeout=60):
    url = f"https://api.apify.com/v2/{path}"
    url += ("&" if "?" in url else "?") + f"token={APIFY_TOKEN}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def run_input(body, label):
    try:
        run = api("POST", f"acts/{ACTOR}/runs", body, timeout=45)
    except urllib.error.HTTPError as e:
        print(f"    start failed ({label}): HTTP {e.code}")
        return []
    rid = run.get("data", {}).get("id")
    if not rid:
        return []
    st = ""
    for _ in range(60):
        time.sleep(10)
        try:
            st = api("GET", f"actor-runs/{rid}").get("data", {}).get("status", "")
        except Exception:
            pass
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    try:
        items = api("GET", f"actor-runs/{rid}/dataset/items?clean=true&limit=1000")
    except Exception:
        items = []
    if items and isinstance(items[0], dict) and items[0].get("_upgradeRequired"):
        print(f"    Apify free-tier limit reached: {items[0].get('_message')}")
        return []
    return items

def _norm(p):
    d = re.sub(r"\D", "", str(p or ""))
    if len(d) == 11 and d[0] in "78": return "+7" + d[1:]
    if len(d) == 10: return "+7" + d
    return d and ("+" + d) or None  # keep non-RU numbers as-is (2GIS covers other countries too)

FIELDS = ["phone", "name", "city", "address", "category", "url"]

def dump(rows):
    data = list(rows.values())
    json.dump(data, open(OUT + ".json", "w"), ensure_ascii=False, indent=1)
    with open(OUT + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(FIELDS)
        for r in data:
            w.writerow([r.get(k, "") for k in FIELDS])

def collect(items, city, rows):
    new = 0
    for it in (items or []):
        phones = it.get("phones") or it.get("phone") or []
        if isinstance(phones, str):
            phones = [phones]
        name = it.get("name") or it.get("fullName") or ""
        addr = it.get("fullAddress") or it.get("address") or city
        url = it.get("url") or ""
        rubr = ", ".join(r.get("name", "") for r in (it.get("rubrics") or []))[:60] if it.get("rubrics") else (it.get("poiCategory") or "")
        for ph in phones:
            n = _norm(ph)
            if not n or n in rows:
                continue
            rows[n] = {"phone": n, "name": name, "city": city,
                       "address": addr, "category": rubr, "url": url}
            new += 1
    return new

def main():
    if not APIFY_TOKEN:
        print("ERROR: set APIFY_TOKEN (get a free one at https://console.apify.com/account/integrations)")
        return
    rows = {}
    base = {"maxResults": MAX, "maxReviews": 0, "maxPhotos": 0, "language": "ru",
            "proxyConfiguration": {"useApifyProxy": True}}
    if START_URLS:
        items = run_input({**base, "startUrls": START_URLS}, "startUrls")
        new = collect(items, "", rows)
        print(f"[startUrls] +{new} | total={len(rows)}")
        dump(rows)
    else:
        for slug, city in _cities():
            items = run_input({**base, "query": [QUERY], "location": city}, city)
            new = collect(items, city, rows)
            print(f"[{city}] +{new} | total={len(rows)}")
            dump(rows)
    dump(rows)
    print(f"\nDone: {len(rows)} unique phones -> {OUT}.csv / {OUT}.json")

if __name__ == "__main__":
    main()
