# 2GIS places parser

Collects daily-rent apartment organizations **with open phones** from 2GIS via
the Apify actor [`zen-studio/2gis-places-scraper-api`](https://apify.com/zen-studio/2gis-places-scraper-api).

2GIS is a business directory — phones are public by design. Daily-rent hosts sit
under a fixed rubric **`rubricId/19487` ("Квартиры посуточно")**, identical in
every Russian city, which targets private hosts/apart-operators (not hotels).

## Requirements
- Python 3.8+ (stdlib only)
- An **Apify API token** — free tier at
  [console.apify.com](https://console.apify.com/account/integrations).
  No personal proxy needed (the actor uses Apify's own).

## Run
```bash
APIFY_TOKEN="apify_api_..." python twogis_parser.py
```

| Env | Default | Meaning |
|---|---|---|
| `APIFY_TOKEN` | — | Apify API token (**required**) |
| `CITIES` | 17 major cities | comma-separated 2GIS slugs (`moscow`, `spb`, …) |
| `MAX` | `500` | max results per city |
| `OUT` | `twogis_daily_rent` | output filename |

## Output
`phone, name, city, address, category, url`

> Apify's free tier caps results per run; a small balance top-up lifts it for
> full-scale collection across all cities.
