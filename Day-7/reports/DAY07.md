# Day 7 — Scoring output + Model report

## What I produced
- A scored test table with calibrated probabilities (p_hat)
- A DuckDB gold-style scored table: gold_diabetes_scored_day7
- Four standard evaluation plots: PR, ROC, Calibration, Gains (Lift)
- A top-K summary table (capacity targeting)

## Test-set metrics (calibrated probabilities)
Prevalence: 0.106733
PR-AUC (Average Precision): 0.207833
ROC-AUC: 0.666614
Brier score: 0.091348
Log loss: 0.321113

## Files
- DAY07_scored_test.csv
- DAY07_topk_summary.csv
- DAY07_pr_curve.png
- DAY07_roc_curve.png
- DAY07_calibration.png
- DAY07_gains_curve.png
