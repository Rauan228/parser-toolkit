"""Resume a run from previously written JSON / JSONL."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

from .schema import record_id


def load_json_records(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def load_jsonl_records(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def load_checkpoint(out_base: str) -> List[Dict[str, Any]]:
    """Load existing records from `{out}.json` (preferred) or `{out}.jsonl`."""
    json_rows = load_json_records(out_base + ".json")
    if json_rows:
        return json_rows
    return load_jsonl_records(out_base + ".jsonl")


def index_by_id(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = record_id(row)
        if key:
            indexed[key] = dict(row)
    return indexed


def seed_rows(
    dest: MutableMapping[str, Any],
    existing: Iterable[Mapping[str, Any]],
    *,
    key_fn=None,
) -> int:
    """Copy existing records into dest. Returns how many were seeded."""
    n = 0
    for row in existing:
        key = key_fn(row) if key_fn else record_id(row)
        if not key or key in dest:
            continue
        dest[key] = dict(row)
        n += 1
    return n
