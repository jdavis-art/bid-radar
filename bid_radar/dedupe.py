"""Cross-source duplicate linking. Same uid is handled by Store.upsert; this links different sources."""
from __future__ import annotations

import datetime as dt
import itertools
import re

from .store import Store

_MAX_DAYS = 3


def title_key(title: str, agency: str) -> str:
    # Every word of the agency name is stripped, so "City of Aurora: Wild Horse Village" and a
    # bare "Wild Horse Village" from another source collapse to the same key.
    agency_tokens = set(re.findall(r"[a-z0-9]+", (agency or "").lower()))
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return " ".join(w for w in words if w not in agency_tokens)


def _closing(row: dict) -> dt.datetime | None:
    return dt.datetime.fromisoformat(row["closing"]) if row.get("closing") else None


def link_duplicates(store: Store, rows: list[dict]) -> int:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(title_key(r["title"], r.get("agency", "")), []).append(r)
    new_links = 0
    for key, members in groups.items():
        if not key or len(members) < 2:
            continue
        for a, b in itertools.combinations(members, 2):
            if a["source"] == b["source"]:
                continue
            ca, cb = _closing(a), _closing(b)
            if ca is None or cb is None or abs((ca - cb).days) > _MAX_DAYS:
                continue
            before = len(store.duplicates_of(a["uid"]))
            store.link_duplicate(a["uid"], b["uid"], "title+closing")
            if len(store.duplicates_of(a["uid"])) > before:
                new_links += 1
    return new_links
