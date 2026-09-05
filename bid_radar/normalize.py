"""Per-source raw dict -> Solicitation."""
from __future__ import annotations

from .model import Solicitation, normalize_state, parse_date, parse_datetime


def _bidnet(raw: dict) -> Solicitation:
    extra = {"searches": raw.get("searches", [])}
    closing = parse_datetime(raw.get("closing"))
    if raw.get("closing") and closing is None:
        extra["closing_raw"] = raw["closing"]
    published = parse_date(raw.get("published"))
    if raw.get("published") and published is None:
        extra["published_raw"] = raw["published"]
    return Solicitation(
        uid=f"bidnet:{raw['id']}", source="bidnet", source_id=str(raw["id"]),
        title=raw.get("title", "").strip(), agency=raw.get("agency", "").strip(),
        location=normalize_state(raw.get("location", "")), bid_type=raw.get("bid_type", ""),
        published=published, closing=closing, url=raw.get("url", ""),
        blurb=raw.get("blurb", ""), mandatory_prebid=bool(raw.get("mandatory_prebid")), extra=extra,
    )


def _samgov(raw: dict) -> Solicitation:
    pop = raw.get("placeOfPerformance") or {}
    state = ((pop.get("state") or {}).get("code")) or ""
    extra = {"type": raw.get("type", ""), "naics": raw.get("naicsCode", ""),
             "set_aside": raw.get("typeOfSetAsideDescription", "")}
    closing = parse_datetime(raw.get("responseDeadLine"))
    if raw.get("responseDeadLine") and closing is None:
        extra["closing_raw"] = raw["responseDeadLine"]
    return Solicitation(
        uid=f"samgov:{raw['noticeId']}", source="samgov", source_id=str(raw["noticeId"]),
        title=raw.get("title", "").strip(), agency=(raw.get("fullParentPathName") or "").strip(),
        location=normalize_state(state), bid_type="Federal",
        published=parse_date(raw.get("postedDate")), closing=closing,
        url=raw.get("uiLink", ""), blurb=raw.get("description_excerpt", ""),
        mandatory_prebid=False, extra=extra,
    )


def _publicpurchase(raw: dict) -> Solicitation:
    extra = {"agency_slug": raw.get("agency_slug", "")}
    closing = parse_datetime(raw.get("closing"))
    if raw.get("closing") and closing is None:
        extra["closing_raw"] = raw["closing"]
    return Solicitation(
        uid=f"publicpurchase:{raw['id']}", source="publicpurchase", source_id=str(raw["id"]),
        title=raw.get("title", "").strip(), agency=raw.get("agency", "").strip(),
        location=normalize_state(raw.get("location", "")), bid_type="State & Local Bids",
        published=parse_date(raw.get("published")), closing=closing,
        url=raw.get("url", ""), blurb=raw.get("blurb", ""), mandatory_prebid=False, extra=extra,
    )


_NORMALIZERS = {"bidnet": _bidnet, "samgov": _samgov, "publicpurchase": _publicpurchase}


def normalize(source: str, raw: dict) -> Solicitation:
    try:
        fn = _NORMALIZERS[source]
    except KeyError:
        raise ValueError(f"unknown source {source!r}") from None
    return fn(raw)
