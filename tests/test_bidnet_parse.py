from lxml import html as lxhtml

from bid_radar.sources.bidnet import parse_rows, saved_searches, result_count, strip_scripts


def _doc(fixtures):
    return strip_scripts(lxhtml.fromstring((fixtures / "bidnet-search-page.html").read_bytes()))


def test_parse_rows_shape(fixtures):
    rows = parse_rows(_doc(fixtures))
    assert len(rows) >= 5
    r = rows[0]
    assert set(r) == {"id", "title", "agency", "bid_type", "closing", "location", "published",
                      "blurb", "mandatory_prebid", "url"}
    assert r["id"].isdigit()
    assert r["url"].endswith(f"/private/solicitations/{r['id']}/abstract")
    assert not r["published"].startswith("Published Date")


def test_saved_searches_and_count(fixtures):
    d = _doc(fixtures)
    searches = saved_searches(d)
    assert all(val.strip() and not name.startswith("-") for name, val in searches)
    rc = result_count(d)
    assert rc is None or (len(rc) == 3 and rc[2] >= rc[1])
