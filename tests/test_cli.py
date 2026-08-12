#!/usr/bin/env python3
"""CLI smoke tests (no network)."""
from __future__ import annotations

import unittest

from parser_toolkit import __version__
from parser_toolkit.cli import run


class TestCLI(unittest.TestCase):
    def test_version(self):
        self.assertEqual(run(["--version"]), 0)
        self.assertEqual(__version__, "0.3.0")

    def test_help(self):
        self.assertEqual(run(["--help"]), 0)

    def test_unknown_source(self):
        self.assertEqual(run(["not-a-source"]), 2)

    def test_source_help_2gis(self):
        # argparse --help raises SystemExit(0) inside parser
        code = run(["2gis", "--help"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
