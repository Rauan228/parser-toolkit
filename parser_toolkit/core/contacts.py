"""Public contacts with verbatim labels and provenance; no role inference."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List
from urllib.parse import unquote, urlsplit

from .models import normalize_phone

CONTACT_FIELDS = ["emails", "websites", "whatsapp", "telegram", "viber", "contacts"]
MESSENGERS = {"whatsapp", "telegram", "viber"}
SOCIAL = {"instagram", "facebook", "vkontakte", "vk", "youtube", "twitter", "odnoklassniki", "social"}


def unwrap_link(value: str) -> str:
    value = str(value or "").strip()
    if (urlsplit(value).hostname or "").startswith("link.2gis.") and "?" in value:
        value = value.split("?", 1)[1]
        if value.startswith(("http%3A", "https%3A", "http%3a", "https%3a")):
            value = unquote(value)
    return value


def link_type(value: str, fallback: str = "website") -> str:
    p = urlsplit(value)
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for kind, hosts in {
        "whatsapp": ("wa.me", "whatsapp.com"),
        "telegram": ("t.me", "telegram.me", "telegram.org"),
        "viber": ("viber.com",),
        "social": ("vk.com", "instagram.com", "facebook.com", "ok.ru", "youtube.com", "twitter.com", "x.com"),
    }.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return kind
    if p.scheme in ("tg", "viber", "whatsapp"):
        return {"tg": "telegram"}.get(p.scheme, p.scheme)
    return fallback


def unique_contacts(contacts: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    result, seen = [], set()
    for c in contacts:
        if not c.get("value"):
            continue
        key = tuple(str(c.get(k) or "") for k in ("type", "value", "label", "extension", "source_url"))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(zip(("type", "value", "label", "extension", "source_url"), key)))
    return result


def make_contact(kind: str, value: Any, *, label: str = "", extension: str = "", source_url: str = "") -> Dict[str, str]:
    value = str(value or "").strip()
    kind = kind.lower()
    if kind == "phone":
        match = re.search(r"(?:доб\.?|ext\.?|;ext=)\s*[:=]?\s*(\d+)", value, re.I)
        if match:
            extension = extension or match.group(1)
            value = value[:match.start()].rstrip(" ,;")
        value = normalize_phone(value) or ""
    elif kind == "email":
        value = unquote(re.sub(r"^mailto:", "", value, flags=re.I).split("?", 1)[0]).strip().lower()
    else:
        value = unwrap_link(value)
        kind = link_type(value, kind)
    return {"type": kind, "value": value, "label": str(label or "").strip(),
            "extension": str(extension or ""), "source_url": source_url}


def _label(obj: Dict[str, Any]) -> str:
    return " · ".join(dict.fromkeys(str(obj[k]).strip() for k in
                     ("comment", "name", "description", "label", "caption", "info", "department", "contact_person")
                     if isinstance(obj.get(k), str) and obj[k].strip()))


def twogis_contacts(item: Dict[str, Any], source_url: str) -> List[Dict[str, str]]:
    result = []
    for group in item.get("contact_groups") or []:
        if not isinstance(group, dict):
            continue
        for c in group.get("contacts") or []:
            if not isinstance(c, dict):
                continue
            kind = str(c.get("type") or "").lower()
            if not kind:
                continue
            value = c.get("value") or c.get("text") or ""
            if kind not in ("phone", "email"):
                value = c.get("url") or value
            own_label = _label(c)
            if not own_label and kind == "phone":
                text = str(c.get("text") or "")
                # Some cards append the department to the rendered phone text.
                if re.search(r"[а-яёa-z]", re.sub(r"(?:доб\.?|ext\.?)\s*\d+", "", text, flags=re.I), re.I):
                    own_label = text
            label = " · ".join(dict.fromkeys(x for x in (_label(group), own_label) if x))
            result.append(make_contact(kind, value, label=label,
                          extension=c.get("extension") or "", source_url=source_url))
    return unique_contacts(result)


def yandex_contacts(item: Dict[str, Any], source_url: str) -> List[Dict[str, str]]:
    result = []
    for kind, field in (("phone", "phones"), ("email", "emails"), ("website", "urls")):
        values = item.get(field) or []
        if isinstance(values, (str, dict)):
            values = [values]
        for c in values:
            if isinstance(c, dict):
                value = c.get("value") or c.get("number") or c.get("url") or c.get("href") or c.get("text")
                result.append(make_contact(kind, value, label=_label(c),
                              extension=c.get("extension") or "", source_url=source_url))
            else:
                result.append(make_contact(kind, c, source_url=source_url))
    for field in ("socialLinks", "businessLinks"):
        for c in item.get(field) or []:
            if isinstance(c, dict):
                result.append(make_contact(c.get("type") or "social", c.get("href") or c.get("url"),
                              label=_label(c), source_url=source_url))
    return unique_contacts(result)


def contact_summary(contacts: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    contacts = unique_contacts(contacts)
    def values(*kinds):
        return list(dict.fromkeys(c["value"] for c in contacts if c["type"] in kinds))
    phones, emails, websites = values("phone"), values("email"), values("website")
    return {"contacts": contacts, "phones": phones, "phone": phones[0] if phones else "",
            "phone2": phones[1] if len(phones) > 1 else "", "emails": emails,
            "email": emails[0] if emails else "", "websites": websites,
            "website": websites[0] if websites else "",
            **{k: values(k) for k in ("whatsapp", "telegram", "viber")}}
