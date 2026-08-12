"""Per-run JSON report written next to CSV/JSON output."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .output import ensure_parent_dir
from .schema import phone_metrics, utc_now


@dataclass
class RunReport:
    source: str
    started_at: str = ""
    finished_at: str = ""
    duration_s: float = 0.0
    status: str = "ok"
    exit_code: int = 0
    counts: Dict[str, Any] = field(default_factory=dict)
    phones: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    out: str = ""
    formats: List[str] = field(default_factory=list)
    resumed: bool = False
    resumed_from: int = 0

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = utc_now()
        self._t0 = time.monotonic()

    def add_error(self, message: str) -> None:
        self.errors.append(str(message))

    def finish(
        self,
        *,
        records: Optional[List[Dict[str, Any]]] = None,
        status: str = "ok",
        exit_code: int = 0,
        extra_phones: Optional[Dict[str, Any]] = None,
    ) -> "RunReport":
        self.finished_at = utc_now()
        self.duration_s = round(time.monotonic() - getattr(self, "_t0", time.monotonic()), 3)
        self.status = status
        self.exit_code = exit_code
        if records is not None:
            self.counts["records"] = len(records)
            metrics = phone_metrics(records)
            if extra_phones:
                metrics.update(extra_phones)
            self.phones = metrics
        elif extra_phones:
            self.phones.update(extra_phones)
        return self

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("_t0", None)
        return data

    def write(self, path: str) -> str:
        ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            f.write("\n")
        return path

    def write_next_to(self, out_base: str) -> str:
        self.out = out_base
        return self.write(out_base + ".run.json")

    def summary_lines(self) -> List[str]:
        rec = self.counts.get("records", "")
        ph = self.phones.get("with_phone", "")
        lines = [
            f"run: source={self.source} status={self.status} records={rec} "
            f"phones={ph} duration={self.duration_s}s"
        ]
        if self.errors:
            lines.append(f"  errors: {len(self.errors)}")
        if self.out:
            lines.append(f"  report: {self.out}.run.json")
        return lines


def persist_run(
    records,
    out_base: Optional[str],
    *,
    fields,
    formats=None,
    keep_raw: bool = True,
    source: str = "",
    report: Optional["RunReport"] = None,
    extra_phones: Optional[Dict[str, Any]] = None,
    echo: bool = True,
):
    """Write output files + run report. No-op (except finish) when out_base is empty."""
    from .output import dump_records

    recs = list(records)
    if report is None:
        report = RunReport(source=source or "")
    if out_base:
        written = dump_records(
            recs,
            out_base,
            fields=fields,
            formats=formats,
            keep_raw=keep_raw,
            source=source,
        )
        report.formats = list(written)
        report.finish(records=recs, extra_phones=extra_phones)
        report.write_next_to(out_base)
        if echo:
            paths = " / ".join(written.values()) if written else out_base
            print(f"\nDone: {len(recs)} records -> {paths}")
            for line in report.summary_lines():
                print(line)
        return written
    report.finish(records=recs, extra_phones=extra_phones)
    return {}
