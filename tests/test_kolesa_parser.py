#!/usr/bin/env python3
"""Unit tests for Kolesa parser (fixtures / pure functions, no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parser_toolkit.parsers import kolesa as kp  # noqa: E402


SAMPLE_HTML = """
<html><body>
<h1>Toyota Camry 2018 г.</h1>
<div class="offer__price">12&nbsp;500&nbsp;000 <span class="a-tenge">₸</span></div>
<div class="offer__parameters">
  <dl>
    <dt class="value-title">Город&nbsp;</dt><dd>Алматы, Алматинская область</dd>
    <dt class="value-title">Поколение</dt><dd>2017 - 2021 XV70</dd>
    <dt class="value-title">Кузов</dt><dd>Седан</dd>
    <dt class="value-title">Объем двигателя, л</dt><dd>2.5 (бензин)</dd>
    <dt class="value-title">Пробег</dt><dd>85 000 км</dd>
    <dt class="value-title">Коробка передач</dt><dd>Автомат</dd>
    <dt class="value-title">Привод</dt><dd>Передний привод</dd>
    <dt class="value-title">Руль</dt><dd>Слева</dd>
    <dt class="value-title">Цвет</dt><dd>белый</dd>
    <dt class="value-title">Растаможен в Казахстане</dt><dd>Да</dd>
  </dl>
</div>
<div class="offer__description">Отличное состояние, один хозяин.</div>
</body></html>
"""

SAMPLE_LIST = """
<div class="a-card" data-id="111222333"></div>
<a href="/a/show/444555666">x</a>
<div data-id="12"></div>
"""


class TestExtract(unittest.TestCase):
    def test_list_ids(self):
        ids = kp.extract_list_ids(SAMPLE_LIST)
        self.assertIn("111222333", ids)
        self.assertIn("444555666", ids)
        self.assertNotIn("12", ids)

    def test_list_url(self):
        self.assertEqual(
            kp.build_list_url("cars", "almaty", 1),
            "https://kolesa.kz/cars/almaty/",
        )
        self.assertIn("page=2", kp.build_list_url("cars", "almaty", 2))

    def test_params_and_normalize(self):
        var_data = {
            "advert": {
                "id": 999,
                "title": "Toyota Camry 2018 г.",
                "phonePrefix": "+7 777",
                "nbPhones": 1,
                "userId": 42,
            }
        }
        row = kp.normalize_listing(
            listing_id="999",
            html=SAMPLE_HTML,
            var_data=var_data,
            phones=["+7 777 111 22 33", "+7 701 000 11 22"],
            keep_raw=False,
        )
        self.assertEqual(row["source"], "kolesa")
        self.assertEqual(row["phone"], "+77771112233")
        self.assertEqual(row["phone2"], "+77010001122")
        self.assertEqual(row["price_kzt"], 12500000)
        self.assertEqual(row["city"], "Алматы")
        self.assertEqual(row["year"], 2018)
        self.assertEqual(row["mileage_km"], 85000)
        self.assertEqual(row["body"], "Седан")
        self.assertIn("2.5", row["engine"])
        self.assertEqual(row["phone_preview"], "+7 777")
        self.assertIn("/a/show/999", row["url"])

    def test_cookie_parse(self):
        cookies = kp.parse_cookie_header("klssid=abc; kumd=xyz%3D; other=1")
        names = {c["name"] for c in cookies}
        self.assertIn("klssid", names)
        self.assertIn("kumd", names)
        self.assertTrue(all(c["domain"] == ".kolesa.kz" for c in cookies))


if __name__ == "__main__":
    unittest.main()
