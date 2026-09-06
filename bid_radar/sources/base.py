"""What every source adapter looks like to the CLI."""
from __future__ import annotations

from typing import Iterator, Protocol

HEALTH_OK = "ok"
HEALTH_NEEDS_COOKIE = "needs_cookie"
HEALTH_NEEDS_KEY = "needs_key"
HEALTH_DOWN = "down"
HEALTH_KEY_PRESENT = "key present"   # key configured, API not probed
HEALTH_RATE_LIMITED = "rate_limited"


class NeedsCookie(RuntimeError):
    def __init__(self, source: str, detail: str = ""):
        super().__init__(f"{source}: session cookie missing or expired. {detail}".strip())
        self.source = source


class NeedsKey(RuntimeError):
    def __init__(self, source: str, detail: str = ""):
        super().__init__(f"{source}: API key missing. {detail}".strip())
        self.source = source


class RateLimited(RuntimeError):
    """The source refused a request on quota. Terminal for this run: no retries, no further queries."""

    def __init__(self, source: str, detail: str = ""):
        super().__init__(f"{source}: rate limited. {detail}".strip())
        self.source = source


class Source(Protocol):
    name: str

    def healthcheck(self) -> str: ...

    def sweep(self) -> Iterator[dict]: ...
