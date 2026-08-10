# Yandex Maps places parser

Collects organizations of **any category** from Yandex Maps with their **open
public phones** via **Direct HTTP** and the **embedded JSON state** that the
Maps SPA hydrates from. **No Apify. No official API key. No browser automation.**

## How it works

```
Python
  ↓
Yandex Maps search HTML  (public pages)
  ↓
embedded application/json  →  stack[0].results.items[]
  ↓
normalize
  ↓
CSV / JSON
```

Search URLs look like:

```
https://{domain}/maps/{geoId}/{citySeo}/search/{query}/?page={n}
```

Observed page size is ~25 businesses; `?page=2`, `?page=3`, … continue the list.
`totalResultCount` in the state may grow as further pages are loaded.

### Domains

`yandex.ru/maps` sometimes answers `429 limited` from datacenter IPs. The same
Maps product is available on regional hosts (`yandex.kz`, `yandex.by`, …) with
the **same embedded JSON shape**. The parser tries a short domain list and uses
the first host that returns a real page. Override with `YANDEX_DOMAINS` / `--domains`.

This is **not** the paid official Places/Search API (`search-maps.yandex.ru/v1`
requires `apikey`). It is the **internal web search payload** embedded in the site.

## Requirements

- Python 3.8+ (stdlib only)

## Run

```bash
python yandex_maps_parser.py --query "барбершоп" --city "Москва" --max 50
```

```bash
QUERY="стоматология" CITIES="Астана,Алматы" python yandex_maps_parser.py
```

| Env / flag | Default | Meaning |
|---|---|---|
| `QUERY` / `--query` | `рестораны` | search text (any category) |
| `CITIES` / `--city` | major cities | city names or slugs (repeatable CLI flag) |
| `MAX` / `--max` | `200` | max results per city |
| `OUT` / `--out` | `output/yandex_maps_places` | output prefix |
| `PROXY` / `--proxy` | — | optional `http://user:pass@host:port` |
| `YANDEX_DOMAINS` / `--domains` | `yandex.ru,yandex.kz,…` | host fallback list |
| `TIMEOUT` `RETRIES` `SLEEP` | `30` / `4` / `0.5` | HTTP behaviour |
| `RAW` / `--no-raw` | on | keep full card under `raw` in JSON |

## Output

Unified directory fields:

`source, phone, phone2, name, category, city, address, rating, reviews_count, latitude, longitude, website, url, place_id`

JSON also has `phones[]`, `metadata` (hours, country, …) and optional `raw`.

Rows without a phone are skipped; de-duplication is by normalized phone.

## Limitations

- Broad queries may surface fewer total cards than the full directory (Maps ranks by relevance/viewport).
- Aggressive rate limits on some IPs/domains → use another domain from the list or a residential proxy.
- Do not hammer the service: default sleep between pages is intentional.
- Respect Yandex Terms of Service and local law; public directory data only.
