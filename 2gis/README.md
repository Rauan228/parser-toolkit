# 2GIS places parser

Collects organizations of **any category** from 2GIS with their **open public
phones** via **Direct HTTP** to the same **Internal Catalog Web API** that
[2gis.ru](https://2gis.ru) uses (`catalog.api.2gis.ru`).

**No Apify. No user-provided API key.** Uses the web key exposed by the 2GIS
frontend (`webApiOutsourceKey`; auto-refreshed if it rotates).

## Run

```bash
python twogis_parser.py --query "кофейни" --city moscow --city spb --max 100
```

```bash
QUERY="стоматология" CITIES="moscow,almaty" python twogis_parser.py
```

| Env / flag | Default | Meaning |
|---|---|---|
| `QUERY` / `--query` | `рестораны` | search text |
| `CITIES` / `--city` | major cities | 2GIS slugs (`moscow`, `spb`, …) |
| `START_URLS` / `--start-url` | — | exact 2GIS URLs |
| `MAX` / `--max` | `500` | max per city |
| `OUT` / `--out` | `output/twogis_places` | output prefix |
| `PROXY` / `--proxy` | — | optional proxy |
| `TWOGIS_KEY` | built-in web key | override if needed |

## How it works

```
Python → catalog.api.2gis.ru/3.0/items (+ region/list) → JSON → normalize → CSV/JSON
```

`page_size` max is 50 (API limit). Pagination walks `page=1..N` until `MAX`.

## Output

`source, phone, phone2, name, city, address, category, url, website, email, rating, reviews_count, latitude, longitude, …`

JSON may include `phones[]`, `place_id`, and `raw`.

## Notes

- A protocol-level web key exists (the one the site itself sends); **you do not register or paste a user API key**. Treat the endpoint as unofficial and rate-limit yourself.
- Respect 2GIS Terms of Service and local law.
