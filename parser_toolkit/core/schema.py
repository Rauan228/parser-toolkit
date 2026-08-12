"""Unified record shape shared by all five parsers.

Source-specific columns stay on the dict. These helpers only *fill* common
keys so CSV/JSON/JSONL consumers can rely on them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .models import normalize_phone


UNIFIED_FIELDS = [
    "source",
    "id",
    "title",
    "phone",
    "phones",
    "city",
    "url",
    "price",
    "currency",
    "latitude",
    "longitude",
    "scraped_at",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_list(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            if item is None or item == "":
                continue
            out.append(str(item))
        return out
    return [str(value)]


def record_id(row: Mapping[str, Any]) -> str:
    for key in ("id", "listing_id", "place_id", "firm_id", "org_id"):
        val = row.get(key)
        if val not in (None, ""):
            return str(val)
    phone = row.get("phone")
    if phone:
        return str(phone)
    url = row.get("url")
    if url:
        return str(url)
    return ""


def apply_schema(
    row: Mapping[str, Any],
    *,
    source: str = "",
    scraped_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a copy with unified keys filled. Extra keys are kept."""
    out: Dict[str, Any] = dict(row)
    out["source"] = out.get("source") or source or ""

    rid = record_id(out)
    if rid:
        out["id"] = rid

    title = out.get("title") or out.get("name") or ""
    out["title"] = title
    if not out.get("name"):
        out["name"] = title

    phones = _as_list(out.get("phones"))
    if not phones:
        phones = [p for p in (out.get("phone"), out.get("phone2")) if p]
    elif out.get("phone"):
        phones = [out.get("phone"), *phones]
    normed: List[str] = []
    seen = set()
    for raw in phones:
        n = normalize_phone(raw) or str(raw)
        if n and n not in seen:
            seen.add(n)
            normed.append(n)
    out["phones"] = normed
    if normed:
        out["phone"] = normed[0]
        if len(normed) > 1:
            out["phone2"] = out.get("phone2") and (normalize_phone(out["phone2"]) or out["phone2"]) or normed[1]

    if out.get("price") in (None, ""):
        if out.get("price_kzt") not in (None, ""):
            out["price"] = out["price_kzt"]
            out.setdefault("currency", "KZT")
        elif out.get("price_rub") not in (None, ""):
            out["price"] = out["price_rub"]
            out.setdefault("currency", "RUB")
    out.setdefault("currency", out.get("currency") or "")

    out.setdefault("city", out.get("city") or "")
    out.setdefault("url", out.get("url") or "")
    out.setdefault("latitude", out.get("latitude") if out.get("latitude") is not None else "")
    out.setdefault("longitude", out.get("longitude") if out.get("longitude") is not None else "")
    out.setdefault("scraped_at", scraped_at or utc_now())
    return out


def apply_schema_many(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str = "",
    scraped_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    stamp = scraped_at or utc_now()
    return [apply_schema(r, source=source, scraped_at=stamp) for r in rows]


def extend_fields(source_fields: Sequence[str]) -> List[str]:
    """Keep source column order; append any missing unified fields."""
    out = list(source_fields)
    have = set(out)
    for key in UNIFIED_FIELDS:
        if key not in have:
            out.append(key)
            have.add(key)
    return out


def phone_metrics(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    total = len(rows)
    with_phone = sum(1 for r in rows if r.get("phone"))
    with_preview = sum(1 for r in rows if r.get("phone_preview"))
    phones_ok = sum(1 for r in rows if r.get("phone"))
    return {
        "total": total,
        "with_phone": with_phone,
        "with_preview": with_preview,
        "without_phone": total - with_phone,
        "phone_rate": round(with_phone / total, 4) if total else 0.0,
        "phones_ok": phones_ok,
    }
