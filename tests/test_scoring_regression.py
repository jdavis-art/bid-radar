import collections
import json

from bid_radar.config import load_config
from bid_radar.model import Solicitation
from bid_radar.scoring import Rules, score

EXPECTED = {0: 4073, 1: 77, 2: 2, 3: 67, 4: 14, 5: 4}


def _load(fixtures):
    with open(fixtures / "sweep-2026-09-04-scored.jsonl", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def _sol(r):
    return Solicitation(uid=f"bidnet:{r['id']}", source="bidnet", source_id=r["id"], title=r["title"],
                        agency=r["agency"], location=r["location"], bid_type=r["bid_type"], blurb=r["blurb"])


def test_distribution_matches_legacy(root, fixtures):
    rules = Rules.from_config(load_config(root)["scoring"])
    dist = collections.Counter(score(_sol(r), rules)[0] for r in _load(fixtures))
    assert dict(sorted(dist.items())) == EXPECTED


def test_every_row_matches_legacy_score_and_note(root, fixtures):
    rules = Rules.from_config(load_config(root)["scoring"])
    mismatches = []
    for r in _load(fixtures):
        s, note = score(_sol(r), rules)
        if s != r["legacy_score"] or note != r["legacy_note"]:
            mismatches.append((r["id"], r["title"][:60], s, r["legacy_score"], note, r["legacy_note"]))
    assert mismatches == [], mismatches[:10]


def test_boost_and_location():
    rules = Rules.from_config(load_config()["scoring"])
    sol = Solicitation(uid="x:1", source="x", source_id="1", title="Workforce Housing Modular Units",
                       location="Colorado", bid_type="State & Local Bids")
    assert score(sol, rules) == (5, "")


def test_exclusion_wins_over_housing():
    rules = Rules.from_config(load_config()["scoring"])
    sol = Solicitation(uid="x:2", source="x", source_id="2", title="Housing Needs Assessment Study",
                       location="Colorado")
    s, note = score(sol, rules)
    assert s == 0 and note.startswith("excluded: ")
