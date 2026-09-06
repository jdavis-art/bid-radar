import json

import pytest

from bid_radar.sources.base import NeedsCookie
from bid_radar.sources.publicpurchase import PublicPurchaseSource, parse_agencies, parse_bid_list

BID_HTML = """
<table><tr class="bidRow"><td><a href="/gems/cityofaurora/bid/bidView?bidId=12345">Wild Horse Tiny Home Village</a></td>
<td>Published 09/01/2026</td><td>Closes 09/25/2026 2:00 PM MDT</td></tr>
<tr class="bidRow"><td><a href="/gems/cityofaurora/bid/bidView?bidId=12346">Pressure Washing Services</a></td>
<td>Published 09/02/2026</td><td>Closes 09/20/2026 2:00 PM MDT</td></tr></table>
"""


def test_parse_agencies_filters_by_pick(fixtures):
    payload = json.loads((fixtures / "publicpurchase-agencies.json").read_text(encoding="utf-8"))
    src = PublicPurchaseSource({"agency_pick": "hous|city of", "bid_pick": "housing|home", "regions": ["CO"]})
    got = [a["slug"] for a in parse_agencies(payload, src.agency_pick)]
    assert got == ["coloradospringshousingauthority", "cityofaurora"]


def test_parse_bid_list_extracts_rows():
    rows = parse_bid_list(BID_HTML, {"slug": "cityofaurora", "name": "City of Aurora", "state": "CO"},
                          base_url="https://www.publicpurchase.com")
    assert len(rows) == 2
    r = rows[0]
    assert r["id"] == "12345"
    assert r["title"] == "Wild Horse Tiny Home Village"
    assert r["agency"] == "City of Aurora" and r["location"] == "CO"
    assert r["closing"] == "09/25/2026 2:00 PM MDT"
    assert r["url"] == "https://www.publicpurchase.com/gems/cityofaurora/bid/bidView?bidId=12345"


def test_healthcheck_without_cookie(tmp_path):
    src = PublicPurchaseSource({"cookie_file": str(tmp_path / "missing.txt"), "regions": ["CO"]})
    assert src.healthcheck() == "needs_cookie"
    with pytest.raises(NeedsCookie):        # the run summary must say needs_cookie, never ok with zero rows
        list(src.sweep())
