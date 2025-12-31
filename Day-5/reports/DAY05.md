# Day 5 — Calibration + Decision Rules (Top-K Targeting)

## What I did today
I turned the Day 4 model into a decision-support tool by (1) evaluating probability quality, (2) calibrating probabilities using sigmoid (Platt) and isotonic regression, and (3) converting probabilities into a capacity rule (top-K targeting). I kept the split leakage-safe by splitting on patient ID (`person_id`).

## Base model
Model: HistGradientBoostingClassifier in a scikit-learn Pipeline with:
- numeric: median imputation
- categorical: most-frequent imputation + one-hot encoding
Note: HistGradientBoosting requires dense input, so one-hot encoding was configured to output dense arrays for this pipeline.

## Probability metrics used
PR-AUC (Average Precision), ROC-AUC, Brier score, log loss, mean/median predicted probability.
Because my sklearn version did not support `log_loss(..., eps=...)`, I clipped probabilities to [1e-15, 1 - 1e-15] before computing log loss.

## Calibration methods
My sklearn version does not allow `CalibratedClassifierCV(cv="prefit")`, so I calibrated manually using the validation set only:
- Sigmoid / Platt scaling: logistic regression on the logit of predicted probabilities
- Isotonic regression: monotone mapping from probability to outcome rate

## Results (base vs calibrated)
BASE (uncalibrated) valid: PR-AUC=0.224678, ROC-AUC=0.667761, Brier=0.096830, LogLoss=0.335768  
BASE (uncalibrated) test : PR-AUC=0.207833, ROC-AUC=0.666614, Brier=0.091344, LogLoss=0.321089  

SIGMOID (Platt) valid: PR-AUC=0.224678, ROC-AUC=0.667761, Brier=0.096816, LogLoss=0.335715  
SIGMOID (Platt) test : PR-AUC=0.207833, ROC-AUC=0.666614, Brier=0.091373, LogLoss=0.321160  

ISOTONIC valid: PR-AUC=0.218224, ROC-AUC=0.670607, Brier=0.096483, LogLoss=0.334329  
ISOTONIC test : PR-AUC=0.199049, ROC-AUC=0.666606, Brier=0.091359, LogLoss=0.325903  

## Calibration error (ECE on validation)
ECE base: 0.004044  
ECE sigmoid: 0.003798  
ECE isotonic: ~0 (2.13e-18)

Interpretation: isotonic achieved essentially perfect calibration on the validation set, which is consistent with overfitting the calibration curve to that set. Test PR-AUC and test log loss were worse for isotonic than the base model.

## Decision rule: top-K targeting on TEST
Top 1%:  k=201   captured=81   precision@k=0.4030   threshold=0.3726  
Top 5%:  k=1007  captured=309  precision@k=0.3069   threshold=0.2363  
Top 10%: k=2015  captured=499  precision@k=0.2476   threshold=0.1926  
Top 20%: k=4030  captured=828  precision@k=0.2055   threshold=0.1436  

## Files saved
- Day-5/reports/DAY05_calibration_metrics.json
- Day-5/reports/DAY05_top200_test_predictions_best.csv
- Day-5/reports/DAY05.md
