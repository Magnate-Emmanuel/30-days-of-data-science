# Day 26 — Probabilistic forecasts (quantiles / prediction intervals)

Day 26 converts Day 25 “champions” into **uncertainty-aware** forecasts (P10 / P50 / P90)
so alerts and staffing/transfer triggers are not based on single point estimates.

## Champion policy (based on Day 25)

- For most target/horizon pairs we use `gbrt_quantile`:
  - a global gradient-boosted model that directly predicts requested quantiles.

- For **inpatient_beds_used at horizon=7**, Day 25 showed the best point model was still a baseline.
  For that pair we use `naive_conformal`:
  - point forecast = naive last value
  - interval width calibrated from historical naive residuals (leakage-safe up to each cutoff)

## Backtesting

Rolling-origin cutoffs:
- n_splits=8, step_days=7
- leakage-safe training: for horizon `h` and cutoff `C`, train/calibrate only on rows with `ds + h <= C`.

## Outputs

DuckDB schema: `day26`
- `day26.runs`
- `day26.quantile_forecasts` (long: q in {0.1,0.5,0.9})
- `day26.calibration` (coverage + width + pinball losses)

Reports in `Day-26/reports/`
- `day26_summary.md`
- `day26_calibration.csv`
- `day26_forecast_samples.csv`

## Run

```powershell
pip install -e .\Day-21
pip install scikit-learn

python -m hospcap.day26 run `
  --db "Day-21\db\hospcap.duckdb" `
  --report-dir "Day-26\reports" `
  --contract-name "hospcap_state_daily_v1" `
  --targets inpatient_beds_used staffed_adult_icu_bed_occupancy `
  --horizons 1 7 14 `
  --quantiles 0.1 0.5 0.9 `
  --n-splits 8 `
  --step 7
```
