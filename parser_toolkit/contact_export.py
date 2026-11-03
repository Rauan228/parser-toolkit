"""Russian spreadsheet exports, with one contact per row and clickable provenance."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List

CONTACT_COLUMNS = ["Компания", "Город", "Адрес", "Категория", "Тип контакта", "Контакт",
                   "Подпись в источнике", "Добавочный", "Где найден", "Карточка компании", "Источник", "ID компании"]
COMPANY_COLUMNS = ["Компания", "Город", "Адрес", "Категория", "Телефоны", "Почты", "Сайты",
                   "WhatsApp", "Telegram", "Viber", "Карточка компании", "Источник", "ID компании"]
TYPES = {"phone": "Телефон", "email": "Почта", "website": "Сайт", "whatsapp": "WhatsApp",
         "telegram": "Telegram", "viber": "Viber", "social": "Соцсеть"}


def contact_rows(records):
    rows = []
    for r in records:
        for c in r.get("contacts") or []:
            rows.append([r.get("name", ""), r.get("city", ""), r.get("address", ""), r.get("category", ""),
                         TYPES.get(c["type"], c["type"]), c["value"], c.get("label", ""),
                         c.get("extension", ""), c.get("source_url", ""), r.get("url", ""),
                         r.get("source", ""), r.get("place_id") or r.get("firm_id") or r.get("id", "")])
    return rows


def company_rows(records):
    return [[r.get("name", ""), r.get("city", ""), r.get("address", ""), r.get("category", ""),
             *["\n".join(r.get(k) or []) for k in ("phones", "emails", "websites", "whatsapp", "telegram", "viber")],
             r.get("url", ""), r.get("source", ""), r.get("place_id") or r.get("firm_id") or r.get("id", "")]
            for r in records]


def _csv_cell(value):
    value = str(value if value is not None else "")
    # Excel may interpret untrusted company names or +7 phones as formulas.
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_contacts(records: List[Dict[str, Any]], out: str, *, excel: bool = True) -> Dict[str, str]:
    base = Path(out)
    base.parent.mkdir(parents=True, exist_ok=True)
    tables = [("contacts", CONTACT_COLUMNS, contact_rows(records)),
              ("companies", COMPANY_COLUMNS, company_rows(records))]
    paths = {}
    for name, columns, rows in tables:
        path = str(base) + "." + name + ".csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(columns)
            writer.writerows([_csv_cell(v) for v in row] for row in rows)
        paths[name] = path
    path = str(base) + ".json"
    temporary = Path(path + ".tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    paths["json"] = path
    if excel:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError:
            print('Excel недоступен: установите python -m pip install -e ".[contacts]". CSV и JSON сохранены.')
        else:
            book = Workbook()
            book.remove(book.active)
            for (_, columns, rows), title in zip(tables, ("Контакты", "Компании")):
                sheet = book.create_sheet(title)
                sheet.append(columns)
                for row in rows:
                    # Explicit text cells preserve +7, leading zeroes and prevent formulas.
                    sheet.append([re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(v or ""))[:32767] for v in row])
                    for cell in sheet[sheet.max_row]:
                        cell.data_type = "s"
                        cell.number_format = "@"
                        cell.alignment = Alignment(vertical="top", wrap_text=True)
                for cell in sheet[1]:
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill("solid", fgColor="2563EB")
                    sheet.column_dimensions[cell.column_letter].width = 30
                sheet.freeze_panes = "A2"
                sheet.auto_filter.ref = sheet.dimensions
            path = str(base) + ".xlsx"
            book.save(path)
            paths["excel"] = path
    return paths
