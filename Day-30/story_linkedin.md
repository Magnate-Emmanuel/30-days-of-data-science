I just finished the final build in my 30-days-of-data-science sprint: **Hospital capacity forecasting + surge alerting + staffing/transfer triggers**.

This wasn’t a “forecast for forecasting’s sake” project. I treated it as an operations analytics product using HHS Protect hospital capacity time series: build a reproducible pipeline (DuckDB + contracts + quality gates), backtest baselines vs main models, generate **probabilistic** forecasts (prediction intervals), then convert uncertainty into decisions: **P(utilization > threshold)** in 1/7/14 days → alert severity → concrete actions (surge staffing, flex beds, transfer prep, elective scheduling coordination).

Big takeaway: **a point forecast isn’t actionable**. Operations teams need risk, lead time, and explicit tradeoffs between false alarms and late alerts. That’s what makes the output dashboard-ready and usable.

If you work in healthcare ops, forecasting, or applied ML for decision support, I’d love your feedback on the alert design and cost tradeoffs.
