# Day 3 — Missingness Diagnostics (MCAR / MAR / MNAR) + Modeling Impact

## What I did today
- Worked in `Day-3/` and reused the existing DuckDB warehouse (`Day-1/data/warehouse/day1.duckdb`).
- Loaded the modeling table `gold_diabetes_features_v1`.
- Computed missingness rates per feature.
- Checked whether missingness is related to the outcome (label) by comparing label prevalence in missing vs observed groups.
- Trained two leakage-safe baseline models to test whether missingness indicators improve performance:
  - Model A: logistic regression pipeline with standard imputation (no indicators)
  - Model B: same pipeline but with `SimpleImputer(add_indicator=True)` (missingness indicators)
- Saved Day 3 artifacts in `Day-3/reports/`.

## Missingness summary
Only one feature has missing values in our current feature set:

- `race`: 2,273 missing values  
- Missing rate: 0.022336 (~2.23%)

All other columns in `gold_diabetes_features_v1` have missing rate = 0.

Saved as:
- `Day-3/reports/DAY03_missingness_summary.csv`

## Missingness vs outcome (MCAR sanity check)
I compared label prevalence among rows where `race` is missing vs observed:

- Prevalence if `race` is missing: 0.08271  
- Prevalence if `race` is observed: 0.112259  
- Difference (missing − observed): −0.029549

Interpretation:
- This pattern is not consistent with MCAR (Missing Completely At Random), because missingness appears related to the outcome.
- The data are more consistent with MAR or MNAR.
- MNAR cannot be proven from observed data alone; MAR is a reasonable working assumption for practical modeling here.

Saved as:
- `Day-3/reports/DAY03_missingness_vs_label.csv`

## Leakage-safe split (patient-aware)
Because many patients have multiple encounters, I used a group split by patient ID (`person_id`) to prevent leakage.

- Train rows: 81,613  
- Test rows: 20,153  
- Train prevalence: 0.1128006568  
- Test prevalence: 0.1067334888  
- Patient overlap between train and test: 0 (leakage-safe)

## Modeling experiment: do missingness indicators help?
### Model A (no missingness indicators)
Metrics:
- Prevalence: 0.1067334888
- Mean predicted probability: 0.1111557385
- Median predicted probability: 0.0939140222
- PR-AUC: 0.1993444354
- ROC-AUC: 0.6584202690
- Brier: 0.0918842474

Top-K:
- Top 1%: precision@k = 0.363184 (captured 73)
- Top 5%: precision@k = 0.297915 (captured 300)
- Top 10%: precision@k = 0.255087 (captured 514)
- Top 20%: precision@k = 0.198263 (captured 799)

### Model B (with missingness indicators)
Metrics and Top-K results were identical to Model A:
- PR-AUC: 0.1993444354
- ROC-AUC: 0.6584202690
- Brier: 0.0918842474
- Same top-K table

Interpretation:
- Adding missingness indicators did not change performance because missingness is limited (only `race`, ~2.23% missing).
- In this feature subset, missingness is unlikely to be a major driver of predictive performance.
- If we later add more clinical variables (labs/diagnoses) with substantial missingness, indicators and more careful missingness strategies may matter more.

Saved as:
- `Day-3/reports/DAY03_metrics.json`
- `Day-3/reports/DAY03_topk_with_indicators.csv`

## Files created today
- `Day-3/notebooks/01_missingness_diagnostics_and_model.ipynb`
- `Day-3/reports/DAY03_missingness_summary.csv`
- `Day-3/reports/DAY03_missingness_vs_label.csv`
- `Day-3/reports/DAY03_metrics.json`
- `Day-3/reports/DAY03_topk_with_indicators.csv`

## What I learned (simple)
- MCAR means missingness is random and unrelated to the data; MAR means missingness depends on what we observe; MNAR means missingness depends on unobserved values (including the missing value itself).
- In this dataset, `race` missingness is associated with a lower observed readmission rate, so MCAR is unlikely.
- In practice, I can treat missingness as a feature (missingness indicators), but here it didn’t help because missingness is small.

## Next step (Day 4 preview)
Train a nonlinear model (tree-based) under the same leakage-safe split and compare to logistic regression, using the same evaluation setup (PR-AUC, Brier, top-K).
