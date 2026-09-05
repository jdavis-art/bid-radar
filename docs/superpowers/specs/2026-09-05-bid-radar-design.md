# Bid Radar — Design Spec

Date: 2026-09-05. Status: approved for planning. Owner: Jason Davis.
Wave 1 of the Sept 2026 portfolio builds.

## 1. Purpose

A scheduled, local pipeline that sweeps public-agency solicitation
sources for modular and affordable-housing work, normalizes every
record into one schema, dedupes across sources, scores each record
against configurable rules, and writes a daily digest. The digest is
what a human (or a vault skill) triages. Nothing in this repo writes
to the CRM.

The hand-run predecessor (`seed/bidnet_pull_legacy.py`) found the City
of Aurora tiny-home RFQ on 2026-09-04 by sweeping 4,237 open
solicitations and scoring 85 of them at 3 or better. Bid Radar makes
that run every morning without a person in the loop and adds two more
sources.

## 2. Scope

### In scope (v1)
- Sources: BidNet Direct (session cookie), PublicPurchase (session
  cookie, vendor registration required), SAM.gov (public API key).
- One normalized `Solicitation` record, SQLite store with first-seen
  and last-seen tracking, cross-source duplicate linking.
- Config-driven scoring that reproduces the legacy scorer exactly on
  the 2026-09-04 sweep, then allows weight changes without code edits.
- Daily markdown and JSON digest, new-since-last-run first.
- Windows Task Scheduler install script and a run log.
- `whoami`, `sweep`, `rescore`, `digest`, `abstract` commands.

### Out of scope (v1)
- Document download and plan-holder registration (the legacy `pull`
  subcommand stays in the vault for that; downloading makes the
  bidder visible to the agency).
- Federal notices behind BidNet's SAML wall (read them from SAM.gov).
- BuildingConnected, private plan rooms, email-only notices.
- CRM writes. A separate vault skill reads the digest and creates
  opportunities through the CRM's MCP with dry run then confirm.
- A web UI. The digest is a markdown file.

## 3. Architecture

```
bid-radar/
  pyproject.toml            # package "bid_radar", console script "bid-radar"
  bid_radar/
    cli.py                  # argparse entry: whoami | sweep | rescore | digest | abstract
    config.py               # load config.yaml, overlay config.local.yaml, env
    model.py                # Solicitation, Sighting, RunLog dataclasses
    normalize.py            # per-source dict -> Solicitation
    dedupe.py               # uid rules + cross-source duplicate linking
    scoring.py              # rule engine driven by config
    store.py                # SQLite schema + upsert/query
    digest.py               # markdown + JSON renderers
    sources/
      base.py               # Source protocol: name, healthcheck(), sweep() -> iter[dict]
      bidnet.py             # ported from legacy: cookie auth, saved searches, row parser
      publicpurchase.py     # ported from legacy scan: region -> agency -> bid list
      samgov.py             # opportunities v2 search, keyword + NAICS + postedFrom
    cookies.py              # parse a "Copy as cURL (bash)" file into headers + cookies
  config.yaml               # public defaults: generic weights, keyword lists, output dir
  config.local.yaml         # gitignored: saved-search ids, tuned weights, output path
  scripts/
    install-task.ps1        # registers "Bid Radar Daily Sweep" in Task Scheduler
    run-sweep.ps1           # what the task runs: sweep + digest, logs to logs/
  tests/
    fixtures/               # sanitized HTML/JSON pages per source
    test_bidnet_parse.py
    test_publicpurchase_parse.py
    test_samgov_parse.py
    test_scoring_regression.py   # exact match to the 2026-09-04 distribution
    test_dedupe.py
    test_digest.py
  seed/                     # gitignored: legacy scripts, the 9/4 sweep JSON
  docs/superpowers/{specs,plans}/
```

Python 3.12+, dependencies: `requests`, `lxml`, `pyyaml`. Tests with
`pytest`. No framework, no async, no browser automation. The `py`
launcher is the interpreter on this machine.

### Source protocol

```python
class Source(Protocol):
    name: str
    def healthcheck(self) -> HealthStatus: ...   # ok | needs_cookie | needs_key | down
    def sweep(self) -> Iterator[dict]: ...        # raw per-source dicts
```

Each adapter owns its own auth failure detection. A login redirect
raises `NeedsCookie(source)`, which the CLI reports as "re-paste the
cURL for <source>" and continues with the other sources. A sweep never
aborts because one source is down; the run log records which sources
ran.

### BidNet adapter

Direct port of the legacy script's verified mechanics (2026-09-04):
explicit `pageNumber`, `pageSize=100`, `selectedSavedSearch=<id>` on
every request; rows are `tr.mets-table-row`; strip `<script>` before
reading text; saved-search ids come from the account page and are
cached in `config.local.yaml`. Result rows carry id, title, agency,
bid type, closing, location, published, blurb, mandatory-prebid flag,
and which saved searches matched.

### PublicPurchase adapter

Region list from `getAgenciesByRegion?region=XX`, then each agency's
`nationalBidList`. Without a vendor cookie every agency answers "No
bids at this time"; the adapter reports `needs_cookie` and yields
nothing rather than pretending the market is empty. Agency and bid
pick-lists from the legacy scan move into `config.yaml`.

### SAM.gov adapter

`GET https://api.sam.gov/opportunities/v2/search` with `api_key` from
`SAM_API_KEY`, `postedFrom` = last successful run minus one day,
`ptype` solicitation and presolicitation and combined synopsis, one
request per configured keyword ("design-build", "modular housing",
"workforce housing", "manufactured housing") plus one per configured
NAICS (236116, 236117, 236220, 321991, 321992). Fields kept: noticeId,
title, department and office as agency, place of performance state as
location, postedDate, responseDeadLine, uiLink, description excerpt
via the description URL only for records that score 3 or higher (the
description endpoint is rate-limited). Public data, no cookie.

### Normalization

`Solicitation` fields: `uid` (`{source}:{source_id}`), `source`,
`source_id`, `title`, `agency`, `location` (two-letter state or full
name normalized to state), `bid_type`, `published` (date),
`closing` (datetime or null), `url`, `blurb`, `mandatory_prebid`,
`extra` (jsonb of source-specific bits such as matched saved
searches). Dates parse from each source's format into ISO; unparseable
dates keep the raw string in `extra` and null the field.

### Dedupe

- Same `uid` on a later sweep: update mutable fields, bump
  `last_seen`, keep `first_seen`.
- Cross-source: normalized title (lowercase, punctuation stripped,
  agency tokens removed) equal AND closing dates within 3 days links
  the records in a `duplicates` table. The digest shows the group
  once, highest score first, with the other sources listed.
- Never delete. A record that stops appearing gets `last_seen` frozen
  and drops out of the open list when `closing` passes.

### Scoring

The rule engine reads `scoring:` from config:

```yaml
scoring:
  exclude_title: [regex, ...]        # score 0, note "excluded: <match>"
  not_housing_title: [regex, ...]    # score 0, note "not housing (<match>)"
  housing: [regex, ...]              # required in title (2) or blurb only (1)
  location_points: {Colorado: 2, Wyoming: 2, California: 1, ...}
  boost: [regex, ...]                # +1 when matched in title or blurb
  federal_note: "federal (CAGE/SAM required)"
```

`score(record, rules) -> (int, note)`. The public `config.yaml` ships
the legacy regexes verbatim (they describe public solicitation
language, not company data). `config.local.yaml` may add, remove, or
reweight. Regression gate: scoring the 4,237 rows in the 2026-09-04
sweep JSON with the shipped config reproduces the legacy distribution
exactly: 4,073 at 0, 77 at 1, 2 at 2, 67 at 3, 14 at 4, 4 at 5. The
fixture for this test is a reduced copy of the sweep (title, agency,
location, bid type, blurb, legacy score) committed to `tests/fixtures/`;
those fields are public solicitation data.

### Store

SQLite at `data/bid-radar.sqlite` (gitignored). Tables:
`solicitations` (one row per uid, all normalized fields, `score`,
`score_note`, `status` in new / seen / dismissed / pursued,
`first_seen`, `last_seen`), `duplicates` (uid_a, uid_b, reason),
`runs` (started, finished, per-source counts and health, error text).
`status` is the only field a human edits, through
`bid-radar mark <uid> dismissed|pursued`.

### Digest

`digest` writes `<output_dir>/bid-radar-<date>.md` and `.json`:

1. Run header: sources that ran, counts, sources that need a cookie.
2. New since last run with score 3 or higher, sorted by score then
   closing.
3. All open with score 3 or higher not already in section 2.
4. Score 1 and 2 as a collapsed count with a link to the JSON.

Each row: score, state, title, agency, closing, source, url, note.
Output dir defaults to `./digest/`; the local config points it at the
vault's scratch folder so the triage skill finds it.

### Scheduling

`scripts/install-task.ps1` registers a daily 7:00 task running
`scripts/run-sweep.ps1`, which activates the venv, runs `sweep` then
`digest`, and appends to `logs/sweep-<month>.log`. Cloud routines
have no egress, so the run is local by design.

## 4. Security and public boundary

- `.gitignore`: `config.local.yaml`, `data/`, `logs/`, `seed/`,
  `digest/`, `.env`, `*.sqlite`, `__pycache__/`.
- Cookie files live in the user profile
  (`~/.bidnet-curl.txt`, `~/.publicpurchase-curl.txt`), never in the
  repo, never logged. `cookies.py` redacts values in any error text.
- `SAM_API_KEY` from env or `.env`.
- Public repo content is the code, the generic config, sanitized
  fixtures, and docs. Saved-search ids, tuned weights, and the store
  stay local.

## 5. Error handling

- Per-source failures are isolated and recorded in `runs`.
- HTTP: 3 retries with backoff on 5xx and timeouts; a 4xx other than
  auth is logged and the page skipped.
- A sweep with zero rows from a source that previously returned rows
  is flagged in the digest header as suspicious, not silently accepted.
- Parser fixtures pin the row markup; a markup change fails the test
  suite before it fails silently in production.

## 6. Testing

- Parser tests per source against saved fixtures.
- Scoring regression against the 9/4 distribution (exact).
- Dedupe tests: same uid update, cross-source link, near-miss (closing
  4 days apart) not linked.
- Digest snapshot test on a fixed store.
- One live smoke command (`bid-radar whoami`) documented for manual
  verification of each source's auth.

## 7. Gates (build session stops at each)

1. Scaffold, config loader, model, store, and the scoring regression
   passing on the fixture. Print the distribution.
2. BidNet adapter live: `sweep` returns the same open count as the
   legacy script on the same day, plus or minus new postings. Print
   per-search counts.
3. SAM.gov adapter live with a real key; PublicPurchase adapter
   reports `needs_cookie` cleanly until a vendor account exists.
4. Digest written to the configured output dir, task installed, one
   scheduled run observed in the log.

## 8. Handoff to the vault

After gate 4 the vault session writes `/bid-radar-triage`, which
reads the newest digest, shows the score 3+ rows, and creates CRM
opportunities through the MCP with dry run then confirm. That skill
is not part of this repo.
