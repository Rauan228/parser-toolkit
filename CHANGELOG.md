# Changelog

## [0.2.0] — 2026-08-10

Hardening of the five v0.1 parsers — no new sources.

### Added

- **CI**: GitHub Actions (`unittest` + CLI smoke on Python 3.9 / 3.12)
- **`parser-toolkit doctor`**: offline environment check (`--live` optional)
- **Run report**: `{out}.run.json` (counts, phone metrics, errors, duration)
- **JSONL**: `--format csv,json,jsonl`
- **`--cookie-file`**: Krisha / Kolesa session cookie from a file
- **`--resume`**: skip ids already present in `{out}.json` / `{out}.jsonl`
- **Library API**: `from parser_toolkit import scrape, sources`

### Changed

- **CIAN** refuses to run without `--proxy` / `PROXY` (exit `4`)
- Krisha / Kolesa print and persist **phone metrics** (full / preview / fail rate)
- Unified record keys filled on dump: `source`, `id`, `title`, `phones`, `price`, `currency`, `scraped_at`

### Exit codes

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | runtime error |
| 2 | bad args / missing optional extra (Playwright) |
| 3 | auth (reserved) |
| 4 | blocked / missing required proxy |

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
