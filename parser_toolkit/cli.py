#!/usr/bin/env python3
"""Unified CLI: parser-toolkit <source> [args...]"""
from __future__ import annotations

import sys
from typing import Callable, List, Optional

from parser_toolkit import __version__

_RUNNERS: dict[str, Callable] = {}

ALIASES = {
    "2gis": "2gis",
    "twogis": "2gis",
    "yandex-maps": "yandex-maps",
    "yandex": "yandex-maps",
    "yandex-realty": "yandex-realty",
    "realty": "yandex-realty",
    "yandex_realty": "yandex-realty",
    "drom": "drom",
    "cian": "cian",
    "krisha": "krisha",
    "kolesa": "kolesa",
}


def _register() -> None:
    if _RUNNERS:
        return
    from parser_toolkit.parsers import cian as cian_mod
    from parser_toolkit.parsers import drom as drom_mod
    from parser_toolkit.parsers import kolesa as kolesa_mod
    from parser_toolkit.parsers import krisha as krisha_mod
    from parser_toolkit.parsers import twogis as twogis_mod
    from parser_toolkit.parsers import yandex_maps as yandex_mod
    from parser_toolkit.parsers import yandex_realty as yandex_realty_mod

    _RUNNERS.update(
        {
            "2gis": twogis_mod.main,
            "yandex-maps": yandex_mod.main,
            "yandex-realty": yandex_realty_mod.main,
            "drom": drom_mod.main,
            "cian": cian_mod.main,
            "krisha": krisha_mod.main,
            "kolesa": kolesa_mod.main,
        }
    )


def _run(fn: Callable, argv: List[str]) -> int:
    try:
        result = fn(argv)
        if result is None:
            return 0
        return int(result)
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001 — CLI boundary
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


HELP = f"""parser-toolkit {__version__}

Local CIS/RU parsers — directories, marketplaces and real estate.
No Apify. Primarily direct HTTP; Playwright only for Kolesa phones.

usage:
  parser-toolkit <source> [options]
  parser-toolkit doctor [--live]
  python -m parser_toolkit <source> [options]

sources:
  2gis           2GIS businesses (Catalog web API)
  yandex-maps    Yandex Maps businesses (embedded JSON)
  yandex-realty  Yandex Realty listings (yandex.ru/realty; phones not public)
  drom           Drom.ru autos (list JSON; phones need session)
  cian           CIAN real estate (embedded JSON, RU proxy required)
  krisha         Krisha.kz real estate (window.data + cookie phones)
  kolesa         Kolesa.kz autos (HTTP + Playwright phones)

common flags:
  --out PREFIX           output path without extension (writes CSV/JSON + .run.json)
  --format csv,json,jsonl
  --resume               skip ids already in PREFIX.json / PREFIX.jsonl
  --cookie-file PATH     session cookie from a file (krisha / kolesa)

examples:
  parser-toolkit doctor
  parser-toolkit 2gis --query "кофейни" --city moscow --max 50
  parser-toolkit yandex-maps --query "стоматология" --city "Астана"
  parser-toolkit yandex-realty --city moscow --deal snyat --max 30
  parser-toolkit drom --city moscow --pages 2 --max 40
  parser-toolkit cian --proxy http://user:pass@host:port --pages 3
  parser-toolkit krisha --city almaty --max 30 --cookie-file ./krisha.cookie
  KOLESA_COOKIE="…" parser-toolkit kolesa --city almaty --max 15

  parser-toolkit 2gis --help
  parser-toolkit --version
"""


def main(argv: Optional[List[str]] = None) -> None:
    """Console entry point (raises SystemExit with process code)."""
    raise SystemExit(run(argv))


def run(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print(f"parser-toolkit {__version__}")
        return 0
    if argv[0] in ("doctor", "check"):
        from parser_toolkit.doctor import run_doctor

        return run_doctor(argv[1:])

    source_key = argv[0]
    if source_key not in ALIASES:
        print(f"ERROR: unknown source {source_key!r}", file=sys.stderr)
        print("Run: parser-toolkit --help", file=sys.stderr)
        return 2

    source = ALIASES[source_key]
    rest = argv[1:]
    if rest and rest[0] == "--":
        rest = rest[1:]

    _register()
    return _run(_RUNNERS[source], rest)


if __name__ == "__main__":
    main()
