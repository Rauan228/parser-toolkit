# Yandex Realty

RU real-estate listings from **`yandex.ru/realty`** (Yandex Search realty vertical).

`realty.yandex.ru` is SmartCaptcha-walled from typical datacenter IPs. This parser does **not** solve captcha and does **not** use Apify.

## What you get

Price, address, rooms, area, floor, metro, coordinates, listing URL.

**Phones are not public** on the SERP JSON. Dedicated cards on `realty.yandex.ru/offer/{id}` require passing SmartCaptcha. The parser leaves `phone` empty and records that in `.run.json`.

## Usage

```bash
parser-toolkit yandex-realty --city moscow --deal snyat --type kvartira --max 30
parser-toolkit yandex-realty --city spb --city kazan --deal kupit --pages 2
```

`--pages` is extra listing *views* (sort variants + text search), not `?page=N` — the SERP ignores numeric page.

Optional: `--proxy`, `--format csv,json,jsonl`, `--resume`.
