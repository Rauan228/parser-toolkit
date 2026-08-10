# 🧰 parser-toolkit

> Готовые парсеры для трёх больших платформ СНГ/РФ — **2ГИС**, **Яндекс.Карты** и **ЦИАН**. Собирают объявления и данные организаций **с открытыми телефонами** в чистые CSV + JSON.

[English version →](README.md)

**Без Apify.** Справочники ходят на платформы напрямую по HTTP.

---

## 📦 Что внутри

| Парсер | Источник | Что собирает | Метод | Прокси | API-ключ |
|---|---|---|---|---|---|
| [`2gis/`](2gis/) | [2ГИС](https://2gis.ru) | любые категории бизнеса | Direct HTTP / Internal Catalog Web API | опционально | — (web-ключ сайта) |
| [`yandex-maps/`](yandex-maps/) | [Яндекс.Карты](https://yandex.ru/maps) | любые категории бизнеса | Direct HTTP / Embedded JSON (search HTML) | опционально | — |
| [`cian/`](cian/) | [ЦИАН](https://cian.ru) | любой раздел недвижимости | Direct HTTP / Embedded JSON | 🇷🇺 нужен RU-прокси | — |

Общие хелперы — в [`core/`](core/) (HTTP-клиент, единая модель place, запись CSV/JSON).

---

## 🚀 Быстрый старт

```bash
git clone https://github.com/Rauan228/parser-toolkit.git
cd parser-toolkit
pip install -r requirements.txt
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

Результаты по умолчанию в `output/`.

---

## 📋 Поля (справочники)

Единый JSON-формат: `source`, `name`, `category`, `phones[]`, `address`, `city`, `latitude`, `longitude`, `rating`, `reviews_count`, `website`, `url`, плюс `raw`/`metadata` для специфики источника.

---

## ⚙️ Как это работает

- **2ГИС** — Internal Catalog Web API (`catalog.api.2gis.ru/3.0/items`) с web-ключом фронтенда 2gis.ru.
- **Яндекс.Карты** — публичные HTML-страницы поиска + embedded JSON (`stack[0].results.items[]`), пагинация `?page=N`. Fallback доменов при `429 limited`.
- **ЦИАН** — embedded `"offers":[…]` в HTML выдачи.

---

## 🧪 Тесты

```bash
python -m unittest discover -s tests -v
```

Только фикстуры, без сетевых запросов.

---

## 📄 Лицензия

[MIT](LICENSE) — автор [@Rauan228](https://github.com/Rauan228).
