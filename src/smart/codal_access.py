"""User-assisted Codal verification in the acquisition client's own session.

Only the user supplies the code. Cookies remain in memory in this process;
browser credentials and browser cookies are never imported or exported.
"""
from __future__ import annotations

import base64
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Iterator
from urllib.parse import urlsplit

import httpx

from .codal import CodalHistoricalProvider
from .financial_history import HistoricalDataRepository, normalize, source_url

SESSION_TTL = 1800
MAX_SESSIONS = 32


@dataclass
class CodalAccess:
    provider: CodalHistoricalProvider
    clients: tuple[httpx.Client, ...]
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    touched: float = field(default_factory=time.monotonic)
    users: int = 0
    mutex: Lock = field(default_factory=Lock)

    def info(self) -> dict[str, object]:
        if not self.provider.challenge_url:
            return {"status": "NOT_REQUIRED"}
        return {"status": "WAITING_FOR_USER" if self.provider.challenge_supported else "UNSUPPORTED_CHALLENGE",
                "session_id": self.token, "source_url": self.provider.challenge_url,
                "expires_in_seconds": max(0, int(SESSION_TTL - (time.monotonic() - self.touched)))}

    def _post(self, token: str, action: str, payload: dict[str, str]) -> object:
        provider = self.provider
        if not secrets.compare_digest(token, self.token) or not provider.challenge_url:
            raise ValueError("Verification session expired; resume discovery to obtain a new challenge")
        if not provider.challenge_supported or not source_url(provider.challenge_url):
            raise ValueError("This verification layout requires assistance on the official website")
        parts = urlsplit(provider.challenge_url)
        url = f"{parts.scheme}://{parts.netloc}/ReportsCaptcha.aspx/{action}"
        # No transport switching or automatic retries for a session-bound POST.
        response = provider.client.post(url, json=payload, timeout=12,
                                        headers={"Referer": provider.challenge_url})
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("Unexpected verification redirect; resume discovery")
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Invalid verification response")
        return result.get("d")

    def image(self, token: str) -> dict[str, str]:
        value = self._post(token, "GetCaptchaImage", {})
        if not isinstance(value, str) or len(value) > 1_000_000:
            raise ValueError("Invalid verification image")
        header, separator, encoded = value.partition(",")
        if not separator or header not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/gif;base64"}:
            raise ValueError("Unsupported verification image")
        base64.b64decode(encoded, validate=True)
        return {"image": value}

    def verify(self, token: str, code: str) -> bool:
        code = code.strip()
        if not 1 <= len(code) <= 10 or any(ord(c) < 32 for c in code):
            raise ValueError("Enter the verification code shown in the image")
        accepted = self._post(token, "VerifyCaptcha", {"code": code}) is True
        if accepted:
            self.provider.challenge_url = None
            self.provider.challenge_supported = False
            self.token = secrets.token_urlsafe(32)
        return accepted


_sessions: dict[tuple[str, str], CodalAccess] = {}
_registry_lock = Lock()


def _create(repo: HistoricalDataRepository) -> CodalAccess:
    primary = httpx.Client(timeout=12, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 SMART"})
    direct = httpx.Client(timeout=12, trust_env=False, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 SMART"})
    return CodalAccess(CodalHistoricalProvider(primary, repo, direct), (primary, direct))


@contextmanager
def access_session(repo: HistoricalDataRepository, symbol: str, *, create: bool = True) -> Iterator[CodalAccess | None]:
    key = (str(repo.path.resolve()), normalize(symbol))
    with _registry_lock:
        for old_key, access in list(_sessions.items()):
            if access.users == 0 and time.monotonic() - access.touched >= SESSION_TTL:
                for client in access.clients:
                    client.close()
                del _sessions[old_key]
        access = _sessions.get(key)
        if access is None and create:
            if len(_sessions) >= MAX_SESSIONS:
                raise ValueError("Too many active Codal sessions; retry after an idle session expires")
            access = _sessions[key] = _create(repo)
        if access is not None:
            access.users += 1
    if access is None:
        yield None
        return
    try:
        with access.mutex:
            yield access
    finally:
        with _registry_lock:
            access.touched = time.monotonic()
            access.users -= 1


def assistance_info(repo: HistoricalDataRepository, symbol: str) -> dict[str, object]:
    with access_session(repo, symbol, create=False) as access:
        if access is not None and access.provider.challenge_url:
            return access.info()
    if repo.state(symbol, "KODAL_COMPANY").get("action_required"):
        return {"status": "SESSION_EXPIRED"}
    retry_at = repo.state("__SOURCE__", "KODAL_HTTP").get("retry_at")
    if retry_at and datetime.fromisoformat(retry_at) > datetime.now(timezone.utc):
        return {"status": "RATE_LIMITED", "retry_at": retry_at}
    return {"status": "NOT_REQUIRED"}
