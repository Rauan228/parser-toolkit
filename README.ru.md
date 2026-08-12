# 🧰 parser-toolkit

> Готовые локальные парсеры для популярных платформ СНГ/РФ — справочники, маркетплейсы и недвижимость.

[English version →](README.md)

**2ГИС**, **Яндекс.Карты**, **Яндекс Недвижимость**, **ЦИАН**, **Krisha.kz** и **Kolesa.kz**. Собирают объявления и данные организаций/листингов в чистые CSV + JSON.

**Без Apify. Парсеры запускаются локально, в основном по прямому HTTP. Browser automation — только там, где источник этого требует.**

Сейчас: Python stdlib + опциональный Playwright для телефонов Kolesa.

---

## 📦 Что внутри

| Парсер | Источник | Что собирает | Метод | Прокси | User API key |
|---|---|---|---|---|---|
| [`2gis/`](2gis/) | [2ГИС](https://2gis.ru) | любые категории бизнеса | Direct HTTP / Internal Catalog Web API | опционально | Not required |
| [`yandex-maps/`](yandex-maps/) | [Яндекс.Карты](https://yandex.ru/maps) | любые категории бизнеса | Direct HTTP / Embedded JSON (search HTML) | опционально | Not required |
| [`yandex-realty/`](yandex-realty/) | [Яндекс Недвижимость](https://yandex.ru/realty) | объявления РФ | Direct HTTP / `yandex.ru/realty` SERP JSON | опционально | Not required |
| [`cian/`](cian/) | [ЦИАН](https://cian.ru) | любой раздел недвижимости | Direct HTTP / Embedded JSON | 🇷🇺 нужен RU-прокси | Not required |
| [`krisha/`](krisha/) | [Krisha.kz](https://krisha.kz) | недвижимость KZ | Direct HTTP / HTML list + `window.data` | опционально | Not required |
| [`kolesa/`](kolesa/) | [Kolesa.kz](https://kolesa.kz) | авто KZ | Direct HTTP + Playwright (телефоны/reCAPTCHA) | опционально | Not required |

Устанавливаемый Python-пакет (`parser_toolkit`) и единый CLI. Общие хелперы: HTTP-клиент, модель place, CSV/JSON. Старые shim-скрипты в `2gis/`, `yandex-maps/`, … тоже работают.

- **2ГИС** использует web-ключ, который отдаёт frontend 2ГИС; **пользовательский API key не нужен**.
- **Krisha**: полные телефоны — через cookie залогиненной сессии (`KRISHA_COOKIE`); метаданные доступны без логина.
- **Kolesa**: телефоны через Playwright (reCAPTCHA v3 в реальном браузере); cookie `KOLESA_COOKIE` желательна.

---

## 🚀 Быстрый старт

```bash
git clone https://github.com/Rauan228/parser-toolkit.git
cd parser-toolkit
pip install -e .

# одна команда → CSV + JSON
parser-toolkit 2gis --query "кофейни" --city moscow --max 50
# алиасы: ptk …   или   python -m parser_toolkit …
```

Телефоны Kolesa (опционально):

```bash
pip install -e ".[kolesa]"
playwright install chromium
```

```text
pip install
  → одна команда (parser-toolkit / ptk / python -m parser_toolkit)
  → CSV / JSON / JSONL в output/ + {out}.run.json
  → понятные ошибки в stderr + ненулевой exit code
  → parser-toolkit doctor
  → unit-тесты (только фикстуры)
```

```bash
parser-toolkit doctor
parser-toolkit 2gis --query "кофейни" --city moscow --max 50 --format csv,json,jsonl
parser-toolkit krisha --city almaty --max 20 --cookie-file ./krisha.cookie --resume
```

### 2ГИС

```bash
parser-toolkit 2gis --query "стоматология" --city moscow --city spb --max 100
```

### Яндекс.Карты

```bash
parser-toolkit yandex-maps --query "стоматология" --city "Астана" --max 50
```

### Яндекс Недвижимость

```bash
parser-toolkit yandex-realty --city moscow --deal snyat --type kvartira --max 30
```

Метаданные (цена, адрес, комнаты, площадь, этаж, метро). Телефонов в публичной выдаче нет; `realty.yandex.ru` закрыт SmartCaptcha.

### ЦИАН

```bash
parser-toolkit cian --proxy "http://user:pass@host:port" --path snyat-kvartiru-posutochno --pages 3
```

### Krisha.kz

```bash
# метаданные + превью телефона
parser-toolkit krisha --deal arenda --type kvartiry --city almaty --pages 2

# полные телефоны — cookie залогиненной сессии krisha.kz
# DevTools → /a/show/… → Network → document → Cookie
# нужны krssid + kumd (не Google Ads)
KRISHA_COOKIE="krishauid=…; krssid=…; kumd=…; …" \
  parser-toolkit krisha --deal prodazha --type kvartiry --city astana --max 30
```

> UI показывает «Показать телефон», но при логине полный номер уже лежит в
> `window.data` → `adverts[].phones`. Парсер читает его оттуда, без капчи.

### Kolesa.kz

```bash
KOLESA_COOKIE="klssid=…; kumd=…" \
  parser-toolkit kolesa --city almaty --max 15 --out output/kolesa
```

Телефоны: `app.kolesa.kz/adverts/{id}/phones` + `captchaTokenV3` из Chromium.

Результаты по умолчанию в `output/`.

```bash
parser-toolkit --help
parser-toolkit 2gis --help
parser-toolkit --version
```

---

## 📋 Поля (справочники)

Единый JSON-формат: `source`, `name`, `category`, `phones[]`, `address`, `city`, `latitude`, `longitude`, `rating`, `reviews_count`, `website`, `url`, плюс `raw`/`metadata` для специфики источника.

---

## 🔑 Что понадобится

| Источник | Нужно |
|---|---|
| 2ГИС | без user API key (web-ключ frontend 2gis.ru) |
| Яндекс.Карты | без user API key (при 429 — другой IP/прокси) |
| Яндекс Недвижимость | без user API key; телефоны не в публичной выдаче |
| ЦИАН | RU residential/mobile proxy |
| Krisha.kz | без user API key; опционально `KRISHA_COOKIE` для полных телефонов |
| Kolesa.kz | Playwright + Chromium; опционально `KOLESA_COOKIE` для session-зависимого phone flow |

---

## ⚙️ Как это работает

- **2ГИС** — Internal Catalog Web API (`catalog.api.2gis.ru/3.0/items`); в протоколе используется web-ключ frontend 2gis.ru, отдельный user API key выдавать не нужно.
- **Яндекс.Карты** — публичные HTML-страницы поиска + embedded JSON (`stack[0].results.items[]`), пагинация `?page=N`. Fallback доменов при `429 limited`.
- **Яндекс Недвижимость** — `yandex.ru/realty/{city}/{deal}/{type}/`, карточки `{"type":"offer"}`. `realty.yandex.ru` закрыт SmartCaptcha.
- **ЦИАН** — embedded `"offers":[…]` в HTML выдачи.
- **Krisha** — list HTML + detail `window.data`; телефоны через `/a/ajaxPhones` (нужна cookie сессии, если Krisha требует логин).
- **Kolesa** — list/detail по HTTP; телефоны через Playwright + `app.kolesa.kz/adverts/{id}/phones` (reCAPTCHA v3 в браузере).

---

## 🧪 Тесты

```bash
python -m unittest discover -s tests -v
```

Только фикстуры, без сетевых запросов. Ошибки CLI — в **stderr**, ненулевой exit code (`4` — CIAN без прокси).

Библиотека:

```python
from parser_toolkit import scrape
rows = scrape("krisha", cities=["almaty"], max_per_city=10, skip_phones=True)
```

---

## 📄 Лицензия

[MIT](LICENSE) — автор [@Rauan228](https://github.com/Rauan228).  
Релизные заметки: [CHANGELOG.md](CHANGELOG.md) (`v0.3.0`).