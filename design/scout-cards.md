# Scout: public credit card master trust data on EDGAR

Written 2026-09-08 (session started ~00:50 local). Status of this file: **interim** - see "Access status" first.

## Access status (read this first)

- Every direct request from this machine to `www.sec.gov`, `data.sec.gov` and `efts.sec.gov` returned HTTP 403
  (Akamai page "Your Request Originates from an Undeclared Automated Tool", body text: "identified as part of a
  network of automated tools"). Tested: curl 8.16 and Python `requests`, the required UA with and without an
  appended contact, extra `Accept-Encoding`/`Host` headers, HTTP/1.1, TLS 1.2, IPv4 (no IPv6 route). Even
  `https://www.sec.gov/robots.txt` and the homepage were 403, so it is an IP-level penalty (public IP 99.196.128.3).
  A once-per-minute probe (00:56-01:03) stayed 403 then `000` (connection dropped). Probe stopped 01:04 on
  coordinator instruction; no local SEC traffic after that.
- Coordinator's diagnosis (01:12): the home ISP is ViaSat satellite CGNAT and the shared address is on Akamai's
  blocklist, so the block will not clear from this machine. Files are being fetched from a GitHub Actions runner
  and will land under `data/raw/scout/edgar/cards/<slug>/` (`10D/<accession>/` for the latest 10-D + exhibits,
  `prospectus/<accession>/` for the 424B, submissions JSON alongside). Section "Plan for the local files" below
  says what to do with them. `data/raw/scout/cards/` therefore holds only the helper scripts (`_scripts/`).
- Everything below marked **[WF]** was obtained through the WebFetch tool, which fetches from Anthropic's
  infrastructure (a different IP, its own UA) and returns an LLM-rendered text of the page, **not the raw file**.
  Numbers quoted from [WF] sources are copied from that rendering; they still need to be re-verified against the
  raw file once direct download works. Nothing under `data/raw/scout/cards/` has been saved yet for that reason.
- WebFetch truncates long documents: every 424B5/424B2 prospectus was cut off before the annex that holds the
  FICO / credit-limit tables (the tool reported the cut-off point each time). So section C tables are **not yet
  copied**; the exact filing URLs to download are listed per trust.
- Requests still to make directly (with UA `abs-risk/0.1 research (+https://github.com/SamuelJWebber/abs-risk)`,
  max 2 req/s) are listed in "Download list once unblocked" at the end.

## Trust register (CIKs) [WF: EDGAR full-text search `efts.sec.gov/LATEST/search-index?q="<name>"&forms=10-D`]

| Trust | Issuing-entity CIK | Related entities (CIK) | 10-D hits (all years) |
|---|---|---|---|
| American Express Credit Account Master Trust | 0001003509 | American Express Receivables Financing Corp III LLC 0001283434, Corp IV LLC 0001283435, Corp II 0000949349 (co-registrants) | 485 |
| Capital One Multi-asset Execution Trust (COMET) | 0001163321 | Capital One Master Trust 0000922869, Capital One Funding LLC 0001162387 (co-registrants on the same 10-D) | 508 |
| Chase Issuance Trust | 0001174821 | Chase Card Funding LLC 0001658982 | 986 |
| Citibank Credit Card Issuance Trust | 0001108348 | Citibank Credit Card Master Trust I 0000921864; Citibank N.A. as depositor 0001522616 | 516 |
| Discover Card Execution Note Trust (DCENT) | 0001407200 | Discover Card Master Trust I 0000894329; Discover Funding LLC 0001645731 | 946 |
| Synchrony Card Issuance Trust (SCIT) | 0001724789 | Synchrony Card Funding LLC 0001724786; Synchrony Credit Card Master Note Trust 0001290098 (separate, older trust; RFS Holding LLC 0001226006) | 190 (SCIT); 996 (SCCMNT) |
| BA Credit Card Trust | 0001128250 | BA Credit Card Funding LLC 0001370238; BA Master Credit Card Trust II 0000936988. Former name: MBNA Credit Card Master Note Trust (through 2006-06-09) | 735 |

## A. 10-D filing cadence [WF: `www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<cik>&type=10-D&count=100`, plus `&dateb=20070630` for the oldest page]

All seven file one 10-D per month, on or about the 15th-17th (Discover on the 12th-17th). Counts below are my own
count of the rows in the fetched list, Jan-2024 through Aug-2026 = 32 months, one filing each.

| Trust | 10-Ds filed on/after 2024-01-01 | Latest 10-D (date, accession) | Earliest 10-D on EDGAR (date, accession) |
|---|---|---|---|
| Amex CAMT | 32 | 2026-08-17, 0001104659-26-097714 | 2006-07-17, 0001125282-06-004108 |
| COMET | 32 (+ a 10-D/A on 2019-03-19 outside window) | 2026-08-17, 0001163321-26-000025 | 2006-02-10, 0001104659-06-007479 |
| Chase Issuance Trust | 32 | 2026-08-17, 0001193125-26-353171 | 2006-03-16, 0001193125-06-056653 |
| Citibank CCIT | 32 | 2026-08-17, 0001193125-26-353756 | 2006-04-17, 0000839947-06-000058 |
| Discover DCENT | 32 (see defeasance note - pool data stops Nov-2025) | 2026-08-17, 0001407200-26-000026 | 2007-08-15, 0001407200-07-000004 (DCENT formed 2007; Discover Card Master Trust I 0000894329 files jointly, its own earlier 10-Ds not yet checked) |
| Synchrony SCIT | 32 | 2026-08-17, 0001104659-26-097449 | 2018-10-15, 0001144204-18-053747 (95 10-Ds total; earlier history is in Synchrony Credit Card Master Note Trust 0001290098, ex-GE Capital Credit Card Master Note Trust, not yet checked) |
| BA Credit Card Trust | 32 | 2026-08-17, 0001140361-26-033313 | 2006-03-15, 0001128250-06-000010 |

Filer-agent changes worth knowing for a parser: Amex switched from RR Donnelley (0001193125-...) to Toppan Merrill
(0001104659-...) in Dec-2025; BA switched from self-filed (0001128250-...) to Broadridge (0001140361-...) in Oct-2025;
Synchrony switched from Vintage (0001144204-...) to Toppan (0001104659-...) in Nov-2019. File names change with the agent.

## B. Latest 10-D: documents, format, and the exact row labels [WF rendering of each exhibit; raw files not yet saved]

### B1. American Express Credit Account Master Trust - 10-D filed 2026-08-17, accession 0001104659-26-097714
Directory: https://www.sec.gov/Archives/edgar/data/1003509/000110465926097714/
- `tm2623074d1_10d.htm` 24,403 bytes - primary 10-D
- `tm2623074d1_ex99-01.htm` 2,442,373 bytes - EX-99.1 "Monthly Servicer's Certificate for American Express Credit Account Master Trust"
Format: HTML tables (single very large HTML file; it repeats the certificate per series).
Period: Distribution Date August 17, 2026; activity period July 1-31, 2026.
Row labels as rendered [WF] (values for July 2026):
- "Beginning Principal Receivable Balance, including any Additions, Removals, or Adjustments of Principal Receivables during the Monthly Period" = 25,169,022,223.30
- "Ending Principal Receivables Balance" = 24,930,085,370.00
- "Ending Total Receivables" = 26,171,740,833.37
- "Defaulted Amount" = 39,467,785.90   (gross defaults, monthly amount)
- "Recoveries" = 15,935,939.02
- "Annualized Default Rate" = 1.8640%   (annualized, gross)
- "Annualized Default Rate, Net of Recoveries" = 1.1114%   (annualized, net)
- "Monthly Payment Rate" = 50.7944%
- "Trust Portfolio Yield" = 31.7408%
- Delinquency buckets: "31-60 Days Delinquent" 52,914,095 (0.20%); "61-90 Days Delinquent" 40,305,716 (0.15%);
  "91-120 Days Delinquent" 32,094,421 (0.12%); "120+ Days Delinquent" 45,924,272 (0.18%); "Total 30+ Days Delinquent" 171,238,503 (0.65%)
- Per-series block (e.g. Series 2023-2): "Excess Spread Percentage" = 25.4648%; "Base Rate" = 6.4400%
Notes: Amex buckets are 31-60/61-90/91-120/120+ (not 30-59...). Both gross and net default rates given, both annualized.
Verify against raw file: whether the trust-level rows appear once or per series, and whether "Recoveries" is on its own row.

### B2. Capital One Multi-asset Execution Trust - 10-D filed 2026-08-17, accession 0001163321-26-000025
Directory: https://www.sec.gov/Archives/edgar/data/1163321/000116332126000025/
- `form10-djuly2026.htm` 31,007 bytes - primary 10-D
- `exhibit9912002-ccjuly2026.htm` 151,134 bytes - EX-99.1 "Monthly Statement for Capital One Master Trust Series 2002-CC" (the master-trust pool report)
- `exhibit992nhsjuly2026.htm` 384,102 bytes - EX-99.2 "Card Series Schedule to Monthly Noteholders' Statement" (per-tranche; sections A-O; has excess spread only)
Format: EX-99.1 rendered as plain text with structured tables (self-filed by the trust, 0001163321-...); EX-99.2 HTML tables.
Period: Distribution Date August 17, 2026; July 2026 monthly period.
Row labels as rendered [WF], EX-99.1:
- "Beginning of the Month Principal Receivables" = $23,403,238,504.06
- "End of the Month Principal Receivables" = $23,264,569,372.71
- "End of the Month Total Receivables" = $23,558,216,188.81
- "30 - 59 Days Delinquent" 22,640 accounts; $110,110,539.56
- "60 - 89 Days Delinquent" 15,588; $78,362,821.12
- "90 - 119 Days Delinquent" 13,204; $69,632,603.08
- "120 - 149 Days Delinquent" 10,310; $61,529,720.87
- "150 + Days Delinquent" 10,515; $62,710,282.09
- "Defaulted Accounts during the Month" 12,498 accounts; $57,730,080.66   (gross default amount)
- "Annualized Default Rate as a Percent of Adjusted Beginning of the Month Principal Receivables which includes Additional Principal Receivables" = 2.96% (annualized, gross)
- "Annualized Net Default Rate as a Percent of Adjusted Beginning of Month Principal Receivables which includes Additional Principal Receivables" = 1.80% (annualized, net)
- "Total Collections and Gross Payment Rate as a Percent of Adjusted Beginning of Month Total Receivables which includes Additional Total Receivables" = $11,756,918,044.92; 49.61%
- "Collections of Principal Receivables and Principal Payment Rate as a Percent of Adjusted Beginning of the Month Principal Receivables which includes Additional Principal Receivables" = $11,229,005,225.75; 47.98%
- "Collections of Finance Charge Receivables and Annualized Yield as a Percent of Adjusted Beginning of the Month Principal Receivables which includes Additional Principal Receivables" = $528,288,601.15; 27.09% (annualized)
EX-99.2 section N: "Current Month Excess Spread Amount" = $213,123,849.91; "Three Month Average Excess Spread Amount" = $155,744,027.22 (dollar amounts; an excess spread *percentage* was not seen in the rendering - check raw file).
Notes: delinquency given in accounts AND dollars; top bucket is 150+ (no 180+ row). Base rate not seen.

### B3. Chase Issuance Trust - 10-D filed 2026-08-17, accession 0001193125-26-353171
Directory: https://www.sec.gov/Archives/edgar/data/1174821/000119312526353171/
- `d169887d10d.htm` 21,766 - primary
- `d169887dex991.htm` 5,527 - EX-99.1 "Monthly Information Officer's Certificate" (dates only)
- `d169887dex992.htm` 64,676 - EX-99.2 "Asset Pool One Monthly Servicer's Certificate" (pool receivables, losses, delinquencies)
- `d169887dex993.htm` 161,266 - EX-99.3 "Chase Issuance Trust CHASEseries Monthly Noteholders' Statement" (yield, base rate, excess spread, payment rate)
Format: HTML tables. Period: July 2026; Payment Date August 17, 2026.
EX-99.2 rows [WF]:
- Principal Receivables "Beginning Balance" = 11,946,847,375.49; "Ending Balance" = 11,728,896,182.88
- "Gross Losses" = 20,157,969.63; "Net Losses" = 15,775,885.97; "Number of Accounts Charged Off During the Monthly Period" = 3,503
- "Gross Losses as a Percentage of Average Pool Balance (Annualized)" = 2.02%
- "Net Losses as a percentage of Average Pool Balance (Annualized)" = 1.58%
- Delinquencies: "30-59 days" 4,651 accts, $27,904,841.61 (0.24%); "60-89 days" 2,832, $20,117,199.14 (0.17%); "90-119 days" 1,953, $15,749,407.73 (0.13%); "120-149 days" 1,736, $15,858,053.30 (0.13%); "150-179 days" 1,843, $16,436,974.16 (0.14%)
EX-99.3 rows [WF]:
- "(a) Portfolio Yield" = 22.83%; "(b) Base Rate" = 6.20%; "(a) - (b) = Excess Spread Percentage" = 16.63%
- "Principal Payment Rate" = 53.56%; "Excess Spread Amount paid to Transferor" = $122,511,491.72
Notes: charge-off rates are on *average pool balance*, not beginning balance. Pool metrics and yield/excess spread are in two different exhibits.

### B4. Citibank Credit Card Issuance Trust - 10-D filed 2026-08-17, accession 0001193125-26-353756
Directory: https://www.sec.gov/Archives/edgar/data/1108348/000119312526353756/
- `d138267d10d.htm` 24,489 - primary; `d138267dex99.htm` 157,610 - EX-99 (single report covering Citibank Credit Card Master Trust I and the Issuance Trust)
Format: HTML tables. Period: "Due Period Ending July 28, 2026" (Citi's due period ends around the 28th, not month-end).
Rows [WF]:
- "Principal Receivables Beginning of Due Period" = $19,165,697,102; "Principal Receivables End of Due Period" = $19,119,983,665
- Total receivables "Current" = $19,406,570,793
- "Investor Default Amount" = $8,766,208   (investor share only - a pool-level gross/net charge-off row was NOT seen in the rendering; must check raw file for a "Principal Receivables charged off"/"Net Credit Losses" row)
- "Total Payment Rate" = 43.06%; "Principal Payment Rate" = 43.84%
- "Portfolio Yield for the Collateral Certificate" = 21.51%
- Delinquencies (dollars): "1-30 days delinquent" $252,230,180; "31-60 days delinquent" $76,269,089; "61-90 days delinquent" $57,536,794; "91-120 days delinquent" $48,137,590; "121-150 days delinquent" $40,781,279; "151-180 days delinquent" $42,241,217
- "3 Month Average Surplus Finance Charge Collections" = 17.23% (Citi's excess-spread analogue; section F.7 "Excess Spread/Early Redemption Event Trigger")
- "Weighted Average Interest Rate" = 4.31%
- Second pass [WF] asking for every row containing Charge/Default/Loss/Recover found only: section A "Credit Loss Component" = 1.90%; section C1 "Investor Default Amount" = $8,766,208 (two columns, same value); no row labelled gross/net charge-offs or a recoveries row was returned.
- Delinquency table = section A.6 "Delinquency (1)", dollars AND % of total receivables: "Current" $19,406,570,793 (97.41%); "1-30 days delinquent" $252,230,180 (1.27%); "31-60" $76,269,089 (0.38%); "61-90" $57,536,794 (0.29%); "91-120" $48,137,590 (0.24%); "121-150" $40,781,279 (0.20%); "151-180" $42,241,217 (0.21%)
Notes: Citi buckets are 1-30/31-60/.../151-180 and include a 1-30 bucket. **Citi's pool-level charge-off rate is the weakest disclosure of the seven** as rendered: "Credit Loss Component" (1.90%) may be the annualized net loss rate used in the base-rate/yield test, but the raw file must confirm its definition (footnote). "Investor Default Amount" is the investor-interest share of defaults, not the pool.

### B5. Discover Card Execution Note Trust - 10-D filed 2026-08-17, accession 0001407200-26-000026  **(post-defeasance)**
Directory: https://www.sec.gov/Archives/edgar/data/1407200/000140720026000026/
- `dcent10-ddocumentxjuly2026.htm` 31,650 - primary; `exhibit991report-postdefea.htm` 24,887 - "Monthly Servicer Certificate, Discover Card Execution Note Trust, DiscoverSeries Class A(2021-2) Notes"
Rendering [WF] quotes: "Under the Defeasance Agreement, dated as of December 18, 2025 (the 'Defeasance Agreement'), by and among Discover Card Execution Note Trust ('DCENT'), as Issuer, U.S. Bank Trust Company, National Association ('USBTC'), in its capacity as Indenture Trustee and as Paying Agent..."
The July-2026 exhibit has NO receivables, charge-off, payment-rate, yield or delinquency rows - only "Total Interest Payment (Class A)" $515,000.00, "Total Principal Distribution (Class A)" $0.00, "Defeasance Interest Funding Account" $607,700.00, "Defeasance Principal Funding Accounts" $906,717,306.59.
=> Discover's public pool series ends with the 10-D filed 2025-12-15 (month ending November 30, 2025). Capital One closed its acquisition of Discover in 2025; the notes were defeased 2025-12-18.
Last pre-defeasance 10-D: filed 2025-12-15, accession 0001407200-25-000040, directory https://www.sec.gov/Archives/edgar/data/1407200/000140720025000040/ - files: `dcent-dcmt10xd121525.htm` (primary, 33,873), `a2007-cccertstatement121.htm` (12,759) + 4 JPGs `a2007-cccertstatement121001..004.jpg`, `noteholders121525.htm` (25,515) + 15 JPGs `noteholders121525001..015.jpg`. The Dec-2024 filing (0001407200-24-000035) has the same shape (16 JPGs). [WF] rendering of `noteholders121525.htm`: title "DISCOVERSERIES NOTEHOLDERS STATEMENT", "Month Ending: November 30, 2025", "Distribution Date: December 15, 2025", text rows seen: "Excess Spread Percentage ... 13.70% ... $33,938,131.67", "Three-month average ... 13.55%", "Coupon interest rate ... 3.14%", "Excess Spread Early Redemption Event: No", "Delinquency Trigger: No". The pool-level tables (receivables, charge-offs, delinquencies) appear to be in the JPG images / the Series 2007-CC certificate statement.
[WF] rendering of `a2007-cccertstatement121.htm` (EX-99.1) confirms it: title "Investor Certificateholders' Monthly Statement Discover Card Master Trust I Series 2007-CC Monthly Statement Distribution Date: December 15, 2025 Month Ending: November 30, 2025"; the HTML text carries only the section headings - "Principal Receivables for November, 2025", "Credit Risk Retention at the end of November, 2025", "Allocation Percentages at the beginning of November, 2025", "Allocation of Receivables and other amounts collected during November, 2025", "Investor Charged-Off Amount", "Cumulative Reductions in Series Investor Interests Due to Investor Charged-Off Amounts", "Investor Monthly Servicing Fee payable to CONA", "Delinquency Summary", "Total Master Trust and Investor Principal Charge-Offs" - plus footnotes (1)-(6); "All numeric data appears only inside embedded images". It cites the "Second Amended and Restated Series Supplement dated as of May 18, 2025" and the servicer is now CONA (Capital One, N.A.). **=> Discover's monthly pool numbers need OCR of 4 JPGs per month (at least for 2024-2025; older years may be text - not checked).**
Discover Card Master Trust I (0000894329) files jointly with DCENT (same accession numbers); its earliest 10-D was not determined (the dateb-filtered list came back with the latest page).

### B6. Synchrony Card Issuance Trust - 10-D filed 2026-08-17, accession 0001104659-26-097449
Directory: https://www.sec.gov/Archives/edgar/data/1724789/000110465926097449/
- `tm2622590d1_10d.htm` 53,293 - primary; `tm2622590d1_ex99-1.htm` 262,145 - EX-99.1 "Monthly Noteholder's Statement for Synchrony Card Issuance Trust, SynchronySeries"
Format: HTML tables. Period: Monthly Period 07/01/2026-07/31/2026; Payment Date 08/17/2026.
Rows [WF]:
- "BOP Aggregate Principal Receivables" = 10,972,300,373.45; "EOP Aggregate Principal Receivables" = 10,893,543,177.22
- "BOP Total Receivables" = 11,475,209,377.40; "EOP Total Receivables" = 11,404,850,598.69
- "Default Amount for Defaulted Accounts" = 48,860,288.23
- "Gross Charge-Off Rate (Default Amount for Defaulted Accounts / BOP Principal Receivables) Current" = 5.3437%
- "Net Charge-Off Rate (Default Amount for Defaulted Accounts - Recoveries/ BOP Principal Receivables) Current" = 4.1142%
- "Payment Rate (Principal Collections / BOP Principal Receivables) Current" = 25.2915%
- "(a) Portfolio Yield" = 21.76%; "(a)- (b) = Excess Spread Percentage" = 16.57% (annualized)
- Delinquencies (accounts; % of receivables): "30-59 Days Delinquent" 32,294; 0.7555% | "60-89 Days Delinquent" 22,721; 0.5784% | "90-119 Days Delinquent" 19,089; 0.5103% | "120-149 Days Delinquent" 14,840; 0.4366% | "150-179 Days Delinquent" 14,079; 0.4365%
Notes: label text embeds the formula; "Current" column implies there are also 3-month-average columns. Charge-off rate 5.34%/4.11% vs 1.9%/1.1% at Amex - private-label/retail pool. Whether the rate is annualized must be checked in the raw file (48.86M / 10.97B = 0.445% monthly, x12 = 5.34%, so it IS annualized despite the label).

### B7. BA Credit Card Trust - 10-D filed 2026-08-17, accession 0001140361-26-033313
Directory: https://www.sec.gov/Archives/edgar/data/1128250/000114036126033313/
- `ef20079972_10d.htm` 27,801 - primary; `ef20079972_ex99-1.htm` 220,813 - EX-99.1 "Monthly Certificateholders' Statement, Series 2001-D" (BA Master Credit Card Trust II pool report); `ef20079972_ex99-2.htm` 118,693 - EX-99.2 "Schedule to Monthly Noteholders' Statement" (sections A-N, per class); `image0.jpg` 102,843.
Format: HTML tables with plain-text sections. Period: Monthly Period Ending July 31, 2026; Transfer Date August 14, 2026.
EX-99.1 rows [WF]:
- "The aggregate amount of Principal Receivables in the Trust as of the beginning of the related Monthly Period" = $14,333,396,313.73
- "The aggregate amount of Principal Receivables in the Trust as of the end of the day on the last day of the related Monthly Period" = $14,216,676,954.68
- "The aggregate amount of Receivables in the Trust as of the end of the day on the last day of the related Monthly Period" = $14,552,256,361.78
- "Total Charge-Offs" (July 31, 2026) = $32,369 (thousands); "Net Charge-Offs" = $25,191 (thousands)
- "Aggregate Class D Investor Default Amount for the related Monthly Period" = $22,876,379.39
- "Collections of Principal Receivables as a percentage of prior month Principal Receivables" = 28.48%
- "The Portfolio Yield for the related Monthly Period" = 17.06% (annualized); "Base Rate for the related Monthly Period" = 4.40%
- "Excess Available Funds Percentage for the related Monthly Period" = 12.66%
- Delinquencies as of July 31, 2026 ($; %): 30-59 days $53,530,346.30 (0.36%); 60-89 $38,603,265.99 (0.27%); 90-119 $30,561,350.43 (0.21%); 120-149 $30,216,475.88 (0.21%); 150-179 $31,042,931.55 (0.21%); 180+ $38,779.50 (0.00%); "60+-Day Delinquency Rate" = 0.90%; "Three-Month Average 60+-Day Delinquency Rate" = 0.92%
- Second pass [WF] found the rate rows (table gives current month and prior month columns, "Month Ended July 31, 2026" / "Month Ended June 30, 2026"):
  "Total Charge-Offs as a percentage of Average Principal Receivables Outstanding" = 2.74% (June: 2.80%)
  "Net Charge-Offs as a percentage of Average Principal Receivables Outstanding" = 2.13% (June: 2.23%)
  "Recoveries as a percentage of Average Principal Receivables Outstanding" = 0.61% (June: 0.57%)
  "Total Cash Yield for the related Monthly Period as a percentage of Series 2001-D Weighted Average" = 19.77%
  "Aggregate Investor Default Amount for the related Monthly Period" = $0.00 (vs the Class D row above)
  Arithmetic check: $32,369K / ~$14.27B avg principal = 0.227%/month, x12 = 2.72% ~ 2.74%, so the rates are annualized even though the label does not say so.
Notes: charge-offs in thousands in a separate table; rates are on *average* principal receivables (like Chase). Has a 180+ bucket.

## C. Prospectuses with composition tables [WF: efts search `q="FICO" "<trust>"`, forms 424B5/424B2/424B3, 2023-01-01..2026-09-08]

None of the tables could be copied yet (WebFetch cut each document off before the annex). Candidates and what the rendering did show:

| Trust | Most recent prospectus with "FICO" | URL | Where the tables sit | Seen in rendering |
|---|---|---|---|---|
| Amex CAMT | 424B5 filed 2025-07-17 (two series same day: 0001193125-25-160040 d938410d424b5.htm and 0001193125-25-160041 d938411d424b5.htm); also 2025-05-07, 2025-02-05, 2024-07-17, 2024-04-17 | https://www.sec.gov/Archives/edgar/data/1003509/000119312525160040/d938410d424b5.htm | "Annex I: The Trust Portfolio" (page A-I-1); text says "Additional information regarding the receivables in the Trust Portfolio is provided in Annex I to this prospectus, which forms an integral part of this prospectus." | As of May 31, 2025: total receivables $26,797,475,459; principal receivables $25,447,441,858; finance charge receivables $1,350,033,601; 13,609,288 accounts |
| COMET | 424B5 filed 2026-07-13 (0001193125-26-302052 d76692d424b5.htm; sibling 0001193125-26-302059 d155768d424b5.htm); earlier 2025-10-28, 2025-09-11 (x2), 2024-09-19, 2023-05-19 | https://www.sec.gov/Archives/edgar/data/1163321/000119312526302052/d76692d424b5.htm | Annex I "The Capital One Credit Card Portfolio" (A-I-1): "The Master Trust Portfolio-General", "Delinquency and Loss Experience", "Revenue Experience", "Payment Rates", "The Receivables", "Review of Receivables in Master Trust Portfolio" | As of June 10, 2026: principal receivables $22,835,080,583; finance charge receivables $275,892,346 |
| Chase Issuance Trust | 424B5 filed 2026-05-22 (0001193125-26-236451 d53666d424b5.htm); earlier 2025-07-18, 2024-01-25 (x2), 2023-09-08 (x2) | https://www.sec.gov/Archives/edgar/data/1174821/000119312526236451/d53666d424b5.htm | Section "JPMorgan Chase Bank's Credit Card Portfolio-Composition of Issuing Entity Receivables" (main body, not an annex) | As of March 31, 2026: total receivables $11,882,685,348; average receivables balance per account $1,787; average credit limit $16,324; receivables-to-credit-limit 10.95%; average account age approximately 293 months |
| Citibank CCIT | 424B2 filed 2025-06-23 (0001193125-25-144485 d946334d424b2.htm; sibling 0001193125-25-144490); earlier 2023-12-06 (x2) | https://www.sec.gov/Archives/edgar/data/1108348/000119312525144485/d946334d424b2.htm | "ANNEX I: THE MASTER TRUST RECEIVABLES AND ACCOUNTS" (after Glossary p.193); Annex II "The U.S. Credit Card Business of Citibank" | nothing numeric reached |
| Discover DCENT | 424B5 filed 2023-06-23 (0001193125-23-173892 d460049d424b5.htm) and 2023-04-06 (0001193125-23-094130). **No 424B* filings since 2024-01-01** (search of trust name, all 424B forms, 2024-2026 = 0 hits) - consistent with the acquisition/defeasance | https://www.sec.gov/Archives/edgar/data/1407200/000119312523173892/d460049d424b5.htm | not fetched yet | - |
| Synchrony SCIT | "FICO" phrase search = 0 hits 2023-2026 (Synchrony may write "FICO(R)" or use a different label). Trust-name search: 424B5 filed 2026-08-07 (0001104659-26-092741 tm2622401d3_424b5.htm), 2026-03-17, 2025-11-12, 2025-06-04, 2025-02-12, 2024-07-25, 2024-03-13 | https://www.sec.gov/Archives/edgar/data/1724789/000110465926092741/tm2622401d3_424b5.htm | "Annex III: The Trust Portfolio" (A-III-1); "Annex II: Static Pool Data" (A-II-1) | As of May 31, 2026: total transferred receivables $11,489,137,310; average account age approximately 101 months |
| BA Credit Card Trust | 424B5 filed 2026-05-11 (0000929638-26-001790 ba424b5.htm); earlier 2025-06-09, 2024-06-10, 2023-12-11, 2023-06-09 | https://www.sec.gov/Archives/edgar/data/1128250/000092963826001790/ba424b5.htm | Annex I "THE MASTER TRUST II PORTFOLIO" (A-I-1): "General", "Delinquency and Principal Charge-Off Experience", "Revenue Experience", "Principal Payment Rates", "The Receivables" | nothing numeric reached |

Whether FICO is refreshed vs at-origination, bucket edges, and by-balance vs by-account: **unknown until the raw prospectuses are downloaded.**

## D. History length
See table in A. Six of seven have 10-Ds back to Feb-Jul 2006 (the first year 10-D existed); DCENT from Aug-2007; SCIT from Oct-2018. SCIT's predecessor Synchrony Credit Card Master Note Trust (CIK 0001290098; former name "GE Capital Credit Card Master Note Trust (filings through 2014-08-18)") has 10-Ds from 2006-11-28 (accession 0001290098-06-000021), filed late in the month (26th-30th) rather than mid-month [WF, browse-edgar dateb=20070630]. It is a different pool (GE/Synchrony private-label) so it is a separate series, not a back-extension of SCIT. Discover's usable series ends Nov-2025.

## Plan for the local files (once the runner artifact is on disk)

Helpers (no SEC traffic, read-only on the raw files):
- `data/raw/scout/cards/_scripts/print_rows.py` - walks `data/raw/scout/edgar/cards/<slug>/**/*.htm*`, skips 424B files, and writes `<slug>/_rows.txt` with every table row (or text line) mentioning receivable / charge-off / default / loss / recover / payment rate / yield / delinq / excess / base rate / days. Also tags each file `html-table`, `text`, or `image-wrapped` (>=3 `<img>` tags).
- `data/raw/scout/cards/_scripts/print_tables.py <424B file>` - writes `<file>.tables.txt` with every table whose text mentions FICO / credit limit / account age / seasoning / VantageScore, pipe-delimited, with the nearest preceding text (title/caption).
- `data/raw/scout/cards/_scripts/fetch_cards.sh` - the direct curl download list (kept for reference; do not run from this machine).

Checks to make per trust, in this order:
1. 10-D: confirm the row labels in section B against the raw HTML (exact spelling, whether labels span cells, which column is "current" vs "3-month average"), confirm annualization from arithmetic (monthly amount / beginning principal x 12), and note where the trust-level block sits (Amex: once, or repeated per series?).
2. Open questions to settle from the raw 10-Ds: Citi - definition of "Credit Loss Component" and whether any pool-level net-loss row exists; COMET - whether EX-99.2 has an excess spread *percentage* and a base rate; BA - whether the charge-off table has 3-month-average columns; Amex - whether "Recoveries" and the per-bucket "% of receivables" are their own rows; Discover - confirm the JPG-only finding and check whether an older year (e.g. 2019) was text.
3. Prospectus: run `print_tables.py`, then copy the FICO and credit-limit tables verbatim into section C with title, as-of date, bucket edges, and the footnote that says refreshed vs at-origination and by-balance vs by-account; note the account-age table if present. Expected locations: Amex Annex I "The Trust Portfolio"; COMET Annex I "The Capital One Credit Card Portfolio" (subsection "The Receivables"); Chase main body "JPMorgan Chase Bank's Credit Card Portfolio-Composition of Issuing Entity Receivables"; Citi Annex I "The Master Trust Receivables and Accounts"; Discover 2023 424B5 (section name unknown); Synchrony Annex III "The Trust Portfolio"; BA Annex I "The Master Trust II Portfolio" subsection "The Receivables".
4. Submissions JSON: recount 10-Ds with filingDate >= 2024-01-01 and confirm the earliest 10-D dates in section A (the JSON `filings.recent` arrays hold only the latest ~1000 filings; older ones are in the `filings.files[]` pages).

## Download list (reference: the exact URLs; the runner fetches these)
Original intent was `data/raw/scout/cards/<slug>/`; the runner drops them under `data/raw/scout/edgar/cards/<slug>/` instead:
1. amex: `https://www.sec.gov/Archives/edgar/data/1003509/000110465926097714/{tm2623074d1_10d.htm,tm2623074d1_ex99-01.htm}`; prospectus `.../1003509/000119312525160040/d938410d424b5.htm`
2. capital-one: `.../1163321/000116332126000025/{form10-djuly2026.htm,exhibit9912002-ccjuly2026.htm,exhibit992nhsjuly2026.htm}`; prospectus `.../1163321/000119312526302052/d76692d424b5.htm`
3. chase: `.../1174821/000119312526353171/{d169887d10d.htm,d169887dex991.htm,d169887dex992.htm,d169887dex993.htm}`; prospectus `.../1174821/000119312526236451/d53666d424b5.htm`
4. citi: `.../1108348/000119312526353756/{d138267d10d.htm,d138267dex99.htm}`; prospectus `.../1108348/000119312525144485/d946334d424b2.htm`
5. discover: `.../1407200/000140720026000026/{dcent10-ddocumentxjuly2026.htm,exhibit991report-postdefea.htm}`; last normal `.../1407200/000140720025000040/{dcent-dcmt10xd121525.htm,a2007-cccertstatement121.htm,noteholders121525.htm}` + JPGs; prospectus `.../1407200/000119312523173892/d460049d424b5.htm`
6. synchrony: `.../1724789/000110465926097449/{tm2622590d1_10d.htm,tm2622590d1_ex99-1.htm}`; prospectus `.../1724789/000110465926092741/tm2622401d3_424b5.htm`
7. bofa: `.../1128250/000114036126033313/{ef20079972_10d.htm,ef20079972_ex99-1.htm,ef20079972_ex99-2.htm}`; prospectus `.../1128250/000092963826001790/ba424b5.htm`
8. submissions JSON for each CIK to confirm counts: `https://data.sec.gov/submissions/CIK0001003509.json` etc.

## Summary so far (interim)
- Monthly charge-off rate public: Amex (gross+net, annualized), COMET (gross+net, annualized), Chase (gross+net, annualized, on average pool balance), Synchrony (gross+net, label says /BOP principal; arithmetic shows annualized), BA (gross+net dollar amounts in thousands; rate row not yet seen), Citi (only "Investor Default Amount" seen so far - pool rate unconfirmed), Discover (none after Nov-2025; pre-defeasance reports look image-based).
- FICO distribution / credit limit distribution: all seven reference a portfolio annex/section; none copied yet (blocked). Chase's summary already gives average credit limit ($16,324) and average account age (293 months).
- Surprises: (1) DCENT defeased 2025-12-18 - Discover pool data ends; (2) Discover's monthly statements are HTML wrappers around JPG images; (3) delinquency bucket edges differ: Amex 31-60/61-90/91-120/120+; Citi 1-30/31-60/.../151-180; COMET top bucket 150+; Chase/Synchrony 30-59..150-179; BA adds 180+; (4) Citi's due period ends on the 28th; (5) Chase splits pool stats (EX-99.2) from yield/excess spread (EX-99.3), COMET likewise (EX-99.1 vs EX-99.2).
