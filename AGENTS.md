# AGENTS.md — abs-risk

**Read `CLAUDE.md` in this directory before doing anything, and follow it.** It is the working agreement for
this project regardless of which assistant is running. `PLAN.md` holds the design, `TASKS.md` the board, and
`design/scout-*.md` the scouting notes that already answered most "how is this filing shaped" questions.

Nothing here replaces CLAUDE.md. The EDGAR rules are repeated because breaking them can get the whole project
blocked, not just the current run.

## EDGAR rules (non-negotiable)

- Every request goes through `absrisk.http.make_session()`: project User-Agent, 5 requests/second cap, retries.
- **Never send a browser User-Agent.** The SEC's edge answers 403 to any User-Agent containing a URL in
  parentheses — verified on a runner 2026-09-08. The accepted form is `<name> <contact-email>`.
- Never scrape faster than the cap. Never hit EDGAR from tests — fixtures only.
- Save every downloaded filing under `data/raw/<track>/<trust-or-deal>/<accession>/` before parsing it.
- Parse by row label or XML element name, **never by position**. Fail loudly on anything unexpected.
- Before writing a parser: download the real file, print its structure, then write the parser and a fixture test.

## What a fresh clone needs

`uv sync` and nothing else, until something touches EDGAR. Then set **`ABSRISK_CONTACT`** to a reachable email
address in the environment (optionally `ABSRISK_NAME` too) — there is no `.env` loader here, so it must be a
real environment variable. Without it the User-Agent names the project but carries no contact, and the SEC
refuses the request. CI already has it as the `ABSRISK_CONTACT` Actions secret.

## This repository is PUBLIC

`SamuelJWebber/abs-risk` is public. Before committing anything under `design/` — especially anything an agent
generated in bulk, such as `design/freeride/` and `workflow-results.json` — read it for personal data, account
identifiers and credentials. Committed: small derived tables under `data/`, `docs/` for the published page,
fixtures under `tests/fixtures/`. Not committed: `data/raw/` (re-downloadable from EDGAR, currently ~3 GB),
`.venv`, `.duckdb` files.

## Settled — do not re-litigate

The cross-lender **free-riding hypothesis is closed** on public data, by a pre-specified test whose
classification was registered before ranking and which then went the other way. The real signal found inverts
the premise: accounts opened with other lenders in the past 24 months predict *more* default (-371 bps/yr,
monotone, holds ex ante). The pool-level version is provably unanswerable here — the minimum detectable effect
is about a quarter of the whole Amex/Synchrony gap. Answering it needs household-level tradeline data
(NY Fed CCP, a bureau extract, or the CFPB panel), which is an access problem, not a code problem.
See `design/two-tests.html`. Do not re-run these tests; extend the auto track (B3-B5) instead.

## Known open bug

`data/cards_monthly.csv` holds **5 duplicate trust-months** (bofa 2018-12 and 2020-05, citi 2019-09 and
2019-10, comet 2019-02) — the same statement ingested from two filings, identical data, different
`source_accession`. It does not move the headline ratios but it overstates coverage and breaks
month-over-month operations. Needs a dedupe on ingest, with a test.
