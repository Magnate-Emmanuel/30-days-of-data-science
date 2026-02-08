# Day 27 — Backtest report (point metrics + interval coverage + drift checks)

Day 27 is the **evaluation and monitoring layer**:
- point accuracy (MAE/RMSE/MAPE/WAPE) using Day-26 **P50** as the point forecast
- interval reliability (coverage + width) using Day-26 **P10/P90**
- drift checks on the **underlying time series** (recent vs baseline window)

This produces a report and dashboard-ready CSV outputs.

## Inputs

- DuckDB database from Day 21–26 (same `Day-21/db/hospcap.duckdb`).
- Day 26 outputs:
  - `day26.runs`
  - `day26.quantile_forecasts`
  - `day26.calibration` (optional; Day 27 recomputes key metrics anyway)
- Gold features from Day 23:
  - `gold.state_features`

## Outputs

In `Day-27/reports/`:
- `day27_summary.md`
- `day27_point_metrics.csv`
- `day27_interval_metrics.csv`
- `day27_quantile_pinball.csv`
- `day27_series_drift.csv`
- `day27_backtest_drift.csv` (early vs late cutoffs)

## Run

From repo root:

```powershell
pip install -e .\Day-21

python -m hospcap.day27 run `
  --db "Day-21\db\hospcap.duckdb" `
  --report-dir "Day-27\reports" `
  --contract-name "hospcap_state_daily_v1"
```

To pin a specific Day-26 run id:

```powershell
python -m hospcap.day27 run `
  --db "Day-21\db\hospcap.duckdb" `
  --report-dir "Day-27\reports" `
  --day26-run-id <PASTE_RUN_ID_HERE>
```

You can adjust drift windows:

```powershell
python -m hospcap.day27 run --db "Day-21\db\hospcap.duckdb" --report-dir "Day-27\reports" --recent-days 60 --baseline-days 180
```

