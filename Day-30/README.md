# Day 30 — Final report + dashboard-ready outputs + publishable story

Day 30 is the capstone: generate a final, stakeholder-facing report and clean outputs that can plug into a dashboard.

This step **does not retrain models**. It reads the most recent successful `day29` pipeline run and compiles:
- a final report (`day30_final_report.md`)
- a dashboard-ready alerts table (`alerts_dashboard.csv`)
- a metrics summary table (`metrics_summary.csv`)
- Medium + LinkedIn drafts (`story_medium.md`, `story_linkedin.md`)

## Run (PowerShell)

From repo root:

```powershell
pip install -e .\Day-21
python -m hospcap.day30 run --db "Day-21\db\hospcap.duckdb" --report-dir "Day-30\reports"
```

If your repo is under Dropbox/OneDrive and you hit file-lock errors, use the local DB helper:

```powershell
powershell -ExecutionPolicy Bypass -File "Day-30\scripts\run_day30_localdb.ps1"
```

## Parameters

- `--day29-run-id` (optional): choose a specific pipeline run. Default: latest successful run.
- `--contract-name` (optional): include in the report header.
- `--alerts-limit` (optional): limit exported alerts for preview.

## Outputs

- `Day-30/reports/day30_final_report.md`
- `Day-30/reports/alerts_dashboard.csv`
- `Day-30/reports/metrics_summary.csv`
- `Day-30/story_medium.md`
- `Day-30/story_linkedin.md`
