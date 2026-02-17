# Day 25 — Main models backtest summary

Run ID: `dfe13c41-0002-45dd-8cde-a5e755fa6377`

Targets: inpatient_beds_used, staffed_adult_icu_bed_occupancy

Horizons: 1, 7, 14

Splits: n_splits=8, step_days=7

Baseline run_id (Day 24): `68915311-4032-41dd-b86f-bf929f896e3b`

## Best Day-25 model by target and horizon (lowest RMSE)

| model         | target                          |   horizon |      mae |     rmse |    mape |    wape |   n |
|:--------------|:--------------------------------|----------:|---------:|---------:|--------:|--------:|----:|
| gbrt_lag      | inpatient_beds_used             |         1 | 107.579  | 178.124  | 1.80516 | 1.15417 | 376 |
| ridge_fourier | inpatient_beds_used             |         7 | 167.758  | 257.941  | 6.44276 | 1.76827 | 376 |
| gbrt_lag      | inpatient_beds_used             |        14 | 202.865  | 339.873  | 5.62023 | 2.15048 | 376 |
| gbrt_lag      | staffed_adult_icu_bed_occupancy |         1 |  15.3556 |  24.5095 | 3.55987 | 1.58243 | 376 |
| gbrt_lag      | staffed_adult_icu_bed_occupancy |         7 |  21.8959 |  32.4102 | 5.84432 | 2.20753 | 376 |
| gbrt_lag      | staffed_adult_icu_bed_occupancy |        14 |  24.8888 |  41.5098 | 6.30786 | 2.5295  | 376 |

## Improvement vs best Day-24 baseline (positive = better)

| model         | target                          |   horizon |    value | baseline_model   |   baseline_value |   improvement |   improvement_pct |
|:--------------|:--------------------------------|----------:|---------:|:-----------------|-----------------:|--------------:|------------------:|
| gbrt_lag      | inpatient_beds_used             |         1 | 178.124  | seasonal_naive_7 |         279.359  |     101.235   |          36.2382  |
| ridge_fourier | inpatient_beds_used             |         1 | 287.303  | seasonal_naive_7 |         279.359  |      -7.94423 |          -2.84373 |
| gbrt_lag      | inpatient_beds_used             |         7 | 261.22   | naive_last       |         252.933  |      -8.28708 |          -3.27639 |
| ridge_fourier | inpatient_beds_used             |         7 | 257.941  | naive_last       |         252.933  |      -5.0074  |          -1.97973 |
| gbrt_lag      | inpatient_beds_used             |        14 | 339.873  | naive_last       |         363.172  |      23.2986  |           6.4153  |
| ridge_fourier | inpatient_beds_used             |        14 | 374.511  | naive_last       |         363.172  |     -11.3393  |          -3.1223  |
| gbrt_lag      | staffed_adult_icu_bed_occupancy |         1 |  24.5095 | seasonal_naive_7 |          34.975  |      10.4655  |          29.9229  |
| ridge_fourier | staffed_adult_icu_bed_occupancy |         1 |  43.9616 | seasonal_naive_7 |          34.975  |      -8.98657 |         -25.6942  |
| gbrt_lag      | staffed_adult_icu_bed_occupancy |         7 |  32.4102 | ewma_opt         |          34.1439 |       1.73363 |           5.07742 |
| ridge_fourier | staffed_adult_icu_bed_occupancy |         7 |  36.6653 | ewma_opt         |          34.1439 |      -2.52137 |          -7.38456 |
| gbrt_lag      | staffed_adult_icu_bed_occupancy |        14 |  41.5098 | naive_last       |          46.4449 |       4.93508 |          10.6257  |
| ridge_fourier | staffed_adult_icu_bed_occupancy |        14 |  54.0412 | naive_last       |          46.4449 |      -7.59629 |         -16.3555  |

## Full Day-25 score table

| model         | target                          |   horizon |      mae |     rmse |     mape |    wape |   n |
|:--------------|:--------------------------------|----------:|---------:|---------:|---------:|--------:|----:|
| gbrt_lag      | inpatient_beds_used             |         1 | 107.579  | 178.124  |  1.80516 | 1.15417 | 376 |
| ridge_fourier | inpatient_beds_used             |         1 | 159.253  | 287.303  |  8.21653 | 1.70856 | 376 |
| ridge_fourier | inpatient_beds_used             |         7 | 167.758  | 257.941  |  6.44276 | 1.76827 | 376 |
| gbrt_lag      | inpatient_beds_used             |         7 | 162.444  | 261.22   |  4.17198 | 1.71226 | 376 |
| gbrt_lag      | inpatient_beds_used             |        14 | 202.865  | 339.873  |  5.62023 | 2.15048 | 376 |
| ridge_fourier | inpatient_beds_used             |        14 | 243.76   | 374.511  | 10.6239  | 2.58398 | 376 |
| gbrt_lag      | staffed_adult_icu_bed_occupancy |         1 |  15.3556 |  24.5095 |  3.55987 | 1.58243 | 376 |
| ridge_fourier | staffed_adult_icu_bed_occupancy |         1 |  30.3162 |  43.9616 | 36.7314  | 3.12416 | 376 |
| gbrt_lag      | staffed_adult_icu_bed_occupancy |         7 |  21.8959 |  32.4102 |  5.84432 | 2.20753 | 376 |
| ridge_fourier | staffed_adult_icu_bed_occupancy |         7 |  26.9952 |  36.6653 | 23.0172  | 2.72164 | 376 |
| gbrt_lag      | staffed_adult_icu_bed_occupancy |        14 |  24.8888 |  41.5098 |  6.30786 | 2.5295  | 376 |
| ridge_fourier | staffed_adult_icu_bed_occupancy |        14 |  37.704  |  54.0412 | 37.8585  | 3.83195 | 376 |
