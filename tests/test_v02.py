#!/usr/bin/env python3
"""v0.2 helpers: schema, JSONL, cookies, resume, doctor, library API."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from parser_toolkit import __version__, scrape, sources
from parser_toolkit.cli import run
from parser_toolkit.core.cookies import cookie_status, load_cookie
from parser_toolkit.core.exitcodes import EXIT_BLOCKED
from parser_toolkit.core.output import dump_records, parse_formats
from parser_toolkit.core.report import RunReport, persist_run
from parser_toolkit.core.resume import load_checkpoint, seed_rows
from parser_toolkit.core.schema import apply_schema, phone_metrics
from parser_toolkit.doctor import collect_checks, run_doctor
from parser_toolkit.parsers import cian as cian_mod


class TestSchema(unittest.TestCase):
    def test_apply_schema_fills_unified_keys(self):
        row = apply_schema(
            {
                "listing_id": "42",
                "name": "Квартира",
                "phone": "87771234567",
                "price_kzt": 15000000,
                "city": "Алматы",
            },
            source="krisha",
        )
        self.assertEqual(row["source"], "krisha")
        self.assertEqual(row["id"], "42")
        self.assertEqual(row["title"], "Квартира")
        self.assertEqual(row["phone"], "+77771234567")
        self.assertEqual(row["phones"], ["+77771234567"])
        self.assertEqual(row["price"], 15000000)
        self.assertEqual(row["currency"], "KZT")
        self.assertTrue(row["scraped_at"])

    def test_phone_metrics(self):
        m = phone_metrics(
            [
                {"phone": "+7701", "phone_preview": "+7 701"},
                {"phone": "", "phone_preview": "+7 702"},
            ]
        )
        self.assertEqual(m["total"], 2)
        self.assertEqual(m["with_phone"], 1)
        self.assertEqual(m["with_preview"], 2)
        self.assertEqual(m["phone_rate"], 0.5)


class TestOutputFormats(unittest.TestCase):
    def test_parse_formats(self):
        self.assertEqual(parse_formats("csv,jsonl"), ["csv", "jsonl"])
        self.assertEqual(parse_formats(None), ["csv", "json"])

    def test_jsonl_and_run_report(self):
        with tempfile.TemporaryDirectory() as td:
            base = os.path.join(td, "out")
            rows = [{"source": "x", "listing_id": "1", "name": "A", "phone": "+79991112233"}]
            written = dump_records(rows, base, fields=["source", "phone", "name"], formats="csv,json,jsonl")
            self.assertTrue(os.path.isfile(written["jsonl"]))
            lines = Path(written["jsonl"]).read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            obj = json.loads(lines[0])
            self.assertEqual(obj["id"], "1")
            self.assertEqual(obj["title"], "A")

            report = RunReport(source="x")
            persist_run(rows, base, fields=["source"], formats="json", source="x", report=report, echo=False)
            run_path = base + ".run.json"
            self.assertTrue(os.path.isfile(run_path))
            payload = json.loads(Path(run_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["source"], "x")
            self.assertEqual(payload["counts"]["records"], 1)
            self.assertEqual(payload["phones"]["with_phone"], 1)


class TestCookiesAndResume(unittest.TestCase):
    def test_cookie_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "sess.cookie")
            Path(path).write_text("# comment\nkrssid=abc; kumd=xyz\n", encoding="utf-8")
            val = load_cookie(cookie_file=path)
            self.assertEqual(val, "krssid=abc; kumd=xyz")
            self.assertEqual(cookie_status(val), "set")
            self.assertEqual(cookie_status(""), "missing")

    def test_cookie_cli_wins(self):
        val = load_cookie(cookie="a=1", cookie_file="nope")
        self.assertEqual(val, "a=1")

    def test_resume_seed(self):
        with tempfile.TemporaryDirectory() as td:
            base = os.path.join(td, "data")
            dump_records(
                [{"listing_id": "10", "source": "krisha", "phone": "+7701"}],
                base,
                fields=["listing_id", "phone"],
                formats="json",
            )
            dest = {}
            n = seed_rows(dest, load_checkpoint(base))
            self.assertEqual(n, 1)
            self.assertIn("10", dest)


class TestDoctorAndCli(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, "0.3.0")
        self.assertEqual(run(["--version"]), 0)

    def test_doctor_offline(self):
        self.assertEqual(run_doctor([]), 0)
        checks = collect_checks()
        names = [n for n, _, _ in checks]
        self.assertIn("python", names)
        self.assertIn("parsers", names)
        self.assertFalse(any(n.startswith("live ") for n in names))

    def test_doctor_cli(self):
        self.assertEqual(run(["doctor"]), 0)

    def test_sources(self):
        self.assertIn("krisha", sources())


class TestCianHardProxy(unittest.TestCase):
    def test_no_proxy_exits_blocked(self):
        with self.assertRaises(SystemExit) as ctx:
            cian_mod.scrape(proxy="", require_proxy=True, write=False)
        self.assertEqual(ctx.exception.code, EXIT_BLOCKED)

    def test_help_does_not_require_proxy(self):
        self.assertEqual(run(["cian", "--help"]), 0)


class TestLibraryApi(unittest.TestCase):
    def test_unknown_source(self):
        with self.assertRaises(ValueError):
            scrape("avito")

    def test_dispatch_calls_source_scrape(self):
        from parser_toolkit import api as api_mod

        api_mod._DISPATCH.clear()
        with mock.patch("parser_toolkit.parsers.krisha.scrape", return_value=[{"id": "1"}]) as fn:
            rows = scrape("krisha", cities=["almaty"], max_per_city=1, skip_phones=True)
        self.assertEqual(rows, [{"id": "1"}])
        fn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
