# Day 4 — Train/Valid/Test + Tree Models (Leakage-Safe by Patient)

## What I did today
- Worked in `Day-4/`.
- Reused DuckDB warehouse from Day 1 (`Day-1/data/warehouse/day1.duckdb`).
- Loaded `gold_diabetes_features_v1`.
- Created a leakage-safe **train/validation/test** split using `GroupShuffleSplit` by `person_id`:
  - Test = 20% of total
  - Validation = 25% of remaining trainval (so ~20% of total)
  - Train = remaining (~60% of total)
  - Verified patient overlap across splits = 0.
- Trained four models on TRAIN, selected on VALID (primary metric: PR-AUC), then evaluated once on TEST:
  1) Logistic Regression (unweighted)
  2) Decision Tree
  3) Random Forest
  4) HistGradientBoosting (with dense one-hot encoder because it requires dense input)

## Why train/valid/test (in plain terms)
- Train is where the model learns.
- Validation is where I choose the model (and later tuning decisions).
- Test is used once at the end so the final performance is honest.

## Leaderboard (selected by VALID PR-AUC)
| model | valid_pr_auc | valid_brier | valid_top10_precision | test_pr_auc | test_brier | test_top10_precision |
|---|---:|---:|---:|---:|---:|---:|
| hist_gb | 0.224678 | 0.096830 | 0.259942 | 0.207833 | 0.091344 | 0.249132 |
| random_forest | 0.224002 | 0.097494 | 0.251697 | 0.204242 | 0.091860 | 0.247643 |
| logreg_unweighted | 0.222778 | 0.097112 | 0.257032 | 0.200228 | 0.091835 | 0.254591 |
| decision_tree | 0.197429 | 0.097766 | 0.245393 | 0.181440 | 0.092266 | 0.241191 |

## Interpretation
- **Best by validation PR-AUC:** `hist_gb`.
- `random_forest` is very close on validation PR-AUC, but slightly worse on test PR-AUC and Brier.
- Logistic regression remains competitive and slightly better on **test top-10% precision**, which matters if the operational goal is strictly “top-K targeting.”
- Overall, `hist_gb` is the best balanced choice today (strong ranking + best Brier on test).

## Artifacts saved
- `Day-4/reports/DAY04_leaderboard.csv`
- `Day-4/reports/DAY04_leaderboard.json`
- `Day-4/reports/DAY04_best_model.joblib` (winner model)
- `Day-4/reports/DAY04_top200_test_predictions.csv`
