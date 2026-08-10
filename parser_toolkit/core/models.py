"""Unified place model shared across directory parsers (2GIS, Yandex Maps)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def normalize_phone(value: Any) -> Optional[str]:
    """Normalize phone to +E.164-ish form for RU/KZ/BY and keep others."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value") or value.get("number") or value.get("text") or ""
    raw = str(value).strip()
    if not raw:
        return None
    # drop extension notes: ", доб. 3"
    raw = re.split(r",\s*доб", raw, maxsplit=1, flags=re.I)[0]
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    if raw.startswith("+"):
        return "+" + digits
    return "+" + digits if digits else None


@dataclass
class Place:
    """Normalized organization record.

    Flat convenience fields (`phone`, `phone2`, …) stay for CSV compatibility
    with earlier toolkit versions. Prefer `phones` / structured fields in JSON.
    """

    source: str
    name: str = ""
    category: str = ""
    phones: List[str] = field(default_factory=list)
    address: str = ""
    city: str = ""
    latitude: Any = ""
    longitude: Any = ""
    rating: Any = ""
    reviews_count: Any = ""
    website: str = ""
    url: str = ""
    # legacy flat fields
    phone: str = ""
    phone2: str = ""
    email: str = ""
    # source-specific ids / extras
    place_id: str = ""
    org_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw: Optional[Dict[str, Any]] = None

    def finalize(self) -> "Place":
        """Fill derived flat fields from lists."""
        if self.phones:
            self.phone = self.phone or self.phones[0]
            if len(self.phones) > 1:
                self.phone2 = self.phone2 or self.phones[1]
        elif self.phone:
            self.phones = [self.phone]
            if self.phone2:
                self.phones.append(self.phone2)
        return self

    def to_dict(self, *, keep_raw: bool = True) -> Dict[str, Any]:
        self.finalize()
        data = asdict(self)
        if not keep_raw:
            data.pop("raw", None)
        return data


# Common CSV columns for directory parsers (order matters for stable files).
DIRECTORY_CSV_FIELDS = [
    "source",
    "phone",
    "phone2",
    "name",
    "category",
    "city",
    "address",
    "rating",
    "reviews_count",
    "latitude",
    "longitude",
    "website",
    "email",
    "url",
    "place_id",
    "org_id",
]


def place_to_csv_row(place: Place, fields: Optional[List[str]] = None) -> List[Any]:
    fields = fields or DIRECTORY_CSV_FIELDS
    d = place.to_dict(keep_raw=False)
    return [d.get(f, "") for f in fields]
