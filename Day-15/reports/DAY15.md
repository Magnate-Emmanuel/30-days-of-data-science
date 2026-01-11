# Day 15 — Predictive no-show risk model (leakage-safe) + targeting

## Goal
Train leakage-safe predictive models for appointment no-shows using a patient-level split (no person overlap across train/valid/test). Compare models on VALID, then evaluate once on TEST. Produce an operational targeting view via top-K performance.

## Data and split
Rows: 110,516  
Split sizes:
- Train: 77,368 (prevalence 0.2030)
- Valid: 16,649 (prevalence 0.2035)
- Test : 16,499 (prevalence 0.1949)

## Models compared (VALID leaderboard)
Models: logistic regression, decision tree, random forest, hist gradient boosting.

Best model on VALID (lowest Brier, best PR-AUC): hist_gb

Leaderboard (VALID → TEST):
- hist_gb: valid_pr_auc 0.371, valid_brier 0.144; test_pr_auc 0.360, test_brier 0.140
- rf     : valid_pr_auc 0.364, valid_brier 0.145; test_pr_auc 0.352, test_brier 0.140
- tree   : weaker
- logreg : weaker

## Calibration
Platt scaling (fit on VALID) produced probabilities with mean close to prevalence:
- VALID calibrated: prevalence 0.2035, mean_p 0.2036
- TEST  calibrated: prevalence 0.1949, mean_p 0.2034

Calibration slightly worsened Brier vs raw hist_gb, suggesting the base model probabilities were already fairly well calibrated.

## Targeting performance (TEST, calibrated)
Top 1% (k=164): precision@k 0.518, captured 85 no-shows  
Top 5% (k=824): precision@k 0.439, captured 362  
Top 10% (k=1649): precision@k 0.411, captured 677  
Top 20% (k=3299): precision@k 0.370, captured 1220  

Interpretation: strong uplift over random selection for capacity-constrained interventions.

## Artifacts saved
- Day-15/artifacts/noshow_base_model.joblib
- Day-15/artifacts/noshow_platt_calibrator.joblib
- Day-15/artifacts/noshow_feature_contract.json
- Day-15/reports/day15_metrics.json

Next: Day 16 begins causal analysis of SMS_received (propensity + overlap + IPW ATE).
