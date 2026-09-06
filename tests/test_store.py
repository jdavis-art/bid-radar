import datetime as dt

from bid_radar.model import Solicitation
from bid_radar.store import Store


def _sol(uid="bidnet:1", title="Modular Housing", closing=None):
    return Solicitation(uid=uid, source=uid.split(":")[0], source_id=uid.split(":")[1], title=title,
                        location="Colorado", bid_type="Member Agency Bids", closing=closing)


def test_upsert_new_then_update(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    t1 = dt.datetime(2026, 9, 5, 7, 0)
    assert st.upsert(_sol(), 4, "", t1) is True
    t2 = dt.datetime(2026, 9, 6, 7, 0)
    assert st.upsert(_sol(title="Modular Housing (Amended)"), 4, "", t2) is False
    row = st.get("bidnet:1")
    assert row.title == "Modular Housing (Amended)"
    rows = st.open_rows(min_score=3, as_of=t2)
    assert rows[0]["first_seen"] == t1.isoformat(timespec="minutes")
    assert rows[0]["last_seen"] == t2.isoformat(timespec="minutes")


def test_open_rows_excludes_closed_and_low_scores(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    now = dt.datetime(2026, 9, 5, 7, 0)
    st.upsert(_sol("bidnet:open", closing=dt.datetime(2026, 9, 30, 14, 0)), 3, "", now)
    st.upsert(_sol("bidnet:closed", closing=dt.datetime(2026, 9, 1, 14, 0)), 5, "", now)
    st.upsert(_sol("bidnet:low"), 1, "", now)
    st.upsert(_sol("bidnet:nodate"), 3, "", now)
    uids = {r["uid"] for r in st.open_rows(min_score=3, as_of=now)}
    assert uids == {"bidnet:open", "bidnet:nodate"}


def test_new_since_and_mark(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    t1 = dt.datetime(2026, 9, 5, 7, 0)
    t2 = dt.datetime(2026, 9, 6, 7, 0)
    st.upsert(_sol("bidnet:a"), 3, "", t1)
    st.upsert(_sol("bidnet:b"), 3, "", t2)
    assert [r["uid"] for r in st.new_since(t1, min_score=3)] == ["bidnet:b"]
    st.mark("bidnet:b", "dismissed")
    assert st.get_row("bidnet:b")["status"] == "dismissed"
    assert [r["uid"] for r in st.open_rows(min_score=3, as_of=t2)] == ["bidnet:a"]


def test_runs(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    assert st.last_successful_run() is None
    rid = st.start_run()
    st.finish_run(rid, {"bidnet": {"rows": 10, "health": "ok"}}, None)
    assert st.last_successful_run() is not None
    rid2 = st.start_run()
    st.finish_run(rid2, {"bidnet": {"rows": 0, "health": "needs_cookie"}}, "bidnet needs cookie")
    assert st.last_run()["error"] == "bidnet needs cookie"


def test_duplicates(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    now = dt.datetime(2026, 9, 5, 7, 0)
    st.upsert(_sol("bidnet:1"), 3, "", now)
    st.upsert(_sol("samgov:9"), 3, "", now)
    st.link_duplicate("bidnet:1", "samgov:9", "title+closing")
    st.link_duplicate("bidnet:1", "samgov:9", "title+closing")  # idempotent
    assert st.duplicates_of("bidnet:1") == ["samgov:9"]
    assert st.duplicates_of("samgov:9") == ["bidnet:1"]


def test_last_successful_run_per_source(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    rid = st.start_run()
    st.finish_run(rid, {"bidnet": {"rows": 10, "health": "ok"}, "samgov": {"rows": 0, "health": "needs_key"}},
                  "samgov: API key missing")
    assert st.last_successful_run() is None                 # the run as a whole had an error
    assert st.last_successful_run("bidnet") is not None     # but bidnet itself was fine
    assert st.last_successful_run("samgov") is None         # samgov never succeeded
    rid2 = st.start_run()
    st.finish_run(rid2, {"samgov": {"rows": 3, "health": "ok"}}, None)
    assert st.last_successful_run("samgov") is not None
