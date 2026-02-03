# Day 24 — Baseline backtest summary

Run ID: `68915311-4032-41dd-b86f-bf929f896e3b`

Targets: inpatient_beds_used, staffed_adult_icu_bed_occupancy

Horizons: 1, 7, 14

Splits: n_splits=8, step_days=7

## Best model by target and horizon (lowest RMSE)

| model            | target                          |   horizon |      mae |     rmse |    mape |    wape |   n |
|:-----------------|:--------------------------------|----------:|---------:|---------:|--------:|--------:|----:|
| seasonal_naive_7 | inpatient_beds_used             |         1 | 166.838  | 279.359  | 2.55778 | 1.78993 | 376 |
| naive_last       | inpatient_beds_used             |         7 | 146.537  | 252.933  | 2.7317  | 1.54459 | 376 |
| naive_last       | inpatient_beds_used             |        14 | 204.511  | 363.172  | 3.61134 | 2.16792 | 376 |
| seasonal_naive_7 | staffed_adult_icu_bed_occupancy |         1 |  22.2952 |  34.975  | 6.09704 | 2.29758 | 376 |
| ewma_opt         | staffed_adult_icu_bed_occupancy |         7 |  23.0636 |  34.1439 | 5.33034 | 2.32526 | 376 |
| naive_last       | staffed_adult_icu_bed_occupancy |        14 |  28.8644 |  46.4449 | 5.75383 | 2.93355 | 376 |

## Full score table

| model            | target                          |   horizon |      mae |     rmse |    mape |    wape |   n |
|:-----------------|:--------------------------------|----------:|---------:|---------:|--------:|--------:|----:|
| seasonal_naive_7 | inpatient_beds_used             |         1 | 166.838  | 279.359  | 2.55778 | 1.78993 | 376 |
| naive_last       | inpatient_beds_used             |         1 | 208.447  | 377.935  | 2.39866 | 2.23633 | 376 |
| ewma_opt         | inpatient_beds_used             |         1 | 224.978  | 398.919  | 2.59456 | 2.41369 | 376 |
| rolling_mean_7   | inpatient_beds_used             |         1 | 375.739  | 596.314  | 4.39641 | 4.03114 | 376 |
| naive_last       | inpatient_beds_used             |         7 | 146.537  | 252.933  | 2.7317  | 1.54459 | 376 |
| seasonal_naive_7 | inpatient_beds_used             |         7 | 146.537  | 252.933  | 2.7317  | 1.54459 | 376 |
| ewma_opt         | inpatient_beds_used             |         7 | 148.188  | 257.567  | 2.7478  | 1.56199 | 376 |
| rolling_mean_7   | inpatient_beds_used             |         7 | 239.138  | 380      | 3.67572 | 2.52066 | 376 |
| naive_last       | inpatient_beds_used             |        14 | 204.511  | 363.172  | 3.61134 | 2.16792 | 376 |
| seasonal_naive_7 | inpatient_beds_used             |        14 | 204.511  | 363.172  | 3.61134 | 2.16792 | 376 |
| ewma_opt         | inpatient_beds_used             |        14 | 208.976  | 372.819  | 3.61545 | 2.21525 | 376 |
| rolling_mean_7   | inpatient_beds_used             |        14 | 293.955  | 486.821  | 4.37025 | 3.11607 | 376 |
| seasonal_naive_7 | staffed_adult_icu_bed_occupancy |         1 |  22.2952 |  34.975  | 6.09704 | 2.29758 | 376 |
| naive_last       | staffed_adult_icu_bed_occupancy |         1 |  29.8617 |  50.7165 | 4.25554 | 3.07733 | 376 |
| ewma_opt         | staffed_adult_icu_bed_occupancy |         1 |  31.0979 |  52.6646 | 4.52088 | 3.20472 | 376 |
| rolling_mean_7   | staffed_adult_icu_bed_occupancy |         1 |  42.5346 |  67.9567 | 6.46628 | 4.3833  | 376 |
| ewma_opt         | staffed_adult_icu_bed_occupancy |         7 |  23.0636 |  34.1439 | 5.33034 | 2.32526 | 376 |
| naive_last       | staffed_adult_icu_bed_occupancy |         7 |  22.8617 |  34.178  | 5.21403 | 2.3049  | 376 |
| seasonal_naive_7 | staffed_adult_icu_bed_occupancy |         7 |  22.8617 |  34.178  | 5.21403 | 2.3049  | 376 |
| rolling_mean_7   | staffed_adult_icu_bed_occupancy |         7 |  27.5232 |  42.4011 | 5.53193 | 2.77487 | 376 |
| naive_last       | staffed_adult_icu_bed_occupancy |        14 |  28.8644 |  46.4449 | 5.75383 | 2.93355 | 376 |
| seasonal_naive_7 | staffed_adult_icu_bed_occupancy |        14 |  28.8644 |  46.4449 | 5.75383 | 2.93355 | 376 |
| ewma_opt         | staffed_adult_icu_bed_occupancy |        14 |  29.1512 |  46.8492 | 5.74275 | 2.9627  | 376 |
| rolling_mean_7   | staffed_adult_icu_bed_occupancy |        14 |  34.6809 |  56.5932 | 6.15288 | 3.5247  | 376 |
