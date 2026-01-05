# Model Card — Diabetes Readmission <30 days (Local demo)

## Intended use
Operational prioritization / capacity targeting (e.g., top-K outreach).
Not for clinical diagnosis.

## Label
label = 1 if readmitted == "<30", else 0.

## Leakage prevention
Patient-level split by person_id (no overlap).
Calibration fit using OOF predictions within TRAIN only (GroupKFold).

## Model
HistGradientBoostingClassifier + preprocessing pipeline.
Platt (sigmoid) calibration on logit(p_raw).

## Reported test performance (from Day 9)
PR-AUC ≈ 0.2078
ROC-AUC ≈ 0.6666
Brier ≈ 0.09135
Log loss ≈ 0.3211

## Uncertainty (from Day 8 patient-level bootstrap)
PR-AUC 95% CI: [0.1911, 0.2270]
ROC-AUC 95% CI: [0.6536, 0.6809]
Brier  95% CI: [0.0880, 0.0944]
Logloss95% CI: [0.3118, 0.3298]

## Limitations / risks
- This is a demonstration on a public dataset
- Potential bias concerns and missingness (e.g., race missingness)
- Model should be monitored for drift and recalibrated over time
