# Krisha.kz listings parser

Collects real-estate listings from [Krisha.kz](https://krisha.kz) (Kazakhstan) with
full public metadata via **Direct HTTP**. No Apify. No official API key.

## Phones: important

The UI shows **«Показать телефон»** even when you are logged in. That is only a
frontend mask.

| Mode | What you get |
|---|---|
| **A — no login** | Metadata + `phone_preview` (`+7 778`) — full number hidden |
| **B — logged-in cookie** | Metadata + **full phones** from `window.data` → `adverts[].phones` |

With a real **krisha.kz session** the first document request already contains:

```json
"contactsInfo": { "phonePreview": "+7 778 ", "phonesNb": 1 },
"phones": ["+7 778 046 4438"]
```

So you usually **do not need** to click «Показать телефон». The parser reads
phones from the detail HTML. The click endpoint
`GET /a/ajaxPhones?id=…` often returns empty phones + **reCAPTCHA** even when
logged in — we only use it as a fallback and **do not** solve captchas.

### How to enable full phones (mode B)

1. Open https://krisha.kz and **sign in**
2. Open any listing (`/a/show/...`)
3. DevTools → Network → the **first document** request to `krisha.kz`
4. Copy as cURL **or** copy Request Header `cookie:`
5. Important cookie names include: `krssid`, `kumd`, `krishauid` (not Google Ads)
6. Run:

```bash
KRISHA_COOKIE="paste-full-cookie-here" python krisha_parser.py --city astana --deal prodazha --pages 1 --max 20
```

Do **not** commit cookies or network logs with sessions. Treat them like passwords.

## How it works

```
Python
  ↓
GET /{deal}/{type}/{city}/?page=N     → listing ids
  ↓
GET /a/show/{id}  (+ session cookie)
  ↓
window.data: metadata + adverts[].phones (when logged in)
  ↓  (fallback only if phones missing)
GET /a/ajaxPhones?id={id}
  ↓
normalize → CSV / JSON
```

## Run

```bash
# metadata + phone_preview (no login)
python krisha_parser.py --deal arenda --type kvartiry --city almaty --pages 2 --max 40

# sale apartments in Astana
python krisha_parser.py --deal prodazha --type kvartiry --city astana --pages 3
```

| Flag / env | Default | Meaning |
|---|---|---|
| `--deal` / `DEAL` | `arenda` | `arenda` or `prodazha` |
| `--type` / `TYPE` | `kvartiry` | `kvartiry`, `doma`, … |
| `--city` / `CITIES` | major KZ cities | city slug(s) |
| `--pages` / `PAGES` | `3` | list pages per city |
| `--max` / `MAX` | `100` | max listings per city |
| `--out` / `OUT` | `output/krisha_listings` | output prefix |
| `--cookie` / `KRISHA_COOKIE` | — | browser session for full phones |
| `--skip-phones` | off | never call ajaxPhones |
| `--proxy` | — | optional HTTP proxy |

## Output fields

`source, phone, phone2, phone_preview, title, city, district, address, price_kzt, rooms, area_m2, floor, floors_total, owner_name, owner_type, deal_type, property_type, latitude, longitude, listing_id, url, description`

JSON also keeps `phones[]`, `posted`, and optional `raw`.

## Notes

- Method: **Direct HTTP / HTML list + embedded `window.data` on detail**
- User API key: **Not required**
- Full phones: **user session cookie** (optional)
- Be polite: default sleep between requests; do not hammer the site
- Respect Krisha Terms of Service and local law
