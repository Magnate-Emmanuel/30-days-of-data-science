# Day 6 — Cross-fitted calibration (OOF) + top-K decision rule

## Goal
Fix calibration overfitting. Instead of fitting isotonic calibration on the same validation set we evaluate on, we built calibration maps using out-of-fold (OOF) predictions on TRAIN (grouped by patient).

## What I did
1) Loaded `gold_diabetes_features_v1` from DuckDB (`Day-1/data/warehouse/day1.duckdb`).
2) Created leakage-safe train/valid/test split using `GroupShuffleSplit` by `person_id`.
3) Built the base model (Day 4 winner): HistGradientBoostingClassifier in a pipeline with:
   - numeric: median imputation
   - categorical: most-frequent imputation + one-hot encoding (dense output)
4) Generated OOF probabilities on TRAIN using `GroupKFold(n_splits=5)` grouped by `person_id`.
5) Fit calibrators on OOF predictions + TRAIN labels:
   - sigmoid / Platt scaling (logistic regression on logit(p))
   - isotonic regression
6) Fit final model on full TRAIN, predicted base probabilities on VALID and TEST.
7) Applied calibrators to VALID/TEST probabilities.
8) Selected the calibration method by VALID Brier score.
9) Produced operational top-K thresholds and precision on TEST.

## Sanity check: OOF predictions on TRAIN
OOF prevalence: 0.112186  
OOF mean_p: 0.111704  
OOF PR-AUC: 0.214610  
OOF ROC-AUC: 0.667027  
OOF Brier: 0.095287  
OOF LogLoss: 0.331525  
OOF ECE: 0.001167  

## VALID metrics
VALID base: PR-AUC=0.224678 ROC-AUC=0.667761 Brier=0.096830 LogLoss=0.335768 ECE=0.004044  
VALID sigmoid_platt_oof: PR-AUC=0.224678 ROC-AUC=0.667761 Brier=0.096827 LogLoss=0.335759 ECE=0.004486  
VALID isotonic_oof: PR-AUC=0.215795 ROC-AUC=0.667189 Brier=0.096897 LogLoss=0.335950 ECE=0.003478  

## TEST metrics
TEST base: PR-AUC=0.207833 ROC-AUC=0.666614 Brier=0.091344 LogLoss=0.321089 ECE=0.004501  
TEST sigmoid_platt_oof: PR-AUC=0.207833 ROC-AUC=0.666614 Brier=0.091348 LogLoss=0.321113 ECE=0.004971  
TEST isotonic_oof: PR-AUC=0.201027 ROC-AUC=0.666322 Brier=0.091349 LogLoss=0.321131 ECE=0.005671  

## Selection
Best by VALID Brier: `sigmoid_platt_oof`.

## Decision rule (capacity targeting on TEST)
Top 1%:  k=201  captured=73  precision@k=0.3632  threshold=0.3494  
Top 5%:  k=1007 captured=304 precision@k=0.3019 threshold=0.2318  
Top 10%: k=2015 captured=502 precision@k=0.2491 threshold=0.1904  
Top 20%: k=4030 captured=829 precision@k=0.2057 threshold=0.1435  

## Key takeaway
Cross-fitted calibration prevents isotonic “perfect-looking” calibration caused by fitting and evaluating on the same set. Platt scaling preserved ranking and avoided overfitting.
