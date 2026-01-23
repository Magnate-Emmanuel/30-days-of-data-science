# Day 20 — Packaging & Reproducible Pipeline (Project 2: No-Show + SMS)

Today we package Days 11–19 into a single reproducible pipeline that reads the DuckDB warehouse, ensures patient-level splits exist, estimates potential outcomes (mu0, mu1), produces risk-based and uplift-based SMS targeting lists under a budget, and writes policy outputs back into DuckDB.

## One command to run (from repo root)

Windows:
python -m src.run_project2_pipeline --db-path "C:\Users\sarfo\Dropbox\Courses\Data Science\30-days-of-data-science\Day-11\data\warehouse\day11_noshow.duckdb" --outdir "Day-20/reports" --budget-frac 0.10

Alternative (relative DB path):
python -m src.run_project2_pipeline --db-path "Day-11/data/warehouse/day11_noshow.duckdb" --outdir "Day-20/reports" --budget-frac 0.10

## What gets produced

Files:
- Day-20/reports/DAY20_policy_summary.csv
- Day-20/reports/DAY20_decisions_test.csv

DuckDB tables:
- policy_runs
- policy_recommendations
- gold_appointments_splits (created if missing)

## Stability fixes included

We use a single DuckDB connection to avoid file-lock errors. The preprocessing objects are cloned per model to avoid one-hot feature mismatch.

Generated: 2026-01-23T14:04:37
