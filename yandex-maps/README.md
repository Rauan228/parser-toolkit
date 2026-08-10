# Yandex Maps places parser

Collects organizations of **any category** from Yandex Maps with their **open
public phones**, via the Apify actor [`zen-studio/yandex-maps-scraper`](https://apify.com/zen-studio/yandex-maps-scraper).

Yandex Maps is a directory, so business phones are public. Returns a dataset
**independent from 2GIS** — combine both and de-duplicate by phone for wider
coverage.

## Requirements
- Python 3.8+ (stdlib only)
- An **Apify API token** — free tier at
  [console.apify.com](https://console.apify.com/account/integrations).
  No personal proxy needed.

## Run
```bash
APIFY_TOKEN="apify_api_..." QUERY="барбершоп" CITIES="Москва,Сочи" python yandex_maps_parser.py
```

`QUERY` can be anything: `рестораны`, `автосервис`, `аптеки`, `фитнес`,
`квартиры посуточно`, …

| Env | Default | Meaning |
|---|---|---|
| `APIFY_TOKEN` | — | Apify API token (**required**) |
| `QUERY` | `рестораны` | search text (any category) |
| `CITIES` | 14 major cities | comma-separated city names (Cyrillic ok) |
| `MAX` | `200` | max results per city |
| `OUT` | `yandex_maps_places` | output filename |

## Output
`phone, phone2, name, city, address, rating, latitude, longitude, url`

> Apify's free tier caps results per run; top up the balance for full-scale runs.
