# Yandex Maps places parser

Collects daily-rent apartment organizations **with open phones** from Yandex Maps
via the Apify actor [`zen-studio/yandex-maps-scraper`](https://apify.com/zen-studio/yandex-maps-scraper).

Yandex Maps is a directory, so phones are public. This is a **separate dataset**
from 2GIS and CIAN (different hosts/apart-operators are listed) — a good third
source to widen coverage. De-duplicate by phone against the others.

## Requirements
- Python 3.8+ (stdlib only)
- An **Apify API token** — free tier at
  [console.apify.com](https://console.apify.com/account/integrations).
  No personal proxy needed.

## Run
```bash
APIFY_TOKEN="apify_api_..." python yandex_maps_parser.py
```

| Env | Default | Meaning |
|---|---|---|
| `APIFY_TOKEN` | — | Apify API token (**required**) |
| `QUERIES` | `квартиры посуточно` | search query |
| `CITIES` | 14 major cities | comma-separated city names (Cyrillic ok) |
| `MAX` | `200` | max results per city |
| `OUT` | `yandex_maps_daily_rent` | output filename |

## Output
`phone, phone2, name, city, address, rating, latitude, longitude, url`

> Apify's free tier caps results per run; top up the balance for full-scale runs.
