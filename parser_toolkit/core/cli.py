"""Shared CLI helpers (argparse + env defaults)."""
from __future__ import annotations

import argparse
import os
from typing import List, Optional, Sequence


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def add_common_args(
    parser: argparse.ArgumentParser,
    *,
    default_query: str = "рестораны",
    default_out: str = "output/places",
    default_max: int = 200,
) -> argparse.ArgumentParser:
    parser.add_argument("-q", "--query", default=env("QUERY", default_query), help="search text / category")
    parser.add_argument(
        "-c",
        "--city",
        action="append",
        dest="cities",
        default=None,
        help="city name or slug (repeatable). Also: CITIES=a,b",
    )
    parser.add_argument("--max", type=int, default=int(env("MAX", str(default_max))), help="max results per city")
    parser.add_argument("--out", default=env("OUT", default_out), help="output path prefix (no extension)")
    parser.add_argument("--proxy", default=env("PROXY", ""), help="optional http://user:pass@host:port")
    parser.add_argument("--timeout", type=float, default=float(env("TIMEOUT", "30")), help="HTTP timeout seconds")
    parser.add_argument("--retries", type=int, default=int(env("RETRIES", "4")), help="HTTP retries")
    parser.add_argument("--sleep", type=float, default=float(env("SLEEP", "0.5")), help="delay between pages")
    parser.add_argument(
        "--raw",
        dest="keep_raw",
        action="store_true",
        default=env("RAW", "1") not in ("0", "false", "no"),
        help="keep raw source objects in JSON (default on)",
    )
    parser.add_argument(
        "--no-raw",
        dest="keep_raw",
        action="store_false",
        help="drop raw objects from JSON",
    )
    return parser


def resolve_cities(cli_cities: Optional[Sequence[str]], env_name: str = "CITIES") -> List[str]:
    if cli_cities:
        return [c.strip() for c in cli_cities if c and c.strip()]
    raw = env(env_name, "")
    if raw:
        return [c.strip() for c in raw.split(",") if c.strip()]
    return []
