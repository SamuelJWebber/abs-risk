# Cards build notes: A1 (10-D fetcher and parser) and A2 (prospectus composition)

Written 2026-09-08 against the scouted filings under `data/raw/scout/edgar/cards/` (design/scout-cards.md).
Code: `src/absrisk/cards/` (`fetch.py`, `parse.py`, `composition.py`, `tables.py`, `edgar.py`).
Fixtures: `tests/fixtures/cards/<slug>/<accession>/` (six July-2026 10-Ds, filed 2026-08-17) and
`tests/fixtures/cards/<slug>/prospectus/<accession>/` (seven latest 424Bs). Tests: `tests/test_cards_*.py`.

    python -m uv run python -m absrisk.cards fetch [--trust amex] [--since 2019-01-01] --raw data/raw/cards [--force] [--limit N]
    python -m uv run python -m absrisk.cards parse --raw data/raw/cards --out data/cards_monthly.csv
    python -m uv run python -m absrisk.cards composition --raw data/raw/cards --out data/cards_composition.csv --crosswalk crosswalks/fico_buckets.csv

`fetch` needs EDGAR and therefore a GitHub Actions runner (PLAN.md section 5, `absrisk.http.make_session()`,
`ABSRISK_CONTACT` set). `parse` and `composition` read local files only; both accept the scout layout
(`<slug>/10D/<accession>/`, `<slug>/prospectus/<accession>/`) as well as the fetcher's (`<slug>/<accession>/`).

## 1. Fetcher (`fetch.py`, `edgar.py`)

- Trust register (issuing-entity CIKs, not depositors): amex 0001003509, comet 0001163321, chase 0001174821,
  citi 0001108348, synchrony 0001724789, bofa 0001128250.
- Listing: `data.sec.gov/submissions/CIK<cik>.json`, recent page plus every page in `filings.files` whose
  `filingTo` reaches past `--since` (Chase, Citi and BofA have older pages, all ending before 2009, so none is
  fetched for 2019+). Forms kept: 10-D and 10-D/A. The list is saved as `<slug>/filings_10D.json`.
- Per filing: `index.json` (document list) and `<accession>-index-headers.html` (exhibit TYPE per file,
  `<PERIOD>`), then every `.htm/.html/.txt` document except index pages and the full-submission
  `<accession>.txt` (it repeats every exhibit; 2.4 MB for Amex). Images, PDFs and XML are not fetched.
- `manifest.json` per filing: slug, trust, cik, form, accession, filing_date, period (from `<PERIOD>`, falling
  back to EDGAR's reportDate), primary_document, folder URL, files [name, exhibit type, size, sha256], fetched.
- Idempotent: a directory whose manifest lists every file at the recorded size is skipped without a request;
  `--force` re-downloads. One failing filing is recorded in `fetch_summary.json` and does not stop the run.
- Prospectus: newest 424B5/424B2/424B3/424B7 on the trust's own submissions, primary document only, into
  `<slug>/prospectus/<accession>/` with the same manifest shape.
- Filer-agent switches (Amex Dec-2025, BofA Oct-2025, Synchrony Nov-2019) rename exhibits; nothing depends on
  a file name. The parser identifies exhibits by their text (section 2) and the manifest records the SEC
  exhibit type for reference only.

### Runner expectations

The submissions JSONs list 92 10-Ds per trust from 2019-01-01 to 2026-08-17 (one per month), 552 in all
for the six live trusts (the "about 1,350" in the task brief is not what the submissions API shows; the
count is printed at the start of each trust's run). Requests per filing: 2 index pages plus 2 to 4
documents, about 3,000 requests in total; at the 5 requests/second cap that is 10 minutes of pure
throttle, realistically 15 to 25 minutes with latency. Bytes: Amex about 2.5 MB per filing (the servicer
certificate carries a block for every outstanding series), the others 0.2 to 0.6 MB, roughly 400 MB in
total. Older exhibits (pre-2020 filer agents) have not been seen from this machine; the parser fails loudly
per filing and `parse` prints the failures and a trust x year coverage table, so the first full run is
also the audit of which years need label variants.

## 2. Parser (`parse.py`): one `cards_monthly` row per filing

Rules: exhibit found by content, every number by row label, rates as fractions, the trust's printed rate
kept and recomputed from the dollar rows (agreement within 1e-4 or the filing fails), `row_labels_json`
carrying labels, printed and recomputed values, inputs, null reasons and every check.

| field | rule |
|---|---|
| period_end | from the exhibit's own period sentence; cross-checked to the same month as EDGAR's `<PERIOD>` |
| receivables_principal | ending principal receivables (every trust prints it) |
| gross_co_rate, net_co_rate | the trust's printed annualised rates; recomputed from dollars where printed |
| co_basis / co_annualisation | see the table below; never mixed across trusts downstream |
| payment_rate | principal collections over beginning principal receivables where the trust prints such a rate |
| yield | the trust's gross yield (finance charge collections based, before credit losses); portfolio yield in `inputs` |
| delinq_30plus_share, delinq_90plus_share | dollar buckets over the trust's own denominator; mapping below |
| excess_spread | the trust's excess spread percentage where one exists at trust or sole-series level |
| source_file | the pool exhibit; Chase lists the pool and series exhibits joined by `;` |

### Per trust

**Amex** (exhibit: document containing "Trust Totals", "Annualized Default Rate, Net of Recoveries" and
"Monthly Payment Rate"; EX-99.01 today). Period: "covers activity from ... through July 31, 2026". Trust
block labels: "Number of days in Monthly Period", "Beginning Principal Receivable Balance...", "Ending
Principal Receivables Balance", "Ending Total Receivables", "Defaulted Amount", "Recoveries", "Total
Collections of Finance Charge Receivables", "Total Collections of Principal Receivables", "Monthly Payment
Rate", "Annualized Default Rate", "Annualized Default Rate, Net of Recoveries", "Trust Portfolio Yield".
Basis: ending principal receivables, x365/days (Defaulted Amount x 365/31 / ending principal = 1.8640%,
exactly; x12 on beginning would give 1.8817%). Delinquency: section D buckets 31-60/61-90/91-120/120+ as
dollar shares of Ending Total Receivables (the table header says so); 30+ = the trust's "Total 30+ Days
Delinquent" row, 90+ = 91-120 + 120+; both exact under Amex's own day count. Gaps: the payment-rate and
yield denominators are not printed (13.21B / 50.7944% implies beginning total receivables of 26.01B);
excess spread is printed per series only (base rates differ by series), so `excess_spread` is null.

**COMET** (exhibit: "CAPITAL ONE MASTER TRUST (RECEIVABLES)" and "Annualized Default Rate"; EX-99.1).
Period: "MONTHLY PERIOD: July 2026" -> month end. Labels: "Beginning of the Month Principal Receivables",
"Additional Principal Receivables" (added to form the "Adjusted Beginning" denominator), "End of the Month
Principal Receivables", "End of the Month Total Receivables", "Defaulted Accounts during the Month",
"Recoveries of Charged-Off Accounts during the Month", "Defaulted Accounts, net of Recoveries, during the
Month", "Annualized Default Rate as a Percent of Adjusted Beginning...", "Annualized Net Default Rate...",
"Collections of Principal Receivables and Principal Payment Rate...", "Collections of Finance Charge
Receivables and Annualized Yield...". Basis: adjusted beginning principal, x12 (recomputed 2.9601% vs
2.96%). Delinquency: 30-59/60-89/90-119/120-149/150+ dollars over End of the Month Total Receivables; 30+ =
"Total 30+ Days Delinquent" (checked against the printed 1.62%), 90+ = 90-119 + 120-149 + 150+; exact.
Gap: no excess spread percentage, base rate or portfolio yield anywhere in the 10-D (only the dollar
"Current Month Excess Spread Amount" in EX-99.2, kept in `inputs`); `excess_spread` null.

**Chase** (pool exhibit: "Asset Pool One" and "Losses and Recoveries", EX-99.2; series exhibit:
"CHASEseries", "Excess Spread Percentage", "Principal Payment Rate", EX-99.3). Period: "Monthly Period:
July 2026". Pool labels: "Principal Receivables" (beginning | ending), "Average Pool Balance (2)", "Gross
Losses (3)", "Recoveries (4)", "Net Losses (5)", "Gross Losses as a Percentage of Average Pool Balance
(Annualized)", "Net Losses as a percentage of Average Pool Balance (Annualized)", "...Collections of
Principal Receivables received by Asset Pool One...". Basis: average pool balance (equal to beginning
principal this month), x12. Series exhibit, section C, column headed by the period month: "Yield - Finance
Charge, Fees & Interchange" (yield), "Principal Payment Rate", "(a) - (b) = Excess Spread Percentage";
"(a) Portfolio Yield", "(b) Base Rate" and "Less: Net Credit Losses" kept in inputs (the last is checked
equal to the pool net loss rate). Delinquency: item 10 buckets 30-59 ... 180+ over the item's own "Pool
Balance" row (principal + finance charge + fee receivables, 11.88B); 30+ = the TOTAL row, 90+ = 90-119 +
120-149 + 150-179 + 180+; exact. Note: recoveries are an allocated share of managed-portfolio recoveries
(footnote 4), not pool-specific.

**Citi** (exhibit: "Portfolio Yield for the Collateral Certificate" and "Credit Loss Component"; EX-99).
Period: "Due Period ending July 28, 2026" (EDGAR's reportDate is the same date; Citi's month ends around
the 28th, so `period_end` is not a calendar month end). Labels: "1. Portfolio Yield for the Collateral
Certificate" with sub-rows "Yield Component" (yield) and "Credit Loss Component" (gross_co_rate), "3. Total
Payment Rate" (inputs), "4. Principal Payment Rate", "Principal Receivables Beginning/Average/End of Due
Period", "Finance Charge Receivables - End of Due Period", "Investor Default Amount", "4. Surplus Finance
Charge Collections" (excess_spread, actual basis). Basis: `co_basis = invested_amount` (the collateral
certificate invested amount, pro rata to the pool), `co_annualisation = actual_365` over the due period
(33 days here; the day count is read from the footnote sentence "from June 26, 2026 to July 28, 2026, 33
days" into inputs). Gross vs net: inferred gross (recoveries are credited to collections, prospectus Annex
I); `net_co_rate` null with that reason. No dollar pool charge-off row exists, so no recompute; the only
identity checked is Portfolio Yield = Yield Component - Credit Loss Component. Delinquency: item 6 buckets
1-30/31-60/61-90/91-120/121-150/151-180 dollars over the sum of "Current" and all buckets (the footnote
says the percentages are of that aggregate, and it reproduces every printed percentage); 30+ = 31+ and 90+
= 91+, both flagged NEAREST CUT in `delinq_basis`; no 180+ bucket (charged off at 180).

**Synchrony** (exhibit: "Gross Charge-Off Rate" and "BOP Aggregate Principal Receivables"; EX-99.1).
Period: "Monthly Period Ending: | 07/31/2026". Rate rows are a header ("c. Gross Charge-Off Rate (Default
Amount for Defaulted Accounts / BOP Principal Receivables)") followed by "i. Current"; the parser takes the
Current sub-row. Labels: "BOP Aggregate Principal Receivables", "EOP Aggregate Principal Receivables", "BOP
Total Receivables", "EOP Total Receivables", "a. Gross Trust Yield (...)" (yield), "b. Payment Rate (...)",
"c. Gross Charge-Off Rate (...)", "d. Net Charge-Off Rate (...)", "e. Default Amount for Defaulted
Accounts", "f. Recovery Amount", "g. Net Charge-Off (...)", "c. Principal Collections" (Trust column),
"(a) Portfolio Yield", "(b) Base Rate", "(a)- (b) = Excess Spread Percentage" (current column by month
header). Basis: BOP principal, x12 (label does not say annualised; Default Amount x 12 / BOP reproduces
5.3437% exactly). Delinquency: j. buckets 1-29/30-59/60-89/90-119/120-149/150-179/180+ dollars over EOP
Total Receivables (matches "Pctg. of Tot. Recv." to four decimals); 30+ from 30-59 up, 90+ from 90-119 up;
exact.

**BofA** (exhibit: "MONTHLY CERTIFICATEHOLDERS' STATEMENT" and "Charge-Offs as a percentage of Average
Principal Receivables Outstanding"; EX-99.1). Period: "MONTHLY PERIOD ENDING July 31, 2026". Pool loss table
"Principal Charge-Off Experience (Dollars in Thousands)": two copies (current | prior month, and two
months earlier); the copy whose date header carries the period-end date is used, column by month header.
Labels: "Average Principal Receivables Outstanding", "Total Charge-Offs", "Total Charge-Offs as a
percentage of Average Principal Receivables Outstanding", "Recoveries", "Net Charge-Offs", "Net Charge-Offs
as a percentage of ...". Basis: average daily principal receivables, x12 (32,369 x 12 / 14,183,450 =
2.7386% vs printed 2.74%). Other labels: item 2 "(b)/(l) ... Principal Receivables ... beginning / end",
"(a)/(k) ... Receivables ... beginning / end" (total), "(f) Collections of Principal Receivables as a
percentage of prior month Principal Receivables" (payment_rate), "(i) Total Cash Yield ..." (yield, includes
recoveries, on the Series 2001-D floating allocation investor interest), "(m) The Portfolio Yield ...", "(n)
Base Rate ...", "(o) Excess Available Funds Percentage ..." (excess_spread), "(k)/(l) Aggregate Class D
Investor Default Amount [net of Recoveries] ... as a percentage of ... Investor Interest" (the second,
investor-interest-based loss pair, kept in inputs). Delinquency: item 6 buckets 30-59 ... "180 - or more
days" (the dash is served by EDGAR as `&#8211;`, normalised) as dollar shares of total Receivables at month
end (item 2(k); it reproduces the printed "(b) 60+-Day Delinquency Rate" 0.90% and the bucket percentages
within 0.01 pp, one bucket off by 0.008 pp from rounding on the SEC side); 30+ = all buckets, 90+ from
90-119 up; exact.

### Charge-off bases (never mixed downstream)

| trust | gross row | net row | co_basis | co_annualisation | recompute check (July 2026) |
|---|---|---|---|---|---|
| amex | Annualized Default Rate | Annualized Default Rate, Net of Recoveries | ending | x365_over_days | 1.8640 / 1.1114 exact |
| comet | Annualized Default Rate as a Percent of Adjusted Beginning... | Annualized Net Default Rate ... | beginning | x12 | 2.9601 vs 2.96; 1.7978 vs 1.80 |
| chase | Gross Losses as a Percentage of Average Pool Balance (Annualized) | Net Losses as a percentage of Average Pool Balance (Annualized) | average | x12 | 2.0248 vs 2.02; 1.5846 vs 1.58 |
| citi | Credit Loss Component (of Portfolio Yield for the Collateral Certificate) | none | invested_amount | actual_365 | none (no dollar row) |
| synchrony | Gross Charge-Off Rate (... / BOP Principal Receivables) | Net Charge-Off Rate (...) | beginning | x12 | 5.3437 / 4.1142 exact |
| bofa | Total Charge-Offs as a percentage of Average Principal Receivables Outstanding | Net Charge-Offs as a percentage of ... | average | x12 | 2.7386 vs 2.74; 2.1313 vs 2.13 |

### Delinquency mapping

| trust | buckets (days) | denominator | 30+ | 90+ |
|---|---|---|---|---|
| amex | 31-60, 61-90, 91-120, 120+ | Ending Total Receivables | Total 30+ row (exact) | 91-120 + 120+ (exact) |
| comet | 30-59, 60-89, 90-119, 120-149, 150+ | End of the Month Total Receivables | Total 30+ row (exact) | 90-119 + 120-149 + 150+ (exact) |
| chase | 30-59, 60-89, 90-119, 120-149, 150-179, 180+ | item 10 Pool Balance (total receivables) | TOTAL row (exact) | 90-119 + ... + 180+ (exact) |
| citi | 1-30, 31-60, 61-90, 91-120, 121-150, 151-180 | Current + all buckets | 31+ (NEAREST CUT) | 91+ (NEAREST CUT) |
| synchrony | 1-29, 30-59, ..., 150-179, 180+ | EOP Total Receivables | 30-59 and up (exact) | 90-119 and up (exact) |
| bofa | 30-59, ..., 150-179, 180+ | total Receivables at month end, item 2(k) | all buckets (exact) | 90-119 and up (exact) |

Every printed bucket percentage and every printed 30+/60+ rate is checked against the dollar-based share
within 1e-4 (0.01 pp); the shares written to the CSV are the dollar-based ones.

## 3. Composition (`composition.py`)

- Tables are found by their header row: first cell matching FICO / VantageScore / Credit Score, Credit Limit,
  or Account Age / Age of Accounts / Age Range / Age, with at least two "receivables" or "accounts" column
  headers and at least three data rows. Column roles from the header text (number of accounts, % of
  accounts, receivables amount, % of receivables). Chase's FICO table carries "As of March 31, 2026" inside
  the table; every other as-of date is the last "as of <date>" in the text preceding the table (Citi: FICO
  as of 2025-03-30, credit limit and age as of 2025-03-26, as the prospectus says).
- Bucket labels to integer edges (`parse_bucket`): "Less than 560" -> (null, 559); "Less than or equal to
  600" -> (null, 600); "601-660"; "Greater than 720" / "Over 720" -> (721, null); "720 and above" -> (720,
  null); "801+"; amounts with cents use lo = ceil, hi = floor ("$1,500.01-$5,000.00" -> 1501..5000, "Less
  than $1,000.99" -> ..1000); months "Over 6 Months to 12 Months" -> (7, 12). Unscored rows ("No score",
  "000", "Unscored", "Refreshed FICO Unavailable"), Amex's "Other" and "No Pre-Set Spending Limit" rows
  are (null, null) with the reason in `sample_note`. Synchrony's "No score and/or less than or equal to
  599" is (null, 599) flagged `includes_unscored`.
- Shares are amount / total-row amount (checked: buckets sum to the total within 1e-6, printed percentage
  within 0.2 pp, since one-decimal tables are shaved to sum to 100.0). Discover's seasoning table prints
  percentages only; those are used as shares. Subtotals (Amex "Total (Credit Card)") are skipped.
- COMET publishes every table twice (Consumer, Small Business); the segment is the nearest preceding
  heading, the two are combined by summing amounts and accounts (consumer 92.2% of receivables), and the
  note says so. Segment tables are available from `extract_tables()` if the split is ever wanted.
- Discover is included from its 2023-06-23 prospectus and marked STALE (defeased 2025-12-18, amounts in
  $000s). Chase carries the 5% random-sample note; Synchrony `score_type = VantageScore`.

Result on the seven prospectuses on disk: 153 rows (fico / credit_limit / account_age buckets: amex 6/9/8,
comet 5/4/7, chase 5/7/8, citi 11/14/7, discover 5/4/6, synchrony 4/12/12, bofa 5/6/8), committed as
`data/cards_composition.csv`; the test suite regenerates it from the fixtures and compares.

### Crosswalk (`crosswalks/fico_buckets.csv`, 41 rows)

One row per (trust, FICO bucket) with six weight columns `w_deep_subprime ... w_superprime`, a `rule`
column and `flags`. Rule: uniform in score over the bucket, open ends clamped to 300 / 850 (weight = tier
points in the bucket / bucket width); unscored buckets weight zero and tier shares renormalised over scored
receivables. Flags: `straddle` (bucket crosses a tier edge), `one_point_offset` (COMET/BofA 601-660 and
661-720, Citi 640-660 and 760-800: one point over the edge), `unscored`, `includes_unscored` (Synchrony),
`amex_nonstandard_buckets`, `vantagescore`, `sample_5pct`, `stale_2023`. Every trust straddles somewhere:
the four-band tables split 600-659 across subprime and near-prime and 720+ across prime-plus and
superprime, so the six CFPB tiers are a stated assumption for every trust, not a measurement. Tier shares
under the crosswalk (receivables basis, July-2026 prospectus set): superprime 0.19 (synchrony) to 0.31
(amex/chase); deep subprime 0.017 (chase) to 0.058 (synchrony).

## 4. Schema notes and deviations

- `cards_monthly` is exactly analysis-plan 3a. `co_basis` takes a fourth value, `invested_amount`, for Citi
  (the collateral certificate invested amount; "beginning" would be an inference). `source_file` joins two
  file names with `;` for Chase.
- `cards_composition` is analysis-plan 3b plus a trailing `bucket_label` column (verbatim row label) so a
  reader can match a row to the prospectus and the crosswalk joins on it.
- `data/cards_monthly.csv` is not written yet: the six July-2026 rows parse (see the test suite) but the
  history needs the runner; writing a six-row file would misstate coverage.

## 5. Known gaps

- Amex: no printed denominators for payment rate and yield; no trust-level excess spread.
- COMET: no excess spread percentage, base rate or portfolio yield.
- Citi: no net charge-off rate, no dollar charge-off row, gross status inferred; due period not a calendar
  month; 30+/90+ are 31+/91+.
- Chase: FICO composition is a sample; recoveries are an allocation, not pool recoveries.
- BofA: charge-off table in $ thousands; one delinquency bucket percentage disagrees with its dollars by
  0.008 pp (SEC-side rounding), inside the 1e-4 check.
- Back history: only the August-2026 filings have been seen; label variants in older filings (before the
  filer-agent switches) will surface as per-filing parse errors on the first runner pass.
