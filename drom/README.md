# Drom.ru

Russian used-car listings from **`auto.drom.ru`**.

No Apify. Direct HTTP. List page embeds JSON in

```html
<script type="application/json" data-drom-module="bulls-list-auto">
```

## What you get

Title, price (RUB), year, mileage, engine, fuel, transmission, drive, city, URL.

**Phones** are behind `GET /api/sales/bulls/{id}/contacts`. Without a logged-in Drom session the API returns `{"type":4}` (no number). We do not solve captcha. Pass `--phones` only if you want to try the contacts call.

## Usage

```bash
parser-toolkit drom --city moscow --pages 2 --max 40
parser-toolkit drom --city spb --city kazan --max 20
```

Pagination: `https://auto.drom.ru/{city}/all/` then `/page2/`, `/page3/`, …
