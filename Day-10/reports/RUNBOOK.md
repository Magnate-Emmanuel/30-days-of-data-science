# Day 10 Runbook — Readmission Scoring (Local)

## What this does
Scores new encounter data with the saved Day-9 artifacts:
- base model pipeline (preprocess + HGB)
- Platt calibrator
Outputs scored probabilities + top-K ranked lists.

## Prerequisites
- Run from repo root
- Python packages: pandas, numpy, scikit-learn, joblib, duckdb

## Run scoring
From repo root:

python Day-10/src/run_scoring.py --input "Day-10/data/input_example.csv" --output "Day-10/outputs" --write_duckdb

## Modes
- auto: if label exists -> evaluate; else -> score
- score: ignores label even if present
- evaluate: requires label and computes metrics

## Outputs
- outputs/scored.csv
- outputs/ranked_top_1pct.csv, ranked_top_5pct.csv, ranked_top_10pct.csv, ranked_top_20pct.csv
- outputs/summary.json
- outputs/run_log.txt

## DuckDB (optional)
Creates/updates:
- gold_diabetes_scored_latest (replaced each run)
- gold_diabetes_scored_runs (appended audit log)

## Common errors
- Missing columns: input must contain all feature columns from readmit_feature_cols.json
- Wrong working directory: cd to repo root first
- Missing artifacts: ensure Day-9/artifacts exists and contains joblib + json files
