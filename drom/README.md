# Drom.ru

Russian used-car listings from **`auto.drom.ru`**.

No Apify. Direct HTTP. List page embeds JSON in

```html
<script type="application/json" data-drom-module="bulls-list-auto">
```

## What you get

Title, price (RUB), year, mileage, engine, fuel, transmission, drive, city, URL.

**Phones** are behind `GET /api/sales/bulls/{id}/contacts` and need a logged-in cookie (`DROM_COOKIE` / `--cookie-file`). Drom kills the session if many reveals fire in a burst. The parser paces them (sleep + jitter + batch pause) and **stops phone calls** on `auth_required` so metadata is not wasted.

```bash
# metadata only (fast)
parser-toolkit drom --city moscow --pages 3 --max 50 --out output/drom_50

# phones: slow, batched, resumable
parser-toolkit drom --city moscow --max 50 --phones --resume \
  --cookie-file drom.cookie --out output/drom_50 \
  --phone-sleep 8 --phone-batch 5 --phone-batch-pause 75 --phone-max 15
```

If Drom asks to log in again: export a fresh cookie, then the same command with `--resume` (already collected numbers are skipped).

Pagination: `https://auto.drom.ru/{city}/all/` then `/page2/`, `/page3/`, …
