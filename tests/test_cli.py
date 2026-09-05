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
