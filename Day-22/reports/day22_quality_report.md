# Day 22 — Quality Report

Run ID: `7237e5cf-052c-46d4-a921-1d92db9366c3`

Generated (UTC): 2026-01-28T16:31:56+00:00

## Gate thresholds

- min_history_days: **180**
- max_missing_run: **3**

## Worst states by missing runs / missing rate (top 15)

| state   |   history_days |   max_missing_run |   missing_rate |
|:--------|---------------:|------------------:|---------------:|
| AR      |           1576 |                62 |       0.013467 |
| LA      |           1579 |                55 |       0.011887 |
| PR      |           1579 |                55 |       0.011887 |
| CA      |           1545 |                21 |       0.004572 |
| NV      |           1578 |                17 |       0.003617 |
| WV      |           1552 |                15 |       0.004989 |
| UT      |           1506 |                 6 |       0.001332 |
| CO      |           1509 |                 2 |       0.000664 |
| MS      |           1531 |                 1 |       0.000218 |

## Failing states (hard violations)

| state   | rule                     |   history_days |   max_missing_run |   missing_rate |
|:--------|:-------------------------|---------------:|------------------:|---------------:|
| AR      | max_missing_run_exceeded |           1576 |                62 |       0.013467 |
| LA      | max_missing_run_exceeded |           1579 |                55 |       0.011887 |
| PR      | max_missing_run_exceeded |           1579 |                55 |       0.011887 |
| CA      | max_missing_run_exceeded |           1545 |                21 |       0.004572 |
| NV      | max_missing_run_exceeded |           1578 |                17 |       0.003617 |
| WV      | max_missing_run_exceeded |           1552 |                15 |       0.004989 |
| UT      | max_missing_run_exceeded |           1506 |                 6 |       0.001332 |

## Drift warnings (last 28d vs prior 28d)

| state   | target              |   mean_shift_sd |   sd_ratio |   n_recent |   n_prior |
|:--------|:--------------------|----------------:|-----------:|-----------:|----------:|
| AK      | inpatient_beds_used |         3.60983 |    1.76573 |         84 |        84 |
| DC      | inpatient_beds_used |         1.12259 |    2.90697 |         84 |        84 |

## Outlier day-to-day changes (robust z >= 6)

(none)
