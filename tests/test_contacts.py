"""Contact collection regressions; no live services required."""
from __future__ import annotations

import argparse
import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from parser_toolkit import contacts as workflow
from parser_toolkit.cli import run
from parser_toolkit.contact_export import export_contacts
from parser_toolkit.core.contacts import contact_summary, link_type, make_contact
from parser_toolkit.core.http import HttpError
from parser_toolkit.parsers import twogis, yandex_maps
from parser_toolkit.website_contacts import crawl_website, extract_contacts


class DirectoryContacts(unittest.TestCase):
    def test_2gis_keeps_labels_extensions_all_contacts_and_email_only_company(self):
        item = {"id": "42", "name": "Завод", "contact_groups": [
            {"name": "Отдел продаж", "contacts": [
                {"type": "phone", "value": "+7 (777) 123-45-67, доб. 123"},
                {"type": "email", "value": "sales@example.org"},
                {"type": "email", "value": "export@example.org"},
                {"type": "whatsapp", "url": "https://wa.me/77771234567"}]},
            {"contacts": [{"type": "phone", "value": "+77771234567", "comment": "Руководитель Иван"}]}]}
        row = twogis.normalize_item(item, city_slug="almaty")
        self.assertEqual(row["emails"], ["sales@example.org", "export@example.org"])
        self.assertEqual(row["phones"], ["+77771234567"])
        self.assertEqual(row["contacts"][0]["extension"], "123")
        self.assertEqual(row["contacts"][0]["label"], "Отдел продаж")
        self.assertEqual(row["contacts"][-1]["label"], "Руководитель Иван")
        self.assertEqual(row["contacts"][0]["source_url"], "https://2gis.ru/almaty/firm/42")
        only_email = twogis.normalize_item({"id": "9", "contact_groups": [{"contacts": [
            {"type": "email", "value": "boss@example.org"}]}]})
        self.assertEqual(only_email["phone"], "")
        self.assertEqual(only_email["contacts"][0]["label"], "")

    def test_branches_with_a_shared_phone_are_not_discarded(self):
        items = [{"id": str(i), "contact_groups": [{"contacts": [
            {"type": "phone", "value": "+77771234567"}]}]} for i in range(2)]
        rows = {}
        self.assertEqual(twogis.collect(items + [items[0]], "Алматы", "almaty", rows), 2)
        self.assertEqual(set(rows), {"0", "1"})

    def test_kazakhstan_query_does_not_force_russian_locale(self):
        with patch.object(twogis, "http_get_json", return_value={}) as fetch:
            twogis.search_page(key="test", query="типография", region_id=67)
        params = parse_qs(urlsplit(fetch.call_args.args[0]).query)
        self.assertNotIn("locale", params)
        self.assertEqual(params["region_id"], ["67"])

    def test_no_guessing_roles_from_mailbox_names(self):
        c = make_contact("email", "mailto:director@example.org?subject=hello")
        self.assertEqual(c["value"], "director@example.org")
        self.assertEqual(c["label"], "")

    def test_yandex_email_social_links_and_labels(self):
        place = yandex_maps.normalize_yandex_item({"id": "99", "title": "Компания",
            "phones": [{"value": "+77771234567", "info": "", "comment": "Менеджер"}],
            "emails": [{"value": "sales@example.org", "description": "Продажи"}],
            "urls": ["https://instagram.com/example", "https://example.org"],
            "socialLinks": [{"type": "telegram", "href": "https://t.me/company"}]})
        self.assertEqual(place.website, "https://example.org")
        self.assertEqual(place.email, "sales@example.org")
        self.assertEqual(place.telegram, ["https://t.me/company"])
        self.assertEqual(place.contacts[0]["label"], "Менеджер")
        self.assertEqual(place.contacts[1]["label"], "Продажи")

    def test_messenger_detection_uses_hostname(self):
        self.assertEqual(link_type("https://example.org/whatsapp"), "website")
        self.assertEqual(link_type("https://wa.me.evil.example/123"), "website")
        self.assertEqual(link_type("https://api.whatsapp.com/send?phone=123"), "whatsapp")
        self.assertEqual(link_type("viber://chat?number=123"), "viber")

    def test_transport_errors_are_not_successful_empty_results(self):
        with patch.object(twogis, "search_page", side_effect=OSError("offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                twogis.search_all(key="test")
        client = unittest.mock.Mock()
        client.get.return_value = "<html>captcha page</html>"
        with self.assertRaises(HttpError):
            yandex_maps.fetch_search_page(client, "yandex.ru", 213, "moscow", "test", 1)

    def test_yandex_fallback_stops_when_server_repeats_page(self):
        state = {"config": {}, "stack": [{"results": {"items": [
            {"id": "1", "title": "Company", "type": "business", "emails": ["hi@example.org"]}]}}]}
        client = unittest.mock.Mock()
        client.get.return_value = '<script type="application/json">' + json.dumps(state) + '</script>'
        rows = yandex_maps.search_text(client, domain="yandex.ru", text="test", fallback_city="Москва",
                                       max_results=50, sleep=0, keep_raw=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(client.get.call_count, 2)

    def test_yandex_resume_keeps_email_only_records_and_labels(self):
        old = {"source": "yandex-maps", "place_id": "1", "name": "Email only", "phone": "",
               **contact_summary([make_contact("email", "boss@example.org", label="Руководитель")])}
        with patch.object(yandex_maps, "pick_domain", return_value="yandex.ru"), \
             patch.object(yandex_maps, "search_city", return_value=[]), \
             patch("parser_toolkit.core.resume.load_checkpoint", return_value=[old]), \
             redirect_stdout(io.StringIO()):
            records = yandex_maps.scrape(cities=["Москва"], out="unused", resume=True, write=False)
        self.assertEqual(records, [old])


class WebsiteContacts(unittest.TestCase):
    def test_visible_contacts_roles_provenance_and_script_exclusion(self):
        html = '''<html><script>"admin@secret.example +7 777 000-00-00"</script>
        <div hidden>hidden@secret.example</div>
        <p>Отдел продаж: <a href="mailto:sales@example.org?subject=hi">sales@example.org</a></p>
        <p>Директор Иван: <a href="tel:+77771234567;ext=42">+7 (777) 123-45-67</a></p>
        <p>Общая почта: info@example.org</p>
        <a href="https://t.me/company">Telegram</a><a href="/contacts">Контакты</a>
        <a href="https://elsewhere.example/contacts">Контакты партнёра</a></html>'''
        contacts, links = extract_contacts(html, "https://example.org/")
        self.assertFalse(any("secret.example" in c["value"] for c in contacts))
        sales = [c for c in contacts if c["value"] == "sales@example.org"]
        self.assertEqual(len(sales), 1)
        self.assertIn("Отдел продаж", sales[0]["label"])
        phone = next(c for c in contacts if c["type"] == "phone" and c["extension"])
        self.assertEqual(phone["value"], "+77771234567")
        self.assertEqual(phone["extension"], "42")
        self.assertEqual(sum(c["type"] == "phone" for c in contacts), 1)
        self.assertIn("Директор Иван", phone["label"])
        self.assertEqual(phone["source_url"], "https://example.org/")
        self.assertIn("https://example.org/contacts", links)
        self.assertTrue(any(c["value"] == "info@example.org" for c in contacts))
        self.assertTrue(any(c["type"] == "telegram" for c in contacts))

    def test_crawl_stays_on_company_host_obeys_limit_and_retains_failures(self):
        html = '<html><a href="/contacts">Контакты</a><a href="/about">О компании</a><a href="https://other.example/contacts">Контакты</a></html>'
        with patch("parser_toolkit.website_contacts.HttpClient") as cls:
            cls.return_value.get.side_effect = [html, OSError("timeout")]
            contacts, errors = crawl_website("https://example.org", max_pages=2, sleep=0)
            self.assertEqual(cls.return_value.get.call_count, 2)
            self.assertEqual(contacts, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("timeout", errors[0])


class ContactExport(unittest.TestCase):
    def test_excel_text_cells_prevent_formulas_and_keep_phone_and_id(self):
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("optional Excel dependency not installed")
        row = {"name": "=HYPERLINK(\"bad\")", "place_id": "001234", "source": "2gis",
               **contact_summary([make_contact("phone", "+77771234567", label="Продажи", source_url="https://example.org")])}
        with tempfile.TemporaryDirectory() as td:
            paths = export_contacts([row], str(Path(td) / "result"))
            book = load_workbook(paths["excel"])
            sheet = book["Контакты"]
            self.assertEqual(book.sheetnames, ["Контакты", "Компании"])
            self.assertEqual(sheet["A2"].data_type, "s")
            self.assertEqual(sheet["F2"].value, "+77771234567")
            self.assertEqual(sheet["F2"].data_type, "s")
            self.assertEqual(sheet["L2"].value, "001234")
            self.assertEqual(sheet["G2"].value, "Продажи")
            book.close()
            with open(paths["contacts"], encoding="utf-8-sig") as f:
                csv_rows = list(csv.reader(f, delimiter=";"))
            self.assertTrue(csv_rows[1][0].startswith("'="))
            self.assertEqual(csv_rows[1][5], "'+77771234567")
            self.assertEqual(json.loads(Path(paths["json"]).read_text(encoding="utf-8"))[0]["name"], row["name"])


class CollectionWorkflow(unittest.TestCase):
    def test_cli_logs_use_utf8_with_legacy_console_encoding(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252")
        with patch("sys.stdout", stream):
            self.assertEqual(run(["--help"]), 0)
            print("Русский журнал")
        stream.flush()
        self.assertIn("Русский журнал", raw.getvalue().decode("utf-8"))
        stream.detach()

    def args(self, out, **kwargs):
        values = dict(source="both", query="типография", cities=["Алматы"], max=2, out=out,
                      websites=False, website_pages=3, timeout=10, sleep=0, proxy="", no_excel=True)
        values.update(kwargs)
        return argparse.Namespace(**values)

    def test_source_failure_preserves_other_source_and_is_not_silent(self):
        row = {"source": "2gis", "place_id": "1", "name": "Company",
               **contact_summary([make_contact("email", "sales@example.org")])}
        with tempfile.TemporaryDirectory() as td, patch.object(workflow, "scrape", side_effect=[[row], RuntimeError("blocked")]), redirect_stdout(io.StringIO()):
            out = str(Path(td) / "result")
            code = workflow.run_collection(self.args(out))
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(Path(out + ".json").read_text(encoding="utf-8"))[0]["name"], "Company")
            report = json.loads(Path(out + ".run.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "partial")
            self.assertIn("blocked", report["errors"][0])

    def test_website_failures_do_not_discard_directory_contacts(self):
        row = {"source": "2gis", "place_id": "1", "name": "Company", **contact_summary([
            make_contact("email", "sales@example.org"), make_contact("website", "https://example.org")])}
        with tempfile.TemporaryDirectory() as td, patch.object(workflow, "scrape", return_value=[row]), \
             patch.object(workflow, "crawl_website", return_value=([], ["https://example.org: offline"])), redirect_stdout(io.StringIO()):
            out = str(Path(td) / "result")
            self.assertEqual(workflow.run_collection(self.args(out, source="2gis", websites=True)), 0)
            report = json.loads(Path(out + ".run.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "partial")
            self.assertTrue(report["website_errors"])
            self.assertEqual(json.loads(Path(out + ".json").read_text(encoding="utf-8"))[0]["email"], "sales@example.org")

    def test_empty_is_reported_and_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as td, patch.object(workflow, "scrape", return_value=[]), redirect_stdout(io.StringIO()):
            out = str(Path(td) / "result")
            self.assertEqual(workflow.run_collection(self.args(out)), 1)
            self.assertEqual(json.loads(Path(out + ".run.json").read_text(encoding="utf-8"))["status"], "empty")

    def test_validation_before_network(self):
        with patch.object(workflow, "scrape") as scrape, redirect_stdout(io.StringIO()):
            self.assertEqual(run(["contacts", "--help"]), 0)
            for extra in (["--max", "0"], ["--sleep", "-1"], ["--city", " "]):
                self.assertEqual(run(["contacts", "--query", "test", "--city", "Алматы", *extra]), 2)
            scrape.assert_not_called()


if __name__ == "__main__":
    unittest.main()
