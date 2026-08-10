#!/usr/bin/env python3
"""Unit tests for Yandex Maps parser (mocked / fixtures only — no live network)."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "yandex-maps"))

import yandex_maps_parser as ym  # noqa: E402
from core.models import normalize_phone  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "yandex_item.json"


class TestPhoneNormalize(unittest.TestCase):
    def test_ru_11(self):
        self.assertEqual(normalize_phone("+7 (985) 038-55-88"), "+79850385588")

    def test_dict_value(self):
        self.assertEqual(normalize_phone({"value": "+77055741119"}), "+77055741119")

    def test_extension_stripped(self):
        self.assertEqual(normalize_phone("+7 (812) 309-42-16, доб. 3"), "+78123094216")

    def test_empty(self):
        self.assertIsNone(normalize_phone(""))
        self.assertIsNone(normalize_phone(None))


class TestExtractState(unittest.TestCase):
    def test_empty_html(self):
        self.assertIsNone(ym.extract_app_state(""))
        self.assertIsNone(ym.extract_app_state("limited"))

    def test_malformed_json(self):
        html = '<script type="application/json">{not-json}</script>'
        self.assertIsNone(ym.extract_app_state(html))

    def test_valid_state(self):
        state = {
            "config": {"csrfToken": "x"},
            "stack": [
                {
                    "results": {
                        "totalResultCount": 2,
                        "items": [
                            {"type": "business", "id": "1", "title": "A"},
                            {"type": "toponym", "id": "2", "title": "Street"},
                        ],
                    }
                }
            ],
        }
        html = f'<html><script type="application/json">{json.dumps(state)}</script></html>'
        parsed = ym.extract_app_state(html)
        self.assertIsNotNone(parsed)
        results, items = ym.extract_search_results(parsed)
        self.assertEqual(results.get("totalResultCount"), 2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "1")

    def test_empty_results(self):
        state = {"config": {}, "stack": [{"results": {"items": []}}]}
        results, items = ym.extract_search_results(state)
        self.assertEqual(items, [])
        self.assertEqual(results.get("items"), [])


class TestNormalizeItem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as f:
            cls.item = json.load(f)

    def test_fixture_normalize(self):
        place = ym.normalize_yandex_item(self.item, fallback_city="Москва", domain="yandex.kz")
        self.assertIsNotNone(place)
        assert place is not None
        self.assertEqual(place.source, "yandex-maps")
        self.assertTrue(place.name)
        self.assertTrue(place.phone.startswith("+"))
        self.assertEqual(place.city, "Москва")
        self.assertNotEqual(place.latitude, "")
        self.assertNotEqual(place.longitude, "")
        self.assertIn("maps/org/", place.url)
        self.assertTrue(place.place_id)
        d = place.to_dict()
        self.assertIn("phones", d)
        self.assertIsInstance(d["phones"], list)

    def test_no_phone_skipped(self):
        item = dict(self.item)
        item["phones"] = []
        self.assertIsNone(ym.normalize_yandex_item(item))

    def test_city_lookup(self):
        self.assertEqual(ym.lookup_city("Москва")[0], 213)
        self.assertEqual(ym.lookup_city("astana")[0], 163)
        self.assertIsNone(ym.lookup_city("unknown-city-xyz"))

    def test_build_search_url_pagination(self):
        u1 = ym.build_search_url("yandex.kz", 213, "moscow", "кофейни", 1)
        u2 = ym.build_search_url("yandex.kz", 213, "moscow", "кофейни", 2)
        self.assertIn("/maps/213/moscow/search/", u1)
        self.assertNotIn("page=", u1)
        self.assertIn("page=2", u2)


class TestInit(unittest.TestCase):
    def test_parse_args_defaults(self):
        args = ym.parse_args([])
        self.assertTrue(args.query)
        self.assertGreater(args.max, 0)
        self.assertTrue(args.out)


if __name__ == "__main__":
    unittest.main()
