#!/usr/bin/env python3
"""Drom.ru parser tests (fixtures only)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from parser_toolkit.cli import run
from parser_toolkit.core.http import decode_http_body
from parser_toolkit.parsers import drom as drom_mod

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "drom_items.json"


def _items():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _list_html(items) -> str:
    payload = {
        "bullList": {"bullsData": [{"bulls": items}]},
        "__slug": "bulls-list-auto",
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        '<html><head><meta charset="windows-1251"><title>Drom</title></head>'
        f'<script type="application/json" data-drom-module="bulls-list-auto">{body}</script>'
        "</html>"
    )


class TestExtract(unittest.TestCase):
    def test_extract_bulls(self):
        html = _list_html(_items())
        bulls = drom_mod.extract_bulls(html)
        self.assertEqual(len(bulls), 2)
        self.assertEqual(bulls[0]["bullId"], 784975014)

    def test_empty(self):
        self.assertEqual(drom_mod.extract_bulls(""), [])
        self.assertEqual(drom_mod.extract_bulls("<html></html>"), [])

    def test_list_url(self):
        self.assertEqual(drom_mod.list_url("moscow", 1), "https://auto.drom.ru/moscow/all/")
        self.assertEqual(drom_mod.list_url("msk", 2), "https://auto.drom.ru/moscow/all/page2/")
        self.assertEqual(drom_mod.resolve_city_slug("питер"), "spb")


class TestNormalize(unittest.TestCase):
    def test_fixture(self):
        row = drom_mod.normalize_listing(_items()[0], fallback_city="Москва", keep_raw=False)
        self.assertEqual(row["source"], "drom")
        self.assertEqual(row["listing_id"], "784975014")
        self.assertEqual(row["price_rub"], 1350000)
        self.assertEqual(row["year"], 2001)
        self.assertEqual(row["mileage_km"], 132000)
        self.assertIn("5.8", row["engine"])
        self.assertEqual(row["fuel"], "бензин")
        self.assertEqual(row["transmission"], "АКПП")
        self.assertEqual(row["drive"], "задний")
        self.assertEqual(row["phone"], "")

    def test_contacts_blocked(self):
        phones, status = drom_mod.parse_contacts_response('{"type":4,"message":null}')
        self.assertEqual(status, "blocked")
        self.assertEqual(phones, [])

    def test_contacts_auth_required(self):
        body = '{"type":5,"contactErrorNotification":{"type":10,"loginUrl":"https://my.drom.ru/sign"}}'
        phones, status = drom_mod.parse_contacts_response(body)
        self.assertEqual(status, "auth_required")
        self.assertEqual(phones, [])

    def test_contacts_ok(self):
        phones, status = drom_mod.parse_contacts_response('{"phone":"+7 999 111-22-33"}')
        self.assertEqual(status, "ok")
        self.assertEqual(phones, ["+79991112233"])

    def test_contacts_type9_html(self):
        body = '{"type":9,"phone":"<span>+7 (915) 385-2795</span> <small>x</small>"}'
        phones, status = drom_mod.parse_contacts_response(body)
        self.assertEqual(status, "ok")
        self.assertEqual(phones, ["+79153852795"])


class TestDecode(unittest.TestCase):
    def test_cp1251(self):
        raw = "<title>Москва</title>".encode("cp1251")
        text = decode_http_body(raw, "text/html; charset=windows-1251")
        self.assertIn("Москва", text)


class TestScrapeMocked(unittest.TestCase):
    def test_scrape_no_network(self):
        html = _list_html(_items())
        client = mock.MagicMock()
        client.get.return_value = html
        with mock.patch.object(drom_mod, "HttpClient", return_value=client):
            rows = drom_mod.scrape(cities=["moscow"], pages=1, max_per_city=10, write=False)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "drom")


class TestCli(unittest.TestCase):
    def test_help(self):
        self.assertEqual(run(["drom", "--help"]), 0)


if __name__ == "__main__":
    unittest.main()
