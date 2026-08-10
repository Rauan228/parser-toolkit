# 🧰 parser-toolkit

> Ready-to-run local parsers for popular CIS/RU platforms — directories, marketplaces and real estate.

[Русская версия →](README.ru.md)

Covers **2GIS**, **Yandex Maps**, **CIAN**, **Krisha.kz** and **Kolesa.kz**. Pull listings and business data into clean CSV + JSON. You decide what to collect.

Directory parsers (2GIS / Yandex) collect **public business phones**. Real-estate / marketplace parsers collect listing metadata; phone rules depend on the site (CIAN phones are open in page state; Krisha needs a logged-in cookie; Kolesa needs Playwright for the reCAPTCHA phone flow — see below).

**No Apify. Parsers run locally, primarily over direct HTTP. Browser automation is used only where the source requires it.**

Currently implemented with Python stdlib + optional Playwright for Kolesa phone extraction.

---

## 📦 What's inside

| Parser | Source | Collects | Method | Proxy | User API key |
|---|---|---|---|---|---|
| [`2gis/`](2gis/) | [2GIS](https://2gis.ru) | any business category | Direct HTTP / Internal Catalog Web API | optional | Not required |
| [`yandex-maps/`](yandex-maps/) | [Yandex Maps](https://yandex.ru/maps) | any business category | Direct HTTP / Embedded JSON (search HTML) | optional | Not required |
| [`cian/`](cian/) | [CIAN](https://cian.ru) | any real-estate section | Direct HTTP / Embedded JSON | 🇷🇺 RU proxy required | Not required |
| [`krisha/`](krisha/) | [Krisha.kz](https://krisha.kz) | any real-estate section (KZ) | Direct HTTP / HTML list + `window.data` | optional | Not required |
| [`kolesa/`](kolesa/) | [Kolesa.kz](https://kolesa.kz) | auto listings (KZ) | Direct HTTP + Playwright (phones/reCAPTCHA) | optional | Not required |

Shared helpers live in [`core/`](core/) (HTTP client, unified place model, CSV/JSON writers).

- **2GIS / Yandex Maps** — business directories: any query + list of cities.
- **CIAN / Krisha** — real estate listings (RU / KZ).
- **2GIS** uses the web key exposed by the 2GIS frontend; no user-provided API key is required.
- **Krisha** full phones need an optional logged-in browser cookie (`KRISHA_COOKIE`); metadata works without it.
- **Kolesa** phones need Playwright (reCAPTCHA v3 runs in a real browser click flow); optional `KOLESA_COOKIE`.

---

## 🚀 Quick start

```bash
git clone https://github.com/Rauan228/parser-toolkit.git
cd parser-toolkit
pip install -r requirements.txt   # stdlib for most parsers; Playwright for Kolesa phones
playwright install chromium       # only needed for kolesa/
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

### Kolesa.kz — autos (HTTP + Playwright phones)

```bash
pip install playwright
playwright install chromium

# phones are ON by default (Playwright clicks «Показать телефон»)
KOLESA_COOKIE="klssid=…; kumd=…; …" \
  python kolesa/kolesa_parser.py --city almaty --pages 1 --max 15 --out output/kolesa
```

Phones API: `GET app.kolesa.kz/adverts/{id}/phones?captchaTokenV3=…&source=advert`  
(token is produced inside Chromium — not hard-coded, not cracked).

Outputs default under `output/`:

```
output/twogis_places.json
output/yandex_maps_places.json
output/krisha_listings.json
output/kolesa_listings.json
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
| Kolesa.kz | Playwright + Chromium; optional `KOLESA_COOKIE` for session-dependent phone flow |

---

## ⚙️ How it works

- **2GIS** — `catalog.api.2gis.ru/3.0/items` (+ `region/list`) with the site’s `webApiOutsourceKey`; paginates and maps `contact_groups` → phones/website/email.
- **Yandex Maps** — fetches public search HTML and parses the SPA hydration JSON at `stack[0].results.items[]`; paginates with `?page=N`. Domain fallback (`yandex.ru` → `yandex.kz` → …) if a host returns `429 limited`.
- **CIAN** — slices the balanced `"offers":[…]` array from server-rendered page state.
- **Krisha** — list HTML (`data-product-id`) + detail `window.data`; phones via `/a/ajaxPhones?id=` (login session cookie when Krisha requires auth).
- **Kolesa** — list/detail over HTTP; phones via Playwright intercept of `app.kolesa.kz/adverts/{id}/phones` (reCAPTCHA v3 in browser).

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
| `KOLESA_COOKIE` / `--cookie` | kolesa | browser session cookie (recommended) |
| `--no-phones` | kolesa | metadata only (phones required by default) |

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
