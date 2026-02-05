# Day 25 — Main forecasting models (global, horizon-specific)

Day 25 trains and backtests **two real forecasting models** using the Day 23 gold feature store:

1) `gbrt_lag` — global gradient boosting regressor on lag/rolling features (with state one-hot effects)
2) `ridge_fourier` — “Prophet-style” linear model: trend + weekly/yearly Fourier seasonality + holiday + key lags
   (also with state one-hot effects)

We use **direct horizon modeling**: a separate model per `(target, horizon)` so each horizon can specialize.
Backtesting uses the same rolling-origin cutoffs as Day 24, with leakage-safe training:
for horizon `h` and cutoff `C`, training rows satisfy `ds + h <= C` (only labels known by cutoff).

## Outputs

DuckDB schema: `day25`
- `day25.runs`
- `day25.forecasts` (point forecasts)
- `day25.scores` (MAE/RMSE/MAPE/WAPE)
- `day25.vs_baseline` (improvements vs the latest Day-24 baseline run)

Reports in `Day-25/reports/`
- `day25_summary.md`
- `day25_scores.csv`
- `day25_best_models.csv`
- `day25_vs_baseline.csv`

## Run

From repo root:

```powershell
pip install -e .\Day-21

python -m hospcap.day25 run `
  --db "Day-21\db\hospcap.duckdb" `
  --report-dir "Day-25\reports" `
  --contract-name "hospcap_state_daily_v1" `
  --targets inpatient_beds_used staffed_adult_icu_bed_occupancy `
  --horizons 1 7 14 `
  --n-splits 8 `
  --step 7
```

If you have not updated Day 23 targets, re-run Day 23 first with the same targets so feature columns exist.
