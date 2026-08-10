# 🧰 parser-toolkit

> Ready-to-run parsers for three big CIS/RU platforms — **2GIS**, **Yandex Maps** and **CIAN**. Pull listings and business data **with open public phone numbers** into clean CSV + JSON. You decide what to collect.

[Русская версия →](README.ru.md)

Each parser targets a source where contact phones are **publicly available** (no CAPTCHA, no "reveal phone" wall). Search **any** category — restaurants, car services, clinics, gyms, real estate, whatever — the parsers don't assume a niche.

**No Apify.** Directory parsers talk to the platforms over Direct HTTP.

---

## 📦 What's inside

| Parser | Source | Collects | Method | Proxy | API key |
|---|---|---|---|---|---|
| [`2gis/`](2gis/) | [2GIS](https://2gis.ru) | any business category | Direct HTTP / Internal Catalog Web API | optional | — (site web key) |
| [`yandex-maps/`](yandex-maps/) | [Yandex Maps](https://yandex.ru/maps) | any business category | Direct HTTP / Embedded JSON (search HTML) | optional | — |
| [`cian/`](cian/) | [CIAN](https://cian.ru) | any real-estate section | Direct HTTP / Embedded JSON | 🇷🇺 RU proxy required | — |

Shared helpers live in [`core/`](core/) (HTTP client, unified place model, CSV/JSON writers).

- **2GIS / Yandex Maps** — business directories: any query + list of cities.
- **CIAN** — real estate: any section via `CIAN_PATH`.

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

Outputs default under `output/`:

```
output/twogis_places.json
output/twogis_places.csv
output/yandex_maps_places.json
output/yandex_maps_places.csv
```

---

## 📋 Output fields (directories)

Unified shape (JSON):

```json
{
  "source": "yandex-maps",
  "name": "…",
  "category": "…",
  "phones": ["+7…"],
  "phone": "+7…",
  "phone2": "",
  "address": "…",
  "city": "…",
  "latitude": 55.75,
  "longitude": 37.62,
  "rating": 4.7,
  "reviews_count": 120,
  "website": "https://…",
  "url": "https://yandex…/maps/org/…",
  "place_id": "…",
  "raw": { }
}
```

**CIAN** keeps its real-estate-specific columns (`price_rub`, `rooms`, `area_m2`, …).

CSV is UTF-8 with BOM for Excel.

---

## 🔑 Prerequisites

| Source | Need |
|---|---|
| 2GIS | nothing (uses the public web key embedded in 2gis.ru frontend) |
| Yandex Maps | nothing (optional proxy if your IP is rate-limited) |
| CIAN | Russian residential/mobile proxy |

---

## ⚙️ How it works

- **2GIS** — `catalog.api.2gis.ru/3.0/items` (+ `region/list`) with the site’s `webApiOutsourceKey`; paginates and maps `contact_groups` → phones/website/email.
- **Yandex Maps** — fetches public search HTML and parses the SPA hydration JSON at `stack[0].results.items[]`; paginates with `?page=N`. Domain fallback (`yandex.ru` → `yandex.kz` → …) if a host returns `429 limited`.
- **CIAN** — slices the balanced `"offers":[…]` array from server-rendered page state.

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
