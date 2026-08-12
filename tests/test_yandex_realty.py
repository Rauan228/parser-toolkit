#!/usr/bin/env python3
"""Yandex Realty parser tests (fixtures only)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from parser_toolkit.cli import run
from parser_toolkit.core.exitcodes import EXIT_BLOCKED
from parser_toolkit.parsers import yandex_realty as yr

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "yandex_realty_items.json"


def _items():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _html_from_items(items) -> str:
    blob = "".join(json.dumps(it, ensure_ascii=False, separators=(",", ":")) for it in items)
    return f"<html><title>Квартиры</title><script>var x={blob};searchResultsCount=2</script></html>"


class TestExtract(unittest.TestCase):
    def test_extract_from_html(self):
        html = _html_from_items(_items())
        offers = yr.extract_offers(html)
        self.assertEqual(len(offers), 2)
        self.assertEqual(offers[0]["id"], "8051294829830356491")

    def test_empty(self):
        self.assertEqual(yr.extract_offers(""), [])
        self.assertEqual(yr.extract_offers("<html></html>"), [])

    def test_captcha(self):
        self.assertTrue(yr.is_captcha('<title>Вы не робот?</title>'))
        self.assertTrue(yr.is_captcha('{"type": "captcha", "captcha": {}}'))
        self.assertFalse(yr.is_captcha("<title>Снять квартиру в Москве</title>"))


class TestNormalize(unittest.TestCase):
    def test_fixture_item(self):
        row = yr.normalize_offer(_items()[0], fallback_city="Москва", keep_raw=False)
        self.assertEqual(row["source"], "yandex-realty")
        self.assertEqual(row["listing_id"], "8051294829830356491")
        self.assertEqual(row["price_rub"], 126500)
        self.assertEqual(row["rooms"], 3)
        self.assertEqual(row["area_m2"], 67.4)
        self.assertEqual(row["floor"], 15)
        self.assertEqual(row["floors_total"], 17)
        self.assertEqual(row["metro"], "Пролетарская")
        self.assertEqual(row["phone"], "")
        self.assertIn("Марксистская", row["address"])
        self.assertTrue(row["url"].endswith("/8051294829830356491"))

    def test_city_deal(self):
        self.assertEqual(yr.resolve_city("msk")[0], "moskva")
        self.assertEqual(yr.resolve_deal("arenda"), "snyat")
        self.assertEqual(yr.resolve_ptype("apartment"), "kvartira")


class TestScrapeMocked(unittest.TestCase):
    def test_scrape_no_network(self):
        html = _html_from_items(_items())

        def fake_get(url, **kwargs):
            return html

        client = mock.MagicMock()
        client.get.side_effect = fake_get
        with mock.patch.object(yr, "HttpClient", return_value=client):
            rows = yr.scrape(
                cities=["moscow"],
                deal="snyat",
                property_type="kvartira",
                pages=1,
                max_per_city=10,
                write=False,
                domains=["yandex.ru"],
            )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "yandex-realty")

    def test_captcha_exits_blocked(self):
        client = mock.MagicMock()
        client.get.return_value = '<title>Вы не робот?</title>'
        with mock.patch.object(yr, "HttpClient", return_value=client):
            with self.assertRaises(SystemExit) as ctx:
                yr.scrape(cities=["moscow"], write=False, domains=["yandex.ru"])
        self.assertEqual(ctx.exception.code, EXIT_BLOCKED)


class TestCli(unittest.TestCase):
    def test_help(self):
        self.assertEqual(run(["yandex-realty", "--help"]), 0)

    def test_alias(self):
        self.assertEqual(run(["realty", "--help"]), 0)


if __name__ == "__main__":
    unittest.main()
