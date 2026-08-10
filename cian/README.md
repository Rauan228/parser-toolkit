# CIAN listings parser

Pulls real-estate listings **with open owner phones** from CIAN by parsing the
server-rendered JSON state (`"offers":[…]`) embedded in the search page. No API
key, no CAPTCHA, no "reveal phone" — the phones are already there.

Works on **any CIAN section** via `CIAN_PATH` — the phones live in the same JSON
state regardless of listing type.

## Requirements
- Python 3.8+ (stdlib only)
- A **Russian residential/mobile proxy** — CIAN geo-blocks non-RU IPs and routes
  automated/headless clients to a decoy page. Set it via the `PROXY` env var.

## Run
```bash
PROXY="http://user:pass@host:port" CIAN_PATH="snyat-kvartiru-posutochno" python cian_parser.py
```

| Env | Default | Meaning |
|---|---|---|
| `PROXY` | — | `http://user:pass@host:port`, **RU proxy (required)** |
| `CIAN_PATH` | `snyat-kvartiru-posutochno` | CIAN search section (see below) |
| `CITIES` | 24 major cities | comma-separated CIAN subdomains (`www` = Moscow) |
| `PAGES` | `5` | pages per sort order |
| `OUT` | `cian_listings` | output filename (`.csv` / `.json`) |

### CIAN_PATH options
| Value | Section |
|---|---|
| `snyat-kvartiru-posutochno` | daily rent (default) |
| `snyat-kvartiru` | long-term rent |
| `kupit-kvartiru` | buy apartment |
| `kupit-dom` | buy house |
| `snyat-pomeshchenie` | commercial rent |

## Output
`phone, phone2, city, price_rub, rooms, area_m2, floor, floors_total, address, metro, build_year, furniture, deposit, owner_id, posted, description, url`

The parser only keeps cards with a resolved address (guards against truncated
proxy responses) and de-duplicates by phone.
