#!/usr/bin/env python3
"""Shim — implementation lives in parser_toolkit.parsers.cian."""
from parser_toolkit.parsers.cian import *  # noqa: F403
from parser_toolkit.parsers.cian import main

if __name__ == "__main__":
    raise SystemExit(main() or 0)
