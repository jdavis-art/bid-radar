"""BidNet Direct adapter. Verified mechanics (2026-09-04):
- explicit pageNumber/pageSize/selectedSavedSearch on every request (the server remembers pageNumber);
- rows are tr.mets-table-row; strip <script> before reading text;
- native abstracts live at /private/solicitations/<id>/abstract (GET without the query string);
- aggregated notices live at /private/supplier/solicitations/notice/<id>/abstract;
- federal notices 404 everywhere here (read them from SAM.gov)."""
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


class FederalNotice(Exception):
    pass


def strip_scripts(d):
    for el in d.xpath("//script|//style"):
        el.getparent().remove(el)
    return d


def text(el) -> str:
    return re.sub(r"\s+", " ", el.text_content()).strip() if el is not None else ""


def first(tr, cls) -> str:
    hit = tr.xpath(f".//*[contains(@class,'{cls}')]")
    return text(hit[0]) if hit else ""


def parse_rows(d, base_url: str = "https://www.bidnetdirect.com") -> list[dict]:
    rows = []
    for tr in d.xpath("//tr[contains(@class,'mets-table-row')]"):
        a = tr.xpath(".//*[contains(@class,'solicitationTitle')]//a")
        if not a:
            continue
        a = a[0]
        href = (a.get("href") or "").split("?")[0]
        sid = href.rstrip("/").split("/")[-1]
        t = text(tr)
        rows.append({
            "id": sid,
            "title": text(a),
            "agency": first(tr, "buyerIdentification"),
            "bid_type": first(tr, "searchContentGroupName"),
            "closing": first(tr, "dateValue"),
            "location": first(tr, "regionValue"),
            "published": first(tr, "publicationDate").replace("Published Date", "").strip(),
            "blurb": first(tr, "solicitationDescription")[:300],
            "mandatory_prebid": "Mandatory Pre-Bid" in t,
            "url": base_url + f"/private/solicitations/{sid}/abstract",
        })
    return rows


def result_count(d):
    body = text(d.body)
    m = re.search(r"(\d+)\s*-\s*(\d+)\s*of\s*(\d+)\s*results", body)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d+)\s*Total Bids", body)
    return (1, 0, int(m.group(1))) if m else None


def saved_searches(d) -> list[tuple[str, str]]:
    out = []
    for o in d.xpath("//select[@id='selectedSavedSearch']/option"):
        val = (o.get("value") or "").strip()
        name = text(o)
        if val and val not in ("", "0") and not name.startswith("-"):
            out.append((name, val))
    return out


def parse_abstract(d):
    body = text(d.body)
    title = text(d.xpath("//h1")[0]) if d.xpath("//h1") else (d.findtext(".//title") or "")
    fields = {}
    for label in ("Solicitation Number", "Reference Number", "Solicitation Type", "Organization",
                  "Purchasing Group", "Publication Date", "Closing Date", "Closing Time", "Location",
                  "Bid Bond", "Pre-Bid", "Pre-Proposal", "Contact", "Email", "Phone", "Delivery",
                  "Piggyback", "Category"):
        m = re.search(re.escape(label) + r"\s*:?\s*(.{1,160}?)(?=\s(?:[A-Z][a-z]+ ?){1,3}\s*:|$)", body)
        if m:
            fields[label] = m.group(1).strip()
    dm = re.search(r"Description\s*:?\s*(.*?)(?:Documents|Attachments|Related Solicitations|Terms & Conditions)",
                   body, re.S)
    description = dm.group(1).strip() if dm else ""
    return title, fields, description, body


class BidNetSource:
    name = "bidnet"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.base = cfg.get("base_url", "https://www.bidnetdirect.com").rstrip("/")
        self.page_size = int(cfg.get("page_size", 100))
        self.max_pages = int(cfg.get("max_pages", 60))
        self.pause = float(cfg.get("pause_seconds", 1.0))
        self.saved_search_ids = [str(x) for x in (cfg.get("saved_search_ids") or [])]
        self._session = None
        self.log = print

    # ---------------------------------------------------------------- http
    def _s(self) -> requests.Session:
        if self._session is None:
            try:
                cookie = cookie_header_from_curl_file(self.cfg.get("cookie_file", "~/.bidnet-curl.txt"))
            except (CookieFileMissing, CookieNotFound) as e:
                raise NeedsCookie(self.name, str(e)) from None
            s = requests.Session()
            s.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                              "Accept-Language": "en-US,en;q=0.9", "Cookie": cookie})
            self._session = s
        return self._session

    def get(self, path: str) -> requests.Response:
        url = path if path.startswith("http") else self.base + path
        r = None
        for attempt in range(3):
            try:
                r = self._s().get(url, timeout=90, allow_redirects=True)
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 + attempt * 2)
                continue
            if r.status_code >= 500:
                time.sleep(2 + attempt * 2)
                continue
            break
        time.sleep(self.pause)
        if "/public/authentication/login" in r.url or r.url.split("?")[0].endswith("/login"):
            raise NeedsCookie(self.name, f"redirected to login; re-paste {self.cfg.get('cookie_file')}")
        r.raise_for_status()
        return r

    def doc(self, r: requests.Response):
        return strip_scripts(lxhtml.fromstring(r.content, base_url=r.url))

    # ---------------------------------------------------------- protocol
    def healthcheck(self) -> str:
        try:
            d = self.doc(self.get("/private/supplier/solicitations/search"))
        except NeedsCookie:
            return HEALTH_NEEDS_COOKIE
        except requests.RequestException:
            return HEALTH_DOWN
        return HEALTH_OK if saved_searches(d) or result_count(d) else HEALTH_NEEDS_COOKIE

    def _searches(self) -> list[tuple[str, str]]:
        d = self.doc(self.get("/private/supplier/solicitations/search"))
        found = saved_searches(d)
        if self.saved_search_ids:
            by_id = dict((v, n) for n, v in found)
            return [(by_id.get(i, i), i) for i in self.saved_search_ids]
        if not found:
            raise NeedsCookie(self.name, "no saved searches on the search page; is the session live?")
        return found

    def run_search(self, name: str, val: str) -> tuple[list[dict], int | None]:
        rows, seen, total = [], set(), None
        for page in range(1, self.max_pages + 1):
            d = self.doc(self.get(f"/private/supplier/solicitations/search?pageNumber={page}"
                                  f"&pageSize={self.page_size}&selectedSavedSearch={val}"))
            rc = result_count(d)
            if rc:
                total = rc[2]
            page_rows = parse_rows(d, self.base)
            new = 0
            for row in page_rows:
                if row["id"] not in seen:
                    seen.add(row["id"])
                    rows.append(row)
                    new += 1
            if new == 0 or len(page_rows) < self.page_size or (rc and rc[1] >= rc[2]):
                break
        self.log(f"  bidnet/{name}: {len(rows)} rows (site says {total})")
        return rows, total

    def sweep(self) -> Iterator[dict]:
        allrows: dict[str, dict] = {}
        for name, val in self._searches():
            rows, _ = self.run_search(name, val)
            for row in rows:
                if row["id"] in allrows:
                    allrows[row["id"]]["searches"].append(name)
                else:
                    row["searches"] = [name]
                    allrows[row["id"]] = row
        yield from allrows.values()

    # ---------------------------------------------------------- abstract
    def abstract(self, sid: str) -> tuple[str, dict, str]:
        r = self.get(f"/private/supplier/interception/open-solicitation/{sid}?target=view")
        base = r.url.split("?")[0]
        for candidate in (base, f"{self.base}/private/supplier/solicitations/notice/{sid}/abstract"):
            try:
                r2 = self.get(candidate)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    continue
                raise
            if re.search(r"<title>\s*No javascript", r2.text, re.I):
                raise FederalNotice(f"{sid}: SAML page returned for {candidate}; session may need a re-paste")
            title, fields, description, _ = parse_abstract(self.doc(r2))
            return candidate, {"title": title, **fields}, description
        raise FederalNotice(f"{sid}: 404 on both abstract paths; federal notices need SAM.gov")
