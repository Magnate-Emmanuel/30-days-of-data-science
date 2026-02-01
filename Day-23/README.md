# Day 23 — Gold tables + Feature engineering (state/day)

Day 23 converts the Day 21 **silver** state time series into **model-ready gold** tables, using Day 22
quality outputs to form an explicit eligible cohort.

## Outputs (DuckDB)

Schemas/tables created:
- `gold.state_cohort` — eligible vs excluded states (with reasons if excluded)
- `gold.state_daily_panel` — complete daily spine for eligible states with missingness flags and QC context
- `gold.us_federal_holidays` — holiday calendar (joined into features)
- `gold.state_features` — lag/rolling/calendar features (computed on a forward-fill-by-3-days signal)
- `gold.model_frame` — filtered rows suitable for backtesting (no leakage, enough history)

## Run

From repo root:

```powershell
pip install -e .\Day-21

python -m hospcap.day23 run `
  --db "Day-21\db\hospcap.duckdb" `
  --report-dir "Day-23\reports" `
  --contract-name "hospcap_state_daily_v1"
```

This writes:
- `Day-23/reports/day23_cohort_summary.md`
- `Day-23/reports/day23_feature_dictionary.md`
- `Day-23/reports/day23_cohort.csv`
