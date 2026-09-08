# Scout: public loan-level auto ABS data on EDGAR (Form ABS-EE, EX-102)

Date: 2026-09-08. Repo root: `C:\Users\samwe\code\abs-risk\`. All paths below are relative to the repo root.
`R` = `data/raw/scout/edgar/autos/` (files fetched by the GitHub Actions runner; URLs and sizes in
`data/raw/scout/edgar/manifest.json`, 157 downloads, 0 errors, run 2026-09-08T05:30:02Z to 05:31:25Z).
Every number below comes from a file on disk; the file is named next to it.

Contents

0. Access diagnostics (why this machine cannot pull from SEC)
1. Issuers that file ABS-EE (19 found, 21 not), with segment guesses
2. The three downloaded EX-102 files: shape, field list, examples
3. Field-by-field answers to the scouting questions
4. Distributions (score buckets, delinquency, zero-balance codes, means)
5. Finding (a): the "persistence" comparison was two different deals; the correct same-deal pair
6. Finding (b): unit and score-type hazards across issuers
7. Finding (c): CarMax exhibit naming and the fetcher's filter
8. Data-volume estimate for a 36-month, 10-deal panel
9. Second pass: exact filings to fetch
10. Summary

---

## 0. Access diagnostics

All SEC hosts returned HTTP 403 "Your Request Originates from an Undeclared Automated Tool" (Akamai) for
every request from this machine, starting with the first request of the session. Tried with the mandated
User-Agent `abs-risk/0.1 research (+https://github.com/User5017)` unless noted; nothing faked a browser.

| Test | Host | Result | Saved response (under `data/raw/scout/autos/_search/`) |
|---|---|---|---|
| efts full-text search, mingw curl | efts.sec.gov | 403, 4818-byte block page | `sdart.json` |
| company browse (atom) | www.sec.gov/cgi-bin/browse-edgar | 403 | `browse_santander.atom` |
| submissions JSON | data.sec.gov | 403 | `sub_test.json` |
| Archives folder index | www.sec.gov/Archives | 403 | `archives_test.html` |
| same UA + `User5017@users.noreply.github.com` appended (SEC's "name + contact" format) | data.sec.gov, efts | 403 | `diag_b.json`, `diag_c.json` |
| curl forced HTTP/1.1 + Accept/Accept-Language/Accept-Encoding | data.sec.gov | 403 | `diag_d.json` |
| Python `requests` (OpenSSL stack) | data.sec.gov, efts | 403, server `AkamaiGHost` | stdout only |
| Windows System32 curl.exe 8.21 (Schannel) | data.sec.gov | 403 | `diag_wincurl.json` |
| PowerShell Invoke-WebRequest | data.sec.gov | 403 | stdout only |
| sec.gov homepage | www.sec.gov/ | 403 (edge 23.5.4.249) | `diag_home.html` |
| 10 min of silence, then one probe, three times | data.sec.gov | 403 at 05:04:08Z, 05:13:13Z, 05:23:25Z | `wait_probe_1.json`, `wait_probe_2.json`, `wait_probe_3.json`, log `sec_wait.log` |
| IPv6 path | - | no IPv6 route on this machine | - |

Cause: the public IPv4 is `99.196.128.3`, hostname `99-196-128-3.cust.exede.net`, org `AS40306 ViaSat, Inc.`
(ipinfo.io lookup, stdout). Satellite internet behind carrier-grade NAT: one address shared by many
customers, and Akamai's "identified as part of a network of automated tools" is the IP-reputation block.
Neither UA format nor TLS client changed the outcome, and quiet periods did not clear it. The coordinator
moved fetching to a GitHub Actions runner (manifest note: `probe data.sec.gov ok=True`). Rule for this
project: EDGAR pulls run from a non-CGNAT address; this machine only analyzes.

## 1. Issuers that file ABS-EE

Source: `R/issuers.json` (full-text search, exact-phrase query, `forms=ABS-EE`, filed 2025-01-01 to
2026-12-31, page 1 of results, entity aggregation buckets; raw pages in `R/_search/<slug>.json`; query URLs
in the manifest). "Hits" = number of ABS-EE filings matching the phrase in that window. Each active trust
files one ABS-EE per month, so hits / ~20 is roughly the number of trusts alive in the window.

### 1a. Found (19)

| Issuer (query phrase) | Hits | Latest filing | Who files (CIK) | Example trusts with CIKs (2023-2026) | Segment guess and basis |
|---|---|---|---|---|---|
| Santander Drive Auto Receivables Trust (SDART) | 472 | 2026-08-17 | Depositor Santander Drive Auto Receivables LLC, CIK 0001383094, trust as co-registrant | 2025-1 (0002049903); 2024-2 (0002018245); 2024-4 (0002031161); 2022-4 (0001934902); 2022-5 (0001941255); 2022-6 (0001943670); 2022-7 (0001947426). Depositor's submissions JSON shows 36 deal name patterns alive since 2025-04 (`R/santander-drive-auto-receivables-trust/submissions_0001383094.json`) | **Subprime**, measured: SDART 2026-1 median "Bureau" score 600, mean 610.6, 16.9% zero; mean APR 17.9% (section 4) |
| Drive Auto Receivables Trust (DRIVE) | 576 (phrase also matches "Santander Drive") | 2026-08-17 | Same depositor, CIK 0001383094 | DRIVE 2025-1 (0002067387); 2025-2 (0002082136); 2024-1 (0002009921); 2024-2 (0002036081); 2021-3 (0001890433) | Deeper than SDART by shelf convention; **not measured** (no EX-102 downloaded) |
| AmeriCredit Automobile Receivables Trust (AMCAR) | 142 | 2026-08-24 | Each trust self-files (accession prefix = trust CIK, e.g. 0001929381-26-000032) | 2024-1 (0002020251); 2023-2 (0001987878); 2023-1 (0001963240); 2022-2 (0001929381); 2022-1 (0001910595). **No 2025 or 2026 AMCAR trust appears** in the 100 hits or the entity buckets (`R/_search/americredit-automobile-receivables-trust.json`) | Subprime by shelf convention; not measured |
| GM Financial Consumer Automobile Receivables Trust (GMCAR) | 346 | 2026-08-20 | Trusts self-file | 2025-1 (0002047316); 2025-2 (0002060535); 2025-3 (0002071240); 2025-4 (0002084404); 2026-1 (0002099048); 2026-2, 2026-3 (in buckets) | Prime by shelf convention; not measured |
| CarMax Auto Owner Trust (CAOT) | 342 | 2026-08-17 | Trusts self-file; pre-closing pool filings by CarMax Business Services, CIK 0001259380 | 2025-1 (0002049715); 2025-2 (0002063979); 2025-3 (0002074530); 2025-4 (0002089777); 2026-1 (0002094950); 2026-2 (0002117307); 2026-3 (0002142044) | Near-prime/prime mix by plan assumption; not measured (EX-102 not fetched, see section 7) |
| Ally Auto Receivables Trust | 132 | 2026-08-20 | Depositor Ally Auto Assets LLC, CIK 0001477336 | 2024-2 (0002035124); 2024-1 (0002010413); 2023-1 (0001980826); 2022-2 (0001946472) | Prime by convention; not measured |
| Capital One Prime Auto Receivables Trust (COPAR) | 117 | 2026-09-02 | Depositor Capital One Auto Receivables LLC, CIK 0001133438 | 2026-1 (copart261, first filing 2026-09-02); 2025-1 (copart251, first 2025-10-22); 2024-1 (0002039534); 2023-2 (0001992483); 2023-1 (0001951264); 2022-2 (0001936748) (`R/capital-one-prime-auto-receivables-trust/submissions_0001133438.json`) | **Prime**, measured: COPAR 2026-1 FICO 740-889, median 801, mean APR 6.5% (section 4) |
| Ford Credit Auto Owner Trust | 263 | 2026-08-18 | Trusts self-file | 2025-A (0002057342); 2025-B (0002082903); 2025-C (0002092555); 2026-A (0002113024); 2026-B (0002137917) | Prime (captive); not measured |
| Toyota Auto Receivables ... Owner Trust | 358 | 2026-08-27 | Depositor Toyota Auto Finance Receivables LLC, CIK 0001131131 (older) and trusts (newer) | 2025-A (0002047571); 2025-B (0002058316); 2025-C (0002063142); 2025-D (0002063141); 2026-A (0002099539); 2026-B (0002099540); 2026-C (0002099541) | Prime (captive); not measured |
| Nissan Auto Receivables ... Owner Trust | 166 | 2026-08-19 | Depositor Nissan Auto Receivables Co II LLC, CIK 0001129068 | 2025-A (0002063629); 2023-B (0001995403); 2023-A (0001971902); 2022-B (0001941405) | Prime (captive); not measured |
| Hyundai Auto Receivables Trust | 303 | 2026-09-04 | Depositor Hyundai ABS Funding LLC, CIK 0001260125 | 2025-A (0002056104); 2023-B (0001980330); 2023-A (0001968583); 2022-C (0001949662) | Prime (captive); not measured |
| World Omni Auto Receivables Trust | 325 | 2026-08-28 | Depositor World Omni Auto Receivables LLC, CIK 0001083199 | 2025-A (0002046523); 2023-A (0001959508); 2022-D (0001950786); 2022-C (0001935951) | Prime; not measured |
| Exeter Automobile Receivables Trust | 483 | 2026-08-31 | Trusts self-file via filer agent (accession prefix 0000929638) | 2025-1 (0002049379); 2025-2 (0002056803); 2025-3 (0002067124); 2025-4 (0002078220); 2025-5 (0002092528); 2026-1 (0002101848); 2026-2 (0002114382); 2026-3 (0002132838) (`R/_search/exeter-automobile-receivables-trust.json`) | Subprime / deep subprime by shelf convention; not measured |
| Fifth Third Auto Trust | 20 | 2026-08-27 | Trust 2023-1 (0001986424); depositor Fifth Third Holdings Funding LLC (0001405332) | Only 2023-1 alive | Prime (bank); not measured; one deal only |
| Harley-Davidson Motorcycle Trust | 126 | 2026-08-27 | Depositor Harley-Davidson Customer Funding Corp., CIK 0001114926 | 2024-B (0002034427); 2024-A (0002017611); 2023-B (0001989332); 2023-A (0001963533) | Motorcycles, not cars; exclude or flag |
| Mercedes-Benz Auto Receivables Trust | 119 | 2026-08-21 | Depositor Mercedes-Benz Retail Receivables LLC, CIK 0001463814 | 2025-1 (0002044492); 2023-2 (0001993977); 2023-1 (0001957424); 2022-1 (0001951118) | Prime (captive); not measured |
| BMW Vehicle Owner Trust | 80 | 2026-09-03 | Trusts self-file; depositor BMW FS Securities LLC (0001136586) | 2025-A (0002049336); 2024-A (0002021594); 2023-A (0001979860); 2022-A (0001921318) | Prime (captive); not measured |
| Volkswagen Auto Loan Enhanced Trust | 97 | 2026-08-20 | Depositor Volkswagen Auto Lease/Loan Underwritten Funding LLC, CIK 0001182534 | 2025-1 (0002054483); 2024-1 (0002043149); 2023-2 (0001998124); 2023-1 (0001976946) | Prime (captive); not measured |
| Carvana Auto Receivables Trust | 357 | 2026-08-14 | Depositor Carvana Receivables Depositor LLC, CIK 0001770373, and trusts | P-series (prime by shelf naming): 2025-P1 (0002037956); 2025-P2 (0002037955); 2025-P3 (0002037953); 2025-P4 (0002037952); 2026-P1 (0001976111); 2026-P2 (0001999855); 2026-P3 (0001999511). N-series (nonprime) 2021-N1..N4 (0001842012, 0001843643, 0001843653, 0001845211) still filing | Two shelves, P and N; not measured |

Monthly cadence is confirmed where a submissions JSON was fetched: every SDART/DRIVE deal alive for the
whole window has 17 ABS-EE filings between 2025-04-15 and 2026-08-17 (17 months); COPAR 2022-1
(`copart221`) has 51 filings from 2022-04-19 to 2026-04-15; CarMax 2026-2 has one per month from
2026-05-15 (`R/carmax-auto-owner-trust/submissions_0002117307.json`). For the other issuers the ~20 hits
per trust over the 20-month window says the same thing.

### 1b. Not found (21; zero ABS-EE hits 2025-2026 for the exact phrase)

Santander Consumer Auto Receivables Trust, Honda Auto Receivables Owner Trust, USAA Auto Owner Trust,
Westlake Automobile Receivables Trust, DT Auto Owner Trust, Flagship Credit Auto Trust, Bank of America
Auto Trust, Chase Auto Owner Trust, GLS Auto Receivables Issuer Trust, CPS Auto Receivables Trust, American
Credit Acceptance Receivables Trust, Credit Acceptance Auto Loan Trust, Prestige Auto Receivables Trust,
United Auto Credit Securitization Trust, First Investors Auto Owner Trust, Foursight Capital Automobile
Receivables Trust, Lendbuzz Securitization Trust, Tricolor Auto Securitization Trust, Arivo Acceptance Auto
Loan Receivables Trust, Santander Retail Auto Lease Trust, Exeter Select Auto Receivables Trust
(`R/issuers.json`, `total: 0` each; raw `R/_search/<slug>.json`, ~1.07 KB each).

Two caveats before calling these "144A only":

- Honda and USAA are probably query artifacts. Their trusts are named with the year in the middle
  ("Toyota Auto Receivables 2025-A Owner Trust" is the pattern that worked for Toyota because the query was
  the shorter "Toyota Auto Receivables"). The Honda query was the full phrase "Honda Auto Receivables Owner
  Trust", which cannot match "Honda Auto Receivables 2025-1 Owner Trust". Retry Honda as "Honda Auto
  Receivables" and USAA as "USAA Auto Owner".
- The rest (Westlake, DriveTime/DT, Flagship, GLS, CPS, ACA, Credit Acceptance, Prestige, UACST, First
  Investors, Foursight, Lendbuzz, Tricolor, Arivo, Exeter Select) are the deep-subprime and specialty
  names, and zero public ABS-EE hits is consistent with 144A-only issuance. That is the expected gap:
  **the public loan-level universe stops at Santander/Exeter-grade subprime; the deep-subprime tier is not
  observable on EDGAR.**

## 2. The three downloaded EX-102 files

| Deal | File | Bytes | Records | Period | Filed | Accession | URL |
|---|---|---|---|---|---|---|---|
| SDART 2026-1 | `R/santander-drive-auto-receivables-trust/0001193125-26-352879/sdart261ex102.xml` | 286,617,174 | 78,455 | 07-01-2026 to 07-31-2026 | 2026-08-17 | 0001193125-26-352879 | https://www.sec.gov/Archives/edgar/data/1383094/000119312526352879/sdart261ex102.xml |
| SDART 2025-4 | `R/santander-drive-auto-receivables-trust/0001193125-26-352878/sdart254ex102.xml` | 261,821,449 | 71,671 | 07-01-2026 to 07-31-2026 | 2026-08-17 | 0001193125-26-352878 | https://www.sec.gov/Archives/edgar/data/1383094/000119312526352878/sdart254ex102.xml |
| COPAR 2026-1 (large-pool variant) | `R/capital-one-prime-auto-receivables-trust/0001193125-26-379485/copart261ex102_0831-1940lp.xml` | 352,286,257 | 91,627 | 07-01-2026 to 07-31-2026 | 2026-09-02 | 0001193125-26-379485 | https://www.sec.gov/Archives/edgar/data/1133438/000119312526379485/copart261ex102_0831-1940lp.xml |

Profiles: `profile.json` in each accession folder (runner output of `analyze_ex102.py`); `profile_local.json`
is my re-run on this machine. For SDART 2026-1 and COPAR 2026-1 the two agree on every key (record count,
size, all distributions; diff printed to stdout with zero differing keys). SDART 2025-4 has only
`profile_local.json`. Each file's companion documents (from `index.json` in the same folder):
`sdart261absee_0810-1513.htm` (primary, 21,185 B) and `sdart261ex103.xml` (22,908 B);
`sdart254absee_81026-1450.htm` and `sdart254ex103.xml` (23,094 B);
`copart261absee_0831-1948lp.htm` (21,097 B) and `copart261ex103_0901-1054lp.xml` (21,771 B).

XML shape (all three): root `{http://www.sec.gov/edgar/document/absee/autoloan/assetdata}assetData`, one
`assets` child per loan, flat leaf elements inside. Bytes per record: 3,653 (both SDART) and 3,845 (COPAR).
`assetNumber` is unique within each file (78,455 / 71,671 / 91,627 distinct).

Important context on the COPAR file: it is the **first** ABS-EE for COPAR 2026-1 and was filed in three
variants the same day (`copart261absee_0831-1948lp.htm` accession 0001193125-26-379485,
`..._2000mp.htm` 0001193125-26-379470, `..._2012sp.htm` 0001193125-26-379453; suffixes lp/mp/sp = large,
medium, small pool). It is the offering-pool snapshot, not a seasoned servicing month: no zero-balance codes,
no charge-offs, 0.24% of loans 1+ days late. SDART 2026-1 shows the same pattern at launch
(`sdart261absee_0210-1933lp.htm` 0001193125-26-045549 and `..._1820sp.htm` 0001193125-26-045529, both
period 2026-01-31), and CarMax 2026-2 too (`abs-ee2026x2largepool040326.htm` 0001259380-26-000017 and
`...smallpool...` 0001259380-26-000015, period 2026-03-31, filed by CarMax Business Services). After closing,
one filing per month.

### 2a. Field list with example values and non-empty shares

SDART 2026-1 (63 element names as they occur, including two repeated-element cases; from
`.../0001193125-26-352879/profile.json`). Share = records where the element is present and non-empty.

| Element | Example | Share | Distinct values (when few) |
|---|---|---|---|
| assetTypeNumber | SDART0202600001 | 1.0 | one value (deal id) |
| assetNumber | 21904424 | 1.0 | 8-digit numeric |
| reportingPeriodBeginningDate | 07-01-2026 | 1.0 | |
| reportingPeriodEndingDate | 07-31-2026 | 1.0 | |
| originatorName | SC | 1.0 | |
| originationDate | 01/2020 | 1.0 | MM/YYYY only |
| originalLoanAmount | 51000.00000000 | 1.0 | |
| originalLoanTerm | 75 | 1.0 | 38 distinct |
| loanMaturityDate | 06/2026 | 1.0 | |
| originalInterestRatePercentage | 0.05960000 | 1.0 | fraction |
| interestCalculationTypeCode | 1 | 1.0 | 1 |
| originalInterestRateTypeCode | 1 | 1.0 | 1 |
| originalFirstPaymentDate | 03/2020 | 1.0 | |
| underwritingIndicator | true | 1.0 | false, true |
| gracePeriodNumber | 2 | 1.0 | 0-4 |
| paymentTypeCode | 2 | 1.0 | 2 |
| subvented | 0 | 1.0 | 0, 1, 98 |
| vehicleManufacturerName | DODGE | 1.0 | |
| vehicleModelName | Ram 2500 | 1.0 | |
| vehicleNewUsedCode | 1 | 1.0 | 1, 2 |
| vehicleModelYear | 2019 | 1.0 | 13 distinct |
| vehicleTypeCode | 2 | 1.0 | 1, 2, 3 |
| vehicleValueAmount | 63044.00000000 | 1.0 | |
| vehicleValueSourceCode | 1 | 1.0 | 1, 3, 98 |
| obligorCreditScoreType | Bureau | 1.0 | Bureau |
| obligorCreditScore | 632 | 1.0 | 497 distinct incl. 0 |
| obligorIncomeVerificationLevelCode | 2 | 1.0 | 2, 3 |
| obligorEmploymentVerificationCode | 2 | 1.0 | 1, 2, 3 |
| coObligorIndicator | true | 1.0 | false, true |
| paymentToIncomePercentage | 0.05515821 | 1.0 | fraction |
| obligorGeographicLocation | CO | 1.0 | 51 distinct (states) |
| remainingTermToMaturityNumber | 0 | 1.0 | |
| reportingPeriodModificationIndicator | false | 1.0 | false, true |
| servicingAdvanceMethodCode | 1 | 1.0 | 1 |
| reportingPeriodBeginningLoanBalanceAmount | 722.43000000 | 1.0 | |
| nextReportingPeriodPaymentAmountDue | 574.60000000 | 1.0 | |
| reportingPeriodInterestRatePercentage | 0.05960000 | 1.0 | |
| nextInterestRatePercentage | 0.05960000 | 1.0 | |
| servicingFeePercentage | 0.03000000 | 1.0 | 0.03 |
| otherAssessedUncollectedServicerFeeAmount | 0.00000000 | 1.0 | |
| scheduledInterestAmount | 0.00000000 | 1.0 | |
| scheduledPrincipalAmount | 0.00000000 | 1.0 | |
| otherPrincipalAdjustmentAmount | 0.00000000 | 1.0 | |
| reportingPeriodActualEndBalanceAmount | 0.00000000 | 1.0 | |
| reportingPeriodScheduledPaymentAmount | 0.00000000 | 1.0 | |
| totalActualAmountPaid | 739.44000000 | 0.9878 | |
| actualInterestCollectedAmount | 2.01000000 | 0.9878 | |
| actualPrincipalCollectedAmount | 722.43000000 | 0.9878 | |
| actualOtherCollectedAmount | 15.00000000 | 0.9878 | |
| interestPaidThroughDate | 06-09-2026 | 0.9779 | |
| zeroBalanceEffectiveDate | 07/2026 | 0.0433 | 03/2026 .. 07/2026 |
| zeroBalanceCode | 1 | 0.0433 | 1, 3, 4 |
| currentDelinquencyStatus | 0 | 1.0 | integer days |
| primaryLoanServicerName | SBNA | 1.0 | SBNA |
| assetSubjectDemandIndicator | false | 1.0 | false |
| chargedoffPrincipalAmount | 0.00000000 | 0.9878 | |
| paymentExtendedNumber | 0 | 1.0 | 0-3 |
| repossessedIndicator | false | 1.0 | false, true |
| subvented (second occurrence in same record) | 98 | 0.0124 | 1, 98 |
| modificationTypeCode | 4 | 0.0064 | 1, 3, 4, 98 |
| repossessedProceedsAmount | -350.00 | 0.0121 | |
| recoveredAmount | 4896.14000000 | 0.012 | |
| modificationTypeCode (second occurrence) | 3 | ~0 | 3 |

SDART 2025-4 has the same 63 names in the same order (`.../0001193125-26-352878/profile_local.json`); shares
that differ: totalActualAmountPaid / actual*Collected / chargedoffPrincipalAmount 0.9694, interestPaidThroughDate
0.997, zeroBalanceEffectiveDate and zeroBalanceCode 0.0718, modificationTypeCode 0.0238, recoveredAmount
0.0227, repossessedProceedsAmount 0.0313, second `subvented` 0.0002.

COPAR 2026-1 (59 element names, no repeats; from `.../0001193125-26-379485/profile.json`). Only the
elements that differ from SDART's list, plus the ones that matter:

| Element | Example | Share | Notes |
|---|---|---|---|
| assetTypeNumber / originatorName / primaryLoanServicerName | CONA | 1.0 | |
| assetNumber | Y2NhZDY3ZmM0MGUwN2E4NTNjY | 1.0 | 25-char base64-looking token, not numeric |
| originationDate | 01/2026 | 1.0 | 12 distinct months 02/2025 .. 01/2026 |
| originalInterestOnlyTermNumber | 0 | 1.0 | not in SDART |
| assetAddedIndicator | false | 1.0 | not in SDART |
| servicerAdvancedAmount | 0.00000000 | 1.0 | not in SDART |
| obligorCreditScoreType | FICO | 1.0 | FICO |
| obligorCreditScore | 816 | 1.0 | 144 distinct, none zero |
| paymentToIncomePercentage | 8.09000000 | 1.0 | **percent**, not fraction |
| servicingFeePercentage | 0.01000000 | 1.0 | |
| chargedoffPrincipalAmount | 0.00000000 | 1.0 | all 0.00 |
| currentDelinquencyStatus | 0 | 1.0 | 24 distinct values |
| zeroBalanceCode, zeroBalanceEffectiveDate, modificationTypeCode, recoveredAmount, repossessedProceedsAmount | absent | 0 | elements omitted entirely when not applicable |
| repossessedIndicator | false | 1.0 | only false |
| subvented | 0 | 1.0 | only 0 |
| underwritingIndicator | true | 1.0 | only true |

Everything else in COPAR matches SDART's names (originalLoanAmount, originalLoanTerm, loanMaturityDate,
vehicle*, obligorIncomeVerificationLevelCode (2, 3), obligorEmploymentVerificationCode (2, 3),
coObligorIndicator, obligorGeographicLocation (52 distinct), remainingTermToMaturityNumber, balances,
scheduled and actual payment amounts, interestPaidThroughDate, paymentExtendedNumber (only 0)).

### 2b. Three full sample records per file

First three `assets` records of each file, verbatim from `profile.json` -> `samples`.

SDART 2026-1, record 1 (loan paid off this month, zeroBalanceCode 1):

```
assetTypeNumber SDART0202600001 | assetNumber 21904424 | reportingPeriodBeginningDate 07-01-2026 | reportingPeriodEndingDate 07-31-2026
originatorName SC | originationDate 01/2020 | originalLoanAmount 51000.00000000 | originalLoanTerm 75 | loanMaturityDate 06/2026
originalInterestRatePercentage 0.05960000 | interestCalculationTypeCode 1 | originalInterestRateTypeCode 1 | originalFirstPaymentDate 03/2020
underwritingIndicator true | gracePeriodNumber 2 | paymentTypeCode 2 | subvented 0
vehicleManufacturerName DODGE | vehicleModelName Ram 2500 | vehicleNewUsedCode 1 | vehicleModelYear 2019 | vehicleTypeCode 2
vehicleValueAmount 63044.00000000 | vehicleValueSourceCode 1
obligorCreditScoreType Bureau | obligorCreditScore 632 | obligorIncomeVerificationLevelCode 2 | obligorEmploymentVerificationCode 2
coObligorIndicator true | paymentToIncomePercentage 0.05515821 | obligorGeographicLocation CO | remainingTermToMaturityNumber 0
reportingPeriodModificationIndicator false | servicingAdvanceMethodCode 1
reportingPeriodBeginningLoanBalanceAmount 722.43000000 | nextReportingPeriodPaymentAmountDue 574.60000000
reportingPeriodInterestRatePercentage 0.05960000 | nextInterestRatePercentage 0.05960000 | servicingFeePercentage 0.03000000
otherAssessedUncollectedServicerFeeAmount 0.00000000 | scheduledInterestAmount 0.00000000 | scheduledPrincipalAmount 0.00000000
otherPrincipalAdjustmentAmount 0.00000000 | reportingPeriodActualEndBalanceAmount 0.00000000 | reportingPeriodScheduledPaymentAmount 0.00000000
totalActualAmountPaid 739.44000000 | actualInterestCollectedAmount 2.01000000 | actualPrincipalCollectedAmount 722.43000000 | actualOtherCollectedAmount 15.00000000
interestPaidThroughDate 06-09-2026 | zeroBalanceEffectiveDate 07/2026 | zeroBalanceCode 1 | currentDelinquencyStatus 0
primaryLoanServicerName SBNA | assetSubjectDemandIndicator false | chargedoffPrincipalAmount 0.00000000 | paymentExtendedNumber 0 | repossessedIndicator false
```

SDART 2026-1, record 2 (paid off; note reportingPeriodInterestRatePercentage 0.1766 differs from original 0.1803):

```
assetNumber 21919291 | originationDate 02/2020 | originalLoanAmount 34444.61000000 | originalLoanTerm 72 | loanMaturityDate 06/2026
originalInterestRatePercentage 0.18030000 | originalFirstPaymentDate 03/2020 | gracePeriodNumber 1 | subvented 0
vehicleManufacturerName MERCEDES-BENZ COMM | vehicleModelName Sprinter | vehicleNewUsedCode 1 | vehicleModelYear 2019 | vehicleTypeCode 1
vehicleValueAmount 41303.00000000 | vehicleValueSourceCode 1 | obligorCreditScoreType Bureau | obligorCreditScore 719
obligorIncomeVerificationLevelCode 3 | obligorEmploymentVerificationCode 3 | coObligorIndicator false | paymentToIncomePercentage 0.15948110
obligorGeographicLocation FL | remainingTermToMaturityNumber 0 | reportingPeriodBeginningLoanBalanceAmount 206.51000000
nextReportingPeriodPaymentAmountDue 425.63000000 | reportingPeriodInterestRatePercentage 0.17660000 | nextInterestRatePercentage 0.17660000
reportingPeriodActualEndBalanceAmount 0.00000000 | totalActualAmountPaid 398.29000000 | actualInterestCollectedAmount 1.90000000
actualPrincipalCollectedAmount 206.51000000 | actualOtherCollectedAmount 189.88000000 | interestPaidThroughDate 06-18-2026
zeroBalanceEffectiveDate 07/2026 | zeroBalanceCode 1 | currentDelinquencyStatus 0 | chargedoffPrincipalAmount 0.00000000 | repossessedIndicator false
(other fields identical in form to record 1: assetTypeNumber SDART0202600001, period 07-01-2026..07-31-2026, SC, codes 1/1/2, underwritingIndicator true, servicingFee 0.03, scheduled amounts 0, SBNA, false, paymentExtendedNumber 0)
```

SDART 2026-1, record 3 (80 days delinquent, still open, rate cut from 0.2155 to 0.06):

```
assetNumber 22376302 | originationDate 02/2020 | originalLoanAmount 20315.44000000 | originalLoanTerm 72 | loanMaturityDate 12/2026
originalInterestRatePercentage 0.21550000 | originalFirstPaymentDate 04/2020 | gracePeriodNumber 2 | subvented 0
vehicleManufacturerName LINCOLN | vehicleModelName MKZ | vehicleNewUsedCode 2 | vehicleModelYear 2017 | vehicleTypeCode 1
vehicleValueAmount 17125.00000000 | vehicleValueSourceCode 98 | obligorCreditScoreType Bureau | obligorCreditScore 733
obligorIncomeVerificationLevelCode 3 | obligorEmploymentVerificationCode 2 | coObligorIndicator true | paymentToIncomePercentage 0.12479887
obligorGeographicLocation LA | remainingTermToMaturityNumber 6 | reportingPeriodBeginningLoanBalanceAmount 3114.93000000
nextReportingPeriodPaymentAmountDue 1745.35000000 | reportingPeriodInterestRatePercentage 0.06000000 | nextInterestRatePercentage 0.06000000
otherAssessedUncollectedServicerFeeAmount 76.41000000 | reportingPeriodActualEndBalanceAmount 2869.21000000
totalActualAmountPaid 300.00000000 | actualInterestCollectedAmount 54.28000000 | actualPrincipalCollectedAmount 245.72000000 | actualOtherCollectedAmount 0.00000000
interestPaidThroughDate 07-17-2026 | currentDelinquencyStatus 80 | chargedoffPrincipalAmount 0.00000000 | paymentExtendedNumber 0 | repossessedIndicator false
(no zeroBalanceCode / zeroBalanceEffectiveDate elements present)
```

SDART 2025-4, record 1 (`profile_local.json`): assetTypeNumber SDART0202500004, assetNumber 20018922,
originationDate 03/2019, originalLoanAmount 40474.22, term 72, rate 0.069 (now 0.06), subvented 1, DODGE Ram
1500 Classic 2019 new, vehicleValueAmount 42254.00, Bureau score 621, PTI 0.06272, IL, remaining term 0,
beginning balance 357.48, end balance 2.29, currentDelinquencyStatus 45, otherAssessedUncollectedServicerFeeAmount
803.42, no zero-balance elements.

COPAR 2026-1, record 1:

```
assetTypeNumber CONA | assetNumber Y2NhZDY3ZmM0MGUwN2E4NTNjY | reportingPeriodBeginningDate 07-01-2026 | reportingPeriodEndingDate 07-31-2026
originatorName CONA | originationDate 01/2026 | originalLoanAmount 17980.50000000 | originalLoanTerm 25 | loanMaturityDate 01/2028
originalInterestRatePercentage 0.07200000 | interestCalculationTypeCode 1 | originalInterestRateTypeCode 1 | originalInterestOnlyTermNumber 0
originalFirstPaymentDate 02/2026 | underwritingIndicator true | gracePeriodNumber 2 | paymentTypeCode 2 | subvented 0
vehicleManufacturerName KIA | vehicleModelName TELLURIDE | vehicleNewUsedCode 1 | vehicleModelYear 2025 | vehicleTypeCode 3
vehicleValueAmount 40750.00000000 | vehicleValueSourceCode 1
obligorCreditScoreType FICO | obligorCreditScore 816 | obligorIncomeVerificationLevelCode 2 | obligorEmploymentVerificationCode 2
coObligorIndicator false | paymentToIncomePercentage 8.09000000 | obligorGeographicLocation NC | assetAddedIndicator false
remainingTermToMaturityNumber 18 | reportingPeriodModificationIndicator false | servicingAdvanceMethodCode 1
reportingPeriodBeginningLoanBalanceAmount 14468.22000000 | nextReportingPeriodPaymentAmountDue 809.08000000
reportingPeriodInterestRatePercentage 0.07200000 | nextInterestRatePercentage 0.07200000 | servicingFeePercentage 0.01000000
otherAssessedUncollectedServicerFeeAmount 0.00000000 | scheduledInterestAmount 85.62000000 | scheduledPrincipalAmount 723.46000000
otherPrincipalAdjustmentAmount 0.00000000 | reportingPeriodActualEndBalanceAmount 13744.76000000 | reportingPeriodScheduledPaymentAmount 809.08000000
totalActualAmountPaid 809.08000000 | actualInterestCollectedAmount 85.62000000 | actualPrincipalCollectedAmount 723.46000000 | actualOtherCollectedAmount 0.00000000
servicerAdvancedAmount 0.00000000 | interestPaidThroughDate 07-23-2026 | currentDelinquencyStatus 0
primaryLoanServicerName CONA | assetSubjectDemandIndicator false | chargedoffPrincipalAmount 0.00000000 | paymentExtendedNumber 0 | repossessedIndicator false
```

COPAR 2026-1, record 2: assetNumber MGMwOTg1ZjRjZTk3ZTFhZjNkO, originationDate 07/2025, originalLoanAmount
29398.35, term 61, maturity 08/2030, rate 0.0475, TOYOTA GRAND HIGHLA 2024 used, vehicleValueAmount 54100.00
(source 98), FICO 783, PTI 1.84, MO, remaining term 49, beginning balance 25013.38, end 24558.52, scheduled
552.51 paid 552.51, delinquency 0.

COPAR 2026-1, record 3: assetNumber ZmQ0YmNiNzczNTJjNzFiODM2N, originationDate 01/2026, originalLoanAmount
19795.00, term 60, maturity 01/2031, rate 0.055, VOLKSWAG JETTA 2021 used, vehicleValueAmount 14375.00
(source 98), FICO 752, PTI 5.25, IL, remaining term 54, beginning balance 18249.03, end 17926.03, scheduled
334.30, paid 400.00 (principal 323.00), delinquency 0.

## 3. Field-by-field answers

| Field | SDART 2026-1 / 2025-4 | COPAR 2026-1 | Verdict |
|---|---|---|---|
| obligorCreditScore | Real integer values, 497 distinct, range 369-900 / 374-900; **exactly 0 in 16.86% / 16.74%** (13,231 / 11,996 loans); no empty strings | Real integers, 144 distinct, 740-889, 0% zero | Actual scores, not bucketed or masked, except the Santander zero block (no-score borrowers, presumably) |
| obligorCreditScoreType | "Bureau" (100%) | "FICO" (100%) | Free text; scale not stated. Both max out above 850 (900 and 889), so at least one is an industry (auto) FICO scale, 250-900 |
| originalLoanAmount | Populated, mean 26,769 / 26,778, median 25,113 / 25,072, range 4,752-127,269 | Mean 27,223, median 25,483, range 4,000-100,177 | Dollars with 8 decimals |
| originalInterestRatePercentage | Fraction: mean 0.1791 / 0.1811, median 0.18, max 0.2999, min 0.0 | Fraction: mean 0.0650, median 0.065, range 0.01-0.1299 | Same unit in both (fraction) |
| originalLoanTerm | Months, mean 70.9 / 71.4, range 12-75 / 24-75 | Mean 67.7, median 73, range 19-85 | |
| remainingTermToMaturityNumber | Populated (example 0 for paid-off loans, 6 for record 3) | Populated (18, 49, 54) | |
| paymentToIncomePercentage | **Fraction**: mean 0.1056 / 0.1041, max 0.294 | **Percent**: mean 5.61, median 4.98, max 21.35 | Unit differs by 100x (section 6) |
| obligorIncomeVerificationLevelCode | 2: 94.3%, 3: 5.7% (2026-1) | 2: 99.7%, 3: 0.3% | Populated; only codes 2 and 3 seen |
| obligorEmploymentVerificationCode | 1: 6.8%, 2: 92.7%, 3: 0.6% | 2: ~100%, 3: 6 loans | Populated |
| vehicleValueAmount | Mean 25,659 / 25,471, median 23,427 / 23,350 | Mean 32,283, median 29,275 | Populated; vehicleValueSourceCode 1/3/98 vs 1/98 |
| vehicleNewUsedCode | 1 (new) 22.1%, 2 (used) 77.9% (2026-1); 20.7% / 79.3% (2025-4) | 30.0% / 70.0% | |
| originationDate | MM/YYYY string, 01/2020-12/2025 (2026-1), 01/2020-12/2024 (2025-4): Santander pools carry loans up to six years old | MM/YYYY, 02/2025-01/2026 | **No day of month**; string min/max is lexicographic, parse before sorting |
| currentDelinquencyStatus | Integer days; 0 for 71.4% / 66.5%; values up to 112 seen in sample; spikes at 15 and 30 | Integer days; 0 for 99.76%; max seen 20 | Populated |
| zeroBalanceCode | Element present only when set: 4.33% / 7.18% of records; values 1, 3, 4 | Never present | See section 4 for counts and meanings |
| zeroBalanceEffectiveDate | MM/YYYY; present exactly when zeroBalanceCode is (3,397 / 5,144 records) | Never present | |
| chargedoffPrincipalAmount | Present 98.78% / 96.94%, mostly 0.00 | Present 100%, all 0.00 | Dollar amount; absent on a minority of Santander records |
| recoveredAmount | Present 1.2% / 2.27% (940 / 1,625 records) | Never | Only on loans with recoveries |
| repossessedIndicator | true 1.13% / 2.93% (888 / 2,101) | All false | repossessedProceedsAmount present 1.21% / 3.13%, can be negative (-350.00) |
| reportingPeriodBeginningLoanBalanceAmount | Sum 1,684.0M / 1,491.0M | Sum 2,109.1M | |
| reportingPeriodActualEndBalanceAmount | Sum 1,618.3M / 1,430.1M; zero for 3,407 / 5,156 loans | Sum 2,067.0M; none zero | |
| subvented | 0: 97.3%, 1: 2.7%, 98: 12 loans (2026-1); 0: 99.4%, 1: 0.6% (2025-4). **Repeated inside 976 / 16 records** (second value 1 or 98) | All 0 | Naive dict parsing overwrites the first value silently |
| obligorGeographicLocation | Two-letter state, 51 / 52 distinct; top TX 14.1%, FL 12.9%, CA 9.2% (2026-1) | 52 distinct; top TX 10.4%, FL 9.8%, OH 7.5% | |
| assetNumber | 8-digit numeric, increasing with origination date in the first 25 | 25-char base64-like token | Stability across months untested (section 5) |

## 4. Distributions

### 4a. obligorCreditScore, 20-point buckets (count of loans with a positive score)

SDART 2026-1 (`.../352879/profile.json`), 65,224 scored + 13,231 zero = 78,455:

```
360-379:     1   380-399:     6   400-419:    40   420-439:   127   440-459:   317
460-479:   879   480-499: 1,693   500-519: 2,904   520-539: 4,267   540-559: 5,873
560-579: 7,514   580-599: 8,642   600-619: 8,245   620-639: 6,541   640-659: 4,569
660-679: 3,126   680-699: 2,586   700-719: 1,855   720-739: 1,464   740-759: 1,109
760-779:   781   780-799:   673   800-819:   632   820-839:   533   840-859:   456
860-879:   287   880-899:    99   900-919:     5
mean 610.6, median 600, min 369, max 900
```

SDART 2025-4 (`.../352878/profile_local.json`), 59,675 scored + 11,996 zero = 71,671:

```
360-379:     2   380-399:     5   400-419:    29   420-439:   118   440-459:   358
460-479:   836   480-499: 1,585   500-519: 2,862   520-539: 4,209   540-559: 5,867
560-579: 7,574   580-599: 7,450   600-619: 7,430   620-639: 5,968   640-659: 4,343
660-679: 2,877   680-699: 2,233   700-719: 1,579   720-739: 1,205   740-759:   820
760-779:   618   780-799:   488   800-819:   401   820-839:   323   840-859:   284
860-879:   160   880-899:    49   900-919:     2
mean 604.8, median 597, min 374, max 900
```

COPAR 2026-1 (`.../379485/profile.json`), 91,627 scored, none zero:

```
740-759: 12,582   760-779: 14,837   780-799: 17,396   800-819: 20,176
820-839: 18,329   840-859:  7,679   860-879:    619   880-899:      9
mean 798.6, median 801, min 740, max 889
```

Read: COPAR's pool is a hard 740 floor (the prospectus cut, not the lender's book). Santander's spans the
whole subprime range with the mode at 580-619 and a 17% no-score block. The two do not overlap below 740 at
all, so same-score cross-lender comparisons need a mid-spectrum issuer (CarMax, Carvana P, Exeter, AmeriCredit).

### 4b. Means and shares requested

| Metric | SDART 2026-1 | SDART 2025-4 | COPAR 2026-1 |
|---|---|---|---|
| Share score missing or zero | 16.86% | 16.74% | 0.00% |
| Mean originalLoanAmount | 26,769 | 26,778 | 27,223 |
| Mean original APR | 17.91% | 18.11% | 6.50% |
| Mean PTI (as filed) | 0.1056 (fraction) | 0.1041 (fraction) | 5.61 (percent) |
| Share 1+ days delinquent | 28.61% | 33.54% | 0.24% |
| Share 30+ days delinquent | **13.33%** | **17.83%** | 0.00% |
| Share 60+ days delinquent | 5.79% | 9.49% | 0.00% |
| Share with zeroBalanceCode = 4 (charge-off) in this file | 1.26% (989) | 4.32% (3,097) | 0 |
| Share zeroBalanceCode = 1 | 2.81% (2,201) | 2.85% (2,045) | 0 |
| Share zeroBalanceCode = 3 | 0.26% (207) | 2 loans | 0 |
| repossessedIndicator true | 1.13% | 2.93% | 0 |

### 4c. currentDelinquencyStatus value counts (top values)

SDART 2026-1: 0: 56,010; 2: 881; 3: 716; 5: 675; 4: 661; 10: 635; 1: 615; 7: 590; 8: 579; 6: 533; 15: 516;
30: 448; 9: 436; 11: 399; 14: 378. SDART 2025-4: 0: 47,636; 2: 923; 5: 615; 3: 604; 1: 578; 4: 551; 15: 512;
10: 485; 7: 465; 8: 443; 30: 441; 6: 436; 9: 426; 16: 417; 12: 401. COPAR: 0: 91,410; 2: 49; 3: 35; 1: 32;
4: 28; 5: 16; 6: 16; 8: 7; 7: 5; 10: 5; 9: 4; 11: 4; 16: 3; 18: 2; 20: 2. The field is days past due as an
integer (Schedule AL: "number of days the obligor is delinquent"); Santander's spikes at exactly 15 and 30
suggest some loans are reported on a bucket convention.

### 4d. zeroBalanceCode by month of zeroBalanceEffectiveDate, SDART 2025-4 (stdout of `zb_dates.py` over
`sdart254ex102.xml`)

```
11/2025: code 4:    1
12/2025: code 4:   12
01/2026: code 4:   54
02/2026: code 4:  242
03/2026: code 4:  291
04/2026: code 4:  470
05/2026: code 4:  603
06/2026: code 4:  712
07/2026: code 1: 2,045   code 3: 2   code 4: 712
```

This is the most useful structural fact in the scout: **charged-off loans (code 4) stay in every later
monthly file with their original charge-off month, while prepaid/matured loans (code 1) appear only in the
month they pay off and are then dropped.** So a single late-month file gives the cumulative charge-off
history of a deal (2,385 prior-month charge-offs plus 712 new ones here), but prepayments need every month.
SDART 2026-1 shows the same: zeroBalanceEffectiveDate spans 03/2026..07/2026 (deal closed February 2026).

Schedule AL code meanings (SEC ABS-EE auto loan schema, Item 3 of Schedule AL; from the schema as I recall
it, verify against the EX-103 / schema document before coding): zeroBalanceCode 1 = prepaid or matured,
2 = third-party sale, 3 = repurchased or replaced, 4 = charged-off, 5 = servicing transfer, 99 = unavailable;
vehicleNewUsedCode 1 = new, 2 = used; obligorIncomeVerificationLevelCode and obligorEmploymentVerificationCode
1 = not stated / not verified, 2 = stated but not verified, 3 = stated and verified; subvented 0 = no,
1 = yes; 98 = "other" and 99 = "unavailable" are the generic escape codes throughout the schema. The
observed values (1, 3, 4 only for zero balance; 1/2/3 for verification; 0/1/98 for subvented) are consistent
with these lists.

## 5. Finding (a): the persistence comparison was two different deals

`R/santander-drive-auto-receivables-trust/asset_persistence.json` compared `sdart254ex102.xml` (71,671 loans)
against `sdart261ex102.xml` (78,455 loans): 0 of 78,455 later ids appear in the earlier file, 0 of 20
sampled, 71,671 only-in-earlier, 78,455 only-in-later, and both files carry period 07-31-2026. They are
SDART 2025-4 (assetTypeNumber `SDART0202500004`) and SDART 2026-1 (`SDART0202600001`), two trusts filed
the same day by the same depositor. The 0/20 says nothing about persistence. Whether `assetNumber` is stable
month to month is **still untested**.

Correct same-deal pairs, from the depositor's submissions JSON
(`R/santander-drive-auto-receivables-trust/submissions_0001383094.json`; the primary document name carries the
deal, e.g. `sdart261absee_*.htm`), all CIK 1383094:

SDART 2026-1 (`sdart261`):

| Filed | Period | Accession | Primary doc | Expected EX-102 | Folder URL |
|---|---|---|---|---|---|
| 2026-08-17 | 2026-07-31 | 0001193125-26-352879 | sdart261absee_0810-1513.htm | sdart261ex102.xml (have it) | https://www.sec.gov/Archives/edgar/data/1383094/000119312526352879/ |
| 2026-07-15 | 2026-06-30 | **0001193125-26-303622** | sdart261absee_0708-2103.htm | sdart261ex102.xml | https://www.sec.gov/Archives/edgar/data/1383094/000119312526303622/ |
| 2026-06-15 | 2026-05-31 | 0001193125-26-269968 | sdart261absee_0507-1821.htm | sdart261ex102.xml | .../000119312526269968/ |
| 2026-05-15 | 2026-04-30 | 0001193125-26-224703 | sdart261absee_0507-1821.htm | | .../000119312526224703/ |
| 2026-04-15 | 2026-03-31 | 0001193125-26-155453 | sdart261absee_0408-1836.htm | | .../000119312526155453/ |
| 2026-03-16 | 2026-02-28 | 0001193125-26-106847 | sdart261absee_0311-1617.htm | first post-closing month | .../000119312526106847/ |
| 2026-02-11 | 2026-01-31 | 0001193125-26-045549 / -045529 | sdart261absee_0210-1933lp.htm / _1820sp.htm | offering pool, large / small variants | |

SDART 2025-4 (`sdart254`): 0001193125-26-352878 (have, period 07-31) and **0001193125-26-303621** (filed
2026-07-15, period 2026-06-30, `sdart254absee_0708-2100.htm`), then 0001193125-26-269962 (05-31),
0001193125-26-224684 (04-30), 0001193125-26-155418 (03-31), 0001193125-26-106843 (02-28),
0001193125-26-052069 (01-31), 0001193125-26-013318 (2025-12-31), 0001193125-25-318042 (2025-11-30),
0001193125-25-267552 (2025-10-31, first filing, 2025-11-06).

Fetch next: `0001193125-26-303622` (expected `sdart261ex102.xml`, ~280 MB) and run `compare_assets.py`
against the existing 352879 file. If the coordinator wants a second pair in the same pull,
`0001193125-26-303621` against 352878. Use the folder `index.json` to confirm the exhibit name; the runner
already fetched index.json for both August filings and the naming was `sdart<deal>ex102.xml`.

Prior for the persistence test: SDART ids are 8-digit integers increasing with origination date (first 25:
21904424 .. 22633739, origination 01/2020 .. 02/2020), which looks like a servicing-system loan number and
should be stable. COPAR ids are 25-character opaque tokens (`Y2NhZDY3ZmM0MGUwN2E4NTNjY`), which could be a
per-filing hash; COPAR needs its own test (copart251, which has 12 monthly filings, is the candidate:
latest `copart251absee_0814-1822.htm` on 2026-08-17; accessions are in the depositor's submissions JSON).

## 6. Finding (b): unit and score-type hazards across issuers

Measured on the two issuers' files (section 3 and 4):

1. **PTI unit.** Santander files paymentToIncomePercentage as a fraction (mean 0.1056, sample 0.05515821
   on a 574.60 payment); Capital One files it as a percent (mean 5.61, sample 8.09 on an 809.08 payment).
   Same element name, 100x apart. A pooled regression on the raw field would be garbage. Rule: normalise
   per file with a max-value check (fraction files max below 1; percent files max above 1).
2. **Score type and scale.** `obligorCreditScoreType` is free text: "Bureau" vs "FICO". Santander's
   range is 369-900 and Capital One's 740-889; both exceed 850, so these are not classic FICO 8/9 (300-850).
   The 250-900 range is the industry (auto) FICO family, but the files do not say which model or bureau,
   and "Bureau" may be a different model from "FICO". Treat score as issuer-specific until the prospectus
   (424B5) states the model; the 424B5s are listed in the submissions JSONs (e.g. COPAR 2025-10-30
   `0001193125-25-258371`, `d47685d424b5.htm`).
3. **Missing-score convention.** Santander uses literal 0 for 16.9% of loans (no empty elements); Capital
   One has no zeros (740 floor). A zero is "no score", not a score; bucket it separately.
4. **Interest rate** is a fraction in both (0.0596, 0.072); servicingFeePercentage too (0.03, 0.01).
   Do not assume the PTI convention carries over.
5. **Dates.** originationDate, loanMaturityDate, originalFirstPaymentDate, zeroBalanceEffectiveDate are
   MM/YYYY (no day); reportingPeriod*Date and interestPaidThroughDate are MM-DD-YYYY. Lexicographic min/max
   of MM/YYYY strings is wrong ('01/2026' < '12/2025' in the profile output).
6. **Element presence, not empty values.** Santander omits zeroBalanceCode, zeroBalanceEffectiveDate,
   modificationTypeCode, recoveredAmount, repossessedProceedsAmount unless applicable, and omits the
   collected-amount elements on 1.2-3.1% of records; Capital One omits the zero-balance group entirely.
   Field sets differ (63 names vs 59); COPAR adds originalInterestOnlyTermNumber, assetAddedIndicator,
   servicerAdvancedAmount. Parse to a superset schema with explicit nulls.
7. **Repeated elements inside one record.** `subvented` occurs twice in 976 SDART 2026-1 records (second
   value 1 or 98) and `modificationTypeCode` twice in a handful. A dict-per-record parser keeps the last
   one silently. Decide a rule (first value, or keep both) and test for it.
8. **assetNumber format** differs (numeric vs opaque token), so any cross-issuer loan key must be
   (issuer, deal, assetNumber).
9. **Offering-pool filings.** The first ABS-EE for a deal comes in two or three pool-size variants (lp/mp/sp
   for COPAR; lp/sp for SDART; largepool/smallpool for CarMax) with the same period date. A panel builder
   must keep exactly one pool per deal per month, and should start the panel at the first post-closing filing.

## 7. Finding (c): CarMax exhibit naming

`R/carmax-auto-owner-trust/0002117307-26-000018/index.json` (CarMax Auto Owner Trust 2026-2, CIK
0002117307, filed 2026-08-17, period 2026-07-31):

| File | Size |
|---|---|
| a2026-2absxee081726.htm (primary) | 11,634 |
| **cart20262.xml** (the EX-102) | **167,788,225** |
| exhibit103november2021.xml (the EX-103, reused since 2021) | 17,054 |
| 0002117307-26-000018-index.html, -index-headers.html, .txt | |

The EX-102 is `cart20262.xml` ("cart" + 2026 + 2); it contains neither "102" nor "ex". Fix for the fetcher:
in `index.json`, take the `.xml` entries, drop any whose name contains `103`, and pick the largest; or parse
`<accession>-index.html`, which labels each document with its exhibit type (EX-102 / EX-103). The
size-based rule is robust across all four folders seen so far (EX-102 is 167-352 MB; EX-103 is 17-23 KB).
Expected URL: https://www.sec.gov/Archives/edgar/data/2117307/000211730726000018/cart20262.xml. Prior
months for 2026-2 (`R/carmax-auto-owner-trust/submissions_0002117307.json`): 0002117307-26-000013
(2026-07-15, period 06-30), -000008 (06-15), -000003 (05-15); expected name `cart20262.xml` each time,
unverified. CarMax's 167 MB for a pool of unknown size implies either fewer loans or a leaner record; check
records after fetching.

## 8. Data-volume estimate: 36 months x 10 deals

From the three files: 261.8, 286.6 and 352.3 MB; 71,671, 78,455 and 91,627 records; 3,653-3,845 bytes per
record (section 2). Mean file 300.2 MB and 80,584 records.

- Upper bound, no attrition: 360 files x 300.2 MB = **108 GB** of XML and 360 x 80,584 = **29.0 million
  loan-months**.
- With attrition: only prepaid loans leave the file (charge-offs stay, section 4d). SDART 2025-4 prepaid
  2.85% of its loans in July 2026; at ~2.5-3% a month a deal's file shrinks to roughly 40-50% of its
  starting size by month 36, so the average file over the panel is about 65-70% of the first one:
  **roughly 70-75 GB and 19-21 million loan-months**. CarMax's 168 MB file suggests some issuers are
  smaller per deal.
- Compressed on disk: ABS-EE XML is highly repetitive (60 element names per record); expect 10-20x with
  gzip/zstd, i.e. 5-10 GB. Parsed into Parquet with ~60 typed columns it should be 1-3 GB.
- Transfer: at 3-5 MB/s from EDGAR that is 4-10 hours of download for the raw XML, spread over 360
  requests (request count is a non-issue; bytes are the constraint). Keep the raw XML, it is the audit trail.
- Record-count side note: the monthly pipeline needs streaming parsing throughout; a 350 MB file loaded
  as a DOM is several GB of memory.

## 9. Second pass: exact filings to fetch

All URLs are `https://www.sec.gov/Archives/edgar/data/<CIK without leading zeros>/<accession without dashes>/`.
Fetch `index.json` first in every case and select the EX-102 by the size rule in section 7.

| # | Purpose | Trust (CIK) | Accession | Filed / period | Expected EX-102 | Source of the accession |
|---|---|---|---|---|---|---|
| 1 | Same-deal pair, month t-1 | SDART 2026-1 under depositor CIK 1383094 | 0001193125-26-303622 | 2026-07-15 / 2026-06-30 | sdart261ex102.xml (~280 MB) | `submissions_0001383094.json` |
| 1b | Optional second pair | SDART 2025-4, CIK 1383094 | 0001193125-26-303621 | 2026-07-15 / 2026-06-30 | sdart254ex102.xml | same |
| 2 | CarMax, latest | CarMax Auto Owner Trust 2026-2 (0002117307) | 0002117307-26-000018 | 2026-08-17 / 2026-07-31 | cart20262.xml (167,788,225 B) | `index.json` on disk |
| 2b | CarMax, month t-1 | same | 0002117307-26-000013 | 2026-07-15 / 2026-06-30 | cart20262.xml (verify) | `submissions_0002117307.json` |
| 3 | Exeter, seasoned 2025 deal | Exeter Automobile Receivables Trust 2025-5 (0002092528) | 0000929638-26-002770 | 2026-07-30 / 2026-06-30 | unknown name; use index.json | `R/_search/exeter-automobile-receivables-trust.json` |
| 3b | Exeter, newest | Exeter 2026-2 (0002114382) | 0000929638-26-002410 | 2026-06-30 / 2026-05-31 | unknown | same; later months exist, get `submissions/CIK0002114382.json` for the newest |
| 4 | AmeriCredit, newest shelf deal | AMCAR 2024-1 (0002020251) | not on page 1 of the search; fetch `https://data.sec.gov/submissions/CIK0002020251.json` and take the latest ABS-EE (pattern 0002020251-26-0000NN) | | unknown | `R/issuers.json` bucket |
| 4b | AmeriCredit, known-good fallback | AMCAR 2023-1 (0001963240) | 0001963240-26-000029 | 2026-08-24 / 2026-07-31 | unknown | `R/issuers.json` latest_hits |
| 5 | Captive prime, seasoned | Toyota Auto Receivables 2025-A Owner Trust (0002047571) | 0001193125-26-370139 | 2026-08-27 / 2026-07-31 | unknown | `R/issuers.json` latest_hits |
| 5b | Captive alternate | Ford Credit Auto Owner Trust 2025-A (0002057342) | 0002057342-26-000025 | 2026-06-16 / 2026-05-31 | unknown | `R/_search/ford-credit-auto-owner-trust.json`; later months exist |
| 6 | COPAR persistence test (opaque ids) | COPAR 2025-1 under depositor CIK 1133438 | two consecutive `copart251absee_*` accessions from `submissions_0001133438.json` (latest primary doc `copart251absee_0814-1822.htm`, 2026-08-17) | | copart251ex102_*.xml | `submissions_0001133438.json` |
| 7 | Query fixes | Honda ("Honda Auto Receivables"), USAA ("USAA Auto Owner") | rerun the efts search with the shorter phrases | | | section 1b |

Also worth one small fetch each: the 424B5 prospectus for SDART 2026-1 and COPAR 2026-1 (listed in the
submissions JSONs) to read the stated score model and the weighted-average score, which would turn the
segment guesses in section 1 into measured facts for the two issuers already profiled.

## 10. Summary

- **Issuers.** 19 of 40 candidate names file public ABS-EE monthly (2025-2026 window). Measured segments:
  Santander Drive is subprime (median Bureau score 600, 17% no-score, mean APR 17.9%, 13-18% of loans 30+
  days late); Capital One Prime is prime (FICO 740-889, median 801, APR 6.5%). By shelf convention, not
  measured: DRIVE and Exeter deeper subprime; AmeriCredit subprime (but no 2025-2026 AMCAR trust found);
  CarMax, Carvana-P, Ally, and the captives (GM Financial, Ford, Toyota, Nissan, Hyundai, World Omni,
  Mercedes, BMW, VW) prime; Harley-Davidson is motorcycles; Fifth Third has one deal. 21 names have zero
  hits: Honda and USAA are probably query artifacts (year sits inside the trust name); the deep-subprime
  and specialty lenders (Westlake, DriveTime, Flagship, GLS, CPS, ACA, Credit Acceptance, Prestige, UACST,
  First Investors, Foursight, Lendbuzz, Tricolor, Arivo) are absent, consistent with 144A-only. The public
  loan-level universe ends at Santander/Exeter-grade subprime.
- **Scores are real.** Integer values with hundreds of distinct levels, not bucketed or masked. Santander
  uses 0 for no-score (16.9%); Capital One's pool has a hard 740 floor. Type labels differ ("Bureau" vs
  "FICO") and both scales run above 850, so the model is issuer-specific until the prospectus says otherwise.
- **Panels: not yet proven, but the structure is favourable.** The runner's 0/20 test compared two
  different deals (SDART 2025-4 vs 2026-1). The same-deal pair to fetch is 0001193125-26-303622 against
  the existing 0001193125-26-352879. Independently of that test, the files already show that charged-off
  loans persist in every later monthly file with their charge-off month (SDART 2025-4 carries charge-offs
  from 11/2025 through 07/2026), while prepaid loans appear only in their payoff month. So charge-off
  outcomes are recoverable from a single late file per deal; prepayment and delinquency transitions need
  the monthly chain.
- **Volume.** About 300 MB and 80k loans per deal-month for Santander and Capital One (3.7 KB per record);
  CarMax is 168 MB. A 36-month, 10-deal panel is at most 108 GB / 29 million loan-months of raw XML,
  realistically 70-75 GB / ~20 million after prepayment attrition; a few GB compressed, 1-3 GB as Parquet.
- **Surprises.** (1) paymentToIncomePercentage is a fraction at Santander and a percent at Capital One,
  100x apart under one element name. (2) A deal's first ABS-EE comes in two or three pool-size variants
  (lp/mp/sp, largepool/smallpool) with identical period dates; the COPAR file profiled here is such an
  offering pool, which is why it shows zero charge-offs and 0.24% delinquency. (3) Santander repeats the
  `subvented` element inside ~1.2% of records and omits zero-balance and recovery elements unless set;
  Capital One omits the whole zero-balance group. (4) CarMax names its EX-102 `cart20262.xml`, so any
  "contains 102" filter misses it; pick the largest non-103 XML in index.json. (5) Depositor-filed shelves
  (Santander, Capital One, Toyota, Nissan, Hyundai, World Omni, Ally, Carvana, Mercedes, VW, Harley) put
  every deal in one submissions JSON keyed by primary-document name, while AmeriCredit, GM Financial,
  CarMax, Ford, Exeter and BMW trusts self-file, so those need one CIK per deal. (6) Santander pools carry
  loans originated up to six years before the deal (2026-1 has 01/2020 originations).
- **Access.** This machine's ViaSat/Exede CGNAT address is on Akamai's block list for all of sec.gov;
  EDGAR pulls stay on the GitHub Actions runner.
