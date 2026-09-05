import datetime as dt
import json

from bid_radar.config import load_config
from bid_radar.digest import build_digest, render_markdown, write_digest
from bid_radar.model import Solicitation
from bid_radar.scoring import Rules
from bid_radar.store import Store


def _seed(st):
    t0 = dt.datetime(2026, 9, 4, 7, 0)
    t1 = dt.datetime(2026, 9, 5, 7, 0)
    st.upsert(Solicitation(uid="bidnet:1", source="bidnet", source_id="1", title="Wild Horse Tiny Home Village",
                           agency="City of Aurora", location="Colorado", bid_type="Member Agency Bids",
                           closing=dt.datetime(2026, 9, 25, 14, 0), url="https://x/1"), 5, "", t0)
    st.upsert(Solicitation(uid="samgov:2", source="samgov", source_id="2", title="Modular Housing Design-Build",
                           agency="DEPT OF THE ARMY", location="Wyoming", bid_type="Federal",
                           closing=dt.datetime(2026, 10, 1, 17, 0), url="https://x/2"), 4, "", t1)
    st.upsert(Solicitation(uid="bidnet:3", source="bidnet", source_id="3", title="Housing Study",
                           location="Utah"), 1, "housing word in blurb only", t1)
    rid = st.start_run()
    st.finish_run(rid, {"bidnet": {"rows": 2, "health": "ok"}, "samgov": {"rows": 1, "health": "ok"},
                        "publicpurchase": {"rows": 0, "health": "needs_cookie"}}, None)
    return t0, t1


def test_build_and_render(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    t0, t1 = _seed(st)
    rules = Rules.from_config(load_config()["scoring"])
    d = build_digest(st, rules, as_of=t1, since=t0)
    assert [r["uid"] for r in d["new"]] == ["samgov:2"]
    assert [r["uid"] for r in d["open"]] == ["bidnet:1"]
    assert d["low_count"] == 1
    assert d["sources"]["publicpurchase"]["health"] == "needs_cookie"
    md = render_markdown(d)
    assert "# Bid Radar digest 2026-09-05" in md
    assert "needs_cookie" in md and "publicpurchase" in md
    assert "| 4 | Wyoming | Modular Housing Design-Build |" in md
    assert "https://x/2" in md


def test_write_digest(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    t0, t1 = _seed(st)
    rules = Rules.from_config(load_config()["scoring"])
    md_path, json_path = write_digest(st, rules, tmp_path / "out", as_of=t1, since=t0)
    assert md_path.name == "bid-radar-2026-09-05.md"
    assert json.load(open(json_path, encoding="utf-8"))["as_of"] == "2026-09-05T07:00"
