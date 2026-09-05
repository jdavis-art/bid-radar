"""SAM.gov Opportunities API v2. Public data; needs a free api.data.gov key in SAM_API_KEY.
Docs: https://open.gsa.gov/api/get-opportunities-public-api/
Search 'design-build', never 'modular' alone: federal notices are written that way."""
from __future__ import annotations

import datetime as dt
import time
from typing import Iterator

import requests

from .base import NeedsKey, HEALTH_OK, HEALTH_NEEDS_KEY, HEALTH_DOWN

DEFAULT_URL = "https://api.sam.gov/opportunities/v2/search"


def build_params(api_key: str, keyword: str | None, naics: str | None, ptypes: list[str],
                 posted_from: dt.date, posted_to: dt.date, limit: int, offset: int) -> dict:
    p = {"api_key": api_key, "postedFrom": posted_from.strftime("%m/%d/%Y"),
         "postedTo": posted_to.strftime("%m/%d/%Y"), "ptype": ",".join(ptypes),
         "limit": str(limit), "offset": str(offset)}
    if keyword:
        p["title"] = keyword
    if naics:
        p["ncode"] = naics
    return p


def parse_search(payload: dict) -> list[dict]:
    return list(payload.get("opportunitiesData") or [])


class SamGovSource:
    name = "samgov"

    def __init__(self, cfg: dict, last_run: dt.datetime | dt.date | None):
        self.cfg = cfg
        self.url = cfg.get("base_url", DEFAULT_URL)
        self.api_key = (cfg.get("api_key") or "").strip()
        self.keywords = list(cfg.get("keywords") or [])
        self.naics = [str(n) for n in (cfg.get("naics") or [])]
        self.ptypes = list(cfg.get("ptypes") or ["o", "p", "k"])
        self.lookback_days = int(cfg.get("lookback_days", 7))
        self.limit = int(cfg.get("limit", 1000))
        self.last_run = last_run.date() if isinstance(last_run, dt.datetime) else last_run
        self.log = print

    def healthcheck(self) -> str:
        if not self.api_key:
            return HEALTH_NEEDS_KEY
        try:
            r = requests.get(self.url, params=build_params(self.api_key, "housing", None, ["o"],
                                                            dt.date.today() - dt.timedelta(days=1),
                                                            dt.date.today(), 1, 0), timeout=60)
        except requests.RequestException:
            return HEALTH_DOWN
        return HEALTH_OK if r.status_code == 200 else (HEALTH_NEEDS_KEY if r.status_code in (401, 403) else HEALTH_DOWN)

    def _window(self) -> tuple[dt.date, dt.date]:
        today = dt.date.today()
        start = (self.last_run - dt.timedelta(days=1)) if self.last_run else today - dt.timedelta(days=self.lookback_days)
        return start, today

    def _page(self, keyword: str | None, naics: str | None, offset: int) -> dict:
        start, end = self._window()
        params = build_params(self.api_key, keyword, naics, self.ptypes, start, end, self.limit, offset)
        for attempt in range(3):
            r = requests.get(self.url, params=params, timeout=90)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 + attempt * 5)
                continue
            if r.status_code in (401, 403):
                raise NeedsKey(self.name, f"HTTP {r.status_code} from SAM.gov")
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}

    def sweep(self) -> Iterator[dict]:
        if not self.api_key:
            raise NeedsKey(self.name, "set SAM_API_KEY")
        seen: set[str] = set()
        queries = [(k, None) for k in self.keywords] + [(None, n) for n in self.naics]
        for keyword, naics in queries:
            offset, got = 0, 0
            while True:
                payload = self._page(keyword, naics, offset)
                recs = parse_search(payload)
                for rec in recs:
                    nid = rec.get("noticeId")
                    if nid and nid not in seen:
                        seen.add(nid)
                        got += 1
                        yield rec
                total = int(payload.get("totalRecords") or 0)
                offset += len(recs)
                if not recs or offset >= total:
                    break
                time.sleep(1.0)
            self.log(f"  samgov/{keyword or naics}: {got} new records")
