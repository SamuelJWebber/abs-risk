# Card and auto loss-decomposition replay

This snapshot uses the 567 monthly trust reports and ten loan-level parquet tables from [source revision b5a0bc9](https://github.com/SamuelJWebber/abs-risk/tree/b5a0bc9ca287510f11ad21f5a15efc1719f29f30/data). The corrected B6 by-score outputs and their digests are included alongside this replay in Git. Use this revision of the replay when later refreshes advance the input tables.

From the repository root, run:

```sh
sha256sum -c checks/replays/2026-11-28/SHA256SUMS
uv sync --frozen
uv run pytest tests/test_cards_results.py tests/test_autos_b6_results.py
```

The card tests regenerate the analysis independently of the saved outputs. The auto test rebuilds all four B6 tables from the ten original analysis inputs (759,808 loan rows) and compares every field by lender and score bucket. Both run offline once dependencies are installed. The SHA-256 manifest also covers the card calibration inputs and the published card decomposition.

| Lead finding | What the saved inputs support |
|---|---|
| Amex versus Synchrony | Amex's geometric-mean monthly net charge-off rate is 0.2901 times Synchrony's, and its 30+ delinquency entry ratio is 0.2871. The calculation uses `data/cards_monthly.csv`, including the SEC accession and source filename per row. |
| Auto roll after 30+ delinquency | For the score buckets with at least 100 observed 30+ loans used on the conclusions page, median roll ratios versus Santander are 0.94 for CarMax, 0.61 for Honda and 0.70 for Toyota. The 50-loan risk-set floor applies within each cohort. The figures represent these securitized loan pools. |

**Coverage.** All 567 parsed card rows have a source accession. The repository's card fixture manifests cover 22 of those 567 filing accessions. The others retain identifiers and the parsed measurements. The ten auto data files each have a sibling diagnostics JSON listing the deal, reporting periods and source files. The complete raw SEC filing archive is excluded from Git. These offline checks reproduce the estimates from the committed parsed data; auditing every original filing still requires an EDGAR download.
