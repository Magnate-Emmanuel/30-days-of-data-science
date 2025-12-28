# Day 2 — Baseline Model (Leakage-Safe) + Fixing Probability Inflation

## What I built
- Created a modeling feature table `gold_diabetes_features_v1` in DuckDB from `silver_diabetes`.
- Trained a baseline logistic regression using a leakage-safe train/test split (patient-aware).
- Evaluated ranking performance (PR-AUC, ROC-AUC) and probability quality (Brier).
- Diagnosed probability inflation from `class_weight="balanced"` and fixed it by training an unweighted logistic regression.

## Data and tables
- Source: `silver_diabetes` (cleaned '?' -> NULL)
- Feature table: `gold_diabetes_features_v1`
- Rows: 101,766
- Label prevalence (overall): 0.1116

## Leakage-safe split
- Method: GroupShuffleSplit by `person_id` (patient ID), test_size = 0.20
- Train rows: 81,613; Test rows: 20,153
- Patient overlap between train and test: 0

## Baseline model: Logistic regression with preprocessing pipeline
- Numeric: median imputation + standard scaling
- Categorical: most-frequent imputation + one-hot encoding
- Model: logistic regression

## Results (balanced vs unweighted)
### With class_weight="balanced"
- PR-AUC: 0.2004
- ROC-AUC: 0.6595
- Brier: 0.2251
- Mean predicted probability: 0.463 (far above prevalence) → probabilities inflated

### Unweighted logistic regression (final baseline)
- PR-AUC: 0.1993
- ROC-AUC: 0.6584
- Brier: 0.0919
- Mean predicted probability: 0.1112 (close to prevalence) → probabilities usable

## Top-K targeting performance (unweighted)
- Top 1% precision: 0.361
- Top 5% precision: 0.298
- Top 10% precision: 0.255
- Top 20% precision: 0.198

Interpretation: The model ranks risk well enough for capacity-constrained targeting; selecting the top 10% captures positives at ~2.4× the random baseline (~0.107).

## Key lesson
`class_weight="balanced"` can help classification decisions but can distort predicted probabilities. Ranking metrics can remain good while probability quality worsens. For decision support that uses probabilities, unweighted training (or later calibration) is preferred.

## Artifacts saved
- `Day-2/reports/DAY02_metrics.json`
- `Day-2/reports/DAY02_top200_predictions_unweighted.csv`
