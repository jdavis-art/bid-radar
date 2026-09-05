"""The one record every source becomes."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")
_DATETIME_FORMATS = ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M", "%Y-%m-%dT%H:%M:%S")


def normalize_state(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if t.upper() in STATES:
        return STATES[t.upper()]
    return t


def parse_date(text: str | None) -> dt.date | None:
    t = (text or "").strip()
    if not t:
        return None
    head = t[:10]
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(head, fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return None


def parse_datetime(text: str | None) -> dt.datetime | None:
    t = (text or "").strip()
    if not t:
        return None
    # Drop a trailing timezone token such as "EDT" or "MST"; times are kept naive.
    t = re.sub(r"\s+[A-Z]{2,4}$", "", t)
    if "T" in t:
        base = t[:19]
        try:
            return dt.datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    for fmt in _DATETIME_FORMATS:
        try:
            return dt.datetime.strptime(t, fmt)
        except ValueError:
            continue
    d = parse_date(t)
    return dt.datetime(d.year, d.month, d.day) if d else None


@dataclasses.dataclass
class Solicitation:
    uid: str
    source: str
    source_id: str
    title: str
    agency: str = ""
    location: str = ""
    bid_type: str = ""
    published: dt.date | None = None
    closing: dt.datetime | None = None
    url: str = ""
    blurb: str = ""
    mandatory_prebid: bool = False
    extra: dict = dataclasses.field(default_factory=dict)

    def to_row(self) -> dict:
        row = dataclasses.asdict(self)
        row["published"] = self.published.isoformat() if self.published else None
        row["closing"] = self.closing.isoformat(timespec="minutes") if self.closing else None
        row["mandatory_prebid"] = int(self.mandatory_prebid)
        row["extra"] = json.dumps(self.extra, sort_keys=True)
        return row

    @classmethod
    def from_row(cls, row: dict) -> "Solicitation":
        return cls(
            uid=row["uid"], source=row["source"], source_id=row["source_id"], title=row["title"],
            agency=row.get("agency") or "", location=row.get("location") or "",
            bid_type=row.get("bid_type") or "",
            published=dt.date.fromisoformat(row["published"]) if row.get("published") else None,
            closing=dt.datetime.fromisoformat(row["closing"]) if row.get("closing") else None,
            url=row.get("url") or "", blurb=row.get("blurb") or "",
            mandatory_prebid=bool(row.get("mandatory_prebid")),
            extra=json.loads(row["extra"]) if isinstance(row.get("extra"), str) else (row.get("extra") or {}),
        )
