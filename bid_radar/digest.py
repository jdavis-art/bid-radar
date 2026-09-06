"""Daily digest: new-since-last-run first, then everything open at or above the threshold."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .scoring import Rules
from .store import Store

_COLS = ("score", "location", "title", "agency", "closing", "source", "url", "score_note")


def _slim(store: Store, row: dict) -> dict:
    out = {c: row.get(c) for c in ("uid",) + _COLS}
    out["duplicates"] = store.duplicates_of(row["uid"])
    extra = row.get("extra")
    extra = json.loads(extra) if isinstance(extra, str) else (extra or {})
    out["searches"] = list(extra.get("searches") or [])
    return out


def _note(r: dict) -> str:
    parts = [r.get("score_note") or ""]
    if r.get("searches"):
        parts.append("searches: " + ", ".join(r["searches"]))
    return "; ".join(p for p in parts if p)


def build_digest(store: Store, rules: Rules, as_of: dt.datetime, since: dt.datetime | None) -> dict:
    min_score = rules.digest_min_score
    new = store.new_since(since, min_score) if since else store.open_rows(min_score, as_of)
    new_uids = {r["uid"] for r in new}
    open_rest = [r for r in store.open_rows(min_score, as_of) if r["uid"] not in new_uids]
    low = [r for r in store.open_rows(1, as_of) if r["score"] < min_score]
    last = store.last_run() or {}
    sources = json.loads(last.get("per_source") or "{}")
    prev = store.db.execute("select per_source from runs where finished is not null order by id desc limit 2").fetchall()
    prev_sources = json.loads(prev[1]["per_source"]) if len(prev) > 1 else {}
    suspicious = sorted(name for name, info in sources.items()
                        if info.get("health") == "ok" and info.get("rows", 0) == 0
                        and prev_sources.get(name, {}).get("rows", 0) > 0)
    return {
        "as_of": as_of.isoformat(timespec="minutes"),
        "since": since.isoformat(timespec="minutes") if since else None,
        "sources": sources,
        "run_error": last.get("error"),
        "new": [_slim(store, r) for r in new],
        "open": [_slim(store, r) for r in open_rest],
        "low_count": len(low),
        "suspicious": suspicious,
    }


def _table(rows: list[dict]) -> str:
    if not rows:
        return "_none_\n"
    lines = ["| Score | State | Title | Agency | Closing | Source | Link | Note |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        dup = f" (+{len(r['duplicates'])} dup)" if r.get("duplicates") else ""
        lines.append(f"| {r['score']} | {r['location'] or ''} | {r['title']} | {r['agency'] or ''} | "
                     f"{(r['closing'] or '')[:16]} | {r['source']}{dup} | {r['url'] or ''} | {_note(r)} |")
    return "\n".join(lines) + "\n"


def render_markdown(d: dict) -> str:
    day = d["as_of"][:10]
    out = [f"# Bid Radar digest {day}", ""]
    out.append("## Run")
    for name, info in sorted(d["sources"].items()):
        out.append(f"- {name}: {info.get('rows', 0)} rows, {info.get('health', '?')}")
    for name in d.get("suspicious", []):
        out.append(f"- suspicious: {name} returned 0 rows after returning rows last run")
    if d.get("run_error"):
        out.append(f"- error: {d['run_error']}")
    if not d["sources"]:
        out.append("- no run recorded")
    out.append("")
    out.append(f"## New since {d['since'] or 'the beginning'}")
    out.append(_table(d["new"]))
    out.append("## Open, score 3 and up")
    out.append(_table(d["open"]))
    out.append(f"## Below threshold: {d['low_count']} open rows (see the JSON)")
    out.append("")
    return "\n".join(out)


def write_digest(store: Store, rules: Rules, output_dir: Path, as_of: dt.datetime,
                 since: dt.datetime | None) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    d = build_digest(store, rules, as_of, since)
    stem = f"bid-radar-{as_of.date().isoformat()}"
    md_path, json_path = output_dir / f"{stem}.md", output_dir / f"{stem}.json"
    md_path.write_text(render_markdown(d), encoding="utf-8")
    json_path.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    return md_path, json_path
