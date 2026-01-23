# Day 19 — Decision + Deployment (SMS targeting)

This day turns model outputs into deployable **policy outputs**. Using the appointments feature table in DuckDB (`gold_appointments_features_v1`) and patient-level splits (`gold_appointments_splits`), we trained two outcome models:

- **mu0(x)**: predicted probability of **no-show** if **no SMS** is sent.
- **mu1(x)**: predicted probability of **no-show** if **SMS** is sent.

We define **uplift(x) = mu0(x) − mu1(x)**. Positive uplift means sending an SMS is expected to reduce no-shows.

We then produce two decision policies under a daily budget **K = 5746**:

1. **Risk policy**: send SMS to the top-K highest baseline risk `mu0`.
2. **Uplift policy**: send SMS to the top-K highest uplift.

Outputs saved in `Day-19/reports/` include:

- `DAY19_policy_value_table.csv`
- `DAY19_decisions_test_k5746.csv`
- `DAY19_target_list_risk_k5746.csv`
- `DAY19_target_list_uplift_k5746.csv`

Artifacts saved in `Day-19/artifacts/` include:

- `day19_outcome_mu0_pipe.joblib`, `day19_outcome_mu1_pipe.joblib`
- `day19_propensity_pipe.joblib`
- `DAY19_input_template.csv`
- `DAY19_metadata.json`

DuckDB tables written:

- `policy_runs`
- `policy_recommendations`

Run id: `b88cb6d2-2719-4277-870a-9f5445546589` at `2026-01-23T09:23:12`.
