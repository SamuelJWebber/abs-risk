# Scout: public credit card master trust data on EDGAR

Written 2026-09-08. Status: **complete for the seven trusts** (sections A-D verified against raw filings; see Provenance).

## Provenance

- All raw files cited below live under `data/raw/scout/edgar/cards/<slug>/` (repo root `C:\Users\samwe\code\abs-risk`), fetched by the coordinator from a GitHub Actions runner on 2026-09-08 05:30-05:31Z (157 downloads, 0 errors; URL-to-path manifest at `data/raw/scout/edgar/manifest.json`). Paths below are written relative to `data/raw/scout/edgar/`. Slugs: amex, comet, chase, citi, discover, synchrony, bofa. Per slug: `submissions_<cik>.json` (EDGAR submissions API), `fts_10D.json` (full-text search 2025-2026), `10D/<accession>/` (latest 10-D: primary doc, every exhibit, full `.txt` submission, `index.json`), `prospectus/<accession>/<file>.htm`.
- This machine's own IP is on Akamai's blocklist for sec.gov (home ISP CGNAT; every host returned 403 "Undeclared Automated Tool"), so nothing was fetched from here. Before the runner artifact arrived, an interim version of this file was built from LLM-rendered fetches; every number in that version has now been re-checked against the raw files. Items marked **verified** matched the raw file exactly; items marked **corrected** or **added** did not exist or were wrong in the rendering.
- Helper scripts (read-only over the raw files, not parsers): `data/raw/scout/cards/_scripts/print_rows.py` (writes `<slug>/_rows.txt` = every table row mentioning receivables/charge-offs/defaults/losses/recoveries/payment rate/yield/delinquency/excess spread/base rate; the `_rows.txt` files are in place), `print_tables.py` (writes `<prospectus>.tables.txt` with every table mentioning FICO / credit limit / account age / seasoning / VantageScore; in place next to each prospectus), `ctx.py` (grep text lines with context), `tblctx.py` (text before/after a table index), `fetch_cards.sh` (the original direct-curl list; reference only).

## Trust register (CIKs)

Source: `<slug>/submissions_<cik>.json` `name` / `formerNames` fields, plus the co-registrant lists in `<slug>/10D/<accession>/<accession>-index-headers.html`.

| Trust | Issuing-entity CIK | Other filers on the same 10-D (CIK) | Notes |
|---|---|---|---|
| American Express Credit Account Master Trust | 0001003509 | American Express Receivables Financing Corp III LLC 0001283434 (depositor); Corp IV LLC 0001283435 and Corp II 0000949349 appear on older filings | |
| Capital One Multi-asset Execution Trust (COMET) | 0001163321 | Capital One Master Trust 0000922869; Capital One Funding, LLC 0001162387 (depositor) | COMET's own submissions JSON was not fetched; the 922869 and 1162387 JSONs list the same 10-Ds |
| Chase Issuance Trust | 0001174821 (former name BANK ONE ISSUANCE TRUST) | Chase Card Funding LLC 0001658982 (depositor since 2016) | |
| Citibank Credit Card Issuance Trust | 0001108348 | Citibank Credit Card Master Trust I 0000921864; Citibank, N.A. as depositor 0001522616 | one EX-99 covers both trusts |
| Discover Card Execution Note Trust (DCENT) | 0001407200 | Discover Card Master Trust I 0000894329; Discover Funding LLC 0001645731 (depositor) | notes defeased 2025-12-18 (see B5) |
| Synchrony Card Issuance Trust (SCIT) | 0001724789 | Synchrony Card Funding, LLC 0001724786 (depositor) | predecessor trust: Synchrony Credit Card Master Note Trust 0001290098 (ex GE Capital Credit Card Master Note Trust), separate pool |
| BA Credit Card Trust | 0001128250 (former name MBNA CREDIT CARD MASTER NOTE TRUST) | BA Credit Card Funding, LLC 0001370238; BA Master Credit Card Trust II 0000936988 | |

## A. 10-D cadence, counts, latest and earliest filings

Counts computed from `filings.recent` in each `submissions_<cik>.json` (form in {10-D, 10-D/A}, filingDate >= 2024-01-01). All seven file one 10-D per month on or about the 15th-17th (Discover 12th-17th); no 10-D/A inside the window for any trust.

| Trust (JSON used) | 10-D since 2024-01-01 | Latest 10-D (filingDate, accession, reportDate) | Earliest 10-D on EDGAR | Total 10-D on recent page |
|---|---|---|---|---|
| Amex (`amex/submissions_0001003509.json`) | 32 | 2026-08-17, 0001104659-26-097714, period 2026-07-31 | 2006-07-17, 0001125282-06-004108 (`b414012_10d.txt`, period 2006-06-25) | 243 (1 x 10-D/A, outside window) |
| COMET (`comet/submissions_0000922869.json`, `..._0001162387.json`) | 32 | 2026-08-17, 0001163321-26-000025 | 2006-02-10, 0001104659-06-007479 [from the browse-edgar list fetched earlier; the COMET CIK 1163321 JSON was not downloaded - the Master Trust 922869 JSON only starts listing 10-Ds at 2011-07-15 because before then the 10-D was filed under the COMET CIK alone] | 133 (922869) |
| Chase (`chase/submissions_0001174821.json`) | 32 | 2026-08-17, 0001193125-26-353171 | 2006-03-16, 0001193125-06-056653 [browse-edgar list; the JSON's recent page stops at 2008-01-15 and its older page `CIK0001174821-submissions-001.json` (2002-06-17..2008-01-13, 432 filings) was not fetched] | 224 on recent page |
| Citi (`citi/submissions_0000921864.json`, `..._0001108348.json`) | 32 | 2026-08-17, 0001193125-26-353756 | 2006-04-17, 0000839947-06-000058 (`it032806t.txt`, Master Trust I JSON); Issuance Trust JSON recent page starts 2006-05-15 (older page not fetched) | 255 (10 x 10-D/A, all pre-2024) |
| Discover (`discover/submissions_0001407200.json`) | 32 (pool data stops with the 2025-12-15 filing - see B5) | 2026-08-17, 0001407200-26-000026 | 2007-08-15, 0001407200-07-000004 (`dcent10-dcover081507.htm`) | 230 |
| Synchrony (`synchrony/submissions_0001724789.json`) | 32 | 2026-08-17, 0001104659-26-097449 | 2018-10-15, 0001144204-18-053747 (`tv504564_10d.htm`) | 95 (complete history) |
| BofA (`bofa/submissions_0001128250.json`) | 32 | 2026-08-17, 0001140361-26-033313 | 2006-03-15, 0001128250-06-000010 (`mot-10d.htm`) | 249 (3 x 10-D/A, pre-2024) |

Filer-agent changes that change exhibit file names: Amex RR Donnelley (0001193125-) to Toppan Merrill (0001104659-) Dec-2025; BofA self-filed (0001128250-) to Broadridge (0001140361-) Oct-2025; Synchrony Vintage (0001144204-) to Toppan (0001104659-) Nov-2019.

## B. Latest 10-D (filed 2026-08-17 for all seven): documents, format, exact row labels and July-2026 values

Every label below is copied from the raw exhibit (via `_rows.txt` / `ctx.py`). "|" separates table cells as they appear.

### B1. American Express Credit Account Master Trust - accession 0001104659-26-097714
Files (`amex/10D/0001104659-26-097714/`): `tm2623074d1_10d.htm` 24,403 B (primary); `tm2623074d1_ex99-01.htm` 2,442,373 B = EX-99.01 "MONTHLY SERVICER'S CERTIFICATE / AMERICAN EXPRESS TRAVEL RELATED SERVICES COMPANY, INC. / AMERICAN EXPRESS CREDIT ACCOUNT MASTER TRUST". Format: HTML tables (one giant file: a trust block, then a per-series block for every outstanding series). Period: "This Certificate relates to the Distribution Date occurring on August 17, 2026 and covers activity from July 01, 2026 through July 31, 2026." "Number of days in Monthly Period | 31".
Trust-level block "A. Trust Activity / Trust Totals" (appears once, at the top) - all **verified**:
- "Beginning Principal Receivable Balance, including any Additions, Removals, or Adjustments of Principal Receivables during the Monthly Period | 25,169,022,223.30"
- "Finance Charge Collections (excluding Recoveries) | 702,036,589.98"; "Recoveries | 15,935,939.02"; "Total Collections of Finance Charge Receivables | 717,972,529.00" (**added**)
- "Total Collections of Principal Receivables | 13,210,591,321.12" (**added**)
- "Monthly Payment Rate | 50.7944 | %"
- "Defaulted Amount | 39,467,785.90"
- "Annualized Default Rate | 1.8640 | %"
- "Annualized Default Rate, Net of Recoveries | 1.1114 | %"
- "Trust Portfolio Yield | 31.7408 | %"
- "Ending Principal Receivables Balance | 24,930,085,370.00"; "Ending Total Receivables | 26,171,740,833.37"
Delinquency table (section D, columns "Dollar Amount | Receivables | Number of Accounts | Number of Accounts" i.e. $ / % of receivables / # accounts / % of accounts) - **verified**, account columns **added**:
- "31-60 Days Delinquent | 52,914,095 | 0.20 | % | 6,669 | 0.05 | %"; "61-90 Days Delinquent | 40,305,716 | 0.15 | % | 4,333 | 0.04 | %"; "91-120 Days Delinquent | 32,094,421 | 0.12 | % | 3,301 | 0.03 | %"; "120+ Days Delinquent | 45,924,272 | 0.18 | % | 4,844 | 0.04 | %"; "Total 30+ Days Delinquent | 171,238,503 | 0.65 | % | 19,147 | 0.16 | %"
"Loss Experience:" block (immediately after the delinquency table) - **added**: "Ending Principal Receivables Balance | 24,930,085,370.00"; "Defaulted Amount | 39,467,785.90"; "Recoveries | 15,935,939.02"; "Net Default Amount | 23,531,846.88"; "Annualized Default Rate | 1.86 | %"; "Annualized Recovery Rate | 0.75 | %"; "Annualized Default Rate, Net of Recoveries | 1.11 | %"; "Number of Accounts Experiencing a Loss | 6,816"; "Average Net Default Amount per Account Experiencing a Loss | 3,452.44".
Per-series blocks (one per series; rendering's attribution **verified**): Series 2023-2 shows "Series Adjusted Portfolio Yield | 31.8412 | %", "Base Rate | 6.4400 | %", "Excess Spread Percentage | 25.4648 | %"; Series 2012-A shows 31.7408 / 6.0132 / 26.4444; section "O. Yield and Base Rate" gives "Three Month Average Base Rate" and "Three Month average Series Adjusted Portfolio Yield".
Charge-off basis (B-3 item): the certificate prints no formula. Arithmetic: 39,467,785.90 x 365/31 / 24,930,085,370.00 = 1.8640% exactly; 23,531,846.88 x 365/31 / 24,930,085,370.00 = 1.1114%; 15,935,939.02 x 365/31 / 24,930,085,370.00 = 0.7526% (printed 0.75). So **Amex annualizes by 365/days-in-period and divides by ENDING principal receivables**, gross ("Defaulted Amount") and net of recoveries both given. (x12 on beginning principal would give 1.8817%.) The prospectus loss table uses a different base: "Average principal receivables outstanding for each indicated period is the average of the month-end principal receivables balances for that period" and "Under the pooling and servicing agreement, recoveries are treated as collections of finance charge receivables. Total net charge-offs are an amount equal to total gross charge-offs minus total recoveries" (`amex/prospectus/0001193125-25-160041/d938411d424b5.htm`, Annex I "Loss Experience of the Trust Portfolio"). Payment-rate and yield denominators are not printed either (13,210,591,321.12 / 50.7944% implies a $26.01B base, i.e. beginning total receivables, which the certificate does not print).

### B2. Capital One Multi-asset Execution Trust - accession 0001163321-26-000025
Files (`comet/10D/0001163321-26-000025/`): `form10-djuly2026.htm` 31,007 B (primary); `exhibit9912002-ccjuly2026.htm` 151,134 B = EX-99.1 monthly statement for Capital One Master Trust Series 2002-CC (the pool report); `exhibit992nhsjuly2026.htm` 384,102 B = EX-99.2 "Card Series Schedule to Monthly Noteholders' Statement". Format: both HTML tables (**corrected**: the rendering called EX-99.1 "plain text"; it is an HTML table with numbered rows). Period: July 2026, Distribution Date August 17, 2026.
EX-99.1 section "A) CAPITAL ONE MASTER TRUST (RECEIVABLES)" - **verified**:
- "1) | Beginning of the Month Principal Receivables | $ | 23,403,238,504.06"; "5) | Beginning of the Month Total Receivables | 9,133,325 | $ | 23,697,540,590.71" (account count column, **added**)
- "15) | End of the Month Principal Receivables | $ | 23,264,569,372.71"; "19) | End of the Month Total Receivables | 9,091,686 | $ | 23,558,216,188.81"
Section "B) CAPITAL ONE MASTER TRUST (DELINQUENCIES AND LOSSES)", columns "ACCOUNTS | RECEIVABLES" - **verified**, rows 7-10 and 13-15 **added**:
- "2) | 30 - 59 Days Delinquent | 22,640 | $ | 110,110,539.56"; "3) | 60 - 89 Days Delinquent | 15,588 | $ | 78,362,821.12"; "4) | 90 - 119 Days Delinquent | 13,204 | $ | 69,632,603.08"; "5) | 120 - 149 Days Delinquent | 10,310 | $ | 61,529,720.87"; "6) | 150 + Days Delinquent | 10,515 | $ | 62,710,282.09"; "7) | Total 30+ Days Delinquent | 72,257 | $ | 382,345,966.72"; "8) | Delinquencies 30 + Days as a Percent of End of the Month Total Receivables | 1.62%"; "9) | Total 60+ Days Delinquent | 49,617 | $ | 272,235,427.16"; "10) | Delinquencies 60 + Days as a Percent of End of the Month Total Receivables | 1.16%"
- "11) | Defaulted Accounts during the Month | 12,498 | $ | 57,730,080.66"
- "12) | Annualized Default Rate as a Percent of Adjusted Beginning of the Month Principal Receivables which includes Additional Principal Receivables | 2.96%"
- "13) | Recoveries of Charged-Off Accounts during the Month | $ | 22,668,317.01"; "14) | Annualized Recoveries as a Percent of Adjusted Beginning of the Month Principal Receivables which includes Additional Principal Receivables | 1.16%"; "15) | Defaulted Accounts, net of Recoveries, during the Month | $ | 35,061,763.65"
- "16) | Annualized Net Default Rate as a Percent of Adjusted Beginning of Month Principal Receivables which includes Additional Principal Receivables | 1.80%"
Section C (collections) - **verified**: "1) | Total Collections and Gross Payment Rate as a Percent of Adjusted Beginning of Month Total Receivables which includes Additional Total Receivables | $ | 11,756,918,044.92 | 49.61%"; "2) | Collections of Principal Receivables and Principal Payment Rate as a Percent of Adjusted Beginning of the Month Principal Receivables which includes Additional Principal Receivables | $ | 11,229,005,225.75 | 47.98%"; "8) | Collections of Finance Charge Receivables and Annualized Yield as a Percent of Adjusted Beginning of the Month Principal Receivables which includes Additional Principal Receivables | $ | 528,288,601.15 | 27.09%". Series rows: "Series 2002-CC Defaulted Amount | $ | 31,864,391.61"; "Shared Excess Finance Charges of Series 2002-CC | $ | 213,123,849.91".
EX-99.2 section "N. Early Redemption Event" - **verified**: "Current Month Excess Spread Amount | $ | 213,123,849.91"; "Prior Month Excess Spread Amount | $ | 128,684,097.20"; "Two Months Prior Excess Spread Amount | $ | 125,424,134.55"; "Three Month Average Excess Spread Amount | $ | 155,744,027.22"; "Is the average of the Excess Spread Amount for preceding three months greater than $0? | YES". **Confirmed: neither exhibit prints an excess spread percentage, a base rate, or a "Portfolio Yield" label** (grep of both files).
Charge-off basis: the label is the definition - gross "Defaulted Accounts during the Month" and net-of-recoveries, each "Annualized ... as a Percent of Adjusted Beginning of the Month Principal Receivables which includes Additional Principal Receivables". Arithmetic: 57,730,080.66 x 12 / 23,403,238,504.06 = 2.9601%; 35,061,763.65 x 12 / 23,403,238,504.06 = 1.7978% -> **x12 on beginning principal receivables**.

### B3. Chase Issuance Trust - accession 0001193125-26-353171
Files (`chase/10D/0001193125-26-353171/`): `d169887d10d.htm` 21,766 B (primary); `d169887dex991.htm` 5,527 B = EX-99.1 Monthly Information Officer's Certificate (dates only); `d169887dex992.htm` 64,676 B = EX-99.2 Asset Pool One Monthly Servicer's Certificate (pool); `d169887dex993.htm` 161,266 B = EX-99.3 "CHASE ISSUANCE TRUST / CHASEseries Monthly Noteholders' Statement / Monthly Period: July 2026". Format: HTML tables.
EX-99.2 - **verified**: "Collateral of Asset Pool One | Beginning Balance | Ending Balance" -> "Principal Receivables | 11,946,847,375.49 | 11,728,896,182.88"; "6a. | The aggregate amount of Collections of Principal Receivables received by Asset Pool One for the related Monthly Period | 6,398,890,105.55" (**added**); "9a. | The Asset Pool One Default Amount for the related Monthly Period | 15,775,885.97" (**added**; equals Net Losses).
Item "10. Delinquencies as of the last day of the related Monthly Period", columns "Number of Accounts | Amount of Receivables (1) | Percentage of Receivables" - **verified**, 180+ row **added**: "30-59 days | 4,651 | 27,904,841.61 | 0.24%"; "60-89 days | 2,832 | 20,117,199.14 | 0.17%"; "90-119 days | 1,953 | 15,749,407.73 | 0.13%"; "120-149 days | 1,736 | 15,858,053.30 | 0.13%"; "150-179 days | 1,843 | 16,436,974.16 | 0.14%"; "180 or more days | 0 | 0.00 | 0.00%". Footnote "(1) The amount of receivables reflected includes all principal, finance charge and fee amounts due from cardholders as of the date specified."
Item "11. Losses and Recoveries for the related Monthly Period" - **verified**, "Average Pool Balance" and "Recoveries" rows **added**: "Average Pool Balance (2) | 11,946,847,375.49"; "Gross Losses (3) | 20,157,969.63"; "Gross Losses as a Percentage of Average Pool Balance (Annualized) | 2.02%"; "Recoveries (4) | 4,382,083.66"; "Net Losses (5) | 15,775,885.97"; "Net Losses as a percentage of Average Pool Balance (Annualized) | 1.58%"; "Number of Accounts Charged Off During the Monthly Period | 3,503"; "Average Net Loss Amount on Accounts Charged Off during the Monthly Period | 4,503.54".
Defining footnotes (verbatim): "(2) Average Pool Balance means 'Asset Pool One Average Principal Balance' as defined in the Asset Pool One Supplement." "(3) Gross Losses are charge-offs of principal receivables. Gross Losses do not include the amount of any reductions in principal receivables due to fraud, returned goods or customer disputes, the amount of which instead results in the reduction of the Asset Pool One Transferor Amount." "(4) Recoveries are amounts received on previously charged-off receivables during the related Monthly Period, and allocated to the issuing entity pro rata, based on the amount of gross losses in the issuing entity as a percentage of gross losses in the Servicer's managed portfolio of credit card receivables for the related Monthly Period." "(5) Net Losses are Gross Losses minus Recoveries. Net Losses do not include any reductions in principal receivables due to fraud, returned goods or customer disputes, the amount of which instead results in the reduction of the Asset Pool One Transferor Amount."
Charge-off basis: gross and net, principal receivables only, denominator "Average Pool Balance" - which in this month equals the beginning principal balance to the cent (11,946,847,375.49). Arithmetic: 20,157,969.63 x 12 / 11,946,847,375.49 = 2.0248%; 15,775,885.97 x 12 / 11,946,847,375.49 = 1.5846% -> **x12**. Recoveries are an allocated share of managed-portfolio recoveries, not pool-specific.
EX-99.3 section "C. Information regarding the performance of the CHASEseries", columns "July Monthly Period | June Monthly Period | May Monthly Period" - **verified**, column structure and the two yield rows **added**: "Yield - Finance Charge, Fees & Interchange | 24.41% | 24.62% | 24.61%"; "Plus: Yield - Collections of Discount Receivables | 0.00% | 0.00% | 0.00%"; "Less: Net Credit Losses | 1.58% | 1.62% | 1.73%"; "(a) Portfolio Yield | 22.83% | 23.00% | 22.88%"; "(b) Base Rate | 6.20% | 6.20% | 6.20%"; "(a) - (b) = Excess Spread Percentage | 16.63% | 16.80% | 16.68%"; "Three Month Average Excess Spread Percentage | 16.70% | 16.76% | 17.45%"; "Excess Spread Amount paid to Transferor | $ | 122,511,491.72 | $ | 115,397,503.10 | $ | 127,512,674.02"; "Principal Payment Rate | 53.56% | 51.83% | 52.55%". Note the net loss rate is repeated here as "Less: Net Credit Losses" with two prior months, so EX-99.3 alone gives a 3-month net-loss history.

### B4. Citibank Credit Card Issuance Trust / Citibank Credit Card Master Trust I - accession 0001193125-26-353756
Files (`citi/10D/0001193125-26-353756/`): `d138267d10d.htm` 24,489 B (primary); `d138267dex99.htm` 157,610 B = EX-99 "CITIBANK, N.A. / CITIBANK CREDIT CARD ISSUANCE TRUST / CITIBANK CREDIT CARD MASTER TRUST I", "This Report relates to the Due Period ending July 28, 2026 and the related Payment Dates for the Notes." Format: HTML tables, sections A, B, C1-C3, D...; Citi's due period ends around the 28th.
Section "A. Information Regarding the Master Trust portfolio" - **verified**, sub-rows and rows 2/5 **added**:
- "1. Portfolio Yield for the Collateral Certificate | 21.51 | %" with sub-rows "Yield Component | 23.41 | %" and "Credit Loss Component | 1.90 | %"
- "2. New Purchase Rate | 41.89 | %"; "3. Total Payment Rate | 43.06 | %"; "4. Principal Payment Rate | 43.84 | %"
- "5. Aggregate Amount of Principal Receivables in the Trust :" -> "Principal Receivables Beginning of Due Period | $ | 19,165,697,102"; "Principal Receivables Average | $ | 19,055,371,156"; "Principal Receivables Lump Sum Addition/(Removal) | $ | 0"; "Principal Receivables End of Due Period | $ | 19,119,983,665"; "Finance Charge Receivables - End of Due Period | $ | 964,582,824"
- "6. Delinquency (1)": dollars then percentages: "Current | $ | 19,406,570,793"; "1-30 days delinquent | $ | 252,230,180"; "31-60 days delinquent | $ | 76,269,089"; "61-90 days delinquent | $ | 57,536,794"; "91-120 days delinquent | $ | 48,137,590"; "121-150 days delinquent | $ | 40,781,279"; "151-180 days delinquent | $ | 42,241,217"; then "1-30 days delinquent | 1.27 | %"; "31-60 | 0.38 | %"; "61-90 | 0.29 | %"; "91-120 | 0.24 | %"; "121-150 | 0.20 | %"; "151-180 | 0.21 | %". (**corrected**: the "Total receivables Current $19,406,570,793" in the rendering is the *current, non-delinquent* bucket of this table, 97.41% of receivables, not a total-receivables row.) Footnote "(1) Shown are (i) the aggregate dollar amount of Receivables that were current or were delinquent for each of the time periods listed and (ii) ... as a percentage of the aggregate dollar amount of Receivables. Accounts and the related Receivables are serviced on multiple servicing platforms. Delinquency data shown for Receivables related to some Accounts is as of the last business day of the same month as the last day of the Due Period and delinquency data shown for Receivables related to other Accounts is as of the last full weekend of the same month ..."
Section C1 (collateral certificate) - **verified**: "1. Portfolio Yield | 21.51 | % | 21.51 | %"; "2. Investor Default Amount | $ | 8,766,208 | $ | 8,766,208" (columns = "Current Due Period on an Actual Basis" / "Standard Basis"); "4. Surplus Finance Charge Collections | 16.83 | %"; section F.7 "Excess Spread/Early Redemption Event Trigger | 1) 3 Month Average Surplus Finance Charge Collections | 17.23 | %". Footnote (1) to section C: "All percentages are based on actual cash revenue or expense for the period, converted to an annualized percent using day count appropriate for the item, either 30/360, actual/360, or actual/actual. Depending on the item, cash expenses may accrue from June 26, 2026 to July 28, 2026, 33 days, or July 10, 2026 to August 6, 2026, 28 days (standard basis)." Footnote (2): "Defined in the definition section of the Indenture".
**Item (4) - pool-level charge-off row:** the 10-D carries **no row labelled charge-off, loss or default at the master-trust level in dollars** (grep of the whole exhibit for charge/loss/default/recover returns only the rows above plus the note-level "Investor Charge-Offs" columns, all $0). The pool-level loss *rate* is the Section A sub-row **"Credit Loss Component | 1.90 | %"** of "1. Portfolio Yield for the Collateral Certificate" (Yield Component 23.41% - Credit Loss Component 1.90% = Portfolio Yield 21.51%). Arithmetic tying it to the investor default amount: Section C3 says the Series 2009 invested amount "currently equals 3.84764% of the Invested Amount of the Collateral Certificate" and prints "Series 2009 Invested Amount as of the end of the Due Period** | $ | 196,806,786", so the collateral certificate invested amount = 196,806,786 / 0.0384764 = $5,115,000,000 (= Class A 4,455,000,000 + Class B 280,000,000 + Class C 380,000,000 outstanding). 8,766,208 x 365/33 / 5,115,000,000 = 1.8956% -> prints as 1.90% (x12 would give 2.06%). Because defaults are allocated to the collateral certificate pro rata, this is the master-trust default rate on principal receivables, annualized actual/365 over the 33-day due period; pool-equivalent monthly defaults = 8,766,208 x 19,055,371,156 / 5,115,000,000 = about $32.7M. Gross vs net: the report does not say; the prospectus (`citi/prospectus/0001193125-25-144490/d945716d424b2.htm`) says "Recoveries of charged-off receivables are credited to the category from which they were charged off" (so principal recoveries come back as principal collections, not as a reduction of the default amount) and, for its historical loss table, "Net losses include principal recoveries. The net losses percentage shown in the tables below is calculated by dividing net principal charged off during the due period by the principal receivables balance as of the beginning of the due period." => treat "Credit Loss Component" as a **gross** (before principal recoveries) annualized default rate; a net rate is not published monthly. This is an inference from the structure, not a printed definition.

### B5. Discover Card Execution Note Trust - accession 0001407200-26-000026 (post-defeasance)
Files (`discover/10D/0001407200-26-000026/`): `dcent10-ddocumentxjuly2026.htm` 31,650 B (primary); `exhibit991report-postdefea.htm` 24,887 B = "Monthly Servicer Certificate, Discover Card Execution Note Trust, DiscoverSeries Class A(2021-2) Notes", Distribution Date August 17, 2026, "Related Interest Accrual Period: July 15, 2026 to August 16, 2026". Format: HTML.
**Verified** verbatim: "Under the Defeasance Agreement, dated as of December 18, 2025 (the 'Defeasance Agreement'), by and among Discover Card Execution Note Trust ('DCENT'), as Issuer, U.S. Bank Trust Company, National Association ('USBTC'), in its capacity as Indenture Trustee and as Paying Agent, and U.S. Bank National ..." The exhibit's only sections are Interest, Principal, "Information Concerning Principal Payments", "Information Concerning Class A(2021-2) Defeasance Interest Funding Account", "Information Concerning Class A(2021-2) Defeasance Principal Funding Accounts". **There is no receivables, charge-off, payment-rate, yield, delinquency or excess-spread row** (`discover/_rows.txt` has 6 lines, none of them metrics). The primary 10-D adds (**added**): "Discover Funding LLC, as depositor for Discover Card Execution Note Trust, filed Form ABS-15G on February 13, 2026 in respect of the credit card receivables held by Discover Card Master Trust I for the period from January 1, 2025 to December 18, 2025."
=> Discover's public pool series ends with the 10-D filed 2025-12-15 (month ending November 30, 2025; accession 0001407200-25-000040, not downloaded). From the earlier directory listing of that filing, the pool statements are `a2007-cccertstatement121.htm` (12,759 B) + 4 JPGs and `noteholders121525.htm` (25,515 B) + 15 JPGs, and the rendered text of the 2007-CC certificate carried only section headings ("Principal Receivables for November, 2025", "Investor Charged-Off Amount", "Delinquency Summary", "Total Master Trust and Investor Principal Charge-Offs") with all numbers inside the images. Still unverified from a local raw file; treat Discover's 2024-2025 monthly numbers as image-only (OCR) until a pre-defeasance filing is downloaded.

### B6. Synchrony Card Issuance Trust - accession 0001104659-26-097449
Files (`synchrony/10D/0001104659-26-097449/`): `tm2622590d1_10d.htm` 53,293 B (primary; contains a "Trust Performance" summary table with columns "July 2026 | June 2026 | May 2026 | 3-Month Avg"); `tm2622590d1_ex99-1.htm` 262,145 B = EX-99.1 Monthly Noteholder's Statement, SynchronySeries, Monthly Period 07/01/2026-07/31/2026, Payment Date 08/17/2026. Format: HTML tables. "Loss Cycles in Period: | 28" (**added**).
EX-99.1 receivables - **verified**: "c. | BOP Aggregate Principal Receivables | 10,972,300,373.45"; "f. | BOP Total Receivables | 11,475,209,377.40"; "m. | EOP Aggregate Principal Receivables | 10,893,543,177.22"; "p. | EOP Total Receivables | 11,404,850,598.69".
Performance labels (the label text is the definition) - **verified**: "a. | Gross Trust Yield (Finance Charge Collections + Recoveries / BOP Principal Receivables)"; "b. | Payment Rate (Principal Collections / BOP Principal Receivables)"; "c. | Gross Charge-Off Rate (Default Amount for Defaulted Accounts / BOP Principal Receivables)"; "d. | Net Charge-Off Rate (Default Amount for Defaulted Accounts - Recoveries/ BOP Principal Receivables)"; each followed by sub-rows i./ii./iii. = current month / prior month / 3-month values. Values (current): Gross Charge-Off Rate 5.3437%, Net Charge-Off Rate 4.1142%, Payment Rate 25.2915% (**verified**). Dollar rows - **verified**, f/g/i **added**: "e. | Default Amount for Defaulted Accounts | 48,860,288.23"; "f. | Recovery Amount | 11,242,167.36"; "g. | Net Charge-Off (Default Amount for Defaulted Accounts - Recoveries) | 37,618,120.87"; "i. | Average Account Charge-Off (Net Charge-Off / Number of Accounts Charged Off) | 1,848.28".
"j. | Delinquency Data | Accounts | Pctg. of Tot. Accts. | Total Receivables | Pctg. of Tot. Recv." - **verified**, dollar column, 1-29 and 180+ rows **added**: "i. | 1-29 Days Delinquent | 93,101 | 0.9674% | 192,381,334.48 | 1.6868%"; "ii. | 30-59 Days Delinquent | 32,294 | 0.3356% | 86,159,844.94 | 0.7555%"; "iii. | 60-89 Days Delinquent | 22,721 | 0.2361% | 65,961,598.03 | 0.5784%"; "iv. | 90-119 Days Delinquent | 19,089 | 0.1984% | 58,196,184.32 | 0.5103%"; "v. | 120-149 Days Delinquent | 14,840 | 0.1542% | 49,793,308.75 | 0.4366%"; "vi. | 150-179 Days Delinquent | 14,079 | 0.1463% | 49,779,111.10 | 0.4365%"; "vii. | 180 or Greater Days Delinquent | 0 | 0.0000% | 0.00 | 0.0000%".
Yield block (three columns = current / prior / 3-month) - **verified**, base rate **added**: "(a) Portfolio Yield | 21.76% | 21.28% | 22.94%"; "(b) Base Rate | 5.19% | 5.42% | 5.45%"; "(a)- (b) = Excess Spread Percentage | 16.57% | 15.86% | 17.49%"; "Three Month Average Excess Spread Percentage | 16.64% | 16.92% | 17.49%".
Primary 10-D summary table (**added**): "Gross Trust Yield | 28.33 % | 28.12 % | 29.16 % | 28.54 %"; "Gross Charge-Off Rate | 5.34 % | 5.27 % | 5.41 % | 5.34 %"; "Net Charge Off Rate | 4.11 % | 4.09 % | 4.17 % | 4.13 %"; "SynchronySeries Excess Spread Percentage | 16.57 % | ..."; "Payment Rate | 25.29 % | ..."; delinquency rows 1-29 through 180+ as % of receivables; "BOP Principal Receivables ($B) | $ | 11.0 | ...".
Charge-off basis: gross and net, "Default Amount for Defaulted Accounts" over BOP (beginning-of-period) principal receivables. No "annualized" wording anywhere, but 48,860,288.23 x 12 / 10,972,300,373.45 = 5.3437% and 37,618,120.87 x 12 / 10,972,300,373.45 = 4.1142% exactly -> **x12 on beginning principal**.

### B7. BA Credit Card Trust / BA Master Credit Card Trust II - accession 0001140361-26-033313
Files (`bofa/10D/0001140361-26-033313/`): `ef20079972_10d.htm` 27,801 B (primary); `ef20079972_ex99-1.htm` 220,813 B = EX-99.1 Monthly Certificateholders' Statement, Series 2001-D (Master Trust II pool report), Monthly Period Ending July 31, 2026, Transfer Date August 14, 2026; `ef20079972_ex99-2.htm` 118,693 B = EX-99.2 Schedule to Monthly Noteholders' Statement (per class; only "L. Excess Available Funds ... | $129,750,080.38"); `image0.jpg` 102,843 B (signature/logo). Format: HTML tables.
EX-99.1 - **verified**: "2. Receivables in the Trust": "(a) The aggregate amount of Receivables in the Trust as of the beginning of the related Monthly Period | $ | 14,677,269,879.21" (**added**); "(b) The aggregate amount of Principal Receivables in the Trust as of the beginning of the related Monthly Period | $ | 14,333,396,313.73"; "(k) The aggregate amount of Receivables in the Trust as of the end of the day on the last day of the related Monthly Period | $ | 14,552,256,361.78"; "(l) The aggregate amount of Principal Receivables in the Trust as of the end of the day on the last day of the related Monthly Period | $ | 14,216,676,954.68".
"6. Delinquent Balances", columns "Aggregate Account Balance | Percentage of Total Receivables" - **verified**: "(i) | 30 - 59 days: | $ | 53,530,346.30 | 0.36%"; "(ii) | 60 - 89 days: | $ | 38,603,265.99 | 0.27%"; "(iii) | 90 - 119 days: | $ | 30,561,350.43 | 0.21%"; "(iv) | 120 - 149 days | $ | 30,216,475.88 | 0.21%"; "(v) | 150 - 179 days: | $ | 31,042,931.55 | 0.21%"; "(vi) | 180 - or more days: | $ | 38,779.50 | 0.00%"; "(b) 60+-Day Delinquency Rate | 0.90%"; "(c) Three-Month Average 60+-Day Delinquency Rate | 0.92%"; "(d) Delinquency Trigger Rate | 7.50%".
"7. Investor Default Amount": "(a) The Aggregate Class D Investor Default Amount for the related Monthly Period | $ | 22,876,379.39"; "(b) The Aggregate Investor Default Amount for the related Monthly Period | $ | 0.00" (**verified**). "3. Trust Yields": "(d) Recoveries allocated to Series 2001-D | $ | 5,072,942.15"; "(i) Total Cash Yield for the related Monthly Period as a percentage of Series 2001-D Weighted Average Floating Allocation Investor Interest | 19.77%"; "(k) Aggregate Class D Investor Default Amount for the related Monthly Period as a percentage of Series 2001-D Weighted Average Floating Allocation Investor Interest | 2.71%"; "(l) Aggregate Class D Investor Default Amount net of Recoveries, each for the related Monthly Period, as a percentage of Series 2001-D Weighted Average Floating Allocation Investor Interest | 2.11%" (**added** - a second, investor-interest-based gross/net loss rate); "(m) The Portfolio Yield for the related Monthly Period as a percentage of Series 2001-D Weighted Average Floating Allocation Investor Interest | 17.06%"; "(n) Base Rate for the related Monthly Period | 4.40%"; "(o) Excess Available Funds Percentage for the related Monthly Period | 12.66%"; "(p) Three Month Average Excess Available Funds Percentage for the related Monthly Period | 12.28%". Payment rate: "(f) Collections of Principal Receivables as a percentage of prior month Principal Receivables | 28.48%"; "(e) Collections as a percentage of prior month Principal Receivables and Finance Charge Receivables | 28.89%" (**added**).
Pool loss table "Principal Charge-Off Experience (Dollars in Thousands, except as noted)*", columns "Month Ended July 31, 2026 | Month Ended June 30, 2026" (a second copy gives May 31, 2026 | April 30, 2026) - **verified**: "Average Principal Receivables Outstanding | $ | 14,183,450 | $ | 14,240,537"; "Total Charge-Offs | $ | 32,369 | $ | 33,214"; "Total Charge-Offs as a percentage of Average Principal Receivables Outstanding | 2.74 | % | 2.80 | %"; "Recoveries | $ | 7,178 | $ | 6,734"; "Recoveries as a percentage of Average Principal Receivables Outstanding | 0.61 | % | 0.57 | %"; "Net Charge-Offs | $ | 25,191 | $ | 26,480"; "Net Charge-Offs as a percentage of Average Principal Receivables Outstanding | 2.13 | % | 2.23 | %"; "Average Net Loss of Accounts with a Loss* | $ | 5,806.98 | $ | 5,821.03"; "* All dollar amounts in this table are expressed as dollars in thousands, except for Average Net Loss of Accounts with a Loss, which is expressed as actual dollars." A "Delinquency Experience (Dollars in Thousands)" table repeats the buckets for the current and three prior month-ends (**added**).
Defining sentence (verbatim, precedes the table): "The following table sets forth the principal charge-off experience for cardholder payments on the credit card accounts comprising the Master Trust II Portfolio for each of the periods shown. Charge-offs consist of write-offs of principal receivables. If accrued finance charge receivables that have been written off were included in total charge-offs, total charge-offs would be higher as an absolute number and as a percentage of the average of principal receivables outstanding during the periods indicated. Average principal receivables outstanding is the average of the daily principal receivables balance during the periods indicated."
Charge-off basis: gross ("Total Charge-Offs") and net, principal only, over the **average daily principal receivables**; no "annualized" wording, but 32,369 x 12 / 14,183,450 = 2.7386% and 25,191 x 12 / 14,183,450 = 2.1313% -> **x12 on average daily principal**.

### B-3 summary: charge-off basis per trust

| Trust | Gross row | Net row | Denominator | Annualization (from arithmetic) | Recoveries row |
|---|---|---|---|---|---|
| Amex | "Annualized Default Rate" | "Annualized Default Rate, Net of Recoveries" | ending principal receivables | x365/days | "Recoveries", "Annualized Recovery Rate" |
| COMET | "Annualized Default Rate as a Percent of Adjusted Beginning of the Month Principal Receivables..." | "Annualized Net Default Rate as a Percent of Adjusted Beginning of Month Principal Receivables..." | adjusted beginning principal receivables | x12 | "Recoveries of Charged-Off Accounts during the Month", "Annualized Recoveries as a Percent of..." |
| Chase | "Gross Losses as a Percentage of Average Pool Balance (Annualized)" | "Net Losses as a percentage of Average Pool Balance (Annualized)" | "Average Pool Balance" (= beginning principal this month) | x12 | "Recoveries (4)" (allocated share of managed-portfolio recoveries) |
| Citi | "Credit Loss Component" (sub-row of Portfolio Yield for the Collateral Certificate) | none | collateral certificate invested amount (pro rata = principal receivables) | actual/365 over the 33-day due period | none |
| Discover | none since Dec-2025 (defeased); pre-defeasance rows were images | - | - | - | - |
| Synchrony | "Gross Charge-Off Rate (Default Amount for Defaulted Accounts / BOP Principal Receivables)" | "Net Charge-Off Rate (Default Amount for Defaulted Accounts - Recoveries/ BOP Principal Receivables)" | BOP principal receivables | x12 (label does not say annualized) | "Recovery Amount" |
| BofA | "Total Charge-Offs as a percentage of Average Principal Receivables Outstanding" | "Net Charge-Offs as a percentage of Average Principal Receivables Outstanding" | average daily principal receivables | x12 (label does not say annualized) | "Recoveries", "Recoveries as a percentage of..." |

All seven measure principal receivables only (finance-charge write-offs excluded; Chase, BofA and Amex say so explicitly). Delinquency bucket edges: Amex 31-60/61-90/91-120/120+; Citi 1-30/31-60/61-90/91-120/121-150/151-180; COMET 30-59/.../120-149/150+; Chase, Synchrony, BofA 30-59/.../150-179/180+ (Synchrony also 1-29).

## C. Prospectus composition tables (FICO / credit limit / account age), verbatim

Tables were located with `print_tables.py` (index numbers are table positions in the HTML) and headings/footnotes read with `tblctx.py` / `ctx.py`. "Basis" says which columns exist.

### C1. Amex - 424B5 filed 2025-07-17, accession 0001193125-25-160041, file `amex/prospectus/0001193125-25-160041/d938411d424b5.htm` (1,444,248 B; the sibling filing 0001193125-25-160040 is the same-day second series)
Location: Annex I "The Trust Portfolio". Intro: "...summarize the Trust Portfolio by various criteria as of May 31, 2025. Because the future composition of the Trust Portfolio may change over time, these tables are not necessarily indicative of the composition of the Trust Portfolio at any time subsequent to May 31, 2025." Pool as of May 31, 2025: total receivables $26,797,475,459; 13,609,288 accounts.
FICO: table title "Composition by Standardized Credit Score(1) / Trust Portfolio" (table #251). Intro: "The following table sets forth the composition of the Trust Portfolio as of May 31, 2025 by FICO* score ranges. To the extent available, FICO scores are obtained at origination and monthly thereafter. ... References to Receivables Outstanding in the following table include both finance charge receivables and principal receivables." Footnote "(1) Standardized Credit Score defined as the FICO score in the most recent Monthly Period." => **refreshed monthly**. Basis: receivables only (no account column).

| FICO Score Range | Receivables Outstanding | Percentage of Total Receivables Outstanding |
|---|---|---|
| Less than 560 | 254,558,510 | 0.95 |
| 560 -659 | 1,253,684,572 | 4.68 |
| 660 -699 | 2,184,964,978 | 8.15 |
| 700 -759 | 8,130,791,475 | 30.34 |
| 760 and above | 14,960,364,284 | 55.83 |
| Refreshed FICO Unavailable | 13,111,640 | 0.05 |
| Total | 26,797,475,459 | 100.00 |

Credit limit: "Composition By Credit Limit / Trust Portfolio" (table #245), preceded by "The average account balance as of May 31, 2025 was $1,969 for all accounts and $4,788 for all accounts other than accounts with a zero balance as of that date." Basis: accounts and receivables. Footnote "(1) The maximum credit limit generally is $100,000."

| Credit Limit Range | Number of Accounts | Percentage of Total Number of Accounts | Receivables Outstanding | Percentage of Total Receivables Outstanding |
|---|---|---|---|---|
| Less than $1,000.99 | 649,176 | 4.77 | 33,743,565 | 0.13 |
| $1,001 to $5,000.99 | 1,478,624 | 10.86 | 417,807,853 | 1.56 |
| $5,001 to $10,000.99 | 2,602,949 | 19.13 | 1,116,927,420 | 4.17 |
| $10,001 to $15,000.99 | 1,593,507 | 11.71 | 1,448,968,875 | 5.41 |
| $15,001 to $20,000.99 | 1,136,933 | 8.35 | 1,526,436,540 | 5.70 |
| $20,001 to $25,000.99 | 810,298 | 5.95 | 1,495,316,420 | 5.58 |
| $25,001 or More(1) | 1,755,688 | 12.90 | 9,430,074,369 | 35.19 |
| Other | 3 | 0.00 | 0 | 0.00 |
| Total (Credit Card) | 10,027,178 | 73.68 | 15,469,275,041 | 57.73 |
| No Pre-Set Spending Limit (Pay Over Time) | 3,582,110 | 26.32 | 11,328,200,418 | 42.27 |
| Grand Total | 13,609,288 | 100.00 | 26,797,475,459 | 100.00 |

Account age: "Composition by Account Age / Trust Portfolio" (table #248), "Account Age (1)" with buckets Not More than 11 Months / 12-17 / 18-23 / 24-35 / 36-47 / 48-59 / 60-71 Months (all 0 | 0.00 | 0 | 0.00) and "72 Months or More | 13,609,288 | 100.00 | 26,797,475,459 | 100.00"; Total 13,609,288 | 100.00 | 26,797,475,459 | 100.00.

### C2. COMET - 424B5 filed 2026-07-13, accession 0001193125-26-302059, file `comet/prospectus/0001193125-26-302059/d155768d424b5.htm` (2,343,695 B)
Location: Annex I "The Capital One Credit Card Portfolio" -> "The Receivables". Intro: "The following tables summarize the Master Trust Consumer Segment and the Master Trust Small Business Segment by various criteria as of June 10, 2026. References to 'Receivables Outstanding' in the following tables include both finance charge receivables and principal receivables." Pool as of June 10, 2026: consumer $21,044,902,090 principal + $264,398,828 finance charge receivables, average principal balance $2,424, average credit limit $11,129, balance-to-limit 22.06%; small business $1,790,178,493 + $11,493,518, average balance $3,408, average credit limit $12,219, 28.07%. **Every table is split into two segments.**
FICO: "Composition by FICO(R) Score / Master Trust Consumer Segment" (table #910) and "... / Master Trust Small Business Segment" (#912). Intro: "The bank obtains, to the extent available, FICO scores at the origination of each account and each month thereafter. In the following two tables, Receivables Outstanding are determined as of June 10, 2026, and FICO scores are determined during the month of April 2026." Footnotes: "(1) The FICO score is the Equifax Enhanced Beacon 5.0 FICO score."; small business "(1) ... only the FICO scores of the business owners are reflected in this table." => **refreshed (April 2026 scores against June 10 balances)**. Basis: receivables only.

Consumer segment:
| FICO Score (1) | Receivables Outstanding | % of Total Receivables Outstanding |
|---|---|---|
| No score | 41,595,881 | 0.20% |
| Less than or equal to 600 | 1,195,773,490 | 5.61 |
| 601-660 | 1,668,407,808 | 7.83 |
| 661-720 | 4,967,559,370 | 23.31 |
| Greater than 720 | 13,435,964,370 | 63.05 |
| TOTAL | 21,309,300,918 | 100.00% |

Small business segment:
| FICO Score (2) | Receivables Outstanding | % of Total Receivables Outstanding |
|---|---|---|
| No score | 8,362,199 | 0.46% |
| Less than or equal to 600 | 62,380,752 | 3.46 |
| 601-660 | 97,405,461 | 5.41 |
| 661-720 | 348,648,531 | 19.35 |
| Greater than 720 | 1,284,875,068 | 71.32 |
| TOTAL | 1,801,672,011 | 100.00% |

Credit limit: "Composition by Credit Limit (1)" per segment (tables #895, #897). Footnote "(1) References to 'Credit Limit' herein include both the line of credit established for purchases, cash advances and balance transfers as well as receivables originated under temporary extensions of credit through account management programs. Credit limits relating to these temporary extensions decrease as cardholder payments are applied to the accounts." Basis: accounts and receivables.

Consumer segment:
| Credit Limit Range | Number of Accounts | % of Total Number of Accounts | Receivables Outstanding | % of Total Receivables Outstanding |
|---|---|---|---|---|
| Less than or equal to $1,500.00 | 598,844 | 6.90% | 191,623,879 | 0.90% |
| $1,500.01-$5,000.00 | 2,337,201 | 26.92 | 2,220,536,325 | 10.42 |
| $5,000.01-$10,000.00 | 2,481,004 | 28.58 | 4,626,805,707 | 21.71 |
| Over $10,000.00 | 3,263,399 | 37.59 | 14,270,335,008 | 66.97 |
| TOTAL | 8,680,448 | 100.00% | 21,309,300,918 | 100.00% |

Small business segment:
| Credit Limit Range | Number of Accounts | % of Total Number of Accounts | Receivables Outstanding | % of Total Receivables Outstanding |
|---|---|---|---|---|
| Less than or equal to $1,500.00 | 46,567 | 8.87% | 8,441,874 | 0.47% |
| $1,500.01-$5,000.00 | 168,209 | 32.02 | 121,191,022 | 6.73 |
| $5,000.01-$10,000.00 | 132,790 | 25.28 | 249,718,071 | 13.86 |
| Over $10,000.00 | 177,713 | 33.83 | 1,422,321,043 | 78.94 |
| TOTAL | 525,279 | 100.00% | 1,801,672,011 | 100.00% |

Account age: "Composition by Account Age" per segment (tables #903, #904): buckets Not More than 6 Months / Over 6-12 / 12-24 / 24-36 / 36-48 / 48-60 Months all zero; "Over 60 Months | 8,680,448 | 100.00 | 21,309,300,918 | 100.00" (consumer) and "Over 60 Months | 525,279 | 100.00 | 1,801,672,011 | 100.00" (small business).

### C3. Chase Issuance Trust - 424B5 filed 2026-05-22, accession 0001193125-26-236451, file `chase/prospectus/0001193125-26-236451/d53666d424b5.htm` (1,587,210 B)
Location: main body, "JPMorgan Chase Bank's Credit Card Portfolio - Composition of Issuing Entity Receivables. As of March 31, 2026:" ... "The following tables summarize the Issuing Entity Receivables by various criteria as of March 31, 2026. Receivables in the following tables include principal, finance charge and fee receivables held directly by the issuing entity." Summary: total receivables $11,882,685,348; average total receivables balance $1,787 (including zero-balance accounts); average credit limit $16,324; balance-to-limit 10.95%; 6,648,090 accounts.
FICO: **a random sample, not the whole pool.** Intro: "JPMorgan Chase Bank primarily uses a proprietary credit scoring model to assess the credit risk of potential and existing cardholders. However, JPMorgan Chase Bank is including FICO score information for a random sample of the Trust Portfolio in this prospectus consistent with the credit card industry's acceptance of FICO scores as a general indicator of credit risk." "The following table reflects the distribution of the FICO scores for a statistically significant, random sample of credit card accounts included in the Trust Portfolio received by JPMorgan Chase Bank in March 2026 and the outstanding receivables balances of the related accounts as of March 31, 2026. The FICO scores set forth below are Experian/FICO Bankcard Score 8 scores." Table "Chase Issuance Trust / FICO Scores(1) / As of March 31, 2026" (table #242); footnote "(1) The FICO scores are Experian/FICO Bankcard Score 8 scores." => **refreshed (March 2026)**, basis receivables of the sample only ($592.5M = 5.0% of the pool); no account column.

| FICO Score Range(2) | Amount of Receivables | Percentage of Total Amount of Receivables |
|---|---|---|
| No FICO Score | 852,912 | 0.14 |
| Less Than 600 | 10,878,194 | 1.84 |
| 600 to 659 | 21,320,211 | 3.60 |
| 660 to 719 | 90,270,375 | 15.24 |
| 720 and Above | 469,195,167 | 79.18 |
| Total | 592,516,859 | 100.00 |

Credit limit: "Composition by Credit Limit / Chase Issuance Trust" (table #238). Basis: accounts and receivables.

| Credit Limit Range | Number of Accounts | Percentage of Total Number of Accounts | Amount of Receivables | Percentage of Total Amount of Receivables |
|---|---|---|---|---|
| $0.01 to $5,000.00 | 1,008,489 | 15.17 | 395,289,019 | 3.33 |
| $5,000.01 to $10,000.00 | 1,351,046 | 20.33 | 1,096,412,722 | 9.22 |
| $10,000.01 to $15,000.00 | 1,335,260 | 20.08 | 1,574,346,269 | 13.25 |
| $15,000.01 to $20,000.00 | 932,969 | 14.03 | 1,575,259,653 | 13.26 |
| $20,000.01 to $25,000.00 | 810,926 | 12.20 | 1,713,613,176 | 14.42 |
| $25,000.01 to $50,000.00 | 1,106,559 | 16.64 | 4,304,663,470 | 36.23 |
| $50,000.01 or More | 102,841 | 1.55 | 1,223,101,039 | 10.29 |
| Total | 6,648,090 | 100.00 | 11,882,685,348 | 100.00 |

Account age: "Composition by Account Age / Chase Issuance Trust" (table #240), "Age Range" buckets Less than or equal to 6 Months / Over 6-12 / 12-24 / 24-36 / 36-48 / 48-60 / 60-120 Months all zero; "Over 120 Months | 6,648,090 | 100.00 | 11,882,685,348 | 100.00". (Prospectus text: average account age "approximately 293 months".)

### C4. Citi - 424B2 filed 2025-06-23, accession 0001193125-25-144490, file `citi/prospectus/0001193125-25-144490/d945716d424b2.htm` (2,158,169 B; sibling 0001193125-25-144485 same day)
Location: "ANNEX I: THE MASTER TRUST RECEIVABLES AND ACCOUNTS". Intro for the credit-limit/age tables: "The following tables summarize the credit card accounts designated to the master trust as of March 26, 2025, by various criteria. References to Receivables Outstanding in these tables include both finance charge receivables and principal receivables." FICO intro: "The following table sets forth the composition of accounts by FICO* score as of March 30, 2025. ... A credit report is generally obtained from one or more credit bureaus for each application for a new account. Once a customer has been issued a card, Citibank refreshes the FICO score on most accounts on a monthly basis. Citibank generally does not refresh the FICO scores of closed accounts that have no balance and certain other categories of accounts. A FICO score of zero indicates that the FICO score of an account has not b[een refreshed for various] reasons or that the customer did not have enough credit history for a FICO score to be calculated. As of March 30, 2025, 93.07%, of the receivables in the master trust related to obligors whose FICO score was greater than 660." => **refreshed monthly**; basis **accounts AND receivables**; 11 buckets (the finest of the seven).
FICO: "Composition of Accounts by FICO Score" (table #705):

| FICO Score | Number of Accounts | Percentage of Total Number of Accounts | Receivables Outstanding | Percentage of Total Receivables Outstanding |
|---|---|---|---|---|
| 000 | 628,038 | 8.18 | 82,967,950 | 0.39 |
| 001 to 599 | 76,614 | 1.00 | 454,865,481 | 2.12 |
| 600 to 639 | 80,435 | 1.05 | 435,454,107 | 2.03 |
| 640 to 660 | 84,661 | 1.10 | 511,950,322 | 2.39 |
| 661 to 679 | 131,202 | 1.71 | 890,772,055 | 4.16 |
| 680 to 699 | 216,196 | 2.82 | 1,593,901,624 | 7.44 |
| 700 to 719 | 295,369 | 3.85 | 2,231,349,895 | 10.42 |
| 720 to 739 | 345,932 | 4.50 | 2,357,669,161 | 11.01 |
| 740 to 759 | 429,110 | 5.59 | 2,454,906,253 | 11.46 |
| 760 to 800 | 1,285,149 | 16.73 | 4,516,884,065 | 21.10 |
| 801+ | 4,107,000 | 53.47 | 5,882,168,485 | 27.48 |
| Total | 7,679,706 | 100.00 | 21,412,889,398 | 100.00 |

Credit limit: "Composition of Accounts by Credit Limit" (table #702), basis accounts and receivables:

| Credit Limit | Number of Accounts | Percentage of Total Number of Accounts | Receivables Outstanding | Percentage of Total Receivables Outstanding |
|---|---|---|---|---|
| Less than or equal to $500.00 | 70,868 | 0.92 | 6,770,890 | 0.03 |
| $500.01 to $1,000.00 | 83,684 | 1.09 | 19,906,144 | 0.09 |
| $1,000.01 to $2,000.00 | 215,411 | 2.80 | 106,570,095 | 0.50 |
| $2,000.01 to $3,000.00 | 220,670 | 2.87 | 167,599,679 | 0.78 |
| $3,000.01 to $4,000.00 | 223,918 | 2.92 | 209,675,315 | 0.98 |
| $4,000.01 to $5,000.00 | 302,161 | 3.93 | 305,454,479 | 1.43 |
| $5,000.01 to $6,000.00 | 268,856 | 3.50 | 301,673,162 | 1.41 |
| $6,000.01 to $7,000.00 | 284,249 | 3.70 | 388,610,979 | 1.81 |
| $7,000.01 to $8,000.00 | 296,314 | 3.86 | 384,422,506 | 1.80 |
| $8,000.01 to $9,000.00 | 293,203 | 3.82 | 436,296,175 | 2.04 |
| $9,000.01 to $10,000.00 | 369,747 | 4.81 | 599,131,504 | 2.80 |
| $10,000.01 to $15,000.00 | 1,398,162 | 18.20 | 2,695,807,268 | 12.58 |
| $15,000.01 to $20,000.00 | 1,448,043 | 18.87 | 3,236,675,125 | 15.12 |
| Over $20,000.00 | 2,204,420 | 28.71 | 12,554,296,077 | 58.63 |
| Total | 7,679,706 | 100.00 | 21,412,889,398 | 100.00 |

Account age: "Composition of Accounts by Age" (table #704): "6 months or less", "Over 6 to 12 months", "Over 12 to 24", "Over 24 to 36", "Over 36 to 48", "Over 48 to 60 months" all "0 | 0.00 | 0 | 0.00"; "Over 60 months | 7,679,706 | 100.00 | 21,412,889,398 | 100.00".

### C5. Discover - 424B5 filed 2023-06-23, accession 0001193125-23-173892, file `discover/prospectus/0001193125-23-173892/d460049d424b5.htm` (1,982,830 B) - **the last prospectus; no 424B filings since 2024**
Location: "The Master Trust - The Master Trust Accounts - Current Composition and Distribution of the Master Trust Accounts" and "- Distribution of the Accounts by FICO Score". Receivables as of May 31, 2023 totaled $25,035,843,754.67; 12,055,789 accounts.
FICO: intro "To the extent available, FICO scores are generally obtained at origination of the account and monthly or quarterly thereafter. ... The following table reflects receivables as of May 31, 2023, and the composition of accounts by FICO score as refreshed during May 31, 2023:" (table #226). => **refreshed**; basis receivables only, in $000s.

| FICO Credit Score Range (1) | Receivables Outstanding ($000s) | Percentage of Total Receivables |
|---|---|---|
| No Score | 11,739 | 0.05% |
| Less than 600 | 556,124 | 2.22% |
| 600 to 659 | 1,430,147 | 5.71% |
| 660 to 719 | 6,042,655 | 24.14% |
| 720 and above | 16,995,179 | 67.88% |
| Total | 25,035,844 | 100.00% |

Credit limit: "Credit Limit Information. As of May 31, 2023, the accounts had the following credit limits:" (table #219), basis receivables ($000s) and accounts:

| Credit Limit | Receivables Outstanding ($000s) | Percentage of Total Receivables | Number of Accounts | Percentage of Total Accounts |
|---|---|---|---|---|
| Less than or equal to $5,000.00 | 415,793 | 1.66% | 1,120,543 | 9.29% |
| $5,000.01 to $10,000.00 | 1,842,524 | 7.36% | 2,309,587 | 19.16% |
| $10,000.01 to $15,000.00 | 4,538,471 | 18.13% | 4,134,839 | 34.30% |
| Over $15,000.00 | 18,239,056 | 72.85% | 4,490,820 | 37.25% |
| Total | 25,035,844 | 100.00% | 12,055,789 | 100.00% |

Account age: "Seasoning. As of May 31, 2023, 100.0% of the accounts were at least 60 months old." (table #221): Less Than 12 / 12-23 / 24-35 / 36-47 / 48-59 Months all 0.00% | 0.00%; "60 Months or Greater | 100.00% | 100.00%" (percent of accounts / percent of receivables only, no counts).

### C6. Synchrony - 424B5 filed 2026-08-07, accession 0001104659-26-092741, file `synchrony/prospectus/0001104659-26-092741/tm2622401d3_424b5.htm` (2,056,173 B)
Location: Annex III "The Trust Portfolio". Intro: "The following tables summarize the trust portfolio by various criteria as of May 31, 2026 for each of the program partners included in the trust portfolio." Pool as of May 31, 2026: total receivables $11,489,137,310; 9,777,270 accounts; average total receivable balance ~$1,175; average credit limit ~$6,450; balance-to-limit 18.2%. (The "FICO" full-text search found nothing for Synchrony because **Synchrony reports VantageScore, not FICO**.)
Score: "Composition by VantageScore Credit Score Range of the Trust Portfolio" (table #770). Intro: "VantageScore credit scores or equivalent are obtained at origination of the account and are refreshed, at a minimum quarterly, to assist in predicting customer behavior. ... The following table reflects receivables as of May 31, 2026, based on the composition of accounts by VantageScore credit score as most recently refreshed:" => **refreshed (at least quarterly)**; basis receivables only.

| VantageScore Credit Score Range | Total Receivables Outstanding | Percentage of Total Receivables Outstanding |
|---|---|---|
| No score and/or less than or equal to 599* | 708,664,528 | 6.2 |
| 600-659 | 2,034,226,994 | 17.7 |
| 660-719 | 3,124,684,656 | 27.2 |
| 720 and above | 5,621,561,133 | 48.9 |
| Total | 11,489,137,310 | 100.0 |

Credit limit: "Composition by Credit Limit Range of the Trust Portfolio" (table #766), basis receivables and accounts:

| Credit Limit Range | Total Receivables Outstanding | Percentage of Total Receivables Outstanding | Number of Accounts | Percentage of Number of Accounts |
|---|---|---|---|---|
| $0.01-$500.00 | 53,070,022 | 0.5 | 410,953 | 4.2 |
| $500.01-$1,000.00 | 177,199,411 | 1.5 | 411,318 | 4.2 |
| $1,000.01-$2,000.00 | 570,347,296 | 5.0 | 939,531 | 9.6 |
| $2,000.01-$3,000.00 | 804,279,689 | 7.0 | 1,224,820 | 12.5 |
| $3,000.01-$4,000.00 | 825,547,853 | 7.2 | 963,895 | 9.9 |
| $4,000.01-$5,000.00 | 832,354,710 | 7.2 | 777,819 | 8.0 |
| $5,000.01-$6,000.00 | 821,481,063 | 7.2 | 675,791 | 6.9 |
| $6,000.01-$7,000.00 | 809,301,282 | 7.0 | 576,519 | 5.9 |
| $7,000.01-$8,000.00 | 884,748,041 | 7.7 | 620,047 | 6.3 |
| $8,000.01-$9,000.00 | 584,217,418 | 5.1 | 431,635 | 4.4 |
| $9,000.01-$10,000.00 | 1,400,694,003 | 12.2 | 938,630 | 9.6 |
| $10,000.01 or more | 3,725,896,523 | 32.4 | 1,806,312 | 18.5 |
| Total | 11,489,137,310 | 100.0 | 9,777,270 | 100.0 |

Account age: "Composition by Account Age Range of the Trust Portfolio" (table #767) - the only trust with a real age distribution (accounts are added continuously):

| Account Age Range | Total Receivables Outstanding | Percentage of Total Receivables Outstanding | Number of Accounts | Percentage of Number of Accounts |
|---|---|---|---|---|
| Up to 6 Months | - | 0.0 | - | 0.0 |
| 6 Months to 12 Months | 80,967,540 | 0.7 | 91,398 | 0.9 |
| Over 12 Months to 24 Months | 385,925,445 | 3.4 | 453,431 | 4.6 |
| Over 24 Months to 36 Months | 561,239,600 | 4.9 | 564,476 | 5.8 |
| Over 36 Months to 48 Months | 732,452,722 | 6.4 | 694,258 | 7.1 |
| Over 48 Months to 60 Months | 986,554,574 | 8.6 | 986,135 | 10.1 |
| Over 60 Months to 72 Months | 895,036,594 | 7.8 | 858,944 | 8.8 |
| Over 72 Months to 84 Months | 952,315,731 | 8.3 | 887,473 | 9.1 |
| Over 84 Months to 96 Months | 977,219,769 | 8.5 | 800,590 | 8.2 |
| Over 96 Months to 108 Months | 954,923,012 | 8.3 | 811,634 | 8.3 |
| Over 108 Months to 120 Months | 1,157,976,858 | 10.1 | 796,814 | 8.1 |
| Over 120 Months | 3,804,525,464 | 33.1 | 2,832,117 | 29.0 |
| Total | 11,489,137,310 | 100.0 | 9,777,270 | 100.0 |

Also present (table #754): "Trust Portfolio - Payment Status" (percentage of accounts paying less than minimum / minimum / between / full, by year 2021-2025 and five cycles to May 2026), and Annex II "Static Pool Data".

### C7. BofA - 424B5 filed 2026-05-11, accession 0000929638-26-001790, file `bofa/prospectus/0000929638-26-001790/ba424b5.htm` (1,889,126 B)
Location: Annex I "The Master Trust II Portfolio" -> "The Receivables". Intro: "The following tables summarize the Master Trust II Portfolio by various criteria as of the beginning of the day on April 1, 2026." Pool: $14,219,308,859 principal + $338,172,515 finance charge receivables; average principal balance $2,978; average credit limit $19,618; balance-to-limit 15.6%; 4,774,134 accounts.
FICO: "Composition by FICO Score / Master Trust II Portfolio" (table #656). Intro: "The following table sets forth the FICO scores on the accounts in the Master Trust II Portfolio, to the extent available, as refreshed during the six-month period ended on April 1, 2026. Receivables, as presented in the following table, are determined as of April 1, 2026. ... The table below sets forth refreshed FICO scores from a single credit bureau as of the beginning of the day on April 1, 2026." => **refreshed (within six months)**; basis receivables only; rows in descending order.

| FICO Score | Receivables | Percentage of Total Receivables |
|---|---|---|
| Over 720 | 10,386,401,725 | 71.2 |
| 661-720 | 3,166,410,199 | 21.8 |
| 601-660 | 605,159,355 | 4.2 |
| Less than or equal to 600 | 299,549,939 | 2.1 |
| Unscored | 99,960,156 | 0.7 |
| TOTAL | 14,557,481,374 | 100.0 |

Credit limit: "Composition by Credit Limit / Master Trust II Portfolio" (table #652), basis accounts and receivables:

| Credit Limit Range | Number of Accounts | Percentage of Total Number of Accounts | Receivables | Percentage of Total Receivables |
|---|---|---|---|---|
| Less than or equal to $ 5,000.00 | 500,379 | 10.5 | 339,244,700 | 2.3 |
| $ 5,000.01 - $ 10,000.00 | 685,523 | 14.4 | 1,073,626,763 | 7.4 |
| $ 10,000.01 - $ 15,000.00 | 806,179 | 16.9 | 1,573,090,754 | 10.8 |
| $ 15,000.01 - $ 20,000.00 | 807,075 | 16.9 | 2,009,827,826 | 13.8 |
| $ 20,000.01 - $ 25,000.00 | 695,521 | 14.6 | 2,521,121,632 | 17.3 |
| $ 25,000.01 or More | 1,279,457 | 26.7 | 7,040,569,699 | 48.4 |
| Total | 4,774,134 | 100.0 | 14,557,481,374 | 100.0 |

Account age: "Composition by Account Age / Master Trust II Portfolio" (table #654): Not More than 6 Months / Over 6-12 / 12-24 / 24-36 / 36-48 / 48-60 / 60-72 Months all "0 | 0.0 | 0 | 0.0"; "Over 72 Months | 4,774,134 | 100.0 | 14,557,481,374 | 100.0".

### C-summary: comparability of the score tables

| Trust | Score | Refreshed? | Basis | Buckets | As of |
|---|---|---|---|---|---|
| Amex | FICO ("Standardized Credit Score") | monthly | receivables only | <560, 560-659, 660-699, 700-759, 760+, unavailable | 2025-05-31 |
| COMET | FICO (Equifax Enhanced Beacon 5.0) | monthly (scores from Apr-2026 vs Jun-10 balances) | receivables only; two segments | no score, <=600, 601-660, 661-720, >720 | 2026-06-10 |
| Chase | FICO (Experian/FICO Bankcard Score 8) | yes, Mar-2026 | receivables only, **5% random sample** | no score, <600, 600-659, 660-719, 720+ | 2026-03-31 |
| Citi | FICO | monthly ("most accounts") | **accounts and receivables** | 000, 001-599, 600-639, 640-660, 661-679, 680-699, 700-719, 720-739, 740-759, 760-800, 801+ | 2025-03-30 |
| Discover | FICO | yes ("as refreshed during May 31, 2023") | receivables only ($000s) | no score, <600, 600-659, 660-719, 720+ | 2023-05-31 (stale) |
| Synchrony | **VantageScore** | at least quarterly | receivables only | no score/<=599, 600-659, 660-719, 720+ | 2026-05-31 |
| BofA | FICO (single bureau) | within six months | receivables only | <=600, 601-660, 661-720, >720, unscored | 2026-04-01 |

Five of seven can be collapsed to the same four bands (<600 / 600-659 / 660-719 / 720+, with COMET and BofA using 601-660 / 661-720 boundaries one point different). Citi's 11 buckets collapse onto those bands exactly (000+001-599; 600-639+640-660; 661-679+680-699+700-719; 720+). Amex cannot be mapped (560 / 660 / 700 / 760 cuts). Synchrony is a different scale (VantageScore). Only Citi gives the account-count distribution. Credit-limit tables all give accounts and receivables, but the bucket edges differ by trust (Amex adds a "No Pre-Set Spending Limit" line equal to 42.27% of receivables). Account-age tables are degenerate (100% in the top bucket) for every trust except Synchrony.

## D. History length

Verified from submissions JSON except where noted in section A: Amex Jul-2006, BofA Mar-2006, Citi Apr-2006 (Master Trust I), COMET Feb-2006 and Chase Mar-2006 (both from browse-edgar lists; JSON older pages not fetched), Discover Aug-2007 to Nov-2025 (defeased), Synchrony SCIT Oct-2018 (predecessor Synchrony Credit Card Master Note Trust, CIK 0001290098, files from 2006-11-28 but is a different pool). All monthly. Caveats for a back-history parser: exhibit formats change with filer agents (see A) and, for the early years, the primary documents are `.txt` (Amex `b414012_10d.txt`, Citi `it032806t.txt`).

## Summary

| Trust | (i) Monthly charge-off rate in 10-D | (ii) FICO distribution | (iii) Credit-limit distribution | Missing / caveats |
|---|---|---|---|---|
| Amex | Yes - gross and net, annualized x365/days on ending principal | Yes, refreshed monthly, receivables only, non-standard buckets | Yes, accounts + receivables; 42% of receivables are no-preset-limit charge products | No account-based FICO; denominators not printed |
| COMET | Yes - gross and net, x12 on adjusted beginning principal | Yes, refreshed, receivables only, split consumer / small business | Yes, both bases, 4 buckets, per segment | No excess-spread % or base rate in the 10-D |
| Chase | Yes - gross and net, x12 on "Average Pool Balance" (= beginning principal) | Yes but only a 5% random sample, refreshed, receivables only | Yes, both bases, 7 buckets | Pool stats (EX-99.2) and yield/excess spread (EX-99.3) in different exhibits |
| Citi | Rate only: "Credit Loss Component" 1.90% (gross, actual/365 over the 33-day due period, on the collateral certificate invested amount = pro-rata pool rate); no dollar pool charge-off row; no net rate | Yes, refreshed monthly, **accounts and receivables**, 11 buckets | Yes, both bases, 14 buckets | Due period ends ~28th; 1-30 day bucket included; no recoveries row |
| Discover | **No** - notes defeased 2025-12-18; last pool report is the Dec-2025 10-D and 2024-25 reports are JPG images | Only in the 2023-06-23 prospectus (stale), refreshed, receivables only | Same prospectus, both bases, 4 buckets | Series ends Nov-2025; historical values need OCR |
| Synchrony | Yes - gross and net, x12 on BOP principal (label does not say annualized) | **No FICO** - VantageScore, refreshed at least quarterly, receivables only | Yes, both bases, 12 buckets | Different score scale; private-label/retail pool (5.3% gross loss rate) |
| BofA | Yes - gross and net, x12 on average daily principal, in $ thousands | Yes, refreshed within six months, receivables only | Yes, both bases, 6 buckets | Also an investor-interest-based loss rate (2.71% / 2.11%) that differs from the pool table |

Surprises: (1) Discover's DCENT was defeased on 2025-12-18 after the Capital One acquisition; its 10-Ds continue but carry no pool data, and there has been no Discover prospectus since June 2023. (2) Chase's FICO table is a 5% random sample, not the pool. (3) Synchrony uses VantageScore, so a "FICO" search misses it. (4) Citi publishes the most granular FICO table (11 buckets, by accounts and by balances) but the least explicit monthly loss disclosure (a single "Credit Loss Component" percentage, gross, with no dollar row and no net rate). (5) Annualization conventions differ: Amex x365/days on ending principal; Citi actual/365 on a 33-day due period; the other four x12 (Chase and BofA on average balances, COMET and Synchrony on beginning balances). (6) Every account-age table except Synchrony's is 100% in the oldest bucket, so account age is not usable as a cross-trust control. (7) Delinquency bucket edges differ (Amex 31-60..., Citi 1-30..., COMET tops at 150+).
