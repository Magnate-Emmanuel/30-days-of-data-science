from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    con.execute("CREATE SCHEMA IF NOT EXISTS day27;")
    con.execute(
        """CREATE TABLE IF NOT EXISTS day27.runs (
            run_id VARCHAR PRIMARY KEY,
            started_at_utc TIMESTAMP,
            finished_at_utc TIMESTAMP,
            status VARCHAR,
            day26_run_id VARCHAR,
            contract_name VARCHAR,
            recent_days INTEGER,
            baseline_days INTEGER,
            notes VARCHAR
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


def _load_day26_forecasts(con: duckdb.DuckDBPyConnection, run_id: str) -> pd.DataFrame:
    if not _table_exists(con, "day26.quantile_forecasts"):
        raise RuntimeError("day26.quantile_forecasts not found. Run Day 26 first.")
    df = con.execute(
        """SELECT method, model, state, target, cutoff_ds, ds, horizon, q, yhat, y
           FROM day26.quantile_forecasts
           WHERE run_id = ?
        """,
        [run_id],
    ).df()
    if df.empty:
        raise RuntimeError(f"No rows found for day26.quantile_forecasts run_id={run_id}")
    df["cutoff_ds"] = pd.to_datetime(df["cutoff_ds"])
    df["ds"] = pd.to_datetime(df["ds"])
    df["q"] = df["q"].astype(float)
    return df


def _pinball(y: np.ndarray, yhat: np.ndarray, q: float) -> float:
    u = y - yhat
    return float(np.mean(np.maximum(q * u, (q - 1.0) * u)))


def _point_metrics(y: np.ndarray, yhat: np.ndarray) -> Dict[str, float]:
    y = y.astype(float)
    yhat = yhat.astype(float)
    err = yhat - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))

    mask = np.abs(y) > 1e-9
    mape = float(np.mean(np.abs(err[mask] / y[mask])) * 100.0) if mask.any() else float("nan")
    wape = float(np.sum(np.abs(err)) / np.sum(np.abs(y))) * 100.0 if np.sum(np.abs(y)) > 1e-9 else float("nan")
    return {"mae": mae, "rmse": rmse, "mape": mape, "wape": wape, "n": float(len(y))}


def _compute_point_metrics_from_quantiles(f: pd.DataFrame) -> pd.DataFrame:
    qs = sorted(set(f["q"].tolist()))
    q_point = min(qs, key=lambda x: abs(x - 0.5))
    fp = f[f["q"] == q_point].copy()
    out = []
    for (method, model, target, horizon), g in fp.groupby(["method", "model", "target", "horizon"]):
        y = g["y"].to_numpy(dtype=float)
        yhat = g["yhat"].to_numpy(dtype=float)
        m = _point_metrics(y, yhat)
        out.append(
            {
                "method": method,
                "model": model,
                "target": target,
                "horizon": int(horizon),
                "q_point": float(q_point),
                "mae": m["mae"],
                "rmse": m["rmse"],
                "mape": m["mape"],
                "wape": m["wape"],
                "n": int(m["n"]),
            }
        )
    return pd.DataFrame(out).sort_values(["target", "horizon", "method", "model"])


def _compute_interval_metrics(f: pd.DataFrame) -> pd.DataFrame:
    qs = sorted(set(f["q"].tolist()))
    q_lo = max([q for q in qs if q < 0.5], default=None)
    q_hi = min([q for q in qs if q > 0.5], default=None)
    if q_lo is None or q_hi is None:
        raise RuntimeError("Need both a lower and upper quantile (e.g., 0.1 and 0.9) to compute interval metrics.")

    wide = f.pivot_table(
        index=["method", "model", "state", "target", "horizon", "cutoff_ds", "ds"],
        columns="q",
        values="yhat",
        aggfunc="first",
    ).reset_index()

    y = f.groupby(["method", "model", "state", "target", "horizon", "cutoff_ds", "ds"])["y"].first().reset_index()
    wide = wide.merge(y, on=["method", "model", "state", "target", "horizon", "cutoff_ds", "ds"], how="left")
    wide = wide.rename(columns={"y": "y_true"})

    lo = wide[q_lo].to_numpy(dtype=float)
    hi = wide[q_hi].to_numpy(dtype=float)
    ytrue = wide["y_true"].to_numpy(dtype=float)

    within = (ytrue >= lo) & (ytrue <= hi)
    width = hi - lo

    out = []
    for (method, model, target, horizon), _g in wide.groupby(["method", "model", "target", "horizon"]):
        idx = (wide["method"] == method) & (wide["model"] == model) & (wide["target"] == target) & (wide["horizon"] == horizon)
        cov = float(np.mean(within[idx.to_numpy()])) if idx.any() else float("nan")
        mw = float(np.mean(width[idx.to_numpy()])) if idx.any() else float("nan")
        medw = float(np.median(width[idx.to_numpy()])) if idx.any() else float("nan")
        p90w = float(np.quantile(width[idx.to_numpy()], 0.9)) if idx.any() else float("nan")
        out.append(
            {
                "method": method,
                "model": model,
                "target": target,
                "horizon": int(horizon),
                "q_lo": float(q_lo),
                "q_hi": float(q_hi),
                "coverage": cov,
                "mean_width": mw,
                "median_width": medw,
                "p90_width": p90w,
                "n": int(idx.sum()),
            }
        )
    return pd.DataFrame(out).sort_values(["target", "horizon", "method", "model"])


def _compute_pinball(f: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (method, model, target, horizon, q), g in f.groupby(["method", "model", "target", "horizon", "q"]):
        y = g["y"].to_numpy(dtype=float)
        yhat = g["yhat"].to_numpy(dtype=float)
        out.append(
            {
                "method": method,
                "model": model,
                "target": target,
                "horizon": int(horizon),
                "q": float(q),
                "pinball": _pinball(y, yhat, float(q)),
                "n": int(len(g)),
            }
        )
    return pd.DataFrame(out).sort_values(["target", "horizon", "method", "model", "q"])


def _normalize_targets(raw_targets: Any) -> List[str]:
    if raw_targets is None:
        return []
    if isinstance(raw_targets, dict):
        raw_targets = [raw_targets]
    if not isinstance(raw_targets, list):
        return []

    out: List[str] = []
    for t in raw_targets:
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, dict):
            name = t.get("name") or t.get("source_column")
            if name:
                out.append(str(name))
    seen = set()
    norm: List[str] = []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            norm.append(t)
    return norm


def _detect_target_column(cols: List[str], target: str, prefer_ffill_days: int) -> str:
    ff = f"{target}_ffill{prefer_ffill_days}"
    if ff in cols:
        return ff
    if target in cols:
        return target
    candidates = [c for c in cols if c.startswith(f"{target}_ffill")]
    if candidates:
        return sorted(candidates)[0]
    raise RuntimeError(f"Could not find target column for '{target}' in gold.state_features.")


def _series_drift(con: duckdb.DuckDBPyConnection, targets: List[str], recent_days: int, baseline_days: int, prefer_ffill_days: int = 3) -> pd.DataFrame:
    if not _table_exists(con, "gold.state_features"):
        raise RuntimeError("gold.state_features not found. Run Day 23 first.")
    cols = con.execute("PRAGMA table_info('gold.state_features')").df()["name"].tolist()
    tcols = {t: _detect_target_column(cols, t, prefer_ffill_days) for t in targets}

    sel = ["state", "ds"] + [f'"{c}" AS "{t}"' for t, c in tcols.items()]
    df = con.execute("SELECT " + ", ".join(sel) + " FROM gold.state_features ORDER BY state, ds").df()
    df["ds"] = pd.to_datetime(df["ds"])
    max_ds = df["ds"].max()
    recent_start = max_ds - pd.Timedelta(days=recent_days)
    base_start = max_ds - pd.Timedelta(days=recent_days + baseline_days)
    base_end = recent_start

    out_rows = []
    for target in targets:
        for state, g in df.groupby("state"):
            g = g.sort_values("ds")
            base = g[(g["ds"] > base_start) & (g["ds"] <= base_end)]
            recent = g[(g["ds"] > recent_start) & (g["ds"] <= max_ds)]
            yb = base[target].to_numpy(dtype=float)
            yr = recent[target].to_numpy(dtype=float)

            base_missing = float(np.mean(~np.isfinite(yb))) if len(yb) else float("nan")
            recent_missing = float(np.mean(~np.isfinite(yr))) if len(yr) else float("nan")

            yb2 = yb[np.isfinite(yb)]
            yr2 = yr[np.isfinite(yr)]

            mb = float(np.mean(yb2)) if len(yb2) else float("nan")
            mr = float(np.mean(yr2)) if len(yr2) else float("nan")
            sb = float(np.std(yb2)) if len(yb2) else float("nan")

            if len(yb2) < 10 or len(yr2) < 10 or sb <= 1e-9:
                z = float("nan")
                pct = float("nan")
            else:
                z = (mr - mb) / sb
                pct = (mr - mb) / abs(mb) * 100.0 if abs(mb) > 1e-9 else float("nan")

            out_rows.append(
                {
                    "target": target,
                    "state": state,
                    "baseline_mean": mb,
                    "recent_mean": mr,
                    "baseline_std": sb,
                    "z_shift": z,
                    "pct_mean_change": pct,
                    "baseline_missing_rate": base_missing,
                    "recent_missing_rate": recent_missing,
                    "baseline_n": int(len(yb2)),
                    "recent_n": int(len(yr2)),
                }
            )

    out = pd.DataFrame(out_rows)
    out["abs_z_shift"] = out["z_shift"].abs()
    out = out.sort_values(["target", "abs_z_shift"], ascending=[True, False]).drop(columns=["abs_z_shift"])
    return out


def _backtest_drift(f: pd.DataFrame) -> pd.DataFrame:
    qs = sorted(set(f["q"].tolist()))
    q_point = min(qs, key=lambda x: abs(x - 0.5))
    q_lo = max([q for q in qs if q < 0.5], default=None)
    q_hi = min([q for q in qs if q > 0.5], default=None)

    cutoffs = sorted(f["cutoff_ds"].unique())
    if len(cutoffs) < 4:
        return pd.DataFrame()

    mid = len(cutoffs) // 2
    early_set = set(cutoffs[:mid])

    fp = f[f["q"] == q_point].copy()
    fp["period"] = np.where(fp["cutoff_ds"].isin(early_set), "early", "late")

    out_rows = []
    for (method, target, horizon, period), g in fp.groupby(["method", "target", "horizon", "period"]):
        y = g["y"].to_numpy(dtype=float)
        yhat = g["yhat"].to_numpy(dtype=float)
        m = _point_metrics(y, yhat)
        out_rows.append(
            {
                "method": method,
                "target": target,
                "horizon": int(horizon),
                "period": period,
                "mae": m["mae"],
                "rmse": m["rmse"],
                "mape": m["mape"],
                "wape": m["wape"],
                "n": int(m["n"]),
            }
        )

    out = pd.DataFrame(out_rows)

    if q_lo is not None and q_hi is not None:
        sub = f[f["q"].isin([q_lo, q_hi])].copy()
        w = sub.pivot_table(
            index=["method", "state", "target", "horizon", "cutoff_ds", "ds"],
            columns="q",
            values="yhat",
            aggfunc="first",
        ).reset_index()
        y = f.groupby(["method", "state", "target", "horizon", "cutoff_ds", "ds"])["y"].first().reset_index()
        w = w.merge(y, on=["method", "state", "target", "horizon", "cutoff_ds", "ds"], how="left").rename(columns={"y": "y_true"})
        w["period"] = np.where(w["cutoff_ds"].isin(early_set), "early", "late")
        w["within"] = (w[q_lo] <= w["y_true"]) & (w["y_true"] <= w[q_hi])
        cov = w.groupby(["method", "target", "horizon", "period"])["within"].mean().reset_index().rename(columns={"within": "coverage"})
        out = out.merge(cov, on=["method", "target", "horizon", "period"], how="left")

    return out.sort_values(["target", "horizon", "method", "period"])


def _write_report(
    report_dir: Path,
    run_id: str,
    day26_run_id: str,
    contract_name: str,
    point: pd.DataFrame,
    interval: pd.DataFrame,
    pinball: pd.DataFrame,
    drift: pd.DataFrame,
    backtest_drift: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    ensure_dir(report_dir)

    point.to_csv(report_dir / "day27_point_metrics.csv", index=False)
    interval.to_csv(report_dir / "day27_interval_metrics.csv", index=False)
    pinball.to_csv(report_dir / "day27_quantile_pinball.csv", index=False)
    drift.to_csv(report_dir / "day27_series_drift.csv", index=False)
    backtest_drift.to_csv(report_dir / "day27_backtest_drift.csv", index=False)

    md = []
    md.append("# Day 27 — Backtest & monitoring summary\n\n")
    md.append(f"Run ID: `{run_id}`\n\n")
    md.append(f"Day 26 run_id used: `{day26_run_id}`\n\n")
    md.append(f"Contract: `{contract_name}`\n\n")
    md.append("Point metrics use the Day-26 **P50** forecast (closest quantile to 0.5).\n\n")
    md.append("## Point accuracy (P50)\n\n")
    md.append(point.to_markdown(index=False) + "\n\n")
    md.append("## Interval reliability (P10/P90)\n\n")
    md.append(interval.to_markdown(index=False) + "\n\n")
    md.append("## Quantile loss (pinball)\n\n")
    md.append(pinball.to_markdown(index=False) + "\n\n")
    md.append(f"## Series drift checks (recent={args.recent_days} days vs baseline={args.baseline_days} days)\n\n")
    md.append("The table ranks states by absolute standardized mean shift (z_shift) within each target.\n\n")
    md.append(drift.groupby("target").head(15).to_markdown(index=False) + "\n\n")
    if not backtest_drift.empty:
        md.append("## Backtest drift (early vs late cutoffs)\n\n")
        md.append(backtest_drift.to_markdown(index=False) + "\n\n")
    (report_dir / "day27_summary.md").write_text("".join(md), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Day 27: backtest report (point + interval + drift).")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True)
    r.add_argument("--report-dir", type=Path, required=True)
    r.add_argument("--contract-name", type=str, default=None)
    r.add_argument("--day26-run-id", type=str, default=None)
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

    raw_targets = contract.get("targets", None)
    if raw_targets is None:
        raw_targets = (contract.get("forecast", {}) or {}).get("targets", None)
    targets = _normalize_targets(raw_targets)
    if not targets:
        targets = ["inpatient_beds_used", "staffed_adult_icu_bed_occupancy"]

    day26_run_id = _select_day26_run_id(con, args.day26_run_id)

    con.execute(
        "INSERT INTO day27.runs VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
        [
            run_id,
            datetime.now(timezone.utc),
            "running",
            day26_run_id,
            contract_name,
            int(args.recent_days),
            int(args.baseline_days),
            "Day27 evaluation + monitoring",
        ],
    )
    register_run_start(con, run_id, sha, cmdline, notes="Day27 evaluation")

    try:
        f = _load_day26_forecasts(con, day26_run_id)

        point = _compute_point_metrics_from_quantiles(f)
        interval = _compute_interval_metrics(f)
        pinball = _compute_pinball(f)
                # Drift targets should match what we actually forecasted in Day 26.
        # Contracts may include optional targets that are not present in gold.state_features.
        drift_targets = sorted(f["target"].unique().tolist())
        if targets:
            # preserve contract ordering first when applicable
            drift_targets = [t for t in targets if t in drift_targets] + [t for t in drift_targets if t not in targets]

        drift = _series_drift(
            con,
            targets=drift_targets,
            recent_days=int(args.recent_days),
            baseline_days=int(args.baseline_days),
            prefer_ffill_days=int(args.prefer_ffill_days),
        )
        bd = _backtest_drift(f)

        _write_report(
            report_dir=args.report_dir,
            run_id=run_id,
            day26_run_id=day26_run_id,
            contract_name=contract_name,
            point=point,
            interval=interval,
            pinball=pinball,
            drift=drift,
            backtest_drift=bd,
            args=args,
        )

        t = Table(title="Day 27 backtest report")
        t.add_column("metric")
        t.add_column("value", justify="right")
        t.add_row("day26_run_id", day26_run_id)
        t.add_row("targets", ", ".join(drift_targets))
        t.add_row("point_rows", str(len(point)))
        t.add_row("interval_rows", str(len(interval)))
        t.add_row("pinball_rows", str(len(pinball)))
        t.add_row("drift_rows", str(len(drift)))
        console.print(t)

        con.execute(
            "UPDATE day27.runs SET finished_at_utc=?, status=? WHERE run_id=?",
            [datetime.now(timezone.utc), "success", run_id],
        )
        register_run_finish(con, run_id, "success")
        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        con.execute(
            "UPDATE day27.runs SET finished_at_utc=?, status=? WHERE run_id=?",
            [datetime.now(timezone.utc), "failed", run_id],
        )
        register_run_finish(con, run_id, "failed")
        console.print(f"\n[red]ERROR[/red] run_id={run_id}\n{e}")
        return 2
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
