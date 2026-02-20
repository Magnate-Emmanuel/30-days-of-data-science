# Day 30 — Hospital capacity forecasting + surge alerting (final report)

Generated: 2026-02-20 00:27 UTC

Day 30 run_id: `a25c5896-db86-4335-ae1d-7a2c7def78ad`

Database: `C:\Users\sarfo\AppData\Local\Temp\hospcap_work\hospcap.duckdb`

Contract: `hospcap_state_daily_v1`

Packaged pipeline (Day 29) run_id: `a42a6ad6-5494-4d76-bb00-1609a762243b`

## What this system does

This build treats hospital capacity forecasting as an operations analytics product. It forecasts utilization for key targets over multiple horizons, quantifies uncertainty, and produces early-warning alerts with concrete staffing/transfer triggers.

## Pipeline overview

The pipeline is contract-driven and reproducible: ingest (Day 21), quality gates (Day 22), gold feature panel (Day 23), baseline backtests (Day 24), main models (Day 25), probabilistic forecasts (Day 26), monitoring (Day 27), decision layer alerts (Day 28), and a single-command runner (Day 29).

## Linked sub-runs

| step | run_id |
|---|---|
| Day 25 main models | `41b5af77-e55b-458b-b2fd-4408ab9a38e1` |
| Day 26 probabilistic | `47a2035e-d21c-44ce-ba4f-113304527562` |
| Day 27 monitoring | `2f7cee45-cc80-4f69-9bec-a6499e1c8289` |
| Day 28 alerts | `93678486-4c32-498f-ab4b-0fa655df35ed` |

## Outputs

- Dashboard-ready alerts exported: `4512` rows → `alerts_dashboard.csv`
- Metrics summary → `metrics_summary.csv`

## Notes and limitations

Capacity series can contain reporting gaps and definitional shifts. The project therefore leans heavily on explicit data-quality gates and monitoring. For production use, you would additionally maintain facility-level forecasting, incorporate exogenous drivers (weather, outbreaks), and tune thresholds and costs with local operational leadership.
