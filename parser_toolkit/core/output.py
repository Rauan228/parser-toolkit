"""CSV/JSON writers for normalized places."""
from __future__ import annotations

import csv
import json
import os
from typing import Dict, Iterable, List, Optional, Sequence

from .models import DIRECTORY_CSV_FIELDS, Place


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


def dump_places(
    places: Iterable[Place],
    out_base: str,
    *,
    fields: Optional[Sequence[str]] = None,
    keep_raw: bool = True,
) -> None:
    """Write `{out_base}.json` and `{out_base}.csv` (UTF-8 BOM for Excel)."""
    fields_list: List[str] = list(fields or DIRECTORY_CSV_FIELDS)
    place_list = list(places)
    rows: List[Dict] = [p.to_dict(keep_raw=keep_raw) for p in place_list]

    json_path = out_base + ".json"
    csv_path = out_base + ".csv"
    ensure_parent_dir(json_path)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(fields_list)
        for r in rows:
            w.writerow([r.get(k, "") for k in fields_list])
