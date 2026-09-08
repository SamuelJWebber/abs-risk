# Scout: public loan-level auto ABS data on EDGAR (Form ABS-EE, EX-102)

Date: 2026-09-08 (second pass folded in). Repo root: `C:\Users\samwe\code\abs-risk\`. All paths are relative to
the repo root. Every number cites the file it came from.

Path shorthands:

- `R1` = `data/raw/scout/edgar/autos/` (first runner pass; URLs and sizes in `data/raw/scout/edgar/manifest.json`)
- `R2` = `data/raw/scout/edgar2/scout-edgar-second_pass-34192024913/autos/` (second pass: pairs, six new issuers, three prospectuses; no manifest, the run crashed after the pairs)
- `R3` = `data/raw/scout/edgar3/scout-edgar-second_pass-34192371366/autos/` (search reruns; `second_pass_results.json` and `_search/*.json`)
- `profile.json` beside each XML is the runner's output of my `analyze_ex102.py`; `zb_scoretype.json` and `persistence2_*.json` are my local outputs (scripts `zb_and_scoretype.py`, `compare_assets2.py`).

Contents

0. Access diagnostics
1. Issuers that file ABS-EE (20 found, 20 not), segments now measured for 8
2. The twelve downloaded EX-102 files
3. Field-by-field answers
4. Distributions per issuer (score buckets, means, delinquency, zero-balance codes)
5. Same-deal persistence results and retention rules per issuer
6. Unit and score-type hazards across issuers
7. Exhibit naming and the fetcher's filter
8. What the prospectuses say (score model, floor, weighted average)
9. Data-volume estimate from real sizes
10. Third pass: what to fetch next
11. Go/no-go for Track B and design inputs for the fetcher and panel builder
12. Summary

---

## 0. Access diagnostics

All SEC hosts returned HTTP 403 "Your Request Originates from an Undeclared Automated Tool" (Akamai) for every
request from this machine, from the first request of the session. Tried with the mandated User-Agent
`abs-risk/0.1 research (+https://github.com/User5017)` unless noted; nothing faked a browser.

| Test | Host | Result | Saved response (under `data/raw/scout/autos/_search/`) |
|---|---|---|---|
| efts full-text search, mingw curl | efts.sec.gov | 403, 4818-byte block page | `sdart.json` |
| company browse (atom) | www.sec.gov/cgi-bin/browse-edgar | 403 | `browse_santander.atom` |
| submissions JSON | data.sec.gov | 403 | `sub_test.json` |
| Archives folder index | www.sec.gov/Archives | 403 | `archives_test.html` |
| same UA + `User5017@users.noreply.github.com` appended | data.sec.gov, efts | 403 | `diag_b.json`, `diag_c.json` |
| curl HTTP/1.1 + Accept/Accept-Language/Accept-Encoding | data.sec.gov | 403 | `diag_d.json` |
| Python `requests` (OpenSSL) | data.sec.gov, efts | 403, server `AkamaiGHost` | stdout only |
| Windows System32 curl.exe 8.21 (Schannel) | data.sec.gov | 403 | `diag_wincurl.json` |
| PowerShell Invoke-WebRequest | data.sec.gov | 403 | stdout only |
| sec.gov homepage | www.sec.gov/ | 403 (edge 23.5.4.249) | `diag_home.html` |
| 10 min silence then one probe, three times | data.sec.gov | 403 at 05:04:08Z, 05:13:13Z, 05:23:25Z | `wait_probe_1..3.json`, `sec_wait.log` |
| IPv6 path | - | no IPv6 route | - |

Cause: public IPv4 `99.196.128.3`, hostname `99-196-128-3.cust.exede.net`, org `AS40306 ViaSat, Inc.` (ipinfo.io,
stdout): satellite internet behind carrier-grade NAT, so the address is shared and sits on Akamai's
IP-reputation list ("identified as part of a network of automated tools"). Not the UA, not the client, not
transient. EDGAR pulls run on the GitHub Actions runner (first-pass manifest note `probe data.sec.gov ok=True`);
this machine only analyzes.

## 1. Issuers that file ABS-EE

Sources: `R1/issuers.json` (exact-phrase full-text search, `forms=ABS-EE`, filed 2025-01-01 to 2026-12-31, page 1,
entity aggregation; raw pages `R1/_search/<slug>.json`) and the reruns in `R3/second_pass_results.json` and
`R3/_search/*.json`. "Hits" = ABS-EE filings matching the phrase in the window; each live trust files monthly, so
hits / ~20 is roughly the number of trusts alive in the window. "Measured" segments come from the EX-102 profiles in
section 4; the others are shelf convention only.

### 1a. Found (20)

| Issuer | Hits | Latest | Who files (CIK) | Example trusts (CIK), 2023-2026 | Segment |
|---|---|---|---|---|---|
| Santander Drive Auto Receivables Trust (SDART) | 472 | 2026-08-17 | Depositor Santander Drive Auto Receivables LLC 0001383094, trust as co-registrant | 2026-1 (0002105961, from the 424B5 hit in `R3`); 2025-1 (0002049903); 2024-4 (0002031161); 2024-2 (0002018245); 2022-4..7 (0001934902, 0001941255, 0001943670, 0001947426); 36 deal patterns alive since 2025-04 in `R1/santander-drive-auto-receivables-trust/submissions_0001383094.json` | **Subprime, measured**: "Bureau" score median 600, 16.9% zero, APR 17.9%, 13-18% 30+ |
| Drive Auto Receivables Trust (DRIVE) | 576 (phrase also matches SDART) | 2026-08-17 | Same depositor 0001383094 | 2025-1 (0002067387); 2025-2 (0002082136); 2024-1 (0002009921); 2024-2 (0002036081) | Deeper than SDART by shelf; not measured |
| AmeriCredit Automobile Receivables Trust (AMCAR) | 142 | 2026-08-24 | Each trust self-files (accession prefix = trust CIK) | 2024-1 (0002020251); 2023-2 (0001987878); 2023-1 (0001963240); 2022-2 (0001929381); 2022-1 (0001910595). Rerun: "AmeriCredit Automobile Receivables Trust 2025" 0 hits, "... 2026" 0 hits (`R3/_search/americredit-*.json`), so **2024-1 is the newest public AMCAR deal** | **Subprime, measured**: "Credit Bureau Score" median 587, APR 16.7%, 14.5% 30+ (2024-1) |
| GM Financial Consumer Automobile Receivables Trust (GMCAR) | 346 | 2026-08-20 | Trusts self-file | 2025-1 (0002047316); 2025-2 (0002060535); 2025-3 (0002071240); 2025-4 (0002084404); 2026-1 (0002099048); 2026-2; 2026-3 | Prime by shelf; not measured (GM Financial's other shelf; AMCAR's score cliff at 640 in section 4 says the split is around there) |
| CarMax Auto Owner Trust (CAOT) | 342 | 2026-08-17 | Trusts self-file; pre-closing pool filings by CarMax Business Services 0001259380 | 2026-2 (0002117307); 2026-1 (0002094950); 2025-4 (0002089777); 2025-3 (0002074530); 2025-2 (0002063979); 2025-1 (0002049715); 2026-3 (0002142044) | **Near-prime/prime, measured**: FICO floor 650, median 763, APR 8.6%, 1.2% 30+ |
| Ally Auto Receivables Trust | 132 | 2026-08-20 | Depositor Ally Auto Assets LLC 0001477336 | 2024-2 (0002035124); 2024-1 (0002010413); 2023-1 (0001980826); 2022-2 (0001946472) | Prime by shelf |
| Capital One Prime Auto Receivables Trust (COPAR) | 117 | 2026-09-02 | Depositor Capital One Auto Receivables LLC 0001133438 | 2026-1 (copart261, first filing 2026-09-02, 424B5 not yet on EDGAR per `R3`); 2025-1 (copart251); 2024-1 (0002039534); 2023-2 (0001992483); 2023-1 (0001951264) | **Prime, measured**: FICO 700-884 (2025-1) / 740-889 (2026-1), median 793 / 801, APR 7.3% / 6.5%, 0.16% 30+ |
| Ford Credit Auto Owner Trust | 263 | 2026-08-18 | Trusts self-file | 2025-A (0002057342); 2025-B (0002082903); 2025-C (0002092555); 2026-A (0002113024); 2026-B (0002137917) | **Prime, measured**, with a 21.6% commercial-obligor slice: consumer "Consumer Bureau" mean 761, APR 4.4%, 0.9% 30+ |
| Toyota Auto Receivables ... Owner Trust | 358 | 2026-08-27 | Depositor Toyota Auto Finance Receivables LLC 0001131131 and trusts | 2025-A (0002047571); 2025-B (0002058316); 2025-C (0002063142); 2025-D (0002063141); 2026-A (0002099539); 2026-B (0002099540); 2026-C (0002099541) | **Prime, measured**: "FICO Score 8 Auto" floor 620, median 773, APR 5.9%, 1.1% 30+ |
| Honda Auto Receivables ... Owner Trust | 288 | 2026-08-31 | Depositor American Honda Receivables LLC 0000890975 | 2025-1 (0002052479); 2025-2 (0002062789); 2025-3 (0002077602); 2025-4 (0002089171); 2024-1..4 (0002008953, 0002019551, 0002029555, 0002037549); 2023-1..4 (0001962487, 0001976562, 0001985449, 0001996308) (`R3/_search/honda-auto-receivables.json`). The first-pass zero was a query artifact (the year sits inside the name). Note the latest hits are form **ABS-EE/A** (amendments filed 2026-08-28/31 for period 2026-07-31) | Prime by shelf |
| Nissan Auto Receivables ... Owner Trust | 166 | 2026-08-19 | Depositor Nissan Auto Receivables Co II LLC 0001129068 | 2025-A (0002063629); 2023-B (0001995403); 2023-A (0001971902) | Prime by shelf |
| Hyundai Auto Receivables Trust | 303 | 2026-09-04 | Depositor Hyundai ABS Funding LLC 0001260125 | 2025-A (0002056104); 2023-B (0001980330); 2023-A (0001968583) | Prime by shelf |
| World Omni Auto Receivables Trust | 325 | 2026-08-28 | Depositor World Omni Auto Receivables LLC 0001083199 | 2025-A (0002046523); 2023-A (0001959508); 2022-D (0001950786) | Prime by shelf |
| Exeter Automobile Receivables Trust (EART) | 483 | 2026-08-31 | Trusts self-file via filer agent 0000929638; depositor EFCAR, LLC 0001654238 (424B5 rerun, `R3`) | 2026-4 (0002150254); 2026-3 (0002132838); 2026-2 (0002114382); 2026-1 (0002101848); 2025-5 (0002092528); 2025-4 (0002078220); 2025-3 (0002067124); 2025-2 (0002056803); 2025-1 (0002049379) | **Subprime, measured**: "Consumer Credit Bureau" (98.9% VantageScore per prospectus) median 584-585, APR 21.7-22.2%, 13.1% 30+ |
| Exeter Select Automobile Receivables Trust (ESART) | not searched under this name | - | Depositor EFCAR, LLC | 2025-1 (0002061324); 2025-2 (0002073963); 2025-3 (0002086449); 2026-1 (0002128772) appear as 424B5 filers in `R3/_search/exeter-automobile-receivables-trust.json` | Exeter's higher-score shelf (bureau >= 640 and proprietary >= 240, section 8). The first-pass zero was for the phrase "Exeter Select Auto Receivables Trust"; the real name has "Automobile". Public 424B5s exist, so ABS-EE almost certainly does too: search it |
| Fifth Third Auto Trust | 20 | 2026-08-27 | Trust 2023-1 (0001986424); depositor 0001405332 | one deal | Prime (bank) |
| Harley-Davidson Motorcycle Trust | 126 | 2026-08-27 | Depositor 0001114926 | 2024-B (0002034427); 2024-A (0002017611); 2023-B; 2023-A | Motorcycles; exclude |
| Mercedes-Benz Auto Receivables Trust | 119 | 2026-08-21 | Depositor 0001463814 | 2025-1 (0002044492); 2023-2 (0001993977); 2023-1 (0001957424) | Prime by shelf |
| BMW Vehicle Owner Trust | 80 | 2026-09-03 | Trusts self-file; depositor 0001136586 | 2025-A (0002049336); 2024-A (0002021594); 2023-A (0001979860) | Prime by shelf |
| Volkswagen Auto Loan Enhanced Trust | 97 | 2026-08-20 | Depositor 0001182534 | 2025-1 (0002054483); 2024-1 (0002043149); 2023-2; 2023-1 | Prime by shelf |
| Carvana Auto Receivables Trust | 357 | 2026-08-14 | Depositor Carvana Receivables Depositor LLC 0001770373 and trusts | P-series 2025-P1..P4 (0002037956, 0002037955, 0002037953, 0002037952), 2026-P1..P3 (0001976111, 0001999855, 0001999511); N-series 2021-N1..N4 still filing | Two shelves (P prime, N nonprime by naming) |

### 1b. Not found (20)

Zero ABS-EE hits 2025-2026 for the exact phrase (`R1/issuers.json`; reruns in `R3`): USAA Auto Owner Trust (rerun
"USAA Auto Owner": 0), Santander Consumer Auto Receivables Trust, Santander Retail Auto Lease Trust, Westlake
Automobile Receivables Trust, DT Auto Owner Trust, Flagship Credit Auto Trust, Bank of America Auto Trust, Chase Auto
Owner Trust, GLS Auto Receivables Issuer Trust, CPS Auto Receivables Trust, American Credit Acceptance Receivables
Trust, Credit Acceptance Auto Loan Trust, Prestige Auto Receivables Trust, United Auto Credit Securitization Trust,
First Investors Auto Owner Trust, Foursight Capital Automobile Receivables Trust, Lendbuzz Securitization Trust,
Tricolor Auto Securitization Trust, Arivo Acceptance Auto Loan Receivables Trust. These are the deep-subprime and
specialty names; zero public ABS-EE is consistent with 144A-only issuance. **The public loan-level universe stops at
Santander/Exeter/AmeriCredit-grade subprime (pool-weighted bureau scores in the 560s-580s).**

Monthly cadence is confirmed wherever a submissions JSON exists: each live SDART/DRIVE deal has 17 ABS-EE filings
over the 17 months 2025-04-15 to 2026-08-17; COPAR 2022-1 has 51 filings 2022-04-19 to 2026-04-15
(`R1/capital-one-prime-auto-receivables-trust/submissions_0001133438.json`); CarMax 2026-2, Exeter 2026-2, Ford
2025-A, Toyota 2025-A and AMCAR 2024-1 submissions JSONs in `R2` show one per month.

## 2. The twelve downloaded EX-102 files

| Deal | Period | File | Bytes | Loans | B/loan | Accession |
|---|---|---|---|---|---|---|
| SDART 2026-1 | 2026-06 | `R2/sdart-2026-1/0001193125-26-303622/sdart261ex102.xml` | 294,428,747 | 80,613 | 3,652 | 0001193125-26-303622 |
| SDART 2026-1 | 2026-07 | `R2/sdart-2026-1/0001193125-26-352879/sdart261ex102.xml` (same as `R1/.../352879/`) | 286,617,174 | 78,455 | 3,653 | 0001193125-26-352879 |
| SDART 2025-4 | 2026-07 | `R1/santander-drive-auto-receivables-trust/0001193125-26-352878/sdart254ex102.xml` | 261,821,449 | 71,671 | 3,653 | 0001193125-26-352878 |
| COPAR 2026-1 (offering pool, lp) | 2026-07 | `R1/capital-one-prime-auto-receivables-trust/0001193125-26-379485/copart261ex102_0831-1940lp.xml` | 352,286,257 | 91,627 | 3,845 | 0001193125-26-379485 |
| COPAR 2025-1 | 2026-06 | `R2/copar-2025-1/0001193125-26-304245/copart251ex102_0714-1832.xml` | 279,651,515 | 72,469 | 3,859 | 0001193125-26-304245 |
| COPAR 2025-1 | 2026-07 | `R2/copar-2025-1/0001193125-26-353478/copart251ex102_0814-1819.xml` | 279,761,409 | 72,469 | 3,860 | 0001193125-26-353478 |
| CarMax 2026-2 | 2026-06 | `R2/carmax-2026-2/0002117307-26-000013/cart20262.xml` | 168,079,368 | 52,812 | 3,183 | 0002117307-26-000013 |
| CarMax 2026-2 | 2026-07 | `R2/carmax-2026-2/0002117307-26-000018/cart20262.xml` | 167,788,225 | 52,812 | 3,177 | 0002117307-26-000018 |
| Exeter 2025-5 | 2026-06 | `R2/exeter-2025-5/0000929638-26-002770/eart2025-5_exhibit102.xml` | 192,831,125 | 55,323 | 3,486 | 0000929638-26-002770 |
| Exeter 2026-2 | 2026-07 | `R2/exeter-2026-2/0000929638-26-003320/eart2026-2_exhibit102.xml` | 109,576,670 | 31,497 | 3,479 | 0000929638-26-003320 |
| AMCAR 2024-1 | 2026-07 | `R2/amcar-2024-1/0002020251-26-000030/exh1024650072026.xml` | 150,951,536 | 36,112 | 4,180 | 0002020251-26-000030 |
| AMCAR 2023-1 | 2026-07 | `R2/amcar-2023-1/0001963240-26-000029/exh1024460072026.xml` | 94,838,470 | 22,685 | 4,181 | 0001963240-26-000029 |
| Toyota 2025-A | 2026-07 | `R2/toyota-2025-a/0001193125-26-370139/taot25aex102.xml` | 173,992,130 | 46,343 | 3,754 | 0001193125-26-370139 |
| Ford 2025-A | 2026-07 | `R2/ford-2025-a/0002057342-26-000033/autoloanmonthlydeal1183pool.xml` | 112,202,303 | 31,535 | 3,558 | 0002057342-26-000033 |

(Figures from each folder's `profile.json`: `size_bytes`, `n_records`, `reportingPeriodEndingDate`.) All share the root
`{http://www.sec.gov/edgar/document/absee/autoloan/assetdata}assetData` with one `assets` element per loan and flat
leaf elements. `assetNumber` is unique within every file. Element counts: SDART 63 (61 unique names), COPAR 59 (2026-1)
/ 64 (2025-1), CarMax 62, Exeter 65, AMCAR 68, Toyota 64, Ford 64.

Offering-pool filings: a deal's first ABS-EE arrives in two or three pool-size variants with identical period dates
(COPAR 2026-1 lp/mp/sp = 0001193125-26-379485 / -379470 / -379453; SDART 2026-1 lp/sp = 0001193125-26-045549 /
-045529; CarMax 2026-2 largepool/smallpool = 0001259380-26-000017 / -000015). The COPAR 2026-1 file in the table is
such a pool: no zero-balance codes, 0.24% one day late. Post-closing there is one filing per month.

Field list with examples and non-empty shares for SDART and COPAR: unchanged from the first pass and kept in the
first-pass profiles (`R1/.../352879/profile.json`, `R1/.../379485/profile.json`); the six new issuers' element sets
differ only at the margins (AMCAR adds four elements, Exeter and Ford carry `originalInterestOnlyTermNumber`,
`assetAddedIndicator`, `servicerAdvancedAmount`; Ford's `subvented` is repeated in 53% of records). Three full sample
records per file are in each `profile.json` under `samples`.

## 3. Field-by-field answers

| Field | What the files show | Verdict |
|---|---|---|
| obligorCreditScore | Real integers everywhere: 497 distinct values in SDART, 494 CarMax, 398 Exeter 2025-5, 357 AMCAR 2024-1, 281 Toyota, 621 Ford, 180 COPAR 2025-1. Not bucketed, not masked. **Zero changes month to month** across 78,455 + 52,812 + 72,469 loans (section 5) | Fixed origination attribute |
| obligorCreditScoreType | Free text and issuer-specific: "Bureau" (SDART, CarMax), "FICO" (COPAR), "FICO Score 8 Auto" (Toyota), "Credit Bureau Score" / "None" (AMCAR), "Consumer Credit Bureau" (Exeter; = VantageScore for 98.9% of the pool per its 424B5), "Consumer Bureau" / "Commercial Bureau" (Ford) | Must be carried with the score |
| Missing-score convention | SDART: literal 0 (16.9%). Exeter: 0 (1.35% / 0.25%). AMCAR: type "None" with a non-numeric value (0.57%). Ford: 30 near-empty records (0.1%). CarMax, COPAR, Toyota: none (prospectus floors) | Three different encodings for "no score" |
| originalLoanAmount, originalInterestRatePercentage, originalLoanTerm | Populated 100% (Ford 99.9%); rate is a fraction in every file (0.0596, 0.072, 0.2171 ...) | Consistent |
| paymentToIncomePercentage | Fraction in SDART (mean 0.106), CarMax (0.064), Exeter (0.100), AMCAR (0.097), Toyota (0.089), Ford consumer (0.091); **percent in COPAR (5.58 / 5.61)**. Ford omits it for commercial obligors (present 77.6%). CarMax, Ford, Toyota, AMCAR have outliers above 1 (max 1.37, 4.15, 0.89, 0.77) | Normalize per file; use the median, not the max, to detect percent files |
| Verification codes | Income 2/3 everywhere (AMCAR and Exeter have real spread: 3 = 59% / 25%; Exeter also 4 for 32 loans). Employment 1/2/3. Ford blank for commercial (21.7%) | Populated |
| vehicleValueAmount, vehicleNewUsedCode | Populated. New share: SDART 22%, CarMax 0.002% (52,811 used), COPAR 21-30%, Exeter 8%, AMCAR 22%, Toyota 89%, Ford 92% | |
| originationDate | MM/YYYY string in every file. Pools carry seasoned loans: SDART 01/2020-12/2025, CarMax 01/2020-12/2025, Exeter 01/2020-12/2025, AMCAR 2024-1 01/2019-12/2023, Toyota 01/2021-12/2023, Ford 01/2020-12/2024 | No day; parse before sorting |
| currentDelinquencyStatus | Integer days. Present 100% at SDART/COPAR/Exeter/Ford; **absent for zero-balance loans** at AMCAR (94.8-95.1% present), CarMax (93.7%), Toyota (98.8%). Exeter resets it to 0 on charge-off (2,710 code-4 loans all show 0); SDART keeps counting (code-4 loans show 120-150) | Issuer conventions differ |
| zeroBalanceCode / zeroBalanceEffectiveDate | Element present only when set. Codes seen: 1, 3, 4 (never 2 or 5). Retention differs by issuer (section 5) | |
| chargedoffPrincipalAmount, recoveredAmount, repossessedIndicator, repossessedProceedsAmount | Present when applicable (SDART chargedoff present 98.8% with 0.00; CarMax only 0.06%; Toyota 1.25%). recoveredAmount present 1-2% at SDART/Exeter, 100% at AMCAR (as 0.00) | |
| assetNumber | SDART 8-digit integer; CarMax base64 with `==` (16-byte hash); COPAR 25-char base64 token; Exeter 18-digit integer; AMCAR `<CIK> - <sequence>` (e.g. `0002020251 - 000010`, assetTypeNumber literally "CIK number-Sequential asset number"); Toyota 8-digit under assetTypeNumber "RANDOMID"; Ford 12-digit | Persistence proven for SDART, CarMax, COPAR (100%); untested for Exeter, AMCAR (sequential), Toyota ("RANDOMID"), Ford |
| Repeated elements in one record | `subvented` twice: SDART 1.2%, AMCAR 8.9-17%, Toyota 6.4%, **Ford 53%**; `modificationTypeCode` twice: all except CarMax/COPAR, under 0.1% | Parser must not silently keep the last |

## 4. Distributions per issuer

All from `profile.json` (score buckets, means, delinquency shares, zero-balance counts) and `zb_scoretype.json`
(score by type) in the folders listed in section 2. Delinquency shares are over all records in the file, including
zero-balance ones.

### 4a. Headline table

| Deal (month) | Score type | Score min-max | Median | Mean | No-score | Mean amount | Mean APR | Mean term | PTI as filed | 1+ | 30+ | 60+ | ZB 1 | ZB 4 | Repo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SDART 2026-1 (07) | Bureau | 369-900 | 600 | 610.6 | 16.86% (=0) | 26,769 | 17.91% | 70.9 | 0.1056 | 28.6% | 13.3% | 5.8% | 2,201 (2.8%) | 989 (1.3%) | 888 |
| SDART 2025-4 (07) | Bureau | 374-900 | 597 | 604.8 | 16.74% | 26,778 | 18.11% | 71.4 | 0.1041 | 33.5% | 17.8% | 9.5% | 2,045 | 3,097 (4.3%) | 2,101 |
| Exeter 2025-5 (06) | Consumer Credit Bureau | 374-831 | 585 | 583.2 | 1.35% (=0) | 24,054 | 21.71% | 74.6 | 0.0996 | 33.5% | 13.1% | 5.5% | 4,312 (7.8%) | 2,710 (4.9%) | 1,981 |
| Exeter 2026-2 (07) | Consumer Credit Bureau | 352-829 | 584 | 581.3 | 0.25% | 24,048 | 22.19% | 74.9 | 0.0998 | 33.2% | 13.1% | 5.7% | 996 (3.2%) | 562 (1.8%) | 571 |
| AMCAR 2024-1 (07) | Credit Bureau Score / None | 375-832 | 587 | 584.4 | 0.57% ("None") | 28,468 | 16.72% | 75.1 | 0.0975 | 38.3% | 14.5% | 3.7% | 605 (1.7%) | 840 (2.3%) | 857 |
| AMCAR 2023-1 (07) | Credit Bureau Score / None | 417-801 | 591 | 586.5 | 0.61% | 29,491 | 13.39% | 75.0 | 0.0979 | 37.4% | 13.4% | 3.2% | 454 | 549 (2.4%) | 520 |
| CarMax 2026-2 (07) | Bureau | 650-900 | 763 | 762.1 | 0% | 23,909 | 8.62% | 66.4 | 0.0639 | 4.3% | 1.2% | 0.5% | 3,318 (6.3%) | 37 (0.07%) | 42 |
| Toyota 2025-A (07) | FICO Score 8 Auto | 620-900 | 773 | 772.0 | 0% | 37,449 | 5.89% | 66.4 | 0.0895 | 5.5% | 1.1% | 0.3% | 1,025 (2.2%) | 578 (1.2%) | 258 |
| Ford 2025-A (07); score and PTI columns consumer-only, the rest all records | Consumer Bureau | 424-900 | - | 760.6 | 30 blank recs | 50,310 (all) | 4.44% | 65.4 | 0.0914 | 5.9% | 0.9% | 0.2% | 956 (3.0%) | 25 (0.08%) | 69 |
| Ford 2025-A, commercial slice | Commercial Bureau | 1-670 | - | 192.1 | - | - | - | - | absent | - | - | - | - | - | - |
| COPAR 2025-1 (07) | FICO | 700-884 | 793 | 789.0 | 0% | 24,973 | 7.34% | 67.2 | 5.58 (percent) | 0.9% | 0.16% | 0.08% | 13,328 (18.4%) | 223 (0.31%) | 27 |
| COPAR 2026-1 offering pool (07) | FICO | 740-889 | 801 | 798.6 | 0% | 27,223 | 6.50% | 67.7 | 5.61 (percent) | 0.24% | 0% | 0% | 0 | 0 | 0 |

Ford's "Commercial Bureau" block is 6,805 loans (21.6%) with scores on a different scale (6,632 numeric, mean 192,
range 1-670; the 0-119 range holds 4,684 loans) and no PTI; `R2/ford-2025-a/0002057342-26-000033/zb_scoretype.json`.
Ford's overall mean of 639 in `profile.json` is meaningless for that reason.

### 4b. obligorCreditScore in 20-point buckets (counts of loans with a positive numeric score)

SDART 2026-1 (07), 65,224 scored + 13,231 zero:
`360:1 380:6 400:40 420:127 440:317 460:879 480:1,693 500:2,904 520:4,267 540:5,873 560:7,514 580:8,642 600:8,245 620:6,541 640:4,569 660:3,126 680:2,586 700:1,855 720:1,464 740:1,109 760:781 780:673 800:632 820:533 840:456 860:287 880:99 900:5`

SDART 2025-4 (07), 59,675 + 11,996 zero:
`360:2 380:5 400:29 420:118 440:358 460:836 480:1,585 500:2,862 520:4,209 540:5,867 560:7,574 580:7,450 600:7,430 620:5,968 640:4,343 660:2,877 680:2,233 700:1,579 720:1,205 740:820 760:618 780:488 800:401 820:323 840:284 860:160 880:49 900:2`

Exeter 2025-5 (06), 54,577 + 746 zero:
`360:1 380:3 400:41 420:128 440:335 460:711 480:1,444 500:2,417 520:4,187 540:6,411 560:8,872 580:9,219 600:8,558 620:8,509 640:1,571 660:893 680:605 700:363 720:167 740:72 760:33 780:26 800:9 820:2`

Exeter 2026-2 (07), 31,418 + 79 zero:
`340:1 360:1 380:3 400:29 420:79 440:203 460:468 480:929 500:1,400 520:2,421 540:3,780 560:5,216 580:5,463 600:4,924 620:4,556 640:802 660:485 680:322 700:165 720:93 740:41 760:17 780:11 800:7 820:2`

AMCAR 2024-1 (07), 35,906 + 206 "None":
`360:1 380:3 400:6 420:19 440:81 460:353 480:1,150 500:2,319 520:3,423 540:4,264 560:4,547 580:4,642 600:4,523 620:7,563 640:1,302 660:929 680:379 700:202 720:121 740:46 760:22 780:9 820:2`

AMCAR 2023-1 (07), 22,546 + 139 "None":
`400:2 420:5 440:46 460:192 480:677 500:1,377 520:1,929 540:2,627 560:2,737 580:3,003 600:2,984 620:5,154 640:781 660:582 680:218 700:105 720:88 740:28 760:6 780:3 800:2`

CarMax 2026-2 (07 and 06 identical), 52,812:
`640:1,993 660:4,134 680:4,260 700:4,712 720:5,110 740:5,201 760:5,432 780:5,343 800:5,236 820:4,812 840:4,014 860:2,192 880:368 900:5`

Toyota 2025-A (07), 46,343:
`620:661 640:1,140 660:1,800 680:3,008 700:3,929 720:4,732 740:4,690 760:4,689 780:4,577 800:4,499 820:4,515 840:4,168 860:2,890 880:989 900:56`

Ford 2025-A (07), all types, 31,028 (consumer 24,396 + commercial 6,632):
`0:1,036 20:1,073 40:957 60:718 80:791 100:109 240:3 260:3 280:1 300:4 320:3 340:5 360:8 380:12 400:24 420:29 440:48 460:107 480:152 500:218 520:339 540:379 560:653 580:659 600:579 620:858 640:999 660:1,263 680:1,331 700:1,562 720:1,698 740:1,898 760:1,950 780:2,226 800:2,439 820:2,480 840:2,301 860:1,538 880:541 900:34`

COPAR 2025-1 (07 and 06 identical), 72,469:
`700:3,243 720:5,158 740:8,953 760:10,635 780:12,681 800:14,016 820:12,277 840:5,087 860:417 880:2`

COPAR 2026-1 offering pool, 91,627: `740:12,582 760:14,837 780:17,396 800:20,176 820:18,329 840:7,679 860:619 880:9`

Two structural facts in these histograms:

- **Cliffs at 640 in Exeter and AMCAR.** Exeter 2025-5 drops from 8,509 (620-639) to 1,571 (640-659); AMCAR 2024-1
  from 7,563 to 1,302. Exeter's prospectus says why: since 2025-4 the EART pools exclude loans whose bureau score is
  >= 640 and proprietary score >= 240, which go to ESART (section 8). AMCAR's cliff is the same shape and is
  presumably the AMCAR/GMCAR split. These are securitization-selection cutoffs, not the lender's approve/decline
  cutoff, so no outcome comparison across 640 is possible inside the public data unless ESART/GMCAR are added.
- **Floors** at 650 (CarMax), 620 (Toyota), 700 (COPAR 2025-1), 740 (COPAR 2026-1 pool) are prospectus eligibility
  criteria (section 8).

### 4c. Zero-balance codes by effective month (retention evidence; `zb_scoretype.json` in each folder)

```
SDART 2026-1 (07):   4: 03/26 17, 04/26 40, 05/26 160, 06/26 271, 07/26 501 | 1: 07/26 only 2,201 | 3: 07/26 only 207
CarMax 2026-2 (07):  1: 03/26 98, 04/26 885, 05/26 857, 06/26 829, 07/26 649 | 4: 04/26 3, 05/26 3, 06/26 10, 07/26 21
COPAR 2025-1 (07):   1: 10/25 1,248, 11/25 1,176, 12/25 1,348, 01/26 1,440, 02/26 1,336, 03/26 1,481, 04/26 1,395,
                        05/26 1,330, 06/26 1,290, 07/26 1,284 | 4: 3, 18, 25, 23, 18, 23, 25, 31, 27, 30 (same months)
Exeter 2025-5 (06):  1: 10/25 111 .. 06/26 684 (every month) | 4: 11/25 6, 12/25 32, 01/26 155, 02/26 381, 03/26 515,
                        04/26 578, 05/26 523, 06/26 520 | 3: 06/26 9
Exeter 2026-2 (07):  1: 03/26 109 .. 07/26 257 (every month) | 4: 04/26 6, 05/26 28, 06/26 161, 07/26 367 | 3: 07/26 9
AMCAR 2024-1 (07):   4: every month 06/24 .. 06/26 at 1-74 per month, then 07/26 380 | 1: 07/26 only 605
AMCAR 2023-1 (07):   4: every month 04/23 .. 06/26 at 1-39 per month, then 07/26 209 | 1: 07/26 only 454
Toyota 2025-A (07):  4: every month 02/25 .. 07/26 at 3-52 per month (07/26 29) | 1: 07/26 only 1,025 | 3: 07/26 1
Ford 2025-A (07):    1: 06/26 14, 07/26 942 | 4: 07/26 25 | 3: 07/26 1
```

### 4d. Delinquency status of zero-balance loans (same files)

SDART code-4 loans carry 120-150 days (charged off at 120 and still counting); CarMax code-4 loans 59-135;
COPAR code-4 loans mostly 0 (173 of 223); Exeter all zero-balance loans 0; AMCAR, CarMax (code 1) and Toyota (code 4)
omit the element. New charge-offs in July had prior-month delinquency 90-105 days at SDART and 90-117 at CarMax
(`persistence2_*.json`, `newly_zero_balance_in_later_by_code_and_prior_delinquency`), so both charge off at about
120 days past due; at COPAR 19 of the ~30 new July charge-offs were 0 days late in June, i.e. non-delinquency events
(total loss, bankruptcy, death) or a status reset.

Schedule AL code meanings (from the SEC auto-loan schema as I recall it; verify against the schema document before
coding): zeroBalanceCode 1 prepaid or matured, 2 third-party sale, 3 repurchased or replaced, 4 charged-off,
5 servicing transfer, 99 unavailable; vehicleNewUsedCode 1 new, 2 used; income and employment verification 1 not
stated/not verified, 2 stated not verified, 3 stated and verified (Exeter also uses 4); subvented 0 no, 1 yes rate,
2 yes cash (AMCAR and Toyota use 2), 98 other. Observed values fit these lists.

## 5. Same-deal persistence and retention rules

### 5a. The three pairs (corrected)

The runner's `persistence_*.json` files were produced by my first `compare_assets.py`, which captured each record at
the `assetNumber` end-event before lxml had parsed the rest of the record; that is why 319 / 285 records showed a
blank period date and why 1-3 sampled loans per pair looked "changed" (blank score, balance and status on one side).
`compare_assets2.py` captures at the record's end and diffs every element over the full id intersection. Its outputs
are `R2/sdart-2026-1/persistence2_303622_352879.json`, `R2/carmax-2026-2/persistence2_000013_000018.json`,
`R2/copar-2025-1/persistence2_304245_353478.json`.

| Pair (June -> July 2026) | Loans June | Loans July | July ids found in June | Left after June | New in July |
|---|---|---|---|---|---|
| SDART 2026-1 | 80,613 | 78,455 | 78,455 (100%) | 2,158 | 0 |
| CarMax 2026-2 | 52,812 | 52,812 | 52,812 (100%) | 0 | 0 |
| COPAR 2025-1 | 72,469 | 72,469 | 72,469 (100%) | 0 | 0 |

**assetNumber persists 100%** in all three, including the opaque tokens (CarMax base64 hash, COPAR 25-char token).

Which fields moved for the loans present in both months:

| Field | SDART | CarMax | COPAR | Reading |
|---|---|---|---|---|
| obligorCreditScore | **0 of 78,455** | **0 of 52,812** | **0 of 72,469** | Score is fixed at origination, never refreshed |
| obligorCreditScoreType, originationDate, originalLoanAmount, originalInterestRatePercentage, originalLoanTerm, paymentToIncomePercentage, vehicle*, verification codes, coObligorIndicator, subvented, underwritingIndicator | 0 | 0 | 0 | Static |
| loanMaturityDate | 692 (0.88%) | 115 (0.22%) | 70 (0.10%) | Extensions push maturity out by 1-2 months (SDART paymentExtendedNumber changed on 0.94%) |
| obligorGeographicLocation | 140 (0.18%) | 157 (0.30%) | 132 (0.18%) | Obligor moved; the state is current address, not origination state |
| Balances, collections, delinquency, remaining term, zero-balance group | 76-100% | 89-95% | 81-100% | Monthly servicing fields, as expected |

So the earlier "17-19 of 20 stable" was my parser, not the data. The only origination-looking fields that drift are
maturity date (modifications) and state (address updates).

### 5b. Retention rules per issuer

Derived from section 4c (single files) and the pairs. "Keep" means the loan stays in later monthly files after its
balance goes to zero.

| Issuer | Prepaid / matured (code 1) | Repurchased (code 3) | Charged-off (code 4) | Evidence |
|---|---|---|---|---|
| Santander (SDART) | Reported in the payoff month, **dropped the next month** (1,855 of 1,858 June code-1 loans gone in July) | Dropped next month (297 of 297) | **Kept** (490 of 493), with delinquency still counting (120-150 days) | `persistence2_303622_352879.json` `earlier_zero_balance_kept_or_dropped`; 4c |
| CarMax | **Kept** (2,565 June code-1 loans all present in July; 52,812 both months = 52,812 receivables at cutoff in the 424B5) | - | Kept (7 of 7) | pair; 4c; section 8 |
| Capital One (COPAR) | **Kept** since deal start (10/2025 .. 07/2026 all present; 72,469 both months) | - | Kept | pair; 4c |
| Exeter | **Kept** (10/2025 .. 06/2026 all present in the June file) | Kept (9 in 06/26) | Kept, delinquency reset to 0 | 4c, 4d |
| AmeriCredit (AMCAR) | Payoff month only (605 / 454 all dated 07/2026) -> dropped next month | - | Kept for the deal's life (06/2024 .. 07/2026; 04/2023 .. 07/2026), but the latest month is 5-8x any prior month (380 vs 49; 209 vs 18), which a single file cannot explain; needs a pair | 4c |
| Toyota | Payoff month only (1,025 all 07/2026) -> dropped; 46,343 of 69,132 cutoff receivables remain after 17 months | - | Kept (02/2025 .. 07/2026, 3-52 a month, flat) | 4c; section 8 |
| Ford | **Dropped after one month** (14 dated 06/2026, 942 dated 07/2026) | Dropped | **Dropped** (only 25, all 07/2026) | 4c |

Consequences for the panel builder:

- Charge-offs can be read off a single late file for Santander, CarMax, COPAR, Exeter, AMCAR and Toyota, with the
  charge-off month in `zeroBalanceEffectiveDate`. Ford (and anyone else who drops) needs every month.
- Prepayments need every month for Santander, AMCAR, Toyota and Ford; they accumulate for CarMax, COPAR and Exeter.
- The loan exit event = the earlier of (first month with a zeroBalanceCode) and (first month absent from the file).
  Loans retained after a zero-balance code must leave the at-risk denominator in that month.
- File sizes stay flat for keep-all issuers (CarMax 52,812 both months; COPAR 72,469) and shrink at the prepayment
  rate for the others (SDART -2.7% in one month).

## 6. Unit and score-type hazards across issuers

1. **PTI unit.** Fraction at Santander, CarMax, Exeter, AMCAR, Toyota, Ford; percent at Capital One (both deals).
   Same element name, 100x apart. Detect with the file median (0.05-0.11 vs 4.95-5.61); do not use the max, because
   CarMax (1.37), Ford (4.15), Toyota (0.89) and AMCAR (0.77) have fraction-scale outliers above 1.
2. **Score type and scale.** Seven labels across seven issuers (section 3). Exeter's "Consumer Credit Bureau" is
   VantageScore for 98.94% of the pool (section 8), so it is not on the FICO scale at all. Toyota states "FICO Score 8
   Auto". CarMax and COPAR run to 900 / 884-889, i.e. an auto-industry FICO scale (250-900), and CarMax averages
   co-obligor scores. SDART "Bureau" and AMCAR "Credit Bureau Score" are unstated; the SDART 2026-1 424B5 is now
   located (section 10). Ford mixes a consumer scale with a commercial one under two type labels in one file.
3. **Missing score.** 0 (Santander, Exeter), "None" type with non-numeric value (AMCAR), 30 near-empty records (Ford).
4. **Rates** are fractions everywhere (APR, servicing fee, period rate). Only PTI deviates.
5. **Dates.** MM/YYYY for origination, maturity, first payment, zero-balance effective; MM-DD-YYYY for period and
   interest-paid-through. Lexicographic min/max on MM/YYYY is wrong ('01/2026' < '12/2025').
6. **Element presence.** Zero-balance, recovery, repossession-proceeds and modification elements appear only when set;
   AMCAR, CarMax and Toyota also omit `currentDelinquencyStatus` (and CarMax the scheduled-payment group) for
   zero-balance loans. Parse to a superset schema with explicit nulls; "absent" is information (loan is closed).
7. **Repeated elements.** `subvented` appears twice in a record at Ford (53% of records), AMCAR (9-17%), Toyota (6%),
   Santander (1%); `modificationTypeCode` twice at most issuers (<0.1%). A dict-per-record parser silently keeps the
   last. Rule: keep the first value and count duplicates.
8. **Delinquency conventions.** Exeter resets to 0 at zero balance; Santander keeps counting past charge-off; AMCAR,
   CarMax, Toyota drop the element. Compute delinquency shares over active loans (end balance > 0 and no
   zeroBalanceCode) only.
9. **Commercial obligors.** Ford's 21.6% "Commercial Bureau" slice has no PTI and a different score scale; exclude
   by `obligorCreditScoreType`.
10. **Offering-pool variants** (lp/mp/sp) share a period date; keep one pool per deal-month and start panels at the
    first post-closing filing.
11. **Amendments.** Honda's latest filings are `ABS-EE/A`; the fetcher must prefer the amendment for a period when one
    exists, or at least record the form type.
12. **Address drift.** `obligorGeographicLocation` changes for ~0.2-0.3% of loans a month; it is current state.

## 7. Exhibit naming and the fetcher's filter

Observed EX-102 file names (`index.json` in each folder): `sdart261ex102.xml`, `copart251ex102_0714-1832.xml`,
`cart20262.xml`, `eart2025-5_exhibit102.xml`, `exh1024650072026.xml` (AMCAR: "exh102" + deal/period digits),
`taot25aex102.xml`, `autoloanmonthlydeal1183pool.xml` (Ford). No name pattern is shared, and CarMax's and Ford's
contain no "102". The companion EX-103 is 17-23 KB (`exhibit103november2021.xml`, `sdart261ex103.xml`, ...). The
rule that worked for all 14 folders: among `.xml` entries in `index.json`, drop names containing `103`, take the
largest (EX-102 is 95-352 MB; EX-103 is under 25 KB). The `-index.html` page labels documents by exhibit type and is
the belt-and-braces alternative.

## 8. What the prospectuses say

Text extracted from the three 424B5 HTML files by tag-stripping (regex over the flattened text; the quotes are
verbatim fragments).

**CarMax Auto Owner Trust 2026-2** (`R2/carmax-2026-2/0001193125-26-173162/d101943d424b5.htm`, $1,175,000,000):

- Selection: "selected from CarMax Business Services' core portfolio of motor vehicle retail installment sale
  contracts with a FICO score at origination greater than or equal to 650."
- "As of the Cutoff Date, the weighted average FICO score of the Receivables is 764.5, with the minimum FICO score
  being 650 and the maximum FICO score being 900." "approximately 90% of the Pool Balance ... between 664 and 859".
- "The percentage of obligors that did not have a FICO score at the time of application was 0.00%".
- Co-obligors: "calculated as the average of each obligor's FICO score at the time of application, if both
  co-obligors have FICO scores at that time, or as the co-obligor's FICO score, if the primary obligor does not".
- Cutoff distribution: 650-699: 10,387 (19.67%); 700-749: 12,369 (23.42%); 750-799: 13,429 (25.43%); 800-849:
  12,114 (22.94%); 850+: 4,513 (8.55%); total **52,812** receivables, $1,180,905,155.32. The EX-102 buckets sum to
  the same: 640-699 = 1,993 + 4,134 + 4,260 = 10,387. So the file's "Bureau" score is exactly the prospectus FICO
  at application, and the monthly file is the full cutoff pool.
- The model version is not named ("A FICO Score is a measurement determined by Fair Isaac Corporation using
  information collected by the major credit bureaus"); the 900 ceiling says it is an auto-industry FICO scale.

**Exeter Automobile Receivables Trust 2026-2** (`R2/exeter-2026-2/0000929638-26-001122/eart2026-2_424b5.htm`,
$648,930,000, depositor EFCAR, LLC):

- "In September 2022, the sponsor transitioned from utilizing FICO score to VantageScore as an input for the purpose
  of making credit underwriting decisions." The "Credit Bureau Score" used in the pool tables is "either a FICO score
  or a VantageScore"; "the weighted average score is based on a blended average of the FICO score for approximately
  1.05% of the pool and the VantageScore for approximately 98.94% of the pool."
- Pool criteria: "a weighted average proprietary credit score of 249 and a weighted average credit bureau score (for
  automobile loan contracts for which a credit bureau score is available) of 582; and a weighted average post-funding
  score of 222."
- Selection: "Like the Exeter Automobile Receivables Trust 2025-4 and ... 2025-5 transactions, this transaction
  employs pool selection criteria intended to exclude obligors ... whose Credit Bureau Scores and proprietary credit
  scores were above certain specified threshold levels": excluded are loans with a Credit Bureau Score >= 640 **and**
  a proprietary score >= 240 (those go to the ESART program, which only includes loans above the thresholds).
  Earlier EART deals (through 2025-3) used no score-based selection.
- Distribution by Credit Bureau Score (% of balance): No Score 0.01%; <540 14.24%; 540-564 15.98%; 565-599 33.71%;
  600-659 35.11%; >=660 0.95%; WA 582. By FICO (for loans with a FICO): No Score 5.14%; <540 31.66%; 540-564 16.40%;
  565-599 23.97%; 600-659 20.35%; >=660 2.47%; WA 562. Proprietary score: <201 7.06%; 201-214 7.61%; 215-224 7.24%;
  225-244 20.44%; >=245 57.65%; WA 249. The proprietary score is not in the EX-102.
- The EX-102 for 2026-2 shows mean 581.3, median 584, 0.25% zero: consistent with the VantageScore-based 582.

**Toyota Auto Receivables 2025-A Owner Trust** (`R2/toyota-2025-a/0000929638-25-000276/taot2025a-424b5.htm`,
$1,900,000,000):

- Eligibility: "as of the Cutoff Date, had a FICO score of at least 620".
- "Weighted Average FICO score 769, Range of FICO scores 620 - 900" (weighted by principal). Static-pool table shows
  766-769 for recent TAOT deals, min 620, max 900.
- Cutoff distribution: 620-650: 1,703 (2.46%); 651-700: 8,249 (11.93%); 701-750: 16,116 (23.31%); 751-800: 17,253
  (24.96%); 801-850: 17,018 (24.62%); >=851: 8,793 (12.72%); total **69,132** receivables, $1,977,161,496.74. The
  July 2026 file has 46,343 loans (67% of cutoff after 17 months) with mean 772, consistent with survivorship.
- Underwriting uses VantageScore plus an internal TMCC score, but the reported score is FICO (the EX-102 says
  "FICO Score 8 Auto").

Not fetched: SDART 2026-1 424B5 (found: accession 0001193125-26-061442, filed 2026-02-20, trust CIK 0002105961,
`R3/_search/santander-drive-auto-receivables-trust-2026-1.json`); COPAR 2026-1 424B5 (0 hits for the exact phrase,
`R3/_search/capital-one-prime-auto-receivables-trust-2026-1.json`, the deal had not priced when the offering-pool
ABS-EE was filed).

## 9. Data-volume estimate from real sizes

Eleven distinct deals were profiled (section 2). Bytes per loan run 3,177 (CarMax) to 4,181 (AMCAR). File sizes
per deal-month: SDART 262-294 MB (72-81k loans), COPAR 280-352 MB (72-92k), CarMax 168 MB (52.8k), Exeter 110-193 MB
(31-55k), AMCAR 95-151 MB (23-36k), Toyota 174 MB (46k), Ford 112 MB (31.5k). Mean over the eleven deals: 198.4 MB
and 53,684 loans per file.

- A 36-month, 10-deal panel: 360 files x 198 MB = **71 GB** and 360 x 53,684 = **19.3 million loan-months** if
  files did not shrink. Keep-all issuers (CarMax, COPAR, Exeter) do not shrink; Santander, AMCAR and Toyota shrink by
  the prepayment rate (SDART -2.7% in a month; Toyota at 67% of cutoff after 17 months); Ford shrinks by all exits.
  Realistic total **55-65 GB / 16-18 million loan-months**. If the ten deals lean toward Santander and Capital One
  (the biggest files) the upper bound rises to about 100 GB.
- Compressed (60 repeated element names per record) expect 10-20x: 4-7 GB on disk; typed Parquet with ~40 kept
  columns: 1-2 GB.
- Transfer: 55-100 GB at 3-5 MB/s is 3-9 hours; 360 requests plus index.json calls is trivial against the 10/s
  limit. Keep the raw XML as the audit trail. Stream-parse everything; a 350 MB file as a DOM is several GB.

## 10. Third pass: what to fetch next

| # | Purpose | Trust (CIK) | What | Why |
|---|---|---|---|---|
| 1 | SDART score model | SDART 2026-1 (0002105961) under depositor 1383094 | 424B5 accession 0001193125-26-061442 (`d*424b5.htm`) | The only measured issuer whose score scale is unstated ("Bureau", 369-900); also gives the cutoff loan count for the retention arithmetic |
| 2 | AMCAR persistence and the July charge-off spike | AMCAR 2024-1 (0002020251) | June 2026 ABS-EE (previous accession in `R2/amcar-2024-1/submissions_0002020251.json`), run `compare_assets2.py` and `zb_and_scoretype.py` | Sequential ids ("CIK number-Sequential asset number") and 380 charge-offs dated 07/2026 vs 49 in 06/2026 |
| 3 | Toyota persistence | Toyota 2025-A (0002047571) | June 2026 ABS-EE (previous accession in `R2/toyota-2025-a/submissions_0002047571.json`) | assetTypeNumber is literally "RANDOMID" |
| 4 | Exeter persistence | Exeter 2026-2 (0002114382) | June 2026 ABS-EE (`R2/exeter-2026-2/submissions_0002114382.json`) | Untested; keep-all issuer, ids are 18-digit integers |
| 5 | Ford persistence | Ford 2025-A (0002057342) | June 2026 ABS-EE (`R2/ford-2025-a/submissions_0002057342.json`) | Drop-everything issuer; every month is needed, so id stability matters most here |
| 6 | Exeter Select | search "Exeter Select Automobile Receivables Trust" forms=ABS-EE; trusts 2025-1 (0002061324), 2025-2 (0002073963), 2025-3 (0002086449), 2026-1 (0002128772) | latest ABS-EE + 424B5 | Fills the 640+ side of Exeter's selection cutoff |
| 7 | GM Financial prime | GMCAR 2025-2 (0002060535) | latest ABS-EE | Fills the 640+ side of AMCAR's cliff with the same originator |
| 8 | Honda amendments | Honda 2025-1 (0002052479) under depositor 0000890975 | index.json for 0001193125-26-374999 (ABS-EE/A) and the original it amends | Decide how the fetcher handles `/A` forms |
| 9 | Carvana | 2026-P2 (0001999855) and 2021-N4 (0001845211) | latest ABS-EE each | Two shelves from one originator, cheap prime/nonprime contrast |

## 11. Go/no-go for Track B and design inputs

**Go.** The four things Track B needs are all present:

1. Loan-level monthly files exist for 20 public issuers, eight of them profiled here, spanning scores from a
   prospectus weighted average of 562 (Exeter, FICO basis) / 582 (VantageScore basis) and file means of 584-612
   (AMCAR, Santander) to 762-773 (CarMax, Toyota) and 789-799 (Capital One).
2. `assetNumber` persists 100% month to month (three issuers, three id formats, 203,736 loans matched with zero
   misses), so loan-month panels are buildable.
3. The credit score is a fixed origination attribute (zero changes across 203,736 loan-months), which is what the
   same-score comparisons and the cutoff designs need.
4. Outcomes are observable: `currentDelinquencyStatus` in days, `zeroBalanceCode` 4 for charge-off with the month in
   `zeroBalanceEffectiveDate`, `chargedoffPrincipalAmount`, `recoveredAmount`, `repossessedIndicator`.

Limits to design around: the deep-subprime tier is not public (section 1b); the sharp 640 cutoffs at Exeter and
AMCAR are securitization selection, so the regression-discontinuity idea needs the partner shelves (ESART, GMCAR)
fetched as well; Ford drops closed loans, so its history must be assembled monthly; three issuers' id stability is
still untested (section 10).

### Design inputs for the fetcher

- Enumerate deals from depositor submissions JSONs for depositor-filed shelves (Santander, Capital One, Toyota,
  Nissan, Hyundai, World Omni, Ally, Carvana, Mercedes, VW, Honda, Harley) keyed by primary-document name, and from
  per-trust CIKs for self-filers (AmeriCredit, GM Financial, CarMax, Ford, Exeter, BMW).
- Per filing: fetch `index.json`, select the EX-102 as the largest `.xml` whose name does not contain `103`; record
  form type (`ABS-EE` vs `ABS-EE/A`) and prefer the amendment for a period; keep one pool variant per deal-month and
  start at the first post-closing filing.
- Store raw XML plus `index.json` and the `-index-headers.html`; log URL, bytes, sha256.

### Design inputs for the panel builder

Fields to keep (typed):

- Keys: `assetTypeNumber` (deal id at Santander; free text elsewhere: use accession/deal from the fetcher instead),
  `assetNumber`, `reportingPeriodBeginningDate`, `reportingPeriodEndingDate`.
- Origination (static): `originationDate`, `originalLoanAmount`, `originalLoanTerm`, `loanMaturityDate` (drifts with
  extensions), `originalInterestRatePercentage`, `originalFirstPaymentDate`, `subvented` (first value),
  `underwritingIndicator`, `vehicleNewUsedCode`, `vehicleModelYear`, `vehicleTypeCode`, `vehicleValueAmount`,
  `vehicleValueSourceCode`, `vehicleManufacturerName`, `obligorCreditScoreType`, `obligorCreditScore`,
  `obligorIncomeVerificationLevelCode`, `obligorEmploymentVerificationCode`, `coObligorIndicator`,
  `paymentToIncomePercentage`, `obligorGeographicLocation` (current state).
- Monthly: `remainingTermToMaturityNumber`, `reportingPeriodBeginningLoanBalanceAmount`,
  `reportingPeriodActualEndBalanceAmount`, `reportingPeriodInterestRatePercentage`, `scheduledPrincipalAmount`,
  `scheduledInterestAmount`, `reportingPeriodScheduledPaymentAmount`, `totalActualAmountPaid`,
  `actualPrincipalCollectedAmount`, `currentDelinquencyStatus`, `zeroBalanceCode`, `zeroBalanceEffectiveDate`,
  `chargedoffPrincipalAmount`, `recoveredAmount`, `repossessedIndicator`, `repossessedProceedsAmount`,
  `paymentExtendedNumber`, `modificationTypeCode`, `reportingPeriodModificationIndicator`, `servicingFeePercentage`.
- Drop: originator/servicer names, `assetSubjectDemandIndicator`, calculation/rate-type/payment-type codes,
  `servicingAdvanceMethodCode`, next-period amounts and rates, `interestPaidThroughDate`, other-collected and
  other-assessed amounts, `otherPrincipalAdjustmentAmount`, `vehicleModelName`, `assetAddedIndicator`,
  `servicerAdvancedAmount`, `originalInterestOnlyTermNumber`, `gracePeriodNumber`.

Per-issuer normalizations:

| Issuer | Score field | Missing score | PTI | Other |
|---|---|---|---|---|
| Santander | "Bureau", scale unstated (369-900), pending the 424B5 | 0 -> null | fraction | delinquency keeps counting after charge-off; drops codes 1 and 3 next month |
| Exeter | "Consumer Credit Bureau" = VantageScore (300-850 scale); label it so | 0 -> null | fraction | delinquency reset to 0 at zero balance; keeps everything; pools since 2025-4 exclude bureau >= 640 & proprietary >= 240 |
| AmeriCredit | "Credit Bureau Score" (375-832), scale unstated | type "None" / non-numeric -> null | fraction | delinquency absent for closed loans; drops code 1 next month; July charge-off spike unexplained |
| CarMax | "Bureau" = FICO at application, auto scale (650-900), co-obligor average | none | fraction (outliers > 1) | keeps everything; delinquency absent for closed loans; 100% used vehicles |
| Toyota | "FICO Score 8 Auto" (620-900) | none | fraction | drops code 1 next month; keeps charge-offs; delinquency absent for closed loans |
| Ford | "Consumer Bureau" (424-900); exclude "Commercial Bureau" records | 30 empty records -> drop | fraction, consumer only | drops all closed loans after one month |
| Capital One | "FICO" (700-889), auto scale | none | **percent -> divide by 100** | keeps everything; charge-offs often at 0 days |

Detection rules instead of hard-coding: PTI is percent if the file median > 1; score scale flagged by
`obligorCreditScoreType` string plus observed max (> 850 means an industry scale); duplicate elements keep the first
value; absent elements are nulls.

Retention rule: a loan's exit month = min(first month with a non-empty `zeroBalanceCode`, first month absent from the
deal's file). At-risk set in month t = loans present with end balance > 0 and no `zeroBalanceCode`. Delinquency shares
are computed over the at-risk set.

Competing risks (from `zeroBalanceCode`): 4 = charge-off (event of interest); 1 = prepaid or matured (competing
exit); 3 = repurchased/replaced (competing exit; Santander repurchased 297 loans in one month, mostly 98-118 days
delinquent, so treat repurchase of delinquent loans as a censoring that correlates with the event); 2 and 5 never
observed. Delinquency states from `currentDelinquencyStatus` (days): 30+, 60+, 90+; charge-off at Santander and
CarMax occurs at about 120 days, so 90+ is the last observable pre-charge-off state there; at COPAR and Exeter the
status is not a reliable precursor (0-day charge-offs; reset).

## 12. Summary

- Twenty public auto-loan ABS-EE filers (Honda was a query artifact; Exeter Select probably is too). Eight profiled:
  Santander SDART (subprime: median "Bureau" 600, 17% no-score, APR 18%, 13-18% 30+), Exeter (subprime: VantageScore
  median 584, APR 22%, 13% 30+), AmeriCredit (subprime: median 587, APR 17%, 14.5% 30+; 2024-1 is its newest public
  deal), CarMax (near-prime/prime: FICO floor 650, median 763, APR 8.6%, 1.2% 30+), Toyota (prime: FICO 8 Auto floor
  620, median 773, APR 5.9%, 1.1% 30+), Ford (prime: consumer-score mean 761, APR 4.4%, 0.9% 30+, plus a 22%
  commercial slice on another score scale), Capital One (prime: FICO 700-889, median 793-801, APR 6.5-7.3%, 0.16%
  30+). Twenty names have no public filings; the deep-subprime tier is 144A-only.
- Scores are real integers, fixed at origination (0 changes across 203,736 loan-months), on issuer-specific scales:
  auto-FICO (CarMax, Toyota, Capital One), VantageScore (Exeter), unstated (Santander, AmeriCredit).
- Panels are buildable: assetNumber persists 100% for Santander, CarMax and Capital One; still to test for Exeter,
  AmeriCredit (sequential ids), Toyota ("RANDOMID"), Ford.
- Retention differs: CarMax, Capital One and Exeter keep every loan for the deal's life; Santander, AmeriCredit and
  Toyota keep charge-offs but drop payoffs after their month; Ford drops everything after a month.
- Hazards: PTI is percent only at Capital One; Ford mixes consumer and commercial scores; three encodings of "no
  score"; repeated `subvented` elements (53% of Ford records); delinquency conventions differ; Honda files
  amendments; offering pools come in lp/mp/sp variants; exhibit names share no pattern (largest non-103 XML rule).
- Volume: 95-352 MB and 23-92k loans per deal-month; a 36-month, 10-deal panel is 55-100 GB raw, 16-19 million
  loan-months, 1-2 GB as Parquet.
- Track B: go, with the third-pass fetches in section 10 (SDART 424B5, four persistence pairs, ESART, GMCAR, Honda
  amendment handling, Carvana).
