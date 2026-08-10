# Changelog

## [0.1.0] — 2026-08-10

First tagged release of **parser-toolkit**.

### Install → one command → CSV/JSON

```bash
pip install -e .
parser-toolkit 2gis --query "кофейни" --city moscow --max 50
# also: ptk …  |  python -m parser_toolkit …
```

### Parsers

| Source | Method | Phones |
|---|---|---|
| **2GIS** | Direct HTTP / Internal Catalog Web API | public |
| **Yandex Maps** | Direct HTTP / embedded search JSON | public |
| **CIAN** | Direct HTTP / embedded offers JSON | public (RU proxy) |
| **Krisha.kz** | Direct HTTP / `window.data` | session cookie (`KRISHA_COOKIE`) |
| **Kolesa.kz** | Direct HTTP + Playwright | reCAPTCHA v3 in browser (`KOLESA_COOKIE` recommended) |

### Packaging

- Installable package: `pip install -e .` (`pyproject.toml`, version `0.1.0`)
- CLI: `parser-toolkit <source> …` / `ptk <source> …` / `python -m parser_toolkit`
- Optional extra: `pip install -e ".[kolesa]"` + `playwright install chromium`
- Shared library: `parser_toolkit.core` (HTTP client, models, output)
- Clear CLI errors on stderr + non-zero exit codes
- Unit tests: `python -m unittest discover -s tests -v` (fixtures only, no network)
- Backward-compatible shims under `2gis/`, `yandex-maps/`, `cian/`, `krisha/`, `kolesa/`

### Principles

- No Apify
- Local runs only
- Primarily direct HTTP; browser automation only where the source requires it
- No captcha cracking (Kolesa uses real Chromium flow)
- Secrets (cookies, network dumps, scraped `output/`) stay out of git
