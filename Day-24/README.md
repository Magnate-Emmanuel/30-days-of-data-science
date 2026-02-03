# Day 24 — Baselines + Proper Backtesting

Day 24 implements **strong forecasting baselines** on the Day 23 gold model frame and runs a
rolling-origin backtest with multiple horizons.

Baselines included:
- `naive_last`: last observed level at cutoff
- `seasonal_naive_7`: weekly seasonal naive (value from cutoff+h-7)
- `rolling_mean_7`: mean of the last 7 days at cutoff
- `ewma_opt`: simple exponential smoothing (EWMA) with alpha optimized on training segment

Outputs written to DuckDB schema `backtest`:
- `backtest.forecasts` — point forecasts for each cutoff/horizon
- `backtest.scores` — MAE/RMSE/MAPE/WAPE aggregated by model/target/horizon
- `backtest.runs` — run metadata

Reports written to `Day-24/reports/`:
- `day24_backtest_summary.md`
- `day24_scores.csv`
- `day24_best_models.csv`

## Run

From repo root:

```powershell
pip install -e .\Day-21

python -m hospcap.day24 run `
  --db "Day-21\db\hospcap.duckdb" `
  --report-dir "Day-24\reports" `
  --contract-name "hospcap_state_daily_v1" `
  --targets inpatient_beds_used icu_beds_used `
  --horizons 1 7 14 `
  --n-splits 8 `
  --step 7
```
