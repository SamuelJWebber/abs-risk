# abs-risk handoff

Rewritten **2026-09-14**. Read `CLAUDE.md` first for the rules, then this for what is true now.
**Rewrite this file at the end of every session — never append.** Under 150 lines.

## State

Two tracks. **Cards is concluded. Autos is stalled and is where the work is.**

221 tests green. Published at https://samueljwebber.github.io/abs-risk/ . Public repo.

## Cards — closed, do not re-run

The cross-lender free-riding hypothesis is **closed on public data**, by a pre-specified test whose
classification was registered before ranking and which then went the other way. The real signal inverts the
premise: accounts opened with other lenders in the past 24 months predict *more* default, −371 bps/yr,
monotone, and it survives ex ante. The pool-level version is provably unanswerable here — the detection floor
is about a quarter of the whole Amex/Synchrony gap. See `design/two-tests.html`.

Only borrower-level tradeline data would answer it (NY Fed CCP, a bureau extract, the CFPB panel), where one
household holds both cards. That is an access problem, not a code problem. **Do not re-run these tests.**

## Autos — the live thread

B3, B4 and B5 have been "doing" since 2026-09-08 with real results already in them:

- B3: at 480-620, Exeter ≈20% cumulative charge-off by 24 months, Santander ≈14%, AmeriCredit ≈10%; at
  700-760, Santander 5-10% against captives under 1.5%.
- B4: the lender excess for Exeter and Santander **vanishes once loan terms are controlled** — APR odds ratios
  1.9-11, LTV 1.7-2.6, PTI 1.3-1.8, amount quintiles not significant.
- B5: regression discontinuity at lender cutoffs, first run in progress; publish only if the first stage exists.

A4 (the card residual page) is also open and waits on nothing but time.

## Known bug

`data/cards_monthly.csv` holds **five duplicate trust-months** — bofa 2018-12 and 2020-05, citi 2019-09 and
2019-10, comet 2019-02. Same statement ingested from two filings: identical data, different `source_accession`.
It does not move the headline ratios but it overstates coverage (bofa and citi show 94 months, hold 92) and
breaks month-over-month operations. Needs a dedupe on ingest, with a test.

## Rules that matter here

- **The SEC refuses any User-Agent containing a URL in parentheses.** Accepted form: `<name> <contact-email>`.
  Set `ABSRISK_CONTACT` in the environment; there is no `.env` loader.
- Never hit EDGAR from tests. Save every filing before parsing. Parse by label, never by position.
- **This repo is public.** Read anything an agent generated in bulk before committing it.
