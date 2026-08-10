# 🧰 parser-toolkit

> Готовые локальные парсеры для популярных платформ СНГ/РФ — справочники, маркетплейсы и недвижимость.

[English version →](README.md)

**2ГИС**, **Яндекс.Карты**, **ЦИАН**, **Krisha.kz** и **Kolesa.kz**. Собирают объявления и данные организаций/листингов в чистые CSV + JSON.

**Без Apify. Парсеры запускаются локально, в основном по прямому HTTP. Browser automation — только там, где источник этого требует.**

Сейчас: Python stdlib + опциональный Playwright для телефонов Kolesa.

---

## 📦 Что внутри

| Парсер | Источник | Что собирает | Метод | Прокси | User API key |
|---|---|---|---|---|---|
| [`2gis/`](2gis/) | [2ГИС](https://2gis.ru) | любые категории бизнеса | Direct HTTP / Internal Catalog Web API | опционально | Not required |
| [`yandex-maps/`](yandex-maps/) | [Яндекс.Карты](https://yandex.ru/maps) | любые категории бизнеса | Direct HTTP / Embedded JSON (search HTML) | опционально | Not required |
| [`cian/`](cian/) | [ЦИАН](https://cian.ru) | любой раздел недвижимости | Direct HTTP / Embedded JSON | 🇷🇺 нужен RU-прокси | Not required |
| [`krisha/`](krisha/) | [Krisha.kz](https://krisha.kz) | недвижимость KZ | Direct HTTP / HTML list + `window.data` | опционально | Not required |
| [`kolesa/`](kolesa/) | [Kolesa.kz](https://kolesa.kz) | авто KZ | Direct HTTP + Playwright (телефоны/reCAPTCHA) | опционально | Not required |

Общие хелперы — в [`core/`](core/) (HTTP-клиент, единая модель place, запись CSV/JSON).

- **2ГИС** использует web-ключ, который отдаёт frontend 2ГИС; **пользовательский API key не нужен**.
- **Krisha**: полные телефоны — через cookie залогиненной сессии (`KRISHA_COOKIE`); метаданные доступны без логина.
- **Kolesa**: телефоны через Playwright (reCAPTCHA v3 в реальном браузере); cookie `KOLESA_COOKIE` желательна.

---

## 🚀 Быстрый старт

```bash
git clone https://github.com/Rauan228/parser-toolkit.git
cd parser-toolkit
pip install -r requirements.txt   # stdlib для большинства; Playwright для телефонов Kolesa
playwright install chromium       # только для kolesa/
```

### 2ГИС

```bash
python 2gis/twogis_parser.py --query "стоматология" --city moscow --city spb --max 100
```

### Яндекс.Карты

```bash
python yandex-maps/yandex_maps_parser.py --query "стоматология" --city "Астана" --max 50
```

### ЦИАН

```bash
PROXY="http://user:pass@host:port" CIAN_PATH="snyat-kvartiru-posutochno" python cian/cian_parser.py
```

### Krisha.kz

```bash
# метаданные + превью телефона
python krisha/krisha_parser.py --deal arenda --type kvartiry --city almaty --pages 2

# полные телефоны — cookie залогиненной сессии krisha.kz
# DevTools → /a/show/… → Network → document → Cookie
# нужны krssid + kumd (не Google Ads)
KRISHA_COOKIE="krishauid=…; krssid=…; kumd=…; …" \
  python krisha/krisha_parser.py --deal prodazha --type kvartiry --city astana --max 30
```

> UI показывает «Показать телефон», но при логине полный номер уже лежит в
> `window.data` → `adverts[].phones`. Парсер читает его оттуда, без капчи.

### Kolesa.kz

```bash
pip install playwright && playwright install chromium
KOLESA_COOKIE="klssid=…; kumd=…" \
  python kolesa/kolesa_parser.py --city almaty --max 15 --out output/kolesa
```

Телефоны: `app.kolesa.kz/adverts/{id}/phones` + `captchaTokenV3` из Chromium.

Результаты по умолчанию в `output/`.

---

## 📋 Поля (справочники)

Единый JSON-формат: `source`, `name`, `category`, `phones[]`, `address`, `city`, `latitude`, `longitude`, `rating`, `reviews_count`, `website`, `url`, плюс `raw`/`metadata` для специфики источника.

---

## 🔑 Что понадобится

| Источник | Нужно |
|---|---|
| 2ГИС | без user API key (web-ключ frontend 2gis.ru) |
| Яндекс.Карты | без user API key (при 429 — другой IP/прокси) |
| ЦИАН | RU residential/mobile proxy |
| Krisha.kz | без user API key; опционально `KRISHA_COOKIE` для полных телефонов |
| Kolesa.kz | Playwright + Chromium; опционально `KOLESA_COOKIE` для session-зависимого phone flow |

---

## ⚙️ Как это работает

- **2ГИС** — Internal Catalog Web API (`catalog.api.2gis.ru/3.0/items`); в протоколе используется web-ключ frontend 2gis.ru, отдельный user API key выдавать не нужно.
- **Яндекс.Карты** — публичные HTML-страницы поиска + embedded JSON (`stack[0].results.items[]`), пагинация `?page=N`. Fallback доменов при `429 limited`.
- **ЦИАН** — embedded `"offers":[…]` в HTML выдачи.
- **Krisha** — list HTML + detail `window.data`; телефоны через `/a/ajaxPhones` (нужна cookie сессии, если Krisha требует логин).
- **Kolesa** — list/detail по HTTP; телефоны через Playwright + `app.kolesa.kz/adverts/{id}/phones` (reCAPTCHA v3 в браузере).

---

## 🧪 Тесты

```bash
python -m unittest discover -s tests -v
```

Только фикстуры, без сетевых запросов.

---

## 📄 Лицензия

[MIT](LICENSE) — автор [@Rauan228](https://github.com/Rauan228).
