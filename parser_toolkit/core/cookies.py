"""Load session cookies from CLI / env / file. Never log the cookie value."""
from __future__ import annotations

import os
from typing import Optional, Sequence


def read_cookie_file(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return ""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"cookie file not found: {path}")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # first non-empty, non-comment line
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line
    return text.strip()


def load_cookie(
    *,
    cookie: str = "",
    cookie_file: str = "",
    env_names: Sequence[str] = (),
) -> str:
    """Resolve cookie string. Precedence: --cookie, --cookie-file, env vars."""
    if (cookie or "").strip():
        return cookie.strip()
    file_path = (cookie_file or "").strip() or os.environ.get("COOKIE_FILE", "").strip()
    if file_path:
        return read_cookie_file(file_path)
    for name in env_names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return ""


def cookie_status(cookie: str) -> str:
    """Safe one-word status for logs (never the secret)."""
    return "set" if (cookie or "").strip() else "missing"
