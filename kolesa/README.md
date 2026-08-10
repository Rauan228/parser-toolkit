# Kolesa.kz auto listings parser

Collects car listings from [Kolesa.kz](https://kolesa.kz) with **metadata + phones**.

No Apify. No official API key.

## How it works

```
Python
  ↓
GET /cars/{city}/?page=N              → listing ids   (HTTP)
  ↓
GET /a/show/{id}                      → title, price, params  (HTTP)
  ↓
Playwright (Chromium)
  open detail + session cookie
  click «Показать телефон»
  reCAPTCHA v3 runs in real browser
  ↓
GET app.kolesa.kz/adverts/{id}/phones?captchaTokenV3=…&source=advert
  ↓
{ "status":"success", "phones":["+7 …", "+7 …"] }
  ↓
normalize → CSV / JSON
```

### Why Playwright for phones?

The phones API **requires a reCAPTCHA v3 token** (`captchaTokenV3`).  
Without it the API returns `403 Forbidden`. Tokens are short-lived and tied to
the browser session — they cannot be hard-coded.

The parser does **not** crack captcha. Chromium executes the same flow as a
normal user click; we intercept the JSON response.

Metadata (list + detail) stays pure HTTP.

## Install

```bash
pip install playwright
playwright install chromium
```

Python 3.8+. Other toolkit parsers still work without Playwright.

## Run

```bash
# recommended: cookie from logged-in kolesa.kz (klssid + kumd)
KOLESA_COOKIE="klssid=…; kumd=…; …" \
  python kolesa_parser.py --city almaty --pages 1 --max 15 --out output/kolesa

# guest browser (may work, login cookie is more stable)
python kolesa_parser.py --city astana --max 10

# metadata only (phones skipped — not the default)
python kolesa_parser.py --city almaty --no-phones
```

| Flag / env | Default | Meaning |
|---|---|---|
| `--section` | `cars` | URL section |
| `--city` / `CITIES` | major cities | city slug(s) |
| `--pages` / `PAGES` | `2` | list pages per city |
| `--max` / `MAX` | `50` | max listings per city |
| `--cookie` / `KOLESA_COOKIE` | — | browser Cookie header |
| `--no-phones` | off | metadata only |
| `--headed` | off | show browser window |
| `--out` / `OUT` | `output/kolesa_listings` | output prefix |
| `--proxy` | — | optional HTTP proxy (list/detail only) |

### Cookie (recommended)

1. Sign in on https://kolesa.kz  
2. Open any listing  
3. DevTools → Network → document request → copy `cookie:`  
4. Need at least `klssid` + `kumd`  

Do **not** commit cookies.

## Output fields

`source, phone, phone2, phone_preview, title, city, price_kzt, year, mileage_km, body, engine, transmission, drive, steering, color, customs_kz, generation, listing_id, url, description, owner_id`

JSON also has `phones[]` and optional `raw` / `params`.

Listings **without** a resolved phone are skipped when phones are enabled (default).

## Notes

- Method: **Direct HTTP** (list/detail) + **Playwright** (phone reveal only)
- User API key: **Not required**
- reCAPTCHA: executed by browser, not bypassed
- Be polite with `--sleep` / volume limits
- Respect Kolesa Terms of Service and local law
