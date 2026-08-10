#!/usr/bin/env python3
"""
Yandex Maps places parser — collects organizations (e.g. daily-rent apartments)
with OPEN phone numbers from Yandex Maps via the Apify actor
`zen-studio/yandex-maps-scraper`.

Like 2GIS, Yandex Maps is a directory: phones are public. This is a SEPARATE
dataset from 2GIS/CIAN (different hosts/apart-operators are listed), so it's
a good third source to widen coverage and de-duplicate against the others.

Requires an Apify API token (free tier available). Set it via APIFY_TOKEN.
The actor uses Apify's own proxies — no personal proxy needed.

Output: CSV + JSON with phone, name, city, address, rating, url, coordinates.

Usage:
    APIFY_TOKEN="apify_api_..." python yandex_maps_parser.py
    APIFY_TOKEN="..." QUERIES="квартиры посуточно" CITIES="Москва,Сочи" MAX=200 python yandex_maps_parser.py
"""
import re, json, time, os, csv, urllib.request, urllib.error

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ACTOR = "zen-studio~yandex-maps-scraper"
OUT = os.environ.get("OUT", "yandex_maps_daily_rent")
MAX = int(os.environ.get("MAX", "200"))
QUERY = os.environ.get("QUERIES", "квартиры посуточно")

DEFAULT_CITIES = ["Москва", "Санкт-Петербург", "Сочи", "Казань", "Краснодар",
                  "Екатеринбург", "Новосибирск", "Нижний Новгород", "Ростов-на-Дону",
                  "Самара", "Уфа", "Красноярск", "Пермь", "Калининград"]

def _cities():
    env = os.environ.get("CITIES")
    return [c.strip() for c in env.split(",")] if env else DEFAULT_CITIES

def api(method, path, body=None, timeout=60):
    url = f"https://api.apify.com/v2/{path}"
    url += ("&" if "?" in url else "?") + f"token={APIFY_TOKEN}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def run_city(city):
    body = {"query": [QUERY], "location": city, "maxResults": MAX,
            "language": "ru", "includeReviews": False}
    try:
        run = api("POST", f"acts/{ACTOR}/runs", body, timeout=45)
    except urllib.error.HTTPError as e:
        print(f"    start failed: HTTP {e.code}")
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
    return None

FIELDS = ["phone", "phone2", "name", "city", "address", "rating", "latitude",
          "longitude", "url"]

def dump(rows):
    data = list(rows.values())
    json.dump(data, open(OUT + ".json", "w"), ensure_ascii=False, indent=1)
    with open(OUT + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(FIELDS)
        for r in data:
            w.writerow([r.get(k, "") for k in FIELDS])

def _addr(it):
    parts = [it.get("city"), it.get("street"), it.get("house")]
    a = it.get("address")
    return a if a else ", ".join(p for p in parts if p)

def main():
    if not APIFY_TOKEN:
        print("ERROR: set APIFY_TOKEN (get a free one at https://console.apify.com/account/integrations)")
        return
    rows = {}
    for city in _cities():
        items = run_city(city)
        new = 0
        for it in (items or []):
            phones = it.get("phones") or it.get("phone") or []
            if isinstance(phones, str):
                phones = [phones]
            nums = [n for n in (_norm(p) for p in phones) if n]
            if not nums:
                continue
            n = nums[0]
            if n in rows:
                continue
            rows[n] = {
                "phone": n, "phone2": nums[1] if len(nums) > 1 else "",
                "name": it.get("title") or it.get("name") or "",
                "city": it.get("city") or city, "address": _addr(it),
                "rating": it.get("rating") or "",
                "latitude": it.get("latitude") or "", "longitude": it.get("longitude") or "",
                "url": it.get("url") or "",
            }
            new += 1
        print(f"[{city}] +{new} | total={len(rows)}")
        dump(rows)
    dump(rows)
    print(f"\nDone: {len(rows)} unique phones -> {OUT}.csv / {OUT}.json")

if __name__ == "__main__":
    main()
