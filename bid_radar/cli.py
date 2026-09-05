"""bid-radar command line."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import traceback
from pathlib import Path

from .config import load_config, resolve_path
from .cookies import redact
from .dedupe import link_duplicates
from .digest import write_digest
from .normalize import normalize
from .scoring import Rules, score
from .sources.base import NeedsCookie, NeedsKey
from .sources.bidnet import BidNetSource, FederalNotice
from .sources.publicpurchase import PublicPurchaseSource
from .sources.samgov import SamGovSource
from .store import Store


def _store(cfg: dict) -> Store:
    return Store(resolve_path(cfg, "data_dir") / "bid-radar.sqlite")


def build_sources(cfg: dict, store: Store, only: list[str] | None = None) -> list:
    sc = cfg["sources"]
    out = []
    if sc["bidnet"].get("enabled", True):
        out.append(BidNetSource(sc["bidnet"]))
    if sc["samgov"].get("enabled", True):
        out.append(SamGovSource(sc["samgov"], last_run=store.last_successful_run()))
    if sc["publicpurchase"].get("enabled", True):
        out.append(PublicPurchaseSource(sc["publicpurchase"]))
    if only:
        out = [s for s in out if s.name in only]
    return out


def run_sweep(cfg: dict, sources: list | None = None, only: list[str] | None = None,
              now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now()
    store = _store(cfg)
    rules = Rules.from_config(cfg["scoring"])
    sources = sources if sources is not None else build_sources(cfg, store, only)
    run_id = store.start_run()
    summary: dict[str, dict] = {}
    errors = []
    for src in sources:
        rows, new = 0, 0
        try:
            for raw in src.sweep():
                sol = normalize(src.name, raw)
                s, note = score(sol, rules)
                if store.upsert(sol, s, note, now):
                    new += 1
                rows += 1
            summary[src.name] = {"rows": rows, "new": new, "health": "ok"}
        except NeedsCookie as e:
            summary[src.name] = {"rows": rows, "new": new, "health": "needs_cookie"}
            errors.append(redact(str(e)))
        except NeedsKey as e:
            summary[src.name] = {"rows": rows, "new": new, "health": "needs_key"}
            errors.append(str(e))
        except Exception as e:  # noqa: BLE001 - a source failing must not stop the sweep
            summary[src.name] = {"rows": rows, "new": new, "health": "down"}
            errors.append(f"{src.name}: {redact(repr(e))}")
            traceback.print_exc()
        print(f"{src.name}: {summary[src.name]}")
    links = link_duplicates(store, store.all_rows())
    print(f"duplicate links added: {links}")
    store.finish_run(run_id, summary, "; ".join(errors) if errors else None)
    store.close()
    return summary


def cmd_whoami(cfg, args):
    store = _store(cfg)
    for src in build_sources(cfg, store, args.only):
        print(f"{src.name}: {src.healthcheck()}")
    return 0


def cmd_sweep(cfg, args):
    run_sweep(cfg, only=args.only)
    return cmd_digest(cfg, args)


def cmd_rescore(cfg, args):
    store = _store(cfg)
    rules = Rules.from_config(cfg["scoring"])
    changed = 0
    for row in store.all_rows():
        sol = store.get(row["uid"])
        s, note = score(sol, rules)
        if s != row["score"] or note != row["score_note"]:
            store.db.execute("update solicitations set score=?, score_note=? where uid=?", (s, note, row["uid"]))
            changed += 1
    store.db.commit()
    print(f"rescored: {changed} rows changed")
    return 0


def cmd_digest(cfg, args):
    store = _store(cfg)
    rules = Rules.from_config(cfg["scoring"])
    since = dt.datetime.fromisoformat(args.since) if getattr(args, "since", None) else _previous_run_start(store)
    md, js = write_digest(store, rules, resolve_path(cfg, "output_dir"), dt.datetime.now(), since)
    print(f"digest: {md}\n        {js}")
    return 0


def _previous_run_start(store: Store) -> dt.datetime | None:
    rows = store.db.execute("select started from runs where finished is not null order by id desc limit 2").fetchall()
    return dt.datetime.fromisoformat(rows[1]["started"]) if len(rows) > 1 else None


def cmd_abstract(cfg, args):
    src = BidNetSource(cfg["sources"]["bidnet"])
    for sid in args.ids:
        try:
            url, fields, description = src.abstract(sid)
        except FederalNotice as e:
            print(f"! {e}")
            continue
        print(f"== {sid}  {url}")
        for k, v in fields.items():
            print(f"  {k}: {v}")
        print("  Description:", description[:1500])
    return 0


def cmd_mark(cfg, args):
    _store(cfg).mark(args.uid, args.status)
    print(f"{args.uid} -> {args.status}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bid-radar")
    p.add_argument("--root", help="project root holding config.yaml")
    p.add_argument("--data-dir", help="override data_dir")
    p.add_argument("--output-dir", help="override output_dir")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("whoami", cmd_whoami), ("sweep", cmd_sweep), ("rescore", cmd_rescore), ("digest", cmd_digest)):
        sp = sub.add_parser(name)
        sp.add_argument("--only", type=lambda s: s.split(","), default=None)
        sp.add_argument("--since", default=None)
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("abstract"); sp.add_argument("ids", nargs="+"); sp.set_defaults(fn=cmd_abstract)
    sp = sub.add_parser("mark"); sp.add_argument("uid"); sp.add_argument("status", choices=["new", "seen", "dismissed", "pursued"]); sp.set_defaults(fn=cmd_mark)
    args = p.parse_args(argv)
    cfg = load_config(Path(args.root) if args.root else None)
    if args.data_dir:
        cfg["data_dir"] = args.data_dir
    if args.output_dir:
        cfg["output_dir"] = args.output_dir
    try:
        return args.fn(cfg, args)
    except (NeedsCookie, NeedsKey) as e:
        print("!", redact(str(e)))
        return 2


if __name__ == "__main__":
    sys.exit(main())
