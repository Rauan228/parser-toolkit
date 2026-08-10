# 🧰 parser-toolkit

> Ready-to-run parsers for three big Russian platforms — **2GIS**, **Yandex Maps** and **CIAN**. Pull listings and business data **with open public phone numbers** into clean CSV + JSON. You decide what to collect.

[Русская версия →](README.ru.md)

Each parser targets a source where contact phones are **publicly available** (no CAPTCHA, no "reveal phone" wall). Search **any** category — restaurants, car services, clinics, gyms, real estate, whatever — the parsers don't assume a niche.

---

## 📦 What's inside

| Parser | Source | Collects | Method | Proxy | API key |
|---|---|---|---|---|---|
| [`2gis/`](2gis/) | [2GIS](https://2gis.ru) | any business category | Apify actor | — (Apify's own) | Apify token |
| [`yandex-maps/`](yandex-maps/) | [Yandex Maps](https://yandex.ru/maps) | any business category | Apify actor | — (Apify's own) | Apify token |
| [`cian/`](cian/) | [CIAN](https://cian.ru) | any real-estate section | Direct HTTP (embedded JSON) | 🇷🇺 RU proxy required | — |

- **2GIS / Yandex Maps** are business directories — feed them any search query and a list of cities.
- **CIAN** is a real-estate platform — point it at any section (rent, sale, daily rent, commercial…) via one env var.

The three sources return **different, complementary datasets** — run them all and de-duplicate by phone for maximum coverage.

---

## 🚀 Quick start

```bash
git clone https://github.com/Rauan228/parser-toolkit.git
cd parser-toolkit
pip install -r requirements.txt   # stdlib-only, but here for completeness
```

### 2GIS — via Apify (token, no proxy)

```bash
APIFY_TOKEN="apify_api_..." QUERY="кофейни" CITIES="moscow,spb" python 2gis/twogis_parser.py
```
`QUERY` — anything: `рестораны`, `автосервис`, `стоматология`, `квартиры посуточно`, …

### Yandex Maps — via Apify (token, no proxy)

```bash
APIFY_TOKEN="apify_api_..." QUERY="барбершоп" CITIES="Москва,Сочи" python yandex-maps/yandex_maps_parser.py
```

### CIAN — direct parser (needs a Russian proxy)

CIAN geo-blocks non-RU IPs and sends headless clients to a decoy page, so a
**Russian residential/mobile proxy** is required.

```bash
PROXY="http://user:pass@host:port" CIAN_PATH="snyat-kvartiru-posutochno" python cian/cian_parser.py
```
`CIAN_PATH` — any section: `snyat-kvartiru` (long-term rent), `kupit-kvartiru` (buy),
`kupit-dom`, `snyat-pomeshchenie` (commercial), … Default is daily rent.

---

## 📋 Output fields

**2GIS**: `phone, name, city, address, category, url`

**Yandex Maps**: `phone, phone2, name, city, address, rating, latitude, longitude, url`

**CIAN**: `phone, phone2, city, price_rub, rooms, area_m2, floor, floors_total, address, metro, build_year, furniture, deposit, owner_id, posted, description, url`

CSV is written with a UTF-8 BOM so Cyrillic opens correctly in Excel.

---

## 🔑 Getting the prerequisites

- **Apify token** (2GIS, Yandex Maps): free tier at [console.apify.com](https://console.apify.com/account/integrations). The free plan caps results per run; a small top-up lifts it for full-scale runs.
- **Russian proxy** (CIAN): any residential/mobile RU proxy provider. Sticky sessions recommended (one IP per session).

---

## ⚙️ How it works

- **2GIS / Yandex Maps** drive public Apify actors that walk directory results for your query; both directories publish business phones by design. Configure by `QUERY` + `CITIES`, or (2GIS) point at exact rubric URLs via `START_URLS`.
- **CIAN** parses the server-rendered JSON state embedded in the search page (`"offers":[…]`) and pulls the balanced array out directly — the phones already live in that state, no reveal click needed. A retry loop guards against proxies truncating the (large) response. Any CIAN section works via `CIAN_PATH`.

---

## ⚙️ Common env vars

| Var | Parsers | Meaning |
|---|---|---|
| `APIFY_TOKEN` | 2gis, yandex-maps | Apify API token |
| `PROXY` | cian | `http://user:pass@host:port` (RU proxy) |
| `QUERY` | 2gis, yandex-maps | search text (any category) |
| `CITIES` | all | comma-separated cities |
| `CIAN_PATH` | cian | CIAN search section |
| `MAX` / `PAGES` | — | volume per city |
| `OUT` | all | output filename |

---

## ⚠️ Notes & disclaimer

- Data comes from **public listings/directories**. Use it responsibly and in line with each source's Terms of Service and your local data-protection laws.
- Sources change their markup/rubrics over time — selectors and paths may need occasional updates.
- This toolkit is for legitimate data collection and research. You are responsible for how you use the collected data.

---

## 📄 License

[MIT](LICENSE) — do what you want, just keep the copyright notice.

---

Made by [@Rauan228](https://github.com/Rauan228). PRs and new source parsers welcome.
