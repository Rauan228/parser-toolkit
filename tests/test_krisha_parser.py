#!/usr/bin/env python3
"""Unit tests for Krisha parser (fixtures only)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parser_toolkit.parsers import krisha as kp  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


class TestExtractors(unittest.TestCase):
    def test_list_ids(self):
        html = (FIX / "krisha_list_snippet.html").read_text(encoding="utf-8")
        ids = kp.extract_list_ids(html)
        self.assertGreaterEqual(len(ids), 1)
        self.assertTrue(ids[0].isdigit())

    def test_window_data_from_fixture_json(self):
        data = json.loads((FIX / "krisha_jsdata.json").read_text(encoding="utf-8"))
        html = f'<script id="jsdata">window.data = {json.dumps(data, ensure_ascii=False)};</script>'
        parsed = kp.extract_window_data(html)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIn("advert", parsed)
        self.assertEqual(str(parsed["advert"]["id"]), str(data["advert"]["id"]))

    def test_malformed_window_data(self):
        self.assertIsNone(kp.extract_window_data("<html>no data</html>"))

    def test_floor_parse(self):
        self.assertEqual(kp.parse_floor_pair("1-комнатная · 30 м² · 10/14 этаж"), (10, 14))
        self.assertEqual(kp.parse_floor_pair("no floor"), ("", ""))


class TestNormalize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((FIX / "krisha_jsdata.json").read_text(encoding="utf-8"))

    def test_normalize_metadata(self):
        row = kp.normalize_listing(
            self.data,
            fallback_city="Алматы",
            deal_type="arenda",
            property_type="kvartiry",
            phones=None,
            keep_raw=True,
        )
        self.assertEqual(row["source"], "krisha")
        self.assertTrue(str(row["phone"]).startswith("+7"))
        self.assertIn("778", row["phone"])
        self.assertTrue(row["title"])
        self.assertEqual(row["rooms"], 1)
        self.assertEqual(row["area_m2"], 30)
        self.assertEqual(row["price_kzt"], 300000)
        self.assertEqual(row["floor"], 10)
        self.assertEqual(row["floors_total"], 14)
        self.assertIn("krisha.kz/a/show/", row["url"])
        self.assertTrue(row["latitude"])
        self.assertTrue(row["phone_preview"])
        self.assertIn("raw", row)

    def test_normalize_ajax_phones_merge(self):
        data = json.loads(json.dumps(self.data))
        data["adverts"][0].pop("phones", None)
        row = kp.normalize_listing(data, phones=["+77081234567"], keep_raw=False)
        self.assertEqual(row["phone"], "+77081234567")
        self.assertNotIn("raw", row)

    def test_normalize_without_phones(self):
        data = json.loads(json.dumps(self.data))
        data["adverts"][0].pop("phones", None)
        row = kp.normalize_listing(data, phones=[], keep_raw=False)
        self.assertEqual(row["phone"], "")
        self.assertNotIn("raw", row)


class TestPhonesResponse(unittest.TestCase):
    def test_ok_payload(self):
        body = (FIX / "krisha_phones_ok.json").read_text(encoding="utf-8")
        phones = kp.parse_phones_response(body)
        self.assertGreaterEqual(len(phones), 1)

    def test_auth_payload(self):
        body = (FIX / "krisha_phones_auth.json").read_text(encoding="utf-8")
        phones = kp.parse_phones_response(body)
        self.assertEqual(phones, [])

    def test_empty(self):
        self.assertEqual(kp.parse_phones_response(""), [])
        self.assertEqual(kp.parse_phones_response("not-json"), [])


class TestUrls(unittest.TestCase):
    def test_list_url(self):
        self.assertEqual(
            kp.build_list_url("arenda", "kvartiry", "almaty", 1),
            "https://krisha.kz/arenda/kvartiry/almaty/",
        )
        self.assertIn("page=2", kp.build_list_url("arenda", "kvartiry", "almaty", 2))


if __name__ == "__main__":
    unittest.main()
