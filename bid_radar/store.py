"""SQLite persistence. One row per uid; nothing is ever deleted."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from .model import Solicitation

SCHEMA = """
create table if not exists solicitations (
  uid text primary key, source text not null, source_id text not null, title text not null,
  agency text, location text, bid_type text, published text, closing text, url text, blurb text,
  mandatory_prebid integer default 0, extra text default '{}',
  score integer default 0, score_note text default '', status text default 'new',
  first_seen text not null, last_seen text not null
);
create index if not exists ix_sol_score on solicitations(score);
create index if not exists ix_sol_closing on solicitations(closing);
create table if not exists duplicates (
  uid_a text not null, uid_b text not null, reason text, primary key (uid_a, uid_b)
);
create table if not exists runs (
  id integer primary key autoincrement, started text not null, finished text,
  per_source text default '{}', error text
);
"""

MUTABLE = ("title", "agency", "location", "bid_type", "published", "closing", "url", "blurb",
           "mandatory_prebid", "extra", "score", "score_note")


def _ts(t: dt.datetime) -> str:
    return t.isoformat(timespec="minutes")


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # ----------------------------------------------------------- solicitations
    def upsert(self, sol: Solicitation, score: int, note: str, seen_at: dt.datetime) -> bool:
        row = sol.to_row()
        row["score"], row["score_note"] = score, note
        existing = self.db.execute("select uid from solicitations where uid=?", (sol.uid,)).fetchone()
        if existing:
            sets = ", ".join(f"{c}=?" for c in MUTABLE)
            self.db.execute(f"update solicitations set {sets}, last_seen=? where uid=?",
                            [row[c] for c in MUTABLE] + [_ts(seen_at), sol.uid])
            self.db.commit()
            return False
        cols = ["uid", "source", "source_id"] + list(MUTABLE) + ["first_seen", "last_seen"]
        vals = [row["uid"], row["source"], row["source_id"]] + [row[c] for c in MUTABLE] + [_ts(seen_at), _ts(seen_at)]
        self.db.execute(f"insert into solicitations ({', '.join(cols)}) values ({', '.join('?' * len(cols))})", vals)
        self.db.commit()
        return True

    def get_row(self, uid: str) -> dict | None:
        r = self.db.execute("select * from solicitations where uid=?", (uid,)).fetchone()
        return dict(r) if r else None

    def get(self, uid: str) -> Solicitation | None:
        r = self.get_row(uid)
        return Solicitation.from_row(r) if r else None

    def open_rows(self, min_score: int, as_of: dt.datetime) -> list[dict]:
        rows = self.db.execute(
            "select * from solicitations where score>=? and status in ('new','seen','pursued') "
            "and (closing is null or closing>=?) order by score desc, closing asc, title asc",
            (min_score, _ts(as_of))).fetchall()
        return [dict(r) for r in rows]

    def new_since(self, ts: dt.datetime, min_score: int) -> list[dict]:
        rows = self.db.execute(
            "select * from solicitations where score>=? and first_seen>? and status<>'dismissed' "
            "order by score desc, closing asc, title asc", (min_score, _ts(ts))).fetchall()
        return [dict(r) for r in rows]

    def mark(self, uid: str, status: str):
        if status not in ("new", "seen", "dismissed", "pursued"):
            raise ValueError(f"bad status {status!r}")
        self.db.execute("update solicitations set status=? where uid=?", (status, uid))
        self.db.commit()

    def all_rows(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("select * from solicitations").fetchall()]

    # ------------------------------------------------------------------ runs
    def start_run(self) -> int:
        cur = self.db.execute("insert into runs (started) values (?)", (_ts(dt.datetime.now()),))
        self.db.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, per_source: dict, error: str | None):
        self.db.execute("update runs set finished=?, per_source=?, error=? where id=?",
                        (_ts(dt.datetime.now()), json.dumps(per_source, sort_keys=True), error, run_id))
        self.db.commit()

    def last_run(self) -> dict | None:
        r = self.db.execute("select * from runs order by id desc limit 1").fetchone()
        return dict(r) if r else None

    def last_successful_run(self) -> dt.datetime | None:
        r = self.db.execute("select started from runs where finished is not null and error is null "
                            "order by id desc limit 1").fetchone()
        return dt.datetime.fromisoformat(r["started"]) if r else None

    # ------------------------------------------------------------ duplicates
    def link_duplicate(self, uid_a: str, uid_b: str, reason: str):
        a, b = sorted((uid_a, uid_b))
        self.db.execute("insert or ignore into duplicates (uid_a, uid_b, reason) values (?,?,?)", (a, b, reason))
        self.db.commit()

    def duplicates_of(self, uid: str) -> list[str]:
        rows = self.db.execute("select uid_a, uid_b from duplicates where uid_a=? or uid_b=?", (uid, uid)).fetchall()
        return sorted(r["uid_b"] if r["uid_a"] == uid else r["uid_a"] for r in rows)
