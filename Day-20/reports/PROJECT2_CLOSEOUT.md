# Project 2 Closeout — No-Show Prediction + SMS Causal/Uplift Targeting

This project built an end-to-end workflow that goes beyond prediction into causal estimation and decision deployment.

The predictive layer produces calibrated risk estimates for no-show, while the causal layer estimates the effect of SMS reminders on no-show (ATE) and then moves to heterogeneous effects (uplift), comparing two operational policies under a fixed SMS budget:
1) risk-based policy: target highest baseline risk
2) uplift-based policy: target those expected to benefit most from SMS

The Day-20 pipeline operationalizes the full workflow: it pulls gold features from DuckDB, enforces patient-level splits, trains models, generates mu0/mu1 and uplift on the test set, writes policy outputs into DuckDB as runs + recommendations, and exports test decisions and a policy summary CSV suitable for reporting or dashboards.
