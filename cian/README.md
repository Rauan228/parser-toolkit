# CIAN daily-rent parser

Pulls daily-rent apartment listings **with open owner phones** from CIAN by
parsing the server-rendered JSON state (`"offers":[…]`) embedded in the search
page. No API key, no CAPTCHA, no "reveal phone" — the phones are already there.

## Requirements
- Python 3.8+ (stdlib only)
- A **Russian residential/mobile proxy** — CIAN geo-blocks non-RU IPs and routes
  automated/headless clients to a decoy page. Set it via the `PROXY` env var.

## Run
```bash
PROXY="http://user:pass@host:port" python cian_parser.py
```

| Env | Default | Meaning |
|---|---|---|
| `PROXY` | — | `http://user:pass@host:port`, **RU proxy (required)** |
| `CITIES` | 24 major cities | comma-separated CIAN subdomains (`www` = Moscow) |
| `PAGES` | `5` | pages per sort order |
| `OUT` | `cian_daily_rent` | output filename (`.csv` / `.json`) |

## Output
`phone, phone2, city, price_per_day_rub, rooms, area_m2, floor, floors_total, address, metro, build_year, furniture, deposit, owner_id, posted, description, url`

The parser only keeps cards with a resolved address (guards against truncated
proxy responses) and de-duplicates by phone.
