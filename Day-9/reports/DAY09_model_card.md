# Day 9 — Readmission model artifacts (deployable locally)
## What exists after Day 9
- Trained base model + Platt calibrator saved as joblib artifacts
- Metadata JSON with metrics and procedure
- Feature/column contract JSON
- Example scored test CSV

## Test metrics (calibrated)
- Prevalence: 0.106733
- PR-AUC: 0.207833
- ROC-AUC: 0.666614
- Brier: 0.091348
- Log loss: 0.321113

## Capacity targeting (TEST)
- Top 1%: k=201 captured=73 precision@k=0.363184 threshold=0.349429
- Top 5%: k=1007 captured=304 precision@k=0.301887 threshold=0.231791
- Top 10%: k=2015 captured=502 precision@k=0.249132 threshold=0.190383
- Top 20%: k=4030 captured=829 precision@k=0.205707 threshold=0.143511
