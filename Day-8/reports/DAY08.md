# Day 8 — Patient-level bootstrap uncertainty

Bootstrap type: cluster bootstrap by person_id

Bootstrap replications B = 500


## Point estimates (test set, calibrated p_hat)

- Prevalence: 0.106733

- PR-AUC: 0.207833

- ROC-AUC: 0.666614

- Brier: 0.091348

- Log loss: 0.321113


## 95% bootstrap CIs (clustered by person_id)

         metric  point_estimate   ci95_low  ci95_high
         pr_auc        0.207833   0.191132   0.226985
        roc_auc        0.666614   0.653555   0.680908
          brier        0.091348   0.087999   0.094434
        logloss        0.321113   0.311778   0.329817
     prec_top_1        0.363184   0.297732   0.446174
     prec_top_5        0.301887   0.267750   0.337954
    prec_top_10        0.249132   0.226828   0.273963
    prec_top_20        0.205707   0.190381   0.221538
 captured_top_1       73.000000  60.000000  89.525000
 captured_top_5      304.000000 269.475000 341.525000
captured_top_10      502.000000 457.000000 552.525000
captured_top_20      829.000000 764.475000 895.525000