"""Source parsers (2GIS, Yandex Maps, CIAN, Krisha, Kolesa).

Prefer ``parser_toolkit.scrape(source, **kwargs)`` over importing these
modules directly. Each module also exposes ``scrape(...)``.
"""

SOURCES = (
    "2gis",
    "yandex-maps",
    "cian",
    "krisha",
    "kolesa",
)

__all__ = ["SOURCES"]
