#!/usr/bin/env python3
"""Tests for shared core helpers."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.http import HttpClient, HttpError  # noqa: E402
from core.models import Place, normalize_phone  # noqa: E402
from core.output import dump_places  # noqa: E402


class TestModels(unittest.TestCase):
    def test_place_finalize(self):
        p = Place(source="test", name="A", phones=["+79990001122", "+79990003344"])
        d = p.to_dict(keep_raw=False)
        self.assertEqual(d["phone"], "+79990001122")
        self.assertEqual(d["phone2"], "+79990003344")
        self.assertNotIn("raw", d) or self.assertIsNone(d.get("raw"))

    def test_normalize_phone(self):
        self.assertEqual(normalize_phone("89991234567"), "+79991234567")


class TestOutput(unittest.TestCase):
    def test_dump_creates_files(self):
        with tempfile.TemporaryDirectory() as td:
            base = os.path.join(td, "out", "places")
            places = [
                Place(source="x", name="Cafe", phones=["+79991112233"], city="Москва").finalize()
            ]
            dump_places(places, base, keep_raw=False)
            self.assertTrue(os.path.isfile(base + ".json"))
            self.assertTrue(os.path.isfile(base + ".csv"))
            with open(base + ".json", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data[0]["name"], "Cafe")
            with open(base + ".csv", encoding="utf-8-sig") as f:
                csv_head = f.readline()
            self.assertIn("phone", csv_head)


class TestHttpClient(unittest.TestCase):
    def test_retries_on_url_error(self):
        client = HttpClient(timeout=1, retries=2, sleep_base=0.01)

        class Boom(Exception):
            pass

        with mock.patch.object(client, "_request", side_effect=TimeoutError("x")):
            with self.assertRaises(HttpError):
                client.get("https://example.invalid/")


if __name__ == "__main__":
    unittest.main()
