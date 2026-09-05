"""Parse a 'Copy as cURL (bash)' file into a Cookie header. Values never appear in logs."""
from __future__ import annotations

import os
import re
from pathlib import Path


class CookieFileMissing(FileNotFoundError):
    pass


class CookieNotFound(ValueError):
    pass


HANDOFF = ("In the logged-in Chrome tab: F12 -> Network -> reload -> right-click any request "
           "for that site -> Copy -> Copy as cURL (bash) -> paste into {path}")


def cookie_header_from_curl_file(path: Path | str) -> str:
    path = Path(os.path.expanduser(str(path)))
    if not path.exists():
        raise CookieFileMissing(f"{path} not found. " + HANDOFF.format(path=path))
    raw = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"-H\s+(['\"])cookie:\s*(.*?)\1", raw, re.I | re.S)
    if m:
        return m.group(2).strip()
    m = re.search(r"(?:-b|--cookie)\s+(['\"])(.*?)\1", raw, re.S)
    if m:
        return m.group(2).strip()
    m = re.search(r"^\s*cookie:\s*(.+)$", raw, re.I | re.M)
    if m:
        return m.group(1).strip()
    stripped = raw.strip()
    if "=" in stripped and ";" in stripped and "\n" not in stripped:
        return stripped
    raise CookieNotFound(f"No Cookie header found in {path}. " + HANDOFF.format(path=path))


def redact(text: str) -> str:
    return re.sub(r"((?:set-)?cookie:\s*).*", r"\1[redacted]", text or "", flags=re.I)
