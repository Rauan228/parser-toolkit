# 🧰 parser-toolkit

> Ready-to-run parsers for popular CIS/RU platforms — **2GIS**, **Yandex Maps**, **CIAN** and **Krisha.kz**. Pull listings and business data into clean CSV + JSON. You decide what to collect.

[Русская версия →](README.ru.md)

Directory parsers (2GIS / Yandex) collect **public business phones**. Real-estate parsers collect listing metadata; phone rules depend on the site (CIAN phones are open in page state; Krisha full phones need a logged-in browser session — see below).

**No Apify.** All parsers talk to the platforms over Direct HTTP (stdlib only).

---

## 📦 What's inside

| Parser | Source | Collects | Method | Proxy | User API key |
|---|---|---|---|---|---|
| [`2gis/`](2gis/) | [2GIS](https://2gis.ru) | any business category | Direct HTTP / Internal Catalog Web API | optional | Not required |
| [`yandex-maps/`](yandex-maps/) | [Yandex Maps](https://yandex.ru/maps) | any business category | Direct HTTP / Embedded JSON (search HTML) | optional | Not required |
| [`cian/`](cian/) | [CIAN](https://cian.ru) | any real-estate section | Direct HTTP / Embedded JSON | 🇷🇺 RU proxy required | Not required |
| [`krisha/`](krisha/) | [Krisha.kz](https://krisha.kz) | any real-estate section (KZ) | Direct HTTP / HTML list + `window.data` | optional | Not required |

Shared helpers live in [`core/`](core/) (HTTP client, unified place model, CSV/JSON writers).

- **2GIS / Yandex Maps** — business directories: any query + list of cities.
- **CIAN / Krisha** — real estate listings (RU / KZ).
- **2GIS** uses the web key exposed by the 2GIS frontend; no user-provided API key is required.
- **Krisha** full phones need an optional logged-in browser cookie (`KRISHA_COOKIE`); metadata works without it.

---

## 🚀 Quick start

```bash
git clone https://github.com/Rauan228/parser-toolkit.git
cd parser-toolkit
pip install -r requirements.txt   # stdlib-only; file kept for completeness
```

### 2GIS — Direct HTTP / Internal Catalog Web API

```bash
python 2gis/twogis_parser.py --query "стоматология" --city moscow --city spb --max 100
# or env-style:
QUERY="кофейни" CITIES="moscow,spb" python 2gis/twogis_parser.py
```

### Yandex Maps — Direct HTTP / Embedded JSON

```bash
python yandex-maps/yandex_maps_parser.py --query "стоматология" --city "Астана" --max 50
QUERY="барбершоп" CITIES="Москва,Сочи" python yandex-maps/yandex_maps_parser.py
```

### CIAN — Direct HTTP / Embedded JSON (RU proxy)

```bash
PROXY="http://user:pass@host:port" CIAN_PATH="snyat-kvartiru-posutochno" python cian/cian_parser.py
```

### Krisha.kz — Direct HTTP (KZ real estate)

```bash
# metadata only (+ phone_preview like "+7 778")
python krisha/krisha_parser.py --deal arenda --type kvartiry --city almaty --pages 2

# metadata + FULL phones (logged-in Krisha session cookie required)
# DevTools → open any /a/show/… → Network → document request → copy Cookie header
# Need krssid + kumd (not Google Ads cookies)
KRISHA_COOKIE="krishauid=…; krssid=…; kumd=…; …" \
  python krisha/krisha_parser.py --deal prodazha --type kvartiry --city astana --pages 1 --max 30
```

> **Note:** the site UI shows «Показать телефон», but with a logged-in session the
> full number is already in the page JSON (`window.data` → `adverts[].phones`).
> The parser reads that — no captcha, no click simulation.

Outputs default under `output/`:

```
output/twogis_places.json
output/yandex_maps_places.json
output/krisha_listings.json
```

---

## 📋 Output fields

### Directories (2GIS / Yandex Maps)

```json
{
  "source": "yandex-maps",
  "name": "…",
  "category": "…",
  "phones": ["+7…"],
  "phone": "+7…",
  "address": "…",
  "city": "…",
  "latitude": 55.75,
  "longitude": 37.62,
  "rating": 4.7,
  "url": "https://…",
  "raw": { }
}
```

### Real estate — Krisha example

```json
{
  "source": "krisha",
  "phone": "+77780965105",
  "phone_preview": "+7 778",
  "title": "4-комнатная квартира · 130 м²",
  "city": "Астана",
  "district": "Сарайшык р-н",
  "address": "Астана, Сарайшык р-н, Шамши Калдаяков 8",
  "price_kzt": 185000000,
  "rooms": 4,
  "area_m2": 130,
  "floor": 7,
  "floors_total": 9,
  "owner_name": "…",
  "deal_type": "prodazha",
  "property_type": "kvartiry",
  "latitude": 51.11,
  "longitude": 71.46,
  "listing_id": "1013203617",
  "url": "https://krisha.kz/a/show/1013203617",
  "description": "…"
}
```

**CIAN** uses its own columns (`price_rub`, `rooms`, `area_m2`, …).  
CSV is UTF-8 with BOM for Excel.

---

## 🔑 Prerequisites

| Source | Need |
|---|---|
| 2GIS | no user API key (uses the web key exposed by the 2GIS frontend) |
| Yandex Maps | no user API key (optional proxy if your IP is rate-limited) |
| CIAN | Russian residential/mobile proxy |
| Krisha.kz | no user API key; optional `KRISHA_COOKIE` for full phones |

---

## ⚙️ How it works

- **2GIS** — `catalog.api.2gis.ru/3.0/items` (+ `region/list`) with the site’s `webApiOutsourceKey`; paginates and maps `contact_groups` → phones/website/email.
- **Yandex Maps** — fetches public search HTML and parses the SPA hydration JSON at `stack[0].results.items[]`; paginates with `?page=N`. Domain fallback (`yandex.ru` → `yandex.kz` → …) if a host returns `429 limited`.
- **CIAN** — slices the balanced `"offers":[…]` array from server-rendered page state.
- **Krisha** — list HTML (`data-product-id`) + detail `window.data`; phones via `/a/ajaxPhones?id=` (login session cookie when Krisha requires auth).

---

## ⚙️ Common env / CLI

| Var / flag | Parsers | Meaning |
|---|---|---|
| `--query` / `QUERY` | 2gis, yandex-maps | search text |
| `--city` / `CITIES` | all | cities (CLI repeatable / comma env) |
| `--max` / `MAX` | 2gis, yandex-maps | volume per city |
| `--out` / `OUT` | all | output prefix |
| `--proxy` / `PROXY` | all (optional except CIAN) | HTTP proxy |
| `CIAN_PATH` | cian | CIAN section |
| `TWOGIS_KEY` | 2gis | optional Catalog key override |
| `YANDEX_DOMAINS` | yandex-maps | Maps host fallback list |
| `KRISHA_COOKIE` / `--cookie` | krisha | browser session cookie for full phones |
| `--deal` `--type` | krisha | e.g. `arenda` / `kvartiry` |

---

## 🧪 Tests

```bash
python -m unittest discover -s tests -v
```

Tests use local fixtures only — they do **not** hit live sites.

---

## ⚠️ Notes & disclaimer

- Data comes from **public listings/directories**. Use it responsibly and in line with each source's Terms of Service and local data-protection laws.
- Sources change markup and endpoints over time — parsers may need occasional updates.
- Built-in delays/retries reduce load; do not disable them for bulk runs without good reason.
- You are responsible for how you use the collected data.

---

## 📄 License

[MIT](LICENSE)

---

Made by [@Rauan228](https://github.com/Rauan228). PRs and new source parsers welcome.
