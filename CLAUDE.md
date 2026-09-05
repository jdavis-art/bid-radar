# Claude Code Operating Context — Bid Radar (Build Session)

You are the **build session** for Bid Radar. A separate supervising
session (the owner's vault) reviews your work gate by gate. Read, in
order:

1. `docs/superpowers/plans/2026-09-05-bid-radar.md` (the build plan; execute it task by task)
2. `docs/superpowers/specs/2026-09-05-bid-radar-design.md` (the design the plan argues from)

## What this is

A local, scheduled Python pipeline that sweeps BidNet Direct,
PublicPurchase, and SAM.gov for modular and affordable-housing
solicitations, normalizes and dedupes them into SQLite, scores them
from a YAML rule set, and writes a daily digest. This repo is
**public**. It never writes to a CRM.

## THE GATE RULE (most important instruction)

The plan has four gates. **At each gate you STOP, print the gate's
required output, and wait.** Do not advance until the supervising
session returns a green light. If a gate result is ambiguous, stop and
report; never paper over it.

## Locked decisions (do not relitigate)

- Python 3.12+, invoked as `py`; venv at `.venv`; deps are `requests`,
  `lxml`, `pyyaml`, `pytest` only.
- The scoring regression must match the 2026-09-04 distribution exactly
  (4,073 / 77 / 2 / 67 / 14 / 4). If it does not, the config or the
  port is wrong, not the fixture.
- A sweep never aborts because one source fails.
- No browser automation. The sites are plain HTML behind a cookie.
- CRM writes happen in the vault, not here.

## Public repo hygiene

- `config.local.yaml`, `data/`, `logs/`, `seed/`, `digest/`, `.env`
  are gitignored. Never `git add -f` any of them. Before every commit
  run `git status` and confirm nothing private is staged.
- Cookie files live in the user profile. Never print their contents.
  Error messages name the path only.
- Fixtures under `tests/fixtures/` must be sanitized: no account
  holder name, email, or session ids. Grep for `@` before committing
  an HTML fixture.
- No company, client, or person names in code, config, README, or
  commit messages. `seed/` holds the private inputs and stays local.

## Seed folder (gitignored, read-only for you)

- `seed/bidnet_pull_legacy.py` — the verified legacy script to port.
- `seed/publicpurchase_scan_legacy.py` — the legacy PublicPurchase scan.
- `seed/bidnet-sweep-2026-09-04.json` — 4,237 scored rows; the
  regression fixture is derived from it by `scripts/make_regression_fixture.py`.

## Working style

- TDD per the plan: failing test, run, implement, run, commit.
- Commit after every task with the message in the plan.
- When you need a cookie paste or an API key, ask the supervisor for
  it in one line and stop; do not guess or fabricate.
- Keep the terminal output at gates short: counts, paths, and the
  `git status` line.
