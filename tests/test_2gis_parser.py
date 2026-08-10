#!/usr/bin/env python3
"""Unit tests for 2GIS parser normalization (fixtures only)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parser_toolkit.parsers import twogis as tg  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "twogis_item.json"


class TestTwoGisNormalize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as f:
            cls.item = json.load(f)

    def test_normalize_item(self):
        row = tg.normalize_item(self.item, fallback_city="Москва", city_slug="moscow")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["source"], "2gis")
        self.assertEqual(row["phone"], "+79850385588")
        self.assertEqual(row["name"], "Humbl cookies, кофейня")
        self.assertIn("Кофейни", row["category"])
        self.assertEqual(row["latitude"], 55.790585)
        self.assertEqual(row["longitude"], 37.530263)
        self.assertIn("2gis.ru/moscow/firm/", row["url"])
        self.assertEqual(row["website"], "http://humbl.ru")
        self.assertEqual(row["email"], "info@humbl.ru")
        self.assertIn("phones", row)

    def test_no_phone(self):
        item = dict(self.item)
        item["contact_groups"] = []
        self.assertIsNone(tg.normalize_item(item))

    def test_parse_start_url(self):
        info = tg.parse_start_url(
            "https://2gis.ru/moscow/search/%D1%80%D0%B5%D1%81%D1%82%D0%BE%D1%80%D0%B0%D0%BD%D1%8B/rubricId/162"
        )
        self.assertEqual(info["city_slug"], "moscow")
        self.assertEqual(info["rubric_id"], "162")
        self.assertTrue(info["query"])

    def test_phone_norm(self):
        self.assertEqual(tg._norm_phone("8 (999) 111-22-33"), "+79991112233")
        self.assertEqual(tg._norm_phone("9991112233"), "+79991112233")


class TestPaginationHelpers(unittest.TestCase):
    def test_page_size_cap(self):
        self.assertLessEqual(tg.PAGE_SIZE, 50)


if __name__ == "__main__":
    unittest.main()
