import datetime as dt

from bid_radar.dedupe import title_key, link_duplicates
from bid_radar.model import Solicitation
from bid_radar.store import Store


def test_title_key_strips_punctuation_and_agency_tokens():
    assert title_key("Wild Horse Tiny Home Village - Modular Housing!", "City of Aurora") == \
           title_key("wild horse tiny home village modular housing", "Aurora")
    assert title_key("City of Aurora: Wild Horse Village", "City of Aurora") == "wild horse village"


def _sol(uid, title, closing, agency="City of Aurora"):
    return Solicitation(uid=uid, source=uid.split(":")[0], source_id=uid.split(":")[1], title=title,
                        agency=agency, closing=closing)


def test_links_same_title_close_dates_across_sources(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    now = dt.datetime(2026, 9, 5, 7, 0)
    st.upsert(_sol("bidnet:1", "Wild Horse Tiny Home Village", dt.datetime(2026, 9, 25, 14, 0)), 5, "", now)
    st.upsert(_sol("publicpurchase:7", "Wild Horse Tiny Home Village", dt.datetime(2026, 9, 26, 14, 0)), 3, "", now)
    st.upsert(_sol("samgov:9", "Wild Horse Tiny Home Village", dt.datetime(2026, 10, 15, 14, 0)), 3, "", now)
    st.upsert(_sol("bidnet:2", "Wild Horse Tiny Home Village", dt.datetime(2026, 9, 22, 14, 0)), 3, "", now)
    n = link_duplicates(st, st.all_rows())
    assert n == 1
    assert st.duplicates_of("bidnet:1") == ["publicpurchase:7"]
    assert st.duplicates_of("samgov:9") == []       # 20 days apart
    assert st.duplicates_of("bidnet:2") == []       # 3 days from bidnet:1 but same source, never linked
    assert link_duplicates(st, st.all_rows()) == 0  # idempotent
