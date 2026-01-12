# Day 16 — Causal setup: SMS reminders → no-show

## Estimand

We estimate the average treatment effect (ATE) of receiving an SMS reminder on the probability of no-show.

- Treatment A: `sms_received` (1 = received SMS)

- Outcome Y: `label` (verify 1 = no-show; see sanity table)


## Confounders X

We adjust for pre-treatment variables that can affect both SMS assignment and attendance/no-show.

Covariates used:

age, lead_time_days, gender, neighbourhood, scholarship, hipertension, diabetes, alcoholism, handcap


## Propensity model and overlap

- Propensity model: logistic regression with one-hot encoding for categorical variables

- Held-out ROC-AUC: 0.8051

Overlap diagnostics were saved in `DAY16_overlap_stats.json` and `DAY16_pscore_overlap.png`.


## Next (Day 17)

Use propensity scores to estimate ATE via IPW and AIPW, with trimming if overlap is weak.
