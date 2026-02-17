# Day 29 — Pipeline run summary

Run ID: `c10c9135-ab45-4d1b-bcec-fc101b94cf1c`

## Parameters

- contract_name: `hospcap_state_daily_v1`
- targets: `inpatient_beds_used, staffed_adult_icu_bed_occupancy`
- horizons: `1, 7, 14`
- n_splits: `8`, step_days: `7`
- quantiles: `0.1, 0.5, 0.9`
- p_trigger: `0.6`, costs: false_alarm=1.0, missed=5.0

## Sub-runs

| step | run_id |
|---|---|
| Day 25 (main models) | `dfe13c41-0002-45dd-8cde-a5e755fa6377` |
| Day 26 (probabilistic) | `f7e63977-795c-4610-ab3c-4b1f523fdfb1` |
| Day 27 (monitoring) | `7d8cd72a-4390-4ded-8f85-cc29bf40c0a2` |
| Day 28 (alerts) | `ca1a79c6-7aa4-47fd-b563-d85717d0e54b` |

## Where to look

- Step logs in DuckDB: `day29.step_logs`
- Day 28 dashboard-ready alerts: `Day-29/reports/alerts_dashboard.csv`
- Full step reports under `Day-29/reports/day23 ... day28`
