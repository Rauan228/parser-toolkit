#!/usr/bin/env python3
"""Shim — implementation lives in parser_toolkit.parsers.krisha."""
from parser_toolkit.parsers.krisha import *  # noqa: F403
from parser_toolkit.parsers.krisha import main

if __name__ == "__main__":
    raise SystemExit(main() or 0)
