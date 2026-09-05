r"""Reduce the private seed sweep to the public fields needed for the scoring regression.
Run once: .venv\Scripts\python.exe scripts\make_regression_fixture.py
Reads seed/bidnet-sweep-2026-09-04.json (gitignored), writes tests/fixtures/sweep-2026-09-04-scored.jsonl.
Kept fields are public solicitation data: title, agency, location, bid_type, blurb, and the legacy score.
Contact email addresses inside blurbs are redacted; they never affect the score."""
import json
import pathlib
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = ROOT / "seed" / "bidnet-sweep-2026-09-04.json"
dst = ROOT / "tests" / "fixtures" / "sweep-2026-09-04-scored.jsonl"
rows = json.load(open(src, encoding="utf-8"))["rows"]
dst.parent.mkdir(parents=True, exist_ok=True)
with open(dst, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps({
            "id": r["id"], "title": r["title"], "agency": r.get("agency", ""),
            "location": r.get("location", ""), "bid_type": r.get("bid_type", ""),
            "blurb": _EMAIL.sub("[email]", r.get("blurb", "")), "legacy_score": r["score"], "legacy_note": r.get("note", ""),
        }, ensure_ascii=False) + "\n")
print(f"wrote {len(rows)} rows to {dst}")
