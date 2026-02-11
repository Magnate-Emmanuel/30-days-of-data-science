from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd
import yaml
from rich.console import Console
from rich.table import Table

from .duck import connect, init_meta, register_run_finish, register_run_start
from .util import ensure_dir, git_sha

console = Console()


def _table_exists(con: duckdb.DuckDBPyConnection, fq_table: str) -> bool:
    schema, name = fq_table.split(".")
    return (
        con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=? AND table_name=?",
            [schema, name],
        ).fetchone()[0]
        > 0
    )


def _load_contract_from_db(con: duckdb.DuckDBPyConnection, contract_name: Optional[str]) -> Dict[str, Any]:
    if not _table_exists(con, "meta.forecast_contracts"):
        raise RuntimeError("meta.forecast_contracts not found. Run Day 21 with --contract to register one.")
    if contract_name:
        row = con.execute(
            """SELECT yaml_text FROM meta.forecast_contracts
               WHERE contract_name = ?
               ORDER BY registered_at_utc DESC
               LIMIT 1""",
            [contract_name],
        ).fetchone()
    else:
        row = con.execute(
            """SELECT yaml_text FROM meta.forecast_contracts
               ORDER BY registered_at_utc DESC
               LIMIT 1"""
        ).fetchone()
    if not row:
        raise RuntimeError("No forecasting contract found in meta.forecast_contracts.")
    return yaml.safe_load(row[0])


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS day28;")
    con.execute(
        """CREATE TABLE IF NOT EXISTS day28.runs (
            run_id VARCHAR PRIMARY KEY,
            started_at_utc TIMESTAMP,
            finished_at_utc TIMESTAMP,
            status VARCHAR,
            day26_run_id VARCHAR,
            contract_name VARCHAR,
            p_trigger DOUBLE,
            inpatient_util_threshold DOUBLE,
            icu_util_threshold DOUBLE,
            c_false_alarm DOUBLE,
            c_missed DOUBLE,
            notes VARCHAR
        );"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS day28.alerts (
            run_id VARCHAR,
            day26_run_id VARCHAR,
            contract_name VARCHAR,
            method VARCHAR,
            model VARCHAR,
            state VARCHAR,
            target VARCHAR,
            cutoff_ds DATE,
            ds DATE,
            horizon INTEGER,
            q_lo DOUBLE,
            q_med DOUBLE,
            q_hi DOUBLE,
            yhat_lo DOUBLE,
            yhat_med DOUBLE,
            yhat_hi DOUBLE,
            p_exceed DOUBLE,
            threshold_value DOUBLE,
            threshold_type VARCHAR,
            util_threshold DOUBLE,
            denom DOUBLE,
            alert_level VARCHAR,
            is_alert BOOLEAN,
            action VARCHAR,
            y_true DOUBLE,
            exceed_true BOOLEAN,
            cost DOUBLE,
            drift_z DOUBLE,
            drift_flag BOOLEAN,
            created_at_utc TIMESTAMP
        );"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS day28.alert_metrics (
            run_id VARCHAR,
            target VARCHAR,
            horizon INTEGER,
            alert_rate DOUBLE,
            exceed_rate DOUBLE,
            precision DOUBLE,
            recall DOUBLE,
            f1 DOUBLE,
            mean_p_exceed DOUBLE,
            total_cost DOUBLE,
            n INTEGER
        );"""
    )


def _select_day26_run_id(con: duckdb.DuckDBPyConnection, run_id: Optional[str]) -> str:
    if run_id:
        return run_id
    if not _table_exists(con, "day26.runs"):
        raise RuntimeError("day26.runs not found. Run Day 26 first.")
    row = con.execute(
        "SELECT run_id FROM day26.runs WHERE status='success' ORDER BY finished_at_utc DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("No successful Day 26 run found in day26.runs.")
    return str(row[0])


def _load_day26_quantiles(con: duckdb.DuckDBPyConnection, run_id: str, horizons: List[int]) -> pd.DataFrame:
    if not _table_exists(con, "day26.quantile_forecasts"):
        raise RuntimeError("day26.quantile_forecasts not found. Run Day 26 first.")
    df = con.execute(
        """SELECT method, model, state, target, cutoff_ds, ds, horizon, q, yhat, y
           FROM day26.quantile_forecasts
           WHERE run_id = ? AND horizon IN (SELECT * FROM UNNEST(?))
        """,
        [run_id, horizons],
    ).df()
    if df.empty:
        raise RuntimeError(f"No rows found for day26.quantile_forecasts run_id={run_id}")
    df["cutoff_ds"] = pd.to_datetime(df["cutoff_ds"]).dt.date
    df["ds"] = pd.to_datetime(df["ds"]).dt.date
    df["q"] = df["q"].astype(float)
    return df


def _closest_quantile(qs: List[float], target: float) -> float:
    return float(min(qs, key=lambda x: abs(x - target)))


def _rmse(y: np.ndarray, yhat: np.ndarray) -> float:
    err = yhat.astype(float) - y.astype(float)
    return float(np.sqrt(np.mean(err**2))) if len(err) else float("nan")


def _choose_best_model(f: pd.DataFrame, q_med: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Pick the best (method, model) per (target, horizon) using RMSE of the median quantile forecast.
    Then filter f down to the selected models.
    """
    med = f[f["q"] == q_med].copy()
    scores = []
    for (method, model, target, horizon), g in med.groupby(["method", "model", "target", "horizon"]):
        scores.append(
            {
                "method": method,
                "model": model,
                "target": target,
                "horizon": int(horizon),
                "rmse": _rmse(g["y"].to_numpy(), g["yhat"].to_numpy()),
                "n": int(len(g)),
            }
        )
    score_df = pd.DataFrame(scores)
    if score_df.empty:
        raise RuntimeError("Could not compute model selection scores (no median quantile rows).")

    best = score_df.sort_values(["target", "horizon", "rmse"]).groupby(["target", "horizon"]).head(1)
    f2 = f.merge(best[["method", "model", "target", "horizon"]], on=["method", "model", "target", "horizon"], how="inner")
    return f2, best.sort_values(["target", "horizon"])


def _detect_col(cols: List[str], preferred: List[str]) -> Optional[str]:
    for c in preferred:
        if c in cols:
            return c
    return None


def _pull_cutoff_denoms(con: duckdb.DuckDBPyConnection, cutoff_dates: List[pd.Timestamp], states: List[str]) -> pd.DataFrame:
    if not _table_exists(con, "gold.state_features"):
        raise RuntimeError("gold.state_features not found. Run Day 23 first.")
    cols = con.execute("PRAGMA table_info('gold.state_features')").df()["name"].tolist()

    inpatient_beds_col = _detect_col(cols, ["inpatient_beds", "inpatient_beds_ffill3", "inpatient_beds_ffill7"])
    icu_beds_col = _detect_col(cols, ["total_staffed_adult_icu_beds", "total_staffed_adult_icu_beds_ffill3", "adult_icu_bed_utilization_denominator"])

    select_cols = ["state", "ds"]
    if inpatient_beds_col:
        select_cols.append(f'"{inpatient_beds_col}" AS inpatient_beds')
    else:
        select_cols.append("NULL::DOUBLE AS inpatient_beds")
    if icu_beds_col:
        select_cols.append(f'"{icu_beds_col}" AS staffed_adult_icu_beds')
    else:
        select_cols.append("NULL::DOUBLE AS staffed_adult_icu_beds")

    dates = [pd.to_datetime(d).date() for d in cutoff_dates]
    df = con.execute(
        "SELECT " + ", ".join(select_cols) + " FROM gold.state_features WHERE ds IN (SELECT * FROM UNNEST(?)) AND state IN (SELECT * FROM UNNEST(?))",
        [dates, states],
    ).df()
    df["ds"] = pd.to_datetime(df["ds"]).dt.date
    return df.rename(columns={"ds": "cutoff_ds"})


def _compute_abs_thresholds_from_history(con: duckdb.DuckDBPyConnection, states: List[str], target: str, cutoffs: List[pd.Timestamp], baseline_days: int, prefer_ffill_days: int = 3) -> pd.DataFrame:
    cols = con.execute("PRAGMA table_info('gold.state_features')").df()["name"].tolist()
    ff = f"{target}_ffill{prefer_ffill_days}"
    target_col = ff if ff in cols else (target if target in cols else None)
    if target_col is None:
        return pd.DataFrame({"state": [], "cutoff_ds": [], "abs_threshold": []})

    cutoff_dates = [c.date() for c in cutoffs]
    min_cutoff = min(cutoff_dates)
    min_ds = (pd.to_datetime(min_cutoff) - pd.Timedelta(days=baseline_days)).date()

    df = con.execute(
        f"""SELECT state, ds, "{target_col}" AS y
            FROM gold.state_features
            WHERE state IN (SELECT * FROM UNNEST(?))
              AND ds >= ? AND ds <= ?
            ORDER BY state, ds""",
        [states, min_ds, max(cutoff_dates)],
    ).df()
    if df.empty:
        return pd.DataFrame({"state": [], "cutoff_ds": [], "abs_threshold": []})

    df["ds"] = pd.to_datetime(df["ds"]).dt.date
    out = []
    for state, g in df.groupby("state"):
        g = g.sort_values("ds")
        for cutoff in cutoff_dates:
            start = (pd.to_datetime(cutoff) - pd.Timedelta(days=baseline_days)).date()
            window = g[(g["ds"] > start) & (g["ds"] <= cutoff)]["y"].to_numpy(dtype=float)
            window = window[np.isfinite(window)]
            thr = float(np.quantile(window, 0.95)) if len(window) >= 30 else float("nan")
            out.append({"state": state, "cutoff_ds": cutoff, "abs_threshold": thr})
    return pd.DataFrame(out)


def _p_exceed_from_quantiles(y_lo: float, y_hi: float, q_lo: float, q_hi: float, thr: float) -> float:
    if not np.isfinite(thr) or not np.isfinite(y_lo) or not np.isfinite(y_hi):
        return float("nan")
    if y_hi <= y_lo + 1e-9:
        return float(1.0 if thr < y_hi else 0.0)
    if thr <= y_lo:
        return float(1.0 - q_lo)
    if thr >= y_hi:
        return float(1.0 - q_hi)
    cdf = q_lo + (q_hi - q_lo) * (thr - y_lo) / (y_hi - y_lo)
    return float(1.0 - cdf)


def _alert_level(p: float) -> str:
    if not np.isfinite(p):
        return "UNKNOWN"
    if p >= 0.8:
        return "RED"
    if p >= 0.5:
        return "AMBER"
    if p >= 0.2:
        return "YELLOW"
    return "GREEN"


def _action_text(target: str, level: str) -> str:
    t = target.lower()
    if "icu" in t:
        if level == "RED":
            return "Activate ICU surge protocol: mobilize critical care staffing, review transfer agreements, prep overflow/step-down conversion."
        if level == "AMBER":
            return "Prepare ICU surge: pre-stage staffing, confirm supplies, coordinate with regional transfer network."
        if level == "YELLOW":
            return "Monitor ICU pressure: validate reporting, watch trend/seasonality, flag if accelerating."
        return "No ICU action."
    if level == "RED":
        return "Activate inpatient surge plan: add staffing, open overflow beds, accelerate discharges, review elective scheduling."
    if level == "AMBER":
        return "Prepare inpatient surge: schedule extra shifts, coordinate bed management, review discharge throughput."
    if level == "YELLOW":
        return "Monitor inpatient capacity: validate reporting, watch trend/seasonality, flag if accelerating."
    return "No inpatient action."


def _series_drift_z(con: duckdb.DuckDBPyConnection, targets: List[str], recent_days: int, baseline_days: int, prefer_ffill_days: int = 3) -> pd.DataFrame:
    cols = con.execute("PRAGMA table_info('gold.state_features')").df()["name"].tolist()
    chosen = {}
    for t in targets:
        ff = f"{t}_ffill{prefer_ffill_days}"
        if ff in cols:
            chosen[t] = ff
        elif t in cols:
            chosen[t] = t
    if not chosen:
        return pd.DataFrame({"state": [], "target": [], "drift_z": []})

    sel = ["state", "ds"] + [f'"{c}" AS "{t}"' for t, c in chosen.items()]
    df = con.execute("SELECT " + ", ".join(sel) + " FROM gold.state_features ORDER BY state, ds").df()
    df["ds"] = pd.to_datetime(df["ds"])
    max_ds = df["ds"].max()
    recent_start = max_ds - pd.Timedelta(days=recent_days)
    base_start = max_ds - pd.Timedelta(days=recent_days + baseline_days)
    base_end = recent_start

    out = []
    for t in chosen.keys():
        for state, g in df.groupby("state"):
            base = g[(g["ds"] > base_start) & (g["ds"] <= base_end)][t].to_numpy(dtype=float)
            recent = g[(g["ds"] > recent_start) & (g["ds"] <= max_ds)][t].to_numpy(dtype=float)
            base = base[np.isfinite(base)]
            recent = recent[np.isfinite(recent)]
            if len(base) < 30 or len(recent) < 10:
                z = float("nan")
            else:
                sb = float(np.std(base))
                z = float((np.mean(recent) - np.mean(base)) / sb) if sb > 1e-9 else float("nan")
            out.append({"state": state, "target": t, "drift_z": z})
    return pd.DataFrame(out)


def _metrics(alerts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (target, horizon), g in alerts.groupby(["target", "horizon"]):
        n = len(g)
        if n == 0:
            continue
        is_alert = g["is_alert"].astype(bool).to_numpy()
        exceed = g["exceed_true"].astype(bool).to_numpy()
        tp = int(np.sum(is_alert & exceed))
        fp = int(np.sum(is_alert & (~exceed)))
        fn = int(np.sum((~is_alert) & exceed))
        prec = tp / (tp + fp) if (tp + fp) else float("nan")
        rec = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = (2 * prec * rec / (prec + rec)) if np.isfinite(prec) and np.isfinite(rec) and (prec + rec) else float("nan")
        rows.append(
            {
                "target": target,
                "horizon": int(horizon),
                "alert_rate": float(np.mean(is_alert)),
                "exceed_rate": float(np.mean(exceed)),
                "precision": float(prec),
                "recall": float(rec),
                "f1": float(f1),
                "mean_p_exceed": float(np.nanmean(g["p_exceed"].to_numpy(dtype=float))),
                "total_cost": float(np.nansum(g["cost"].to_numpy(dtype=float))),
                "n": int(n),
            }
        )
    return pd.DataFrame(rows).sort_values(["target", "horizon"])


def _write_report(report_dir: Path, run_id: str, day26_run_id: str, model_sel: pd.DataFrame, alerts: pd.DataFrame, metrics: pd.DataFrame, args: argparse.Namespace) -> None:
    ensure_dir(report_dir)
    model_sel.to_csv(report_dir / "day28_model_selection.csv", index=False)
    alerts.to_csv(report_dir / "day28_alerts.csv", index=False)
    metrics.to_csv(report_dir / "day28_metrics.csv", index=False)

    md = []
    md.append("# Day 28 — Decision layer summary\n\n")
    md.append(f"Run ID: `{run_id}`\n\n")
    md.append(f"Day 26 run_id used: `{day26_run_id}`\n\n")
    md.append(f"p_trigger: **{args.p_trigger}**\n\n")
    md.append("## Model selection (per target/horizon)\n\n")
    md.append(model_sel.to_markdown(index=False) + "\n\n")
    md.append("## Alert performance + cost\n\n")
    md.append(metrics.to_markdown(index=False) + "\n\n")
    md.append("## Example alerts (top p_exceed)\n\n")
    top = alerts.sort_values("p_exceed", ascending=False).head(20)
    md.append(top.to_markdown(index=False) + "\n\n")
    (report_dir / "day28_summary.md").write_text("".join(md), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Day 28: surge alerts + staffing/transfer triggers.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True)
    r.add_argument("--report-dir", type=Path, required=True)
    r.add_argument("--contract-name", type=str, default=None)
    r.add_argument("--day26-run-id", type=str, default=None)
    r.add_argument("--horizons", type=int, nargs="+", default=[1, 7, 14])
    r.add_argument("--p-trigger", type=float, default=0.6)
    r.add_argument("--inpatient-util-threshold", type=float, default=0.85)
    r.add_argument("--icu-util-threshold", type=float, default=0.80)
    r.add_argument("--c-false-alarm", type=float, default=1.0)
    r.add_argument("--c-missed", type=float, default=5.0)
    r.add_argument("--recent-days", type=int, default=60)
    r.add_argument("--baseline-days", type=int, default=180)
    r.add_argument("--prefer-ffill-days", type=int, default=3)
    args = p.parse_args(argv)

    run_id = str(uuid.uuid4())
    sha = git_sha()
    cmdline = " ".join(sys.argv)

    con = connect(args.db)
    init_meta(con)
    _ensure_schema(con)

    contract = _load_contract_from_db(con, args.contract_name)
    contract_name = contract.get("name", args.contract_name or "(latest)")

    day26_run_id = _select_day26_run_id(con, args.day26_run_id)

    con.execute(
        "INSERT INTO day28.runs VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            run_id,
            datetime.now(timezone.utc),
            "running",
            day26_run_id,
            contract_name,
            float(args.p_trigger),
            float(args.inpatient_util_threshold),
            float(args.icu_util_threshold),
            float(args.c_false_alarm),
            float(args.c_missed),
            "Day28 decision layer",
        ],
    )
    register_run_start(con, run_id, sha, cmdline, notes="Day28 decision layer")

    try:
        f = _load_day26_quantiles(con, day26_run_id, horizons=list(args.horizons))

        qs = sorted(f["q"].unique().tolist())
        q_lo = _closest_quantile(qs, 0.1)
        q_med = _closest_quantile(qs, 0.5)
        q_hi = _closest_quantile(qs, 0.9)
        if q_lo == q_hi:
            raise RuntimeError("Day 28 needs at least two distinct quantiles (low/high).")

        # Select best model per target/horizon using median quantile RMSE
        f_best, model_sel = _choose_best_model(f, q_med=q_med)

        # Wide forecasts
        wide = f_best.pivot_table(
            index=["method", "model", "state", "target", "cutoff_ds", "ds", "horizon"],
            columns="q",
            values="yhat",
            aggfunc="first",
        ).reset_index()

        y = f_best.groupby(["method", "model", "state", "target", "cutoff_ds", "ds", "horizon"])["y"].first().reset_index()
        wide = wide.merge(y, on=["method", "model", "state", "target", "cutoff_ds", "ds", "horizon"], how="left")

        for q in [q_lo, q_med, q_hi]:
            if q not in wide.columns:
                wide[q] = np.nan

        wide = wide.rename(columns={q_lo: "yhat_lo", q_med: "yhat_med", q_hi: "yhat_hi", "y": "y_true"})
        wide["q_lo"] = float(q_lo)
        wide["q_med"] = float(q_med)
        wide["q_hi"] = float(q_hi)

        # Drift (informational)
        drift = _series_drift_z(
            con,
            targets=sorted(wide["target"].unique().tolist()),
            recent_days=int(args.recent_days),
            baseline_days=int(args.baseline_days),
            prefer_ffill_days=int(args.prefer_ffill_days),
        )

        # Denominators at cutoff
        cutoffs = sorted(set(pd.to_datetime(wide["cutoff_ds"]).tolist()))
        states = sorted(wide["state"].unique().tolist())
        den = _pull_cutoff_denoms(con, cutoff_dates=cutoffs, states=states)
        wide = wide.merge(den, on=["state", "cutoff_ds"], how="left")

        # Fallback abs threshold (q95 history window) when denom missing
        abs_thr_frames = []
        for target in sorted(wide["target"].unique().tolist()):
            abs_thr_frames.append(
                _compute_abs_thresholds_from_history(
                    con,
                    states=states,
                    target=target,
                    cutoffs=[pd.to_datetime(d) for d in sorted(set(wide["cutoff_ds"]))],
                    baseline_days=int(args.baseline_days),
                    prefer_ffill_days=int(args.prefer_ffill_days),
                )
            )
        abs_thr = pd.concat(abs_thr_frames, ignore_index=True) if abs_thr_frames else pd.DataFrame()
        wide = wide.merge(abs_thr, on=["state", "cutoff_ds"], how="left") if not abs_thr.empty else wide.assign(abs_threshold=np.nan)

        def _row_threshold(rw: pd.Series) -> Tuple[float, str, float, float]:
            t = str(rw["target"]).lower()
            if "icu" in t:
                denom = float(rw["staffed_adult_icu_beds"]) if pd.notna(rw.get("staffed_adult_icu_beds")) else float("nan")
                util_thr = float(args.icu_util_threshold)
            else:
                denom = float(rw["inpatient_beds"]) if pd.notna(rw.get("inpatient_beds")) else float("nan")
                util_thr = float(args.inpatient_util_threshold)

            if np.isfinite(denom) and denom > 0:
                return util_thr * denom, "utilization", util_thr, denom

            abs_thr_val = float(rw["abs_threshold"]) if pd.notna(rw.get("abs_threshold")) else float("nan")
            return abs_thr_val, "historical_q95", util_thr, denom

        thr_vals = wide.apply(_row_threshold, axis=1, result_type="expand")
        thr_vals.columns = ["threshold_value", "threshold_type", "util_threshold", "denom"]
        wide = pd.concat([wide, thr_vals], axis=1)

        wide["p_exceed"] = wide.apply(
            lambda r: _p_exceed_from_quantiles(
                float(r["yhat_lo"]),
                float(r["yhat_hi"]),
                float(q_lo),
                float(q_hi),
                float(r["threshold_value"]),
            ),
            axis=1,
        )

        wide["alert_level"] = wide["p_exceed"].apply(_alert_level)
        wide["is_alert"] = wide["p_exceed"] >= float(args.p_trigger)
        wide["action"] = wide.apply(lambda r: _action_text(str(r["target"]), str(r["alert_level"])), axis=1)

        wide["exceed_true"] = wide["y_true"].astype(float) > wide["threshold_value"].astype(float)
        wide["cost"] = np.where(
            wide["is_alert"] & (~wide["exceed_true"]),
            float(args.c_false_alarm),
            np.where((~wide["is_alert"]) & wide["exceed_true"], float(args.c_missed), 0.0),
        )

        wide = wide.merge(drift, on=["state", "target"], how="left") if not drift.empty else wide.assign(drift_z=np.nan)
        wide["drift_flag"] = wide["drift_z"].abs() >= 2.0

        out = wide[
            [
                "method",
                "model",
                "state",
                "target",
                "cutoff_ds",
                "ds",
                "horizon",
                "q_lo",
                "q_med",
                "q_hi",
                "yhat_lo",
                "yhat_med",
                "yhat_hi",
                "p_exceed",
                "threshold_value",
                "threshold_type",
                "util_threshold",
                "denom",
                "alert_level",
                "is_alert",
                "action",
                "y_true",
                "exceed_true",
                "cost",
                "drift_z",
                "drift_flag",
            ]
        ].copy()

        out.insert(0, "contract_name", contract_name)
        out.insert(0, "day26_run_id", day26_run_id)
        out.insert(0, "run_id", run_id)
        out["created_at_utc"] = datetime.now(timezone.utc)

        metrics = _metrics(out)

        con.register("alerts_df", out)
        con.execute("INSERT INTO day28.alerts SELECT * FROM alerts_df")
        con.register("metrics_df", metrics.assign(run_id=run_id))
        con.execute(
            "INSERT INTO day28.alert_metrics SELECT run_id, target, horizon, alert_rate, exceed_rate, precision, recall, f1, mean_p_exceed, total_cost, n FROM metrics_df"
        )

        _write_report(args.report_dir, run_id, day26_run_id, model_sel, out, metrics, args)

        t = Table(title="Day 28 decision layer")
        t.add_column("metric")
        t.add_column("value", justify="right")
        t.add_row("day26_run_id", day26_run_id)
        t.add_row("targets", ", ".join(sorted(out["target"].unique().tolist())))
        t.add_row("alerts_rows", str(len(out)))
        t.add_row("total_cost", f"{float(np.nansum(out['cost'].to_numpy(dtype=float))):.2f}")
        console.print(t)

        con.execute(
            "UPDATE day28.runs SET finished_at_utc=?, status=? WHERE run_id=?",
            [datetime.now(timezone.utc), "success", run_id],
        )
        register_run_finish(con, run_id, "success")
        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        con.execute(
            "UPDATE day28.runs SET finished_at_utc=?, status=? WHERE run_id=?",
            [datetime.now(timezone.utc), "failed", run_id],
        )
        register_run_finish(con, run_id, "failed")
        console.print(f"\n[red]ERROR[/red] run_id={run_id}\n{e}")
        return 2
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
