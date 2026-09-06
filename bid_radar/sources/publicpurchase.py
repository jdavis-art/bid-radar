"""PublicPurchase.com adapter. Verified 2026-09-04: region -> agency list is a plain GET
(/gems/global/home/getAgenciesByRegion?region=XX); each agency's list is /gems/<slug>/global/home/nationalBidList.
Without a vendor cookie every agency answers "No bids at this time", so this adapter raises NeedsCookie
from the sweep (the run records needs_cookie) rather than pretending the market is empty."""
from __future__ import annotations

import re
import time
from typing import Iterator

import requests
from lxml import html as lxhtml

from ..cookies import cookie_header_from_curl_file, CookieFileMissing, CookieNotFound
from .base import NeedsCookie, HEALTH_OK, HEALTH_NEEDS_COOKIE, HEALTH_DOWN

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def parse_agencies(payload, agency_pick: re.Pattern) -> list[dict]:
    out = []
    for a in payload or []:
        name = a.get("agencyName") or a.get("name") or ""
        slug = a.get("agencyId") or a.get("id") or ""
        if slug and agency_pick.search(name):
            out.append({"slug": str(slug), "name": name, "state": a.get("state", "")})
    return out


def parse_bid_list(html_text: str, agency: dict, base_url: str) -> list[dict]:
    d = lxhtml.fromstring(html_text)
    rows = []
    for tr in d.xpath("//tr[contains(@class,'bidRow')]|//tr[.//a[contains(@href,'bidId=')]]"):
        a = tr.xpath(".//a[contains(@href,'bidId=')]")
        if not a:
            continue
        a = a[0]
        m = re.search(r"bidId=(\d+)", a.get("href") or "")
        if not m:
            continue
        t = re.sub(r"\s+", " ", tr.text_content()).strip()
        pub = re.search(r"Published\s*([\d/]+)", t)
        clo = re.search(r"Closes?\s*([\d/]+(?:\s+[\d:]+\s*[AP]M(?:\s*[A-Z]{2,4})?)?)", t)
        rows.append({
            "id": m.group(1), "title": re.sub(r"\s+", " ", a.text_content()).strip(),
            "agency": agency["name"], "agency_slug": agency["slug"], "location": agency.get("state", ""),
            "published": pub.group(1) if pub else "", "closing": clo.group(1).strip() if clo else "",
            "url": base_url + a.get("href"), "blurb": "",
        })
    return rows


class PublicPurchaseSource:
    name = "publicpurchase"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.base = cfg.get("base_url", "https://www.publicpurchase.com").rstrip("/")
        self.regions = list(cfg.get("regions") or ["CO"])
        self.agency_pick = re.compile(cfg.get("agency_pick") or "hous", re.I)
        self.bid_pick = re.compile(cfg.get("bid_pick") or "housing", re.I)
        self.pause = float(cfg.get("pause_seconds", 1.0))
        self._session = None
        self._cookie_error = ""
        self.log = print

    def _s(self) -> requests.Session | None:
        if self._session is None:
            try:
                cookie = cookie_header_from_curl_file(self.cfg.get("cookie_file", "~/.publicpurchase-curl.txt"))
            except (CookieFileMissing, CookieNotFound) as e:
                self._cookie_error = str(e)
                return None
            s = requests.Session()
            s.headers.update({"User-Agent": UA, "Cookie": cookie, "Accept": "*/*"})
            self._session = s
        return self._session

    def healthcheck(self) -> str:
        s = self._s()
        if s is None:
            return HEALTH_NEEDS_COOKIE
        try:
            r = s.get(f"{self.base}/gems/global/home/getAgenciesByRegion", params={"region": self.regions[0]}, timeout=60)
        except requests.RequestException:
            return HEALTH_DOWN
        if r.status_code != 200 or "login" in r.url:
            return HEALTH_NEEDS_COOKIE
        return HEALTH_OK

    def sweep(self) -> Iterator[dict]:
        s = self._s()
        if s is None:
            raise NeedsCookie(self.name, self._cookie_error or "no vendor cookie")
        for region in self.regions:
            r = s.get(f"{self.base}/gems/global/home/getAgenciesByRegion", params={"region": region}, timeout=60)
            if r.status_code != 200:
                continue
            try:
                payload = r.json()
            except ValueError:
                continue
            for agency in parse_agencies(payload, self.agency_pick):
                rb = s.get(f"{self.base}/gems/{agency['slug']}/global/home/nationalBidList", timeout=60)
                time.sleep(self.pause)
                if rb.status_code != 200 or "No bids at this time" in rb.text:
                    continue
                for row in parse_bid_list(rb.text, agency, self.base):
                    if self.bid_pick.search(row["title"]):
                        yield row
