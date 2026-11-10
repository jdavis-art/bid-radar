import datetime as dt

from bid_radar.normalize import normalize
from bid_radar.scoring import Rules, score
from bid_radar.sources.prop123 import parse_list


def _rows(fixtures):
    return parse_list((fixtures / "prop123-selections.txt").read_text(encoding="utf-8"))


def test_parse_list_header_and_rows(fixtures):
    label, date, rows = _rows(fixtures)
    assert label == "FY25-26 Land Banking Program Selections - Rural/Rural Resort Round"
    assert date == dt.date(2026, 8, 31)
    assert [r["email"] for r in rows] == ["admin@example.org", "sam@example.gov", "pat@example.com"]
    first = rows[0]
    assert first["who"] == "Town of Exampleville Lakeside Flats Exampleville"
    assert (first["requested"], first["awarded"], first["units"]) == (1_820_000, 1_820_000, 52)
    assert first["purpose"] == "Homeownership" and first["contact"] == "Alex Sample"
    assert first["phone"] == "303-555-0101"
    assert rows[1]["who"] == "City of Testburg Riverside Lot 5 Workforce Housing Development Testburg"
    assert rows[2]["requested"] == 7_000_000 and rows[2]["purpose"] == "Rental and Homeownership"


def test_rows_normalize_and_score_into_the_digest(fixtures, tmp_path):
    import yaml
    from pathlib import Path
    cfg = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text(encoding="utf-8"))
    rules = Rules.from_config(cfg["scoring"])
    label, date, rows = _rows(fixtures)
    sols = [normalize("prop123", {**r, "list_label": label, "list_date": date.isoformat(), "posted": "2026-09-02",
                                  "closing": "2026-12-01", "slug": "lb-rrr", "url": "https://x/lb-rrr.pdf"})
            for r in rows]
    assert sols[0].uid == "prop123:lb-rrr:admin@example.org:52"
    assert sols[0].location == "Colorado" and sols[0].closing == dt.datetime(2026, 12, 1)
    scores = [score(s, rules) for s in sols]
    # Every row clears the digest threshold; a sponsor named "... Services" must not trip the exclusions.
    assert all(sc >= 4 for sc, _ in scores), scores
    assert scores[1][0] == 5   # "Workforce Housing" in the sponsor/project text boosts
