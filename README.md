# Bid Radar

A local, scheduled Python pipeline that sweeps public-agency solicitation
sources for modular and affordable-housing work, normalizes every record
into one schema, dedupes across sources, scores each record against a
YAML rule set, and writes a daily markdown and JSON digest. Sources in
v1: BidNet Direct, PublicPurchase, and SAM.gov, plus Colorado Prop 123
award lists (applicants and selections, read from the fund's public
WordPress media API; each row is a lead with a 90-day call window,
not a bid). The digest is what a
person triages; nothing here writes to a CRM.

## Install

Python 3.12 or newer. On Windows the `py` launcher is assumed.

```
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e .[dev]
.venv\Scripts\python.exe -m pytest -q
```

Runtime dependencies are `requests`, `lxml`, and `pyyaml`. Tests use
`pytest`.

## Auth handoff

BidNet Direct and PublicPurchase are plain HTML behind a session cookie.
The pipeline reads that cookie from a "Copy as cURL" file in your user
profile. No browser automation is involved.

1. Log in to the site in Chrome.
2. Press F12, open the Network tab, and reload the page.
3. Right-click any request to that site, choose Copy, then
   Copy as cURL (bash).
4. Paste the clipboard into the file for that site:

| Site | Cookie file |
| --- | --- |
| BidNet Direct | `~/.bidnet-curl.txt` |
| PublicPurchase | `~/.publicpurchase-curl.txt` |

Session cookies die when Chrome closes, so paste right before a sweep.
When a cookie is stale the source reports `needs_cookie`, the sweep
continues with the other sources, and the run log records it. Error
messages name the file path only; cookie values are never printed or
logged.

PublicPurchase requires a vendor registration before any agency shows
bids. Without one the source reports `needs_cookie` in the run summary
and the digest rather than pretending the market is empty.

## SAM.gov key

SAM.gov is public data behind a free API key from
[api.data.gov](https://api.data.gov/signup/). Provide it either as the
`SAM_API_KEY` environment variable or as a line in a gitignored `.env`
file at the repository root:

```
SAM_API_KEY=your-key-here
```

The real environment wins over `.env` when both are set. Without a key
the source reports `needs_key` and the sweep continues.

A personal SAM.gov key allows 10 requests per day. The default sweep
spends 9 (one per keyword and one per NAICS code). A 429 ends the
SAM.gov portion of that run with health `rate_limited`, keeps whatever
arrived before it, and skips the remaining queries so the budget is not
spent on refusals. Each run records the per-query yield so the list can
be trimmed after a week of data.

## Local configuration

`config.yaml` holds public defaults: source settings, keyword lists,
and the scoring rules. Private values go in `config.local.yaml`, which
is gitignored and deep-merged over the defaults. Example:

```yaml
output_dir: C:/path/to/your/triage/folder
sources:
  bidnet:
    saved_search_ids: []        # empty = discover every saved search on the account
scoring:
  location_points:
    Colorado: 3                 # reweight without touching code
    Wyoming: 2
    Montana: 1
```

`BID_RADAR_OUTPUT_DIR` in the environment or `.env` overrides
`output_dir` as well.

## Commands

All commands run through the console script installed in the venv.

| Command | What it does |
| --- | --- |
| `bid-radar whoami [--probe]` | Health check every source: `ok`, `needs_cookie`, `needs_key`, `key present`, or `down`. SAM.gov is not called unless `--probe` is passed, since each call spends daily quota. |
| `bid-radar sweep [--only bidnet,samgov]` | Sweep the sources, normalize, score, upsert into SQLite, link duplicates, record the run, then write the digest. |
| `bid-radar rescore` | Re-run the scorer over every stored row after a rule change. |
| `bid-radar digest [--since YYYY-MM-DD]` | Rewrite today's digest without sweeping. |
| `bid-radar abstract <id> [<id> ...]` | Print a BidNet abstract page's fields and description. |
| `bid-radar mark <uid> new\|seen\|dismissed\|pursued` | Set a row's triage status. Dismissed rows leave the open list. |

`--root`, `--data-dir`, and `--output-dir` override the project root,
the SQLite location, and the digest folder for a single invocation.

A sweep never aborts because one source fails. Each source's row count
and health land in the `runs` table and in the digest's Run section. A
source that returns zero rows right after a run that returned rows is
flagged as suspicious in the digest rather than silently accepted.

## Digest

Each run writes `<output_dir>/bid-radar-<date>.md` and `.json`. The
markdown has four sections: the run header with per-source counts and
health, rows new since the previous run with score 3 or higher, every
other open row with score 3 or higher, and a count of open rows scoring
1 or 2. Each row shows score, state, title, agency, closing, source,
link, and a note that carries the scoring reason plus, for BidNet, the
saved searches that found it.

## Scheduling

```
powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1
```

registers a daily 7:00 AM task named "Bid Radar Daily Sweep" for the
current user. It runs `scripts\run-sweep.ps1`, which activates the venv,
runs `bid-radar sweep`, and appends to `logs\sweep-<yyyy-MM>.log`.
Cloud routines have no egress to the cookie-gated sites, so the run is
local by design.

## What is public and what is not

This repository is public. Committed content is the code, the generic
`config.yaml`, sanitized fixtures under `tests/fixtures/`, and the docs.
The following stay on the local machine and are gitignored:

- `config.local.yaml` (saved-search ids, tuned weights, output path)
- `.env` (API keys)
- `data/` (the SQLite store)
- `logs/`, `digest/`
- `seed/` (legacy scripts and the original sweep used to build the fixture)
- cookie files, which live in the user profile, not the repository

## Scoring regression

The scorer is a config-driven port of a hand-run predecessor. The test
suite scores the 4,237 rows of the 2026-09-04 sweep with the shipped
`config.yaml` and requires the exact legacy distribution: 4,073 at 0,
77 at 1, 2 at 2, 67 at 3, 14 at 4, and 4 at 5, with every row's score
and note matching. If that test fails after a config edit, the config
changed the rules; the fixture is the reference.
