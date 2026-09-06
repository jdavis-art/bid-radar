import datetime as dt

from bid_radar.cli import run_sweep, main
from bid_radar.store import Store


class FakeGood:
    name = "bidnet"
    def healthcheck(self): return "ok"
    def sweep(self):
        yield {"id": "1", "title": "Workforce Housing Modular Units", "agency": "City of Aurora",
               "bid_type": "Member Agency Bids", "closing": "09/25/2026 02:00 PM MDT", "location": "Colorado",
               "published": "09/01/2026", "blurb": "", "mandatory_prebid": False, "url": "https://x/1", "searches": ["Modular"]}


class FakeBroken:
    name = "samgov"
    def healthcheck(self): return "needs_key"
    def sweep(self):
        from bid_radar.sources.base import NeedsKey
        raise NeedsKey("samgov", "set SAM_API_KEY")
        yield  # pragma: no cover


def test_run_sweep_isolates_failures(tmp_path, root, monkeypatch):
    from bid_radar.config import load_config
    cfg = load_config(root)
    cfg["data_dir"] = str(tmp_path / "data")
    cfg["output_dir"] = str(tmp_path / "digest")
    now = dt.datetime(2026, 9, 5, 7, 0)
    summary = run_sweep(cfg, sources=[FakeGood(), FakeBroken()], now=now)
    assert summary["bidnet"]["rows"] == 1 and summary["bidnet"]["health"] == "ok"
    assert summary["samgov"]["health"] == "needs_key"
    st = Store(tmp_path / "data" / "bid-radar.sqlite")
    row = st.get_row("bidnet:1")
    assert row["score"] == 5
    assert st.last_run()["error"] is not None  # a failed source is recorded, not hidden


def test_mark_command(tmp_path, root):
    from bid_radar.config import load_config
    cfg = load_config(root)
    cfg["data_dir"] = str(tmp_path / "data")
    run_sweep(cfg, sources=[FakeGood()], now=dt.datetime(2026, 9, 5, 7, 0))
    code = main(["--data-dir", str(tmp_path / "data"), "mark", "bidnet:1", "pursued"])
    assert code == 0
    assert Store(tmp_path / "data" / "bid-radar.sqlite").get_row("bidnet:1")["status"] == "pursued"


class FakeRateLimited:
    name = "samgov"
    query_yield = {"design-build": 3, "modular housing": "rate_limited"}
    def healthcheck(self): return "key present"
    def sweep(self):
        from bid_radar.sources.base import RateLimited
        yield {"noticeId": "n1", "title": "Modular Housing Design-Build", "postedDate": "2026-09-05",
               "placeOfPerformance": {"state": {"code": "CO"}}, "uiLink": "https://x/n1"}
        raise RateLimited("samgov", "HTTP 429")


def test_rate_limit_is_recorded_with_query_yield(tmp_path, root):
    from bid_radar.config import load_config
    cfg = load_config(root)
    cfg["data_dir"] = str(tmp_path / "data")
    summary = run_sweep(cfg, sources=[FakeRateLimited()], now=dt.datetime(2026, 9, 5, 7, 0))
    assert summary["samgov"]["health"] == "rate_limited"
    assert summary["samgov"]["rows"] == 1              # what arrived before the 429 is kept
    assert summary["samgov"]["queries"] == {"design-build": 3, "modular housing": "rate_limited"}
    st = Store(tmp_path / "data" / "bid-radar.sqlite")
    assert st.get_row("samgov:n1") is not None
    assert "rate limited" in st.last_run()["error"]


def test_whoami_does_not_probe_samgov_by_default(tmp_path, root, monkeypatch, capsys):
    import bid_radar.sources.samgov as mod
    monkeypatch.setenv("SAM_API_KEY", "k")
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("API touched")))
    assert main(["--data-dir", str(tmp_path / "data"), "whoami", "--only", "samgov"]) == 0
    assert "samgov: key present" in capsys.readouterr().out
