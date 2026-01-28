# Day 22 — Time-series EDA + Automated Quality Gates

Day 22 adds **pipeline-enforced quality checks** on the Day 21 silver tables so that downstream
feature engineering, backtesting, and alerting are not built on broken reporting series.

What Day 22 produces (written to DuckDB, schema `quality`):
- `quality.state_gaps`: date spine + missingness flags per state/day
- `quality.state_metrics`: per-state coverage and missing-run diagnostics
- `quality.state_drift`: simple rolling-window drift checks (mean/variance shift)
- `quality.outliers`: robust change-point/outlier flags on day-to-day deltas for key targets
- `quality.failures`: a compact table of rule violations that will fail the run in strict mode

It also writes a Markdown report and a CSV summary under `Day-22/reports/`.

## Run

From the top-level repo folder:

```powershell
# ensure Day-21 package is installed (editable) so `hospcap.day22` is available
pip install -e .\Day-21

python -m hospcap.day22 run `
  --db "Day-21\db\hospcap.duckdb" `
  --report-dir "Day-22\reports" `
  --contract-name "hospcap_state_daily_v1" `
  --strict
```


## Interpreting “FAILED strict mode”

Day 22 is designed to **fail fast** when the underlying reporting time series is not reliable enough to support forecasting and surge alerting. A strict failure is not a bug; it is a pipeline gate that prevents downstream modeling from silently training on broken series.

### What failed means (hard gates)

The forecasting contract enforces:
- **min_history_days = 180**: each state must have at least 180 days between its first and last observed date.
- **max_missing_run = 3**: within that date range, the longest consecutive run of missing days cannot exceed 3.

If any state violates either rule, it appears in `quality.failures` and the strict run exits non-zero.

Artifacts:
- `Day-22/reports/day22_quality_report.md` (human-readable summary)
- `Day-22/reports/day22_state_metrics.csv` (per-state diagnostics)
- `Day-22/reports/day22_failures.csv` (export of `quality.failures`)

### Why this matters for ops forecasting

Surge alerting is a decision system: false confidence is worse than no forecast. Long gaps or short histories can produce unstable lags/rollups, biased backtests, and miscalibrated prediction intervals—exactly the failure modes that create late alerts or noisy false alarms.

### What happens in Day 23

We will build “gold” time-series tables using an explicit policy:
1) **Primary cohort:** states that pass the gates (used for baseline + model backtests).
2) **Excluded or flagged cohort:** failing states are either (a) excluded from modeling, or (b) included only with explicit imputation + missingness indicators, depending on the use case.

This keeps the pipeline reproducible and makes quality decisions explicit and auditable.
