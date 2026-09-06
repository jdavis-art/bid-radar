import datetime as dt
import json

from bid_radar.normalize import normalize
from bid_radar.sources.samgov import SamGovSource, parse_search, build_params


def test_parse_search_returns_records(fixtures):
    payload = json.loads((fixtures / "samgov-search.json").read_text(encoding="utf-8"))
    recs = parse_search(payload)
    assert [r["noticeId"] for r in recs] == ["a1b2c3d4e5", "f6g7h8i9j0"]
    sol = normalize("samgov", recs[0])
    assert sol.uid == "samgov:a1b2c3d4e5"
    assert sol.location == "Colorado"
    assert sol.closing == dt.datetime(2026, 9, 30, 14, 0)
    assert sol.agency.endswith("OMAHA DISTRICT")


def test_build_params_dates_and_key():
    p = build_params(api_key="k", keyword="modular housing", naics=None, ptypes=["o", "p", "k"],
                     posted_from=dt.date(2026, 8, 29), posted_to=dt.date(2026, 9, 5), limit=1000, offset=0)
    assert p["api_key"] == "k"
    assert p["postedFrom"] == "08/29/2026" and p["postedTo"] == "09/05/2026"
    assert p["ptype"] == "o,p,k"
    assert p["title"] == "modular housing"
    assert "ncode" not in p
    p2 = build_params(api_key="k", keyword=None, naics="236220", ptypes=["o"],
                      posted_from=dt.date(2026, 8, 29), posted_to=dt.date(2026, 9, 5), limit=1000, offset=0)
    assert p2["ncode"] == "236220" and "title" not in p2


def test_healthcheck_without_key():
    src = SamGovSource({"api_key": "", "keywords": ["x"], "naics": []}, last_run=None)
    assert src.healthcheck() == "needs_key"


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_healthcheck_with_key_does_not_touch_the_api_unless_probed(monkeypatch):
    import bid_radar.sources.samgov as mod
    calls = []
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: calls.append(1) or _Resp(200))
    src = SamGovSource({"api_key": "k"}, last_run=None)
    assert src.healthcheck() == "key present"
    assert calls == []
    assert src.healthcheck(probe=True) == "ok"
    assert len(calls) == 1


def test_429_is_terminal_and_query_yield_is_recorded(monkeypatch):
    import bid_radar.sources.samgov as mod
    from bid_radar.sources.base import RateLimited
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params.get("title") or params.get("ncode"))
        if len(calls) == 1:
            return _Resp(200, {"totalRecords": 2, "opportunitiesData": [{"noticeId": "a"}, {"noticeId": "b"}]})
        return _Resp(429)

    monkeypatch.setattr(mod.requests, "get", fake_get)
    src = SamGovSource({"api_key": "k", "keywords": ["design-build", "modular housing"], "naics": ["236220"]},
                       last_run=None)
    got = []
    try:
        for rec in src.sweep():
            got.append(rec["noticeId"])
        raise AssertionError("expected RateLimited")
    except RateLimited as e:
        assert e.source == "samgov"
    assert got == ["a", "b"]
    assert calls == ["design-build", "modular housing"]      # one 429, no retry, third query skipped
    assert src.query_yield == {"design-build": 2, "modular housing": "rate_limited"}
