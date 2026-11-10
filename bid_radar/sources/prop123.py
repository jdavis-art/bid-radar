"""Colorado Prop 123 (Affordable Housing Financing Fund) application and selection lists.

The fund's WordPress site posts each round's applicant and selection list as a PDF. The media API
(/wp-json/wp/v2/media?search=...) lists every one with its upload date, so no browser is needed.
Each PDF row carries sponsor, project, city, dollars, units, purpose and a contact, which makes every
row a lead: cheap capital in hand, a builder not yet chosen. These are awards, not bids, so a row gets
a synthetic closing date (posted + call_window_days) and ages out of the open digest after that."""
from __future__ import annotations

import datetime as dt
import io
import re
from typing import Iterator

import requests

from .base import HEALTH_OK, HEALTH_DOWN

DEFAULT_BASE = "https://coloradoaffordablehousingfinancingfund.com"
_UA = {"User-Agent": "Mozilla/5.0 (bid-radar)"}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\(?\d{3}\)?[-. ]\d{3}-\d{4}")
_MONEY = re.compile(r"\$\s*\d{1,3}(?:\s?,\d{3})*")  # the PDFs sometimes print "$7 ,000,000"
_HEADER = re.compile(r"^(?P<label>.+?)\s*-\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*$", re.M)


def _money(text: str) -> int:
    return int(re.sub(r"[^\d]", "", text))


def parse_list(text: str) -> tuple[str, dt.date | None, list[dict]]:
    """PDF text -> (list label, list date, rows). Rows are split on the contact email that ends each one."""
    m = _HEADER.search(text)
    label = m.group("label").strip() if m else ""
    date = dt.datetime.strptime(m.group("date"), "%m/%d/%Y").date() if m else None
    # The column header ends with "Email"; rows start after it.
    head = re.search(r"\bPhone\s+Email\s*\n", text)
    body = text[head.end():] if head else text
    rows, pos = [], 0
    for em in _EMAIL.finditer(body):
        chunk = " ".join(body[pos:em.start()].split())
        pos = em.end()
        monies = list(_MONEY.finditer(chunk))
        if not monies:
            continue
        prefix = chunk[:monies[0].start()].strip()
        tail = chunk[monies[-1].end():].strip()
        phones = list(_PHONE.finditer(tail))
        before_phone = tail[:phones[-1].start()].strip() if phones else tail
        um = re.match(r"(\d[\d,]*)\s+(.*)$", before_phone)
        units = int(um.group(1).replace(",", "")) if um else None
        rest = um.group(2).split() if um else before_phone.split()
        contact = " ".join(rest[-2:]) if len(rest) >= 2 else " ".join(rest)
        purpose = " ".join(rest[:-2]) if len(rest) > 2 else ""
        amounts = [_money(x.group(0)) for x in monies]
        rows.append({
            "who": prefix, "requested": amounts[0], "awarded": amounts[1] if len(amounts) > 1 else None,
            "units": units, "purpose": purpose, "contact": contact,
            "phone": phones[-1].group(0) if phones else "", "email": em.group(0),
        })
    return label, date, rows


class Prop123Source:
    name = "prop123"

    def __init__(self, cfg: dict):
        self.base = (cfg.get("base_url") or DEFAULT_BASE).rstrip("/")
        self.searches = list(cfg.get("searches") or ["Selections", "Applications"])
        self.min_date = dt.date.fromisoformat(str(cfg.get("min_date") or "2025-07-01"))
        self.window = int(cfg.get("call_window_days", 90))
        self.skipped: list[str] = []
        self.log = print

    def healthcheck(self) -> str:
        try:
            r = requests.get(f"{self.base}/wp-json/wp/v2/media", params={"per_page": 1}, headers=_UA, timeout=30)
        except requests.RequestException:
            return HEALTH_DOWN
        return HEALTH_OK if r.status_code == 200 else HEALTH_DOWN

    def _media(self) -> list[dict]:
        seen, out = set(), []
        for term in self.searches:
            r = requests.get(f"{self.base}/wp-json/wp/v2/media", headers=_UA, timeout=60,
                             params={"search": term, "per_page": 100, "_fields": "id,date,source_url,mime_type"})
            r.raise_for_status()
            for m in r.json():
                if m.get("mime_type") == "application/pdf" and m["source_url"] not in seen:
                    seen.add(m["source_url"])
                    out.append(m)
        return out

    def sweep(self) -> Iterator[dict]:
        from pypdf import PdfReader  # imported here so the other sources run without it
        for m in self._media():
            posted = dt.date.fromisoformat(m["date"][:10])
            if posted < self.min_date:
                continue
            url = m["source_url"]
            slug = url.rsplit("/", 1)[-1].removesuffix(".pdf")
            r = requests.get(url, headers=_UA, timeout=90)
            r.raise_for_status()
            try:
                text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)
            except Exception as e:  # noqa: BLE001 - one unreadable list must not hide the others
                self.skipped.append(slug)
                self.log(f"  prop123/{slug}: unreadable ({type(e).__name__}), skipped")
                continue
            label, list_date, rows = parse_list(text)
            self.log(f"  prop123/{slug}: {len(rows)} rows")
            for row in rows:
                yield {**row, "list_label": label or slug, "list_date": (list_date or posted).isoformat(),
                       "posted": posted.isoformat(), "closing": (posted + dt.timedelta(days=self.window)).isoformat(),
                       "slug": slug, "url": url}
