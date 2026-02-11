# Day 28 — Decision layer: surge alerts + staffing/transfer triggers

Day 28 turns probabilistic forecasts into **operational decisions**:
- compute probability of exceeding capacity thresholds using Day-26 quantiles (P10/P50/P90)
- generate **surge alerts** with recommended actions
- quantify tradeoffs with a simple cost model (false alarm vs missed/late alerts)
- write dashboard-ready alert tables back to DuckDB and to `Day-28/reports/`

## Inputs

- DuckDB from Day 21–26 (same `Day-21/db/hospcap.duckdb`)
- Day 26: `day26.quantile_forecasts` (must include lower + upper quantiles, e.g. 0.1/0.9)
- Day 23: `gold.state_features` (for denominators like inpatient beds and staffed ICU beds)

## Outputs

DuckDB:
- `day28.runs`
- `day28.alerts`
- `day28.alert_metrics` (aggregated performance + cost by target/horizon)

Files in `Day-28/reports/`:
- `day28_summary.md`
- `day28_alerts.csv` (dashboard-ready)
- `day28_metrics.csv` (precision/recall + cost)
- `day28_model_selection.csv` (which Day-26 model was selected per target/horizon)

## Run

From repo root:

```powershell
pip install -e .\Day-21

python -m hospcap.day28 run `
  --db "Day-21\db\hospcap.duckdb" `
  --report-dir "Day-28\reports" `
  --contract-name "hospcap_state_daily_v1"
```

Common knobs:
- `--p-trigger 0.6` alerts only when P(exceed) >= 0.6
- `--inpatient-util-threshold 0.85` threshold as % of inpatient beds
- `--icu-util-threshold 0.80` threshold as % of staffed ICU beds
- `--c-false-alarm 1 --c-missed 5` relative cost of false alarms vs missed alerts
