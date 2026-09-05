import datetime as dt

from bid_radar.model import Solicitation, parse_date, parse_datetime, normalize_state
from bid_radar.normalize import normalize


def test_parse_date_formats():
    assert parse_date("08/17/2026") == dt.date(2026, 8, 17)
    assert parse_date("2026-08-17") == dt.date(2026, 8, 17)
    assert parse_date("2026-08-17T10:00:00-04:00") == dt.date(2026, 8, 17)
    assert parse_date("not a date") is None
    assert parse_date("") is None


def test_parse_datetime_bidnet_closing():
    got = parse_datetime("09/17/2026 04:00 PM EDT")
    assert got == dt.datetime(2026, 9, 17, 16, 0)


def test_normalize_state():
    assert normalize_state("Colorado") == "Colorado"
    assert normalize_state("CO") == "Colorado"
    assert normalize_state("co") == "Colorado"
    assert normalize_state("") == ""
    assert normalize_state("Unknown Place") == "Unknown Place"


def test_normalize_bidnet_row():
    raw = {
        "id": "2714057612",
        "title": "YELL 326141 YELLOWSTONE MODULAR HOUSING",
        "agency": "",
        "bid_type": "Federal Bids",
        "closing": "09/17/2026 04:00 PM EDT",
        "location": "Colorado",
        "published": "08/17/2026",
        "blurb": "YELL 326141 Yellowstone Modular Housing",
        "mandatory_prebid": False,
        "url": "https://www.bidnetdirect.com/private/solicitations/2714057612/abstract",
        "searches": ["All Housing", "Modular"],
    }
    sol = normalize("bidnet", raw)
    assert sol.uid == "bidnet:2714057612"
    assert sol.published == dt.date(2026, 8, 17)
    assert sol.closing == dt.datetime(2026, 9, 17, 16, 0)
    assert sol.extra["searches"] == ["All Housing", "Modular"]


def test_unparseable_date_kept_in_extra():
    raw = {"id": "1", "title": "t", "closing": "TBD", "published": "", "location": "CO"}
    sol = normalize("bidnet", raw)
    assert sol.closing is None
    assert sol.extra["closing_raw"] == "TBD"
    assert sol.location == "Colorado"


def test_row_round_trip():
    sol = normalize("samgov", {"noticeId": "abc", "title": "T", "postedDate": "2026-09-01",
                               "responseDeadLine": "2026-09-20T17:00:00-06:00",
                               "placeOfPerformance": {"state": {"code": "WY"}},
                               "fullParentPathName": "DEPT OF X.OFFICE Y", "uiLink": "https://sam.gov/opp/abc/view",
                               "type": "Solicitation"})
    row = sol.to_row()
    back = Solicitation.from_row(row)
    assert back == sol
    assert back.location == "Wyoming"
    assert back.agency == "DEPT OF X.OFFICE Y"
