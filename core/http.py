"""Minimal HTTP client with timeout, retries, optional proxy and cookies."""
from __future__ import annotations

import http.cookiejar
import ssl
import time
import urllib.error
import urllib.request
from typing import Dict, Mapping, Optional


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class HttpError(RuntimeError):
    def __init__(self, message: str, *, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class HttpClient:
    """Small urllib wrapper shared by parsers.

    Features:
    - optional HTTP(S) proxy
    - cookie jar (useful for Yandex session)
    - retries with exponential backoff on transient errors
    - configurable timeout / User-Agent
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        retries: int = 4,
        proxy: str = "",
        user_agent: str = DEFAULT_UA,
        sleep_base: float = 0.6,
    ) -> None:
        self.timeout = timeout
        self.retries = max(1, retries)
        self.proxy = (proxy or "").strip()
        self.user_agent = user_agent
        self.sleep_base = sleep_base
        self.cookie_jar = http.cookiejar.CookieJar()
        self._ssl = ssl.create_default_context()
        self._opener = self._build_opener()

    def _build_opener(self) -> urllib.request.OpenerDirector:
        handlers = [
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            urllib.request.HTTPSHandler(context=self._ssl),
        ]
        if self.proxy:
            handlers.insert(
                0,
                urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}),
            )
        return urllib.request.build_opener(*handlers)

    def get(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        accept: str = "*/*",
        referer: str = "",
    ) -> str:
        last_err: Optional[BaseException] = None
        last_status: Optional[int] = None
        last_body = ""
        for attempt in range(1, self.retries + 1):
            try:
                return self._request(
                    url,
                    headers=headers,
                    accept=accept,
                    referer=referer,
                )
            except HttpError as e:
                last_err = e
                last_status = e.status
                last_body = e.body or ""
                # Hard client errors (except 429) — don't retry endlessly.
                if e.status in (400, 401, 403, 404):
                    raise
                if e.status == 429 or e.status is None or (e.status and e.status >= 500):
                    # 429: back off more aggressively (rate limit).
                    delay = self.sleep_base * attempt * (3.0 if e.status == 429 else 1.5)
                    time.sleep(min(delay, 20.0))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
                time.sleep(min(self.sleep_base * attempt * 1.5, 10.0))
        raise HttpError(
            f"GET failed after {self.retries} attempts: {last_err}",
            status=last_status,
            body=last_body,
        )

    def _request(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]],
        accept: str,
        referer: str,
    ) -> str:
        h: Dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }
        if referer:
            h["Referer"] = referer
        if headers:
            h.update(dict(headers))
        req = urllib.request.Request(url, headers=h)
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "ignore")
            except Exception:
                pass
            raise HttpError(f"HTTP {e.code} for {url}", status=e.code, body=body) from e
