# 2GIS places parser

Collects organizations of **any category** from 2GIS with their **open public
phones**, via the Apify actor [`zen-studio/2gis-places-scraper-api`](https://apify.com/zen-studio/2gis-places-scraper-api).

2GIS is a business directory — phones are public by design, no "reveal" step.
Search any free-text query across any set of cities, or point at exact 2GIS
rubric/category URLs.

## Requirements
- Python 3.8+ (stdlib only)
- An **Apify API token** — free tier at
  [console.apify.com](https://console.apify.com/account/integrations).
  No personal proxy needed (the actor uses Apify's own).

## Run
```bash
APIFY_TOKEN="apify_api_..." QUERY="кофейни" CITIES="moscow,spb" python twogis_parser.py
```

`QUERY` can be anything: `рестораны`, `автосервис`, `стоматология`, `фитнес`,
`квартиры посуточно`, …

| Env | Default | Meaning |
|---|---|---|
| `APIFY_TOKEN` | — | Apify API token (**required**) |
| `QUERY` | `рестораны` | search text (any category) |
| `CITIES` | 17 major cities | comma-separated 2GIS slugs (`moscow`, `spb`, …) |
| `START_URLS` | — | exact 2GIS URLs; overrides QUERY+CITIES |
| `MAX` | `500` | max results per city |
| `OUT` | `twogis_places` | output filename |

## Output
`phone, name, city, address, category, url`

> Tip: for a precise category, grab a 2GIS rubric URL from the site and pass it
> via `START_URLS` — e.g. daily-rent apartments live under `rubricId/19487`.

> Apify's free tier caps results per run; a small balance top-up lifts it.
