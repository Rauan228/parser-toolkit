# 🏘️ parser-toolkit

> A small collection of real-estate lead parsers for the Russian market — pull daily-rent apartment listings **with open owner phone numbers** from CIAN, 2GIS and Yandex Maps.

[Русская версия →](README.ru.md)

Each parser targets a source where contact phones are **publicly available** (no CAPTCHA, no "reveal phone" wall) and outputs clean **CSV + JSON** ready for a CRM or a sales team.

---

## 📦 What's inside

| Parser | Source | Method | Phones | Proxy | API key |
|---|---|---|---|---|---|
| [`cian/`](cian/) | [CIAN](https://cian.ru) daily rent | Direct HTTP (embedded JSON state) | ✅ open | 🇷🇺 RU proxy required | — |
| [`2gis/`](2gis/) | [2GIS](https://2gis.ru) directory | Apify actor | ✅ open | — (Apify's own) | Apify token |
| [`yandex-maps/`](yandex-maps/) | [Yandex Maps](https://yandex.ru/maps) directory | Apify actor | ✅ open | — (Apify's own) | Apify token |

All three return **different, complementary datasets** — run all of them and de-duplicate by phone for maximum coverage.

---

## 🚀 Quick start

```bash
git clone https://github.com/Rauan228/parser-toolkit.git
cd parser-toolkit
pip install -r requirements.txt   # stdlib-only, but here for completeness
```

### 1. CIAN — direct parser (needs a Russian proxy)

CIAN geo-blocks non-RU IPs and sends headless clients to a decoy page, so a
**Russian residential/mobile proxy** is required.

```bash
PROXY="http://user:pass@host:port" python cian/cian_parser.py
```

Optional env: `CITIES="www,spb,sochi"` (www = Moscow), `PAGES=5`, `OUT=my_leads`.

### 2. 2GIS — via Apify (needs a token, no proxy)

```bash
APIFY_TOKEN="apify_api_..." python 2gis/twogis_parser.py
```

Optional env: `CITIES="moscow,spb,sochi"`, `MAX=500`, `OUT=my_leads`.

### 3. Yandex Maps — via Apify (needs a token, no proxy)

```bash
APIFY_TOKEN="apify_api_..." python yandex-maps/yandex_maps_parser.py
```

Optional env: `QUERIES="квартиры посуточно"`, `CITIES="Москва,Сочи"`, `MAX=200`.

---

## 📋 Output fields

**CIAN** (richest): `phone, phone2, city, price_per_day_rub, rooms, area_m2, floor, floors_total, address, metro, build_year, furniture, deposit, owner_id, posted, description, url`

**2GIS**: `phone, name, city, address, category, url`

**Yandex Maps**: `phone, phone2, name, city, address, rating, latitude, longitude, url`

CSV is written with a UTF-8 BOM so Cyrillic opens correctly in Excel.

---

## 🔑 Getting the prerequisites

- **Apify token** (2GIS, Yandex Maps): free tier at [console.apify.com](https://console.apify.com/account/integrations). The free plan caps results per run; a small top-up lifts it for full-scale runs.
- **Russian proxy** (CIAN): any residential/mobile RU proxy provider. Sticky sessions recommended (one IP per session).

---

## ⚙️ How it works

- **CIAN** parses the server-rendered JSON state embedded in the search page (`"offers":[…]`) and pulls the balanced array out directly — the phones already live in that state, no reveal click needed. A retry loop guards against proxies truncating the (large) response.
- **2GIS / Yandex Maps** drive public Apify actors that walk the directory listings; both directories publish business phones by design.

---

## ⚠️ Notes & disclaimer

- Data comes from **public listings/directories**. Use it responsibly and in line with each source's Terms of Service and your local data-protection laws (e.g. personal-data regulations).
- Sources change their markup/rubrics over time — selectors and rubric IDs may need occasional updates.
- This toolkit is for legitimate lead-generation and research. You are responsible for how you use the collected data.

---

## 📄 License

[MIT](LICENSE) — do what you want, just keep the copyright notice.

---

Made by [@Rauan228](https://github.com/Rauan228). PRs and new source parsers welcome.
