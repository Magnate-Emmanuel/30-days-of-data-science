# Day 18 — Heterogeneous Effects / Uplift Modeling (SMS → No-Show)

## Goal
Estimate **who benefits most** from sending SMS reminders, and compare two targeting strategies under limited budgets:
1. **Risk-based**: send SMS to those with highest baseline predicted no-show risk (mu0).
2. **Uplift-based**: send SMS to those with largest estimated reduction in no-show probability (uplift = mu0 - mu1).

## Data + Setup
- Source: DuckDB table `gold_appointments_features_v1` built earlier (gold features).
- Treatment `A`: `sms_received` (1 = SMS received).
- Outcome `Y`: `label` (assumed 1 = no-show; confirm interpretation).
- Patient-level splits (by `person_id`): 70% train, 15% valid, 15% test.

## Method
We use a **T-learner**:
- Fit outcome model on treated: mu1(x) = P(Y=1 | X=x, A=1)
- Fit outcome model on control: mu0(x) = P(Y=1 | X=x, A=0)
- Uplift: uplift(x) = mu0(x) - mu1(x) (positive = SMS reduces no-show)

## Key Results (Test)
- Mean uplift (mu0 - mu1): -0.053116
- Uplift distribution figure: `reports/DAY18_uplift_hist.png`
- Budget comparison table: `reports/DAY18_policy_comparison.csv`
- Budget curve: `reports/DAY18_budget_curve.png`

## Targeting Outputs
Ranked lists saved for operational use:
- Risk-based top lists: `reports/DAY18_top5pct_risk.csv`, `reports/DAY18_top10pct_risk.csv`
- Uplift-based top lists: `reports/DAY18_top5pct_uplift.csv`, `reports/DAY18_top10pct_uplift.csv`

## Interpretation
Risk targeting finds those likely to no-show, but **uplift targeting** aims to find those whose probability of no-show actually **changes most** under SMS. Under budget constraints, uplift-based targeting can outperform risk-based targeting when treatment effects are heterogeneous.
