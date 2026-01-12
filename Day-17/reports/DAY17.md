# Day 17 — Causal effect of SMS reminders on no-shows (IPW + AIPW)

## Goal

Day 17 is the first “causal” day of Project 2. The predictive model from Day 15 answers: *who is likely to no-show?*  
Here, we ask a different question: *does receiving an SMS reminder causally reduce no-shows?* We treat this as an observational causal inference problem, using adjustment for measured confounders and two estimators: inverse probability weighting (IPW) and augmented IPW (AIPW / doubly robust).

## Data and variables

We work with the engineered appointment-level table built earlier in the project (from the Day 11–15 pipeline). The modeling dataframe has 110,516 rows and the following core columns:

- Treatment: `sms_received` (A), coded 0/1  
- Outcome: `label` (Y), coded 0/1  
- Covariates used for adjustment (examples): `age`, `gender`, `neighbourhood`, `scholarship`, comorbidity indicators, scheduling lead-time features, calendar features, and prior utilization (`prior_appt_count`, `nbhd_n`, etc.).

Counts in the full dataset:

- Treatment distribution: A=0: 75,035; A=1: 35,481  
- Outcome distribution: Y=0: 88,205; Y=1: 22,311

**Outcome interpretation:** throughout Day 17 we estimate effects on `Y = label`. If `label=1` denotes a no-show (as is common in no-show datasets), then a **negative ATE means SMS reduces no-show probability (improves attendance)**.

## Causal estimand

We estimate the average treatment effect (ATE):

\[
\text{ATE} = \mathbb{E}[Y(1) - Y(0)],
\]

where \(Y(1)\) is the outcome if the appointment receives an SMS reminder, and \(Y(0)\) is the outcome if it does not.

Because this is observational data, identification relies on standard assumptions: consistency, conditional exchangeability given measured covariates, and positivity (overlap).

## Methods

### 1) Naive difference in means (for contrast only)

We first compute the raw difference in outcome means by treatment:

- Mean(Y|A=0) = 0.166949  
- Mean(Y|A=1) = 0.275753  
- Naive difference = 0.108804

This naive comparison suggests SMS is associated with *higher* no-show risk, which is a classic sign of selection/targeting: reminders may have been used more often for appointments that were already higher-risk.

### 2) Propensity score model

We fit a propensity model for treatment assignment:

\[
e(X) = \mathbb{P}(A=1 \mid X),
\]

using logistic regression with appropriate preprocessing (imputation + one-hot encoding for categorical features). Held-out performance:

- Propensity ROC-AUC ≈ 0.8919

A high AUC indicates SMS assignment is strongly predictable from observed features, reinforcing why naive comparisons can be misleading and why careful adjustment is needed.

### 3) IPW ATE with trimming (overlap protection)

We estimate the IPW ATE and apply propensity trimming for positivity:

- Trim region: pscore in [0.01, 0.99]  
- n used after trimming: 61,390  
- IPW ATE = -0.046055  
- Bootstrap 95% CI: (-0.056290, -0.037508)

Interpretation (if label=1 is no-show): **SMS reduces no-show probability by ~4.6 percentage points** in the overlap (trimmed) population.

We also track effective sample sizes under weighting to ensure weights are not dominated by a few observations:

- ESS treated ≈ 15,311  
- ESS control ≈ 23,437

### 4) Doubly robust AIPW (AIPW / DR)

We estimate the ATE using AIPW, which combines a treatment model (propensity) and outcome regression models and remains consistent if either component is correctly specified:

- AIPW ATE = -0.042294  
- Analytic SE ≈ 0.004989  
- Analytic 95% CI: (-0.052073, -0.032516)  
- Bootstrap mean and 95% CI: -0.042251 (-0.051490, -0.033758)

Interpretation (if label=1 is no-show): **SMS reduces no-show probability by ~4.2 percentage points** in the trimmed overlap population, with a tight confidence interval.

## Main result (what we would report)

After adjustment for measured confounding using IPW and AIPW, the estimated causal effect of receiving an SMS reminder on `Y=label` is **negative** and statistically distinguishable from zero in the overlap sample.

If `label=1` denotes a no-show, the result is practically meaningful: **SMS reminders reduce no-show risk by roughly 4–5 percentage points** for appointments where treatment overlap is adequate.

## What this does and does not claim

This is a causal estimate under observational assumptions. It does not claim randomized evidence. The estimate is valid only to the extent that:

- all important confounders were measured and included,
- model misspecification is not severe (AIPW helps, but is not magic),
- overlap is adequate (we explicitly trimmed to address this),
- the outcome coding is correctly interpreted.

## Outputs saved

Day 17 writes the results to `Day-17/reports/`:

- `DAY17_ate_results.csv`  
- `DAY17_results.json`

These files contain the naive estimate, IPW estimate + CI, and AIPW estimate + CI, along with trimming details and sample size used.

## Next step (Day 18)

Day 18 moves from “average effect” to “who benefits most”:

- estimate heterogeneous effects / uplift (CATE-like targeting),
- compare a risk-based policy (message highest predicted no-show risk) versus an uplift-based policy (message those with largest predicted SMS benefit),
- evaluate both under realistic daily SMS budgets.

The key idea is decision support: we will not just estimate effects; we will turn them into a targeting rule.
