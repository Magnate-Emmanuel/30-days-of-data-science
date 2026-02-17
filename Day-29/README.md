# Day 29 — Package run: one command to produce forecasts + alerts

Day 29 is the “ops product” packaging step: **one command** that runs the end-to-end
pipeline (gold build → main models → probabilistic forecasts → monitoring → surge alerts)
and writes everything back to DuckDB.

## What it runs

Default pipeline:

1. Day 23: build gold tables + features (`gold.state_features`)
2. Day 25: main models backtest (`day25.*`)
3. Day 26: probabilistic forecasts / quantiles (`day26.*`)
4. Day 27: monitoring report (drift + coverage) (`day27.*`)
5. Day 28: decision layer alerts + triggers (`day28.*`)

All outputs are stored in DuckDB + `Day-29/reports/`.

## Run (Windows PowerShell)

From repo root:

```powershell
pip install -e .\Day-21

python -m hospcap.day29 run `
  --db "Day-21\db\hospcap.duckdb" `
  --report-dir "Day-29\reports" `
  --contract-name "hospcap_state_daily_v1"
```

## Useful knobs

- Skip gold rebuild if already done:
  `--skip-gold`
- Skip monitoring:
  `--skip-monitoring`
- Alert strictness:
  `--p-trigger 0.7 --c-false-alarm 1 --c-missed 8`

## Outputs

DuckDB:
- `day29.runs` (links sub-run IDs)
- `day29.step_logs` (stdout/stderr snippets per step)
- plus the existing tables from Day 23/25/26/27/28

Reports:
- `Day-29/reports/day29_summary.md`
- `Day-29/reports/alerts_dashboard.csv` (same as Day 28, copied for convenience)
