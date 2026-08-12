"""Environment checks: python, extras, cookies, optional live ping."""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Tuple

from parser_toolkit import __version__
from parser_toolkit.core.exitcodes import EXIT_ERROR, EXIT_OK


Check = Tuple[str, bool, str]


def _ok(name: str, detail: str = "") -> Check:
    return (name, True, detail)


def _fail(name: str, detail: str) -> Check:
    return (name, False, detail)


def _python() -> Check:
    v = sys.version_info
    detail = f"{v.major}.{v.minor}.{v.micro}"
    if v < (3, 8):
        return _fail("python", f"{detail} (need >= 3.8)")
    return _ok("python", detail)


def _package() -> Check:
    return _ok("parser-toolkit", __version__)


def _imports() -> Check:
    try:
        from parser_toolkit.parsers import (  # noqa: F401
            cian,
            kolesa,
            krisha,
            twogis,
            yandex_maps,
            yandex_realty,
        )
    except Exception as e:  # noqa: BLE001
        return _fail("parsers", f"{type(e).__name__}: {e}")
    return _ok("parsers", "2gis, yandex-maps, yandex-realty, cian, krisha, kolesa")


def _playwright() -> Check:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return _ok("playwright", "not installed (optional; needed for Kolesa phones)")
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return _fail("playwright", f"import failed: {e}")
    return _ok("playwright", "installed")


def _secret(name: str, present: bool, *, optional: bool = True) -> Check:
    if present:
        return _ok(name, "set")
    if optional:
        return _ok(name, "missing (optional)")
    return _fail(name, "missing")


def _cookie_file(path: str) -> Check:
    if not path:
        return _ok("cookie-file", "not passed")
    if os.path.isfile(path):
        return _ok("cookie-file", path)
    return _fail("cookie-file", f"not found: {path}")


def _live_ping(url: str, timeout: float = 8.0) -> Check:
    from parser_toolkit.core.http import HttpClient, HttpError

    client = HttpClient(timeout=timeout, retries=1, sleep_base=0.1)
    try:
        body = client.get(url)
    except HttpError as e:
        return _fail(f"live {url}", str(e))
    except Exception as e:  # noqa: BLE001
        return _fail(f"live {url}", f"{type(e).__name__}: {e}")
    return _ok(f"live {url}", f"{len(body)} bytes")


def collect_checks(*, cookie_file: str = "", live: bool = False, proxy: str = "") -> List[Check]:
    checks: List[Check] = [
        _python(),
        _package(),
        _imports(),
        _playwright(),
        _secret("PROXY", bool((proxy or os.environ.get("PROXY", "")).strip())),
        _secret("KRISHA_COOKIE", bool(os.environ.get("KRISHA_COOKIE", "").strip())),
        _secret("KOLESA_COOKIE", bool(os.environ.get("KOLESA_COOKIE", "").strip())),
        _cookie_file(cookie_file or os.environ.get("COOKIE_FILE", "")),
    ]
    if live:
        checks.extend(
            [
                _live_ping("https://2gis.ru/"),
                _live_ping("https://krisha.kz/"),
            ]
        )
    return checks


def format_report(checks: List[Check]) -> str:
    lines = [f"parser-toolkit doctor {__version__}", ""]
    for name, ok, detail in checks:
        mark = "OK " if ok else "FAIL"
        extra = f" — {detail}" if detail else ""
        lines.append(f"  [{mark}] {name}{extra}")
    failed = sum(1 for _, ok, _ in checks if not ok)
    lines.append("")
    lines.append(f"{len(checks) - failed}/{len(checks)} checks passed")
    return "\n".join(lines) + "\n"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check local environment for parser-toolkit")
    p.add_argument("--cookie-file", default="", help="optional cookie file to verify exists")
    p.add_argument("--proxy", default=os.environ.get("PROXY", ""), help="proxy to report (not used unless --live)")
    p.add_argument(
        "--live",
        action="store_true",
        help="GET 2gis.ru and krisha.kz (network). Off by default.",
    )
    return p.parse_args(argv)


def run_doctor(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    checks = collect_checks(cookie_file=args.cookie_file, live=args.live, proxy=args.proxy)
    sys.stdout.write(format_report(checks))
    required_failed = any(not ok for name, ok, _ in checks if not name.startswith("live "))
    # live failures are warnings unless everything else is fine — still fail
    live_failed = any(not ok for name, ok, _ in checks if name.startswith("live "))
    if required_failed or live_failed:
        return EXIT_ERROR
    return EXIT_OK
