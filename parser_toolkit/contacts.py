"""End-user contact collection workflow: directory -> company websites -> Excel."""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import List, Optional

from parser_toolkit.api import scrape
from parser_toolkit.contact_export import export_contacts
from parser_toolkit.core.contacts import contact_summary
from parser_toolkit.core.schema import record_id, utc_now
from parser_toolkit.website_contacts import crawl_website


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("укажите целое число больше нуля")
    return number


def nonnegative(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("значение не может быть отрицательным")
    return number


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Сбор контактов организаций в Excel, CSV и JSON")
    p.add_argument("--source", choices=("2gis", "yandex-maps", "both"), default="2gis", help="источник; both — оба")
    p.add_argument("-q", "--query", required=True, help="категория или название компании")
    p.add_argument("-c", "--city", action="append", required=True, dest="cities", help="город; можно повторить")
    p.add_argument("--max", type=positive, default=50, help="максимум организаций на город и источник")
    p.add_argument("--out", default="output/contacts", help="путь без расширения; повторный запуск перезаписывает файлы")
    p.add_argument("--websites", action="store_true", help="дополнительно читать публичные сайты компаний")
    p.add_argument("--website-pages", type=positive, default=3, help="максимум страниц сайта на компанию")
    p.add_argument("--timeout", type=positive, default=20)
    p.add_argument("--sleep", type=nonnegative, default=1.0, help="пауза между страницами и сайтами")
    p.add_argument("--proxy", default="", help="необязательный HTTP-прокси")
    p.add_argument("--no-excel", action="store_true", help="сохранить только CSV и JSON")
    args = p.parse_args(argv)
    if not args.query.strip() or not all(c.strip() for c in args.cities):
        p.error("Заполните запрос и город")
    if not args.out.strip():
        p.error("Укажите путь результата")
    return args


def run_collection(args) -> int:
    started = time.monotonic()
    report = {"started_at": utc_now(), "query": args.query, "cities": args.cities,
              "source": args.source, "errors": [], "website_errors": [], "status": "running"}
    records = {}
    paths = {}
    sources = ("2gis", "yandex-maps") if args.source == "both" else (args.source,)
    def save(*, final=False):
        nonlocal paths
        paths = export_contacts(list(records.values()), args.out, excel=final and not args.no_excel)
        report.update(records=len(records), contacts=sum(len(r.get("contacts") or []) for r in records.values()),
                      files=paths, duration_s=round(time.monotonic() - started, 2))
        path = Path(args.out + ".run.json")
        tmp = Path(str(path) + ".tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    try:
        for source in sources:
            for city in args.cities:
                try:
                    print(f"\nСобираю: {source}, {city}, {args.query}", flush=True)
                    found = scrape(source, query=args.query.strip(), cities=[city.strip()], max_results=args.max,
                                   timeout=args.timeout, retries=2, sleep=args.sleep, proxy=args.proxy,
                                   keep_raw=False, write=False)
                    for row in found:
                        # Keep branches even when they share the same reception number.
                        key = (source, record_id(row))
                        if key[1]:
                            records[key] = row
                    print(f"Найдено организаций: {len(found)}. Всего: {len(records)}", flush=True)
                    save()
                except (Exception, SystemExit) as exc:
                    if isinstance(exc, SystemExit) and exc.code == 0:
                        raise
                    message = f"{source}, {city}: {exc}"
                    report["errors"].append(message)
                    print(f"Ошибка источника: {message}", flush=True)
        if args.websites:
            cache = {}
            for index, row in enumerate(records.values(), 1):
                urls = row.get("websites") or ([row["website"]] if row.get("website") else [])
                # One primary company site; avoids following every social or advert URL.
                if not urls:
                    continue
                website = urls[0]
                print(f"Сайт {index}/{len(records)}: {row.get('name')} — {website}", flush=True)
                if website not in cache:
                    if cache:
                        time.sleep(args.sleep)
                    cache[website] = crawl_website(website, max_pages=args.website_pages,
                                                  timeout=args.timeout, sleep=args.sleep, proxy=args.proxy)
                contacts, errors = cache[website]
                row.update(contact_summary([*(row.get("contacts") or []), *contacts]))
                report["website_errors"].extend(e for e in errors if e not in report["website_errors"])
                save()
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        report["finished_at"] = utc_now()
        save(final=True)
        print("Сбор остановлен. Уже обработанные организации сохранены.", flush=True)
        return 130
    report["finished_at"] = utc_now()
    if report["errors"]:
        report["status"] = "partial" if records else "error"
    elif not records:
        report["status"] = "empty"
    elif report["website_errors"]:
        report["status"] = "partial"
    else:
        report["status"] = "ok"
    save(final=True)
    if not records:
        print("Организации не получены. Проверьте запрос, город и ошибки выше; пустая таблица не подтверждает отсутствие компаний.", flush=True)
    else:
        print(f"\nСохранено: {len(records)} организаций, {report['contacts']} контактов.", flush=True)
    for path in paths.values():
        print(path, flush=True)
    if report["website_errors"]:
        print(f"Не удалось прочитать часть страниц сайтов: {len(report['website_errors'])}. Подробности в {args.out}.run.json", flush=True)
    return 1 if report["errors"] or not records else 0


def main(argv: Optional[List[str]] = None) -> int:
    return run_collection(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
