"""CSV / JSON / JSONL writers for normalized records."""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

from .models import DIRECTORY_CSV_FIELDS, Place

ALL_FORMATS = ("csv", "json", "jsonl")
DEFAULT_FORMATS = ("csv", "json")


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


def parse_formats(value: Optional[Union[str, Sequence[str]]] = None) -> List[str]:
    if value is None or value == "":
        raw = list(DEFAULT_FORMATS)
    elif isinstance(value, str):
        raw = [p.strip().lower() for p in value.replace(" ", ",").split(",") if p.strip()]
    else:
        raw = [str(p).strip().lower() for p in value if str(p).strip()]
    out: List[str] = []
    for item in raw:
        if item in ALL_FORMATS and item not in out:
            out.append(item)
    if not out:
        raise ValueError(f"no valid formats in {value!r}; use csv,json,jsonl")
    return out


def _strip_raw(row: Mapping[str, Any]) -> Dict[str, Any]:
    data = dict(row)
    data.pop("raw", None)
    data.pop("params", None)
    return data


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(v) for v in value if v not in (None, ""))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def dump_records(
    records: Iterable[Mapping[str, Any]],
    out_base: str,
    *,
    fields: Optional[Sequence[str]] = None,
    formats: Optional[Union[str, Sequence[str]]] = None,
    keep_raw: bool = True,
    source: str = "",
) -> Dict[str, str]:
    """Write requested formats under `out_base` (no extension).

    Returns ``{format: path}`` for files written.
    """
    from .schema import apply_schema_many, extend_fields

    rows = apply_schema_many(records, source=source)
    if not keep_raw:
        rows = [_strip_raw(r) for r in rows]
    fields_list: List[str] = extend_fields(fields or DIRECTORY_CSV_FIELDS)
    wanted = parse_formats(formats)
    written: Dict[str, str] = {}
    ensure_parent_dir(out_base + ".json")

    if "json" in wanted:
        path = out_base + ".json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
            f.write("\n")
        written["json"] = path

    if "jsonl" in wanted:
        path = out_base + ".jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        written["jsonl"] = path

    if "csv" in wanted:
        path = out_base + ".csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(fields_list)
            for row in rows:
                w.writerow([_cell(row.get(k, "")) for k in fields_list])
        written["csv"] = path

    return written


def dump_places(
    places: Iterable[Place],
    out_base: str,
    *,
    fields: Optional[Sequence[str]] = None,
    keep_raw: bool = True,
    formats: Optional[Union[str, Sequence[str]]] = None,
    source: str = "",
) -> Dict[str, str]:
    """Write Place objects. Same files as `dump_records`."""
    rows = [p.to_dict(keep_raw=keep_raw) for p in places]
    return dump_records(
        rows,
        out_base,
        fields=fields,
        formats=formats,
        keep_raw=keep_raw,
        source=source,
    )
