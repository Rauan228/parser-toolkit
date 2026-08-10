#!/usr/bin/env python3
"""Shim — implementation lives in parser_toolkit.parsers.yandex_maps."""
from parser_toolkit.parsers.yandex_maps import *  # noqa: F403
from parser_toolkit.parsers.yandex_maps import main

if __name__ == "__main__":
    raise SystemExit(main() or 0)
