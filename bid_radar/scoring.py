"""Config-driven scorer. Mirrors the legacy scorer's order of checks exactly:
exclude (title) -> not-housing (title) -> housing (title, else blurb) -> location -> boost -> federal note."""
from __future__ import annotations

import dataclasses
import re

from .model import Solicitation


def _compile(patterns: list[str]) -> re.Pattern | None:
    patterns = [p for p in (patterns or []) if p]
    if not patterns:
        return None
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.I)


@dataclasses.dataclass
class Rules:
    exclude_title: re.Pattern | None
    not_housing_title: re.Pattern | None
    housing: re.Pattern | None
    location_points: dict[str, int]
    boost: re.Pattern | None
    federal_bid_type: str
    federal_note: str
    digest_min_score: int = 3

    @classmethod
    def from_config(cls, sc: dict) -> "Rules":
        return cls(
            exclude_title=_compile(sc.get("exclude_title")),
            not_housing_title=_compile(sc.get("not_housing_title")),
            housing=_compile(sc.get("housing")),
            location_points={k: int(v) for k, v in (sc.get("location_points") or {}).items()},
            boost=_compile(sc.get("boost")),
            federal_bid_type=sc.get("federal_bid_type", "Federal Bids"),
            federal_note=sc.get("federal_note", "federal (CAGE/SAM required)"),
            digest_min_score=int(sc.get("digest_min_score", 3)),
        )


def score(sol: Solicitation, rules: Rules) -> tuple[int, str]:
    title = sol.title or ""
    text = title + " " + (sol.blurb or "")
    if rules.exclude_title and (m := rules.exclude_title.search(title)):
        return 0, "excluded: " + m.group(0).lower()
    if rules.not_housing_title and (m := rules.not_housing_title.search(title)):
        return 0, "not housing (" + m.group(0).lower() + ")"
    if not rules.housing or not rules.housing.search(title):
        if rules.housing and rules.housing.search(text):
            return 1, "housing word in blurb only"
        return 0, "not housing"
    sc = 2 + rules.location_points.get(sol.location, 0)
    if rules.boost and rules.boost.search(text):
        sc += 1
    if sol.bid_type == rules.federal_bid_type:
        return sc, rules.federal_note
    return sc, ""
