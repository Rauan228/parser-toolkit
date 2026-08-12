"""Stable library API.

    from parser_toolkit import scrape, sources
    rows = scrape("krisha", cities=["almaty"], max_per_city=10, skip_phones=True)

Each source also exposes ``scrape(...)`` on its module.
Passing ``out=`` writes CSV/JSON/JSONL + ``.run.json``; omit it to only return rows.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from parser_toolkit.parsers import SOURCES

_DISPATCH: Dict[str, Callable[..., List[Dict[str, Any]]]] = {}

ALIASES = {
    "2gis": "2gis",
    "twogis": "2gis",
    "yandex-maps": "yandex-maps",
    "yandex": "yandex-maps",
    "cian": "cian",
    "krisha": "krisha",
    "kolesa": "kolesa",
}


def sources() -> tuple:
    return SOURCES


def _load() -> None:
    if _DISPATCH:
        return
    from parser_toolkit.parsers import cian, kolesa, krisha, twogis, yandex_maps

    _DISPATCH.update(
        {
            "2gis": twogis.scrape,
            "yandex-maps": yandex_maps.scrape,
            "cian": cian.scrape,
            "krisha": krisha.scrape,
            "kolesa": kolesa.scrape,
        }
    )


def scrape(source: str, **kwargs: Any) -> List[Dict[str, Any]]:
    """Run a parser and return unified records.

    Keyword arguments match the source ``scrape()`` (cities, query, cookie, …).
    """
    key = ALIASES.get((source or "").strip().lower())
    if not key:
        known = ", ".join(SOURCES)
        raise ValueError(f"unknown source {source!r}; expected one of: {known}")
    _load()
    return _DISPATCH[key](**kwargs)
