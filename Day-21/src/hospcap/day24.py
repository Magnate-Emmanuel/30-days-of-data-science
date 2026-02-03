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


def _contract_horizons(contract: Dict[str, Any]) -> List[int]:
    f = contract.get("forecast", {}) or {}
    if "horizons" in f and isinstance(f["horizons"], list):
        return [int(x) for x in f["horizons"]]
    if "horizon_days" in f:
        h = int(f["horizon_days"])
        return [1, 7, 14] if h >= 14 else ([1, 7] if h >= 7 else [1])
    return [1, 7, 14]


def _ensure_backtest_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS backtest;")
    con.execute(
        """CREATE TABLE IF NOT EXISTS backtest.runs (
            run_id VARCHAR PRIMARY KEY,
            started_at_utc TIMESTAMP,
            finished_at_utc TIMESTAMP,
            status VARCHAR,
            contract_name VARCHAR,
            targets VARCHAR,
            horizons VARCHAR,
            n_splits INTEGER,
            step_days INTEGER,
            max_horizon INTEGER
        );"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS backtest.forecasts (
            run_id VARCHAR,
            model VARCHAR,
            state VARCHAR,
            target VARCHAR,
            cutoff_ds DATE,
            ds DATE,
            horizon INTEGER,
            yhat DOUBLE,
            y DOUBLE
        );"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS backtest.scores (
            run_id VARCHAR,
            model VARCHAR,
            target VARCHAR,
            horizon INTEGER,
            mae DOUBLE,
            rmse DOUBLE,
            mape DOUBLE,
            wape DOUBLE,
            n INTEGER
        );"""
    )


def _fetch_series(con: duckdb.DuckDBPyConnection, targets: List[str], ffill_days: int) -> pd.DataFrame:
    if not _table_exists(con, "gold.state_features"):
        raise RuntimeError("gold.state_features not found. Run Day 23 first.")
    cols = con.execute("PRAGMA table_info('gold.state_features')").df()["name"].tolist()

    use_cols = ["state", "ds"]
    y_cols = []
    for t in targets:
        ff = f"{t}_ffill{ffill_days}"
        if ff in cols:
            y_cols.append(ff)
        elif t in cols:
            y_cols.append(t)
        else:
            raise RuntimeError(f"Target {t} not found in gold.state_features (checked {ff} and {t}).")
    use_cols += y_cols

    sel = []
    for c in use_cols:
        if c in ("state", "ds"):
            sel.append(c)
        else:
            sel.append(f'"{c}"')
    q = "SELECT " + ", ".join(sel) + " FROM gold.state_features ORDER BY state, ds;"
    df = con.execute(q).df()

    ren = {}
    for t in targets:
        ff = f"{t}_ffill{ffill_days}"
        if ff in df.columns:
            ren[ff] = t
    df = df.rename(columns=ren)
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def _rolling_cutoffs(ds: pd.Series, n_splits: int, step_days: int, max_h: int) -> List[pd.Timestamp]:
    unique = pd.to_datetime(pd.Series(ds.unique())).sort_values()
    max_ds = unique.iloc[-1]
    last_cutoff = max_ds - pd.Timedelta(days=max_h)
    cutoffs = [last_cutoff - pd.Timedelta(days=step_days * i) for i in range(n_splits)][::-1]
    min_ds = unique.iloc[0]
    return [c for c in cutoffs if c >= min_ds]


def _naive_last(train: pd.Series) -> float:
    return float(train.iloc[-1])


def _seasonal_naive(train: pd.Series, target_date: pd.Timestamp, season: int = 7) -> float:
    ref_date = target_date - pd.Timedelta(days=season)
    if ref_date in train.index:
        return float(train.loc[ref_date])
    return float(train.iloc[-1])


def _rolling_mean(train: pd.Series, window: int = 7) -> float:
    w = min(window, len(train))
    return float(train.iloc[-w:].mean())


def _ewma_opt_level(train: np.ndarray) -> Tuple[float, float]:
    y = train.astype(float)
    if len(y) < 3:
        return 0.5, float(y[-1])

    best_alpha = 0.3
    best_sse = float("inf")

    for alpha in np.linspace(0.05, 0.95, 19):
        level = y[0]
        sse = 0.0
        for t in range(1, len(y)):
            yhat = level
            err = y[t] - yhat
            sse += err * err
            level = alpha * y[t] + (1 - alpha) * level
        if sse < best_sse:
            best_sse = sse
            best_alpha = float(alpha)

    level = y[0]
    for t in range(1, len(y)):
        level = best_alpha * y[t] + (1 - best_alpha) * level
    return best_alpha, float(level)


def _metrics(y: np.ndarray, yhat: np.ndarray) -> Dict[str, float]:
    err = yhat - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    denom = np.where(np.abs(y) < 1e-9, np.nan, np.abs(y))
    mape = float(np.nanmean(np.abs(err) / denom) * 100.0)
    wape = float(np.sum(np.abs(err)) / np.sum(np.abs(y)) * 100.0) if np.sum(np.abs(y)) > 0 else float("nan")
    return {"mae": mae, "rmse": rmse, "mape": mape, "wape": wape}


def _backtest_one_series(
    df: pd.DataFrame,
    state: str,
    target: str,
    horizons: List[int],
    n_splits: int,
    step_days: int,
) -> pd.DataFrame:
    s = df[df["state"] == state][["ds", target]].dropna().sort_values("ds")
    if s.empty or len(s) < 60:
        return pd.DataFrame()

    s = s.set_index("ds")[target]
    max_h = max(horizons)
    cutoffs = _rolling_cutoffs(s.index, n_splits=n_splits, step_days=step_days, max_h=max_h)

    rows = []
    for cutoff in cutoffs:
        train = s.loc[:cutoff]
        if len(train) < 28:
            continue

        y_last = _naive_last(train)
        y_roll7 = _rolling_mean(train, window=7)
        alpha, level = _ewma_opt_level(train.values)

        for h in horizons:
            target_date = cutoff + pd.Timedelta(days=h)
            if target_date not in s.index:
                continue
            y_true = float(s.loc[target_date])

            y_seas = _seasonal_naive(train, target_date, season=7)

            rows.append({"model": "naive_last", "state": state, "target": target, "cutoff_ds": cutoff.date(), "ds": target_date.date(), "horizon": h, "yhat": y_last, "y": y_true})
            rows.append({"model": "seasonal_naive_7", "state": state, "target": target, "cutoff_ds": cutoff.date(), "ds": target_date.date(), "horizon": h, "yhat": y_seas, "y": y_true})
            rows.append({"model": "rolling_mean_7", "state": state, "target": target, "cutoff_ds": cutoff.date(), "ds": target_date.date(), "horizon": h, "yhat": y_roll7, "y": y_true})
            rows.append({"model": "ewma_opt", "state": state, "target": target, "cutoff_ds": cutoff.date(), "ds": target_date.date(), "horizon": h, "yhat": level, "y": y_true})

    return pd.DataFrame(rows)


def _aggregate_scores(forecasts: pd.DataFrame) -> pd.DataFrame:
    out_rows = []
    for (model, target, h), g in forecasts.groupby(["model", "target", "horizon"], dropna=False):
        y = g["y"].to_numpy(dtype=float)
        yhat = g["yhat"].to_numpy(dtype=float)
        m = _metrics(y, yhat)
        out_rows.append({"model": model, "target": target, "horizon": int(h), "mae": m["mae"], "rmse": m["rmse"], "mape": m["mape"], "wape": m["wape"], "n": int(len(g))})
    return pd.DataFrame(out_rows).sort_values(["target", "horizon", "rmse"])


def _best_models(scores: pd.DataFrame) -> pd.DataFrame:
    idx = scores.groupby(["target", "horizon"])["rmse"].idxmin()
    best = scores.loc[idx].copy()
    return best.sort_values(["target", "horizon"])


def _write_report(report_dir: Path, run_id: str, scores: pd.DataFrame, best: pd.DataFrame, args: argparse.Namespace) -> None:
    ensure_dir(report_dir)
    scores.to_csv(report_dir / "day24_scores.csv", index=False)
    best.to_csv(report_dir / "day24_best_models.csv", index=False)

    md = []
    md.append("# Day 24 — Baseline backtest summary\n\n")
    md.append(f"Run ID: `{run_id}`\n\n")
    md.append(f"Targets: {', '.join(args.targets)}\n\n")
    md.append(f"Horizons: {', '.join(map(str, args.horizons))}\n\n")
    md.append(f"Splits: n_splits={args.n_splits}, step_days={args.step}\n\n")
    md.append("## Best model by target and horizon (lowest RMSE)\n\n")
    md.append(best.to_markdown(index=False) + "\n\n" if not best.empty else "(no results)\n\n")
    md.append("## Full score table\n\n")
    md.append(scores.to_markdown(index=False) + "\n" if not scores.empty else "(no results)\n")
    (report_dir / "day24_backtest_summary.md").write_text("".join(md), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Day 24: baselines + rolling-origin backtest.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True)
    r.add_argument("--report-dir", type=Path, required=True)
    r.add_argument("--contract-name", type=str, default=None)
    r.add_argument("--targets", nargs="+", default=["inpatient_beds_used", "icu_beds_used"])
    r.add_argument("--horizons", nargs="+", type=int, default=None)
    r.add_argument("--n-splits", type=int, default=8)
    r.add_argument("--step", type=int, default=7)
    r.add_argument("--ffill-days", type=int, default=3)
    args = p.parse_args(argv)

    run_id = str(uuid.uuid4())
    sha = git_sha()
    cmdline = " ".join(sys.argv)

    con = connect(args.db)
    init_meta(con)
    _ensure_backtest_schema(con)

    contract = _load_contract_from_db(con, args.contract_name)
    contract_name = contract.get("name", args.contract_name or "(latest)")

    horizons = args.horizons or _contract_horizons(contract)
    horizons = sorted(set(int(h) for h in horizons))
    max_h = max(horizons)

    # run log
    con.execute(
        "INSERT INTO backtest.runs VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)",
        [run_id, datetime.now(timezone.utc), "running", contract_name, ",".join(args.targets), ",".join(map(str, horizons)), int(args.n_splits), int(args.step), int(max_h)],
    )
    register_run_start(con, run_id, sha, cmdline, notes="Day24 baselines backtest")

    try:
        df = _fetch_series(con, targets=list(args.targets), ffill_days=int(args.ffill_days))
        states = df["state"].unique().tolist()

        all_fc = []
        for target in args.targets:
            for state in states:
                fc = _backtest_one_series(df, state=state, target=target, horizons=horizons, n_splits=int(args.n_splits), step_days=int(args.step))
                if not fc.empty:
                    all_fc.append(fc)

        forecasts = pd.concat(all_fc, ignore_index=True) if all_fc else pd.DataFrame(columns=["model","state","target","cutoff_ds","ds","horizon","yhat","y"])
        scores = _aggregate_scores(forecasts) if not forecasts.empty else pd.DataFrame(columns=["model","target","horizon","mae","rmse","mape","wape","n"])
        best = _best_models(scores) if not scores.empty else pd.DataFrame(columns=scores.columns)

        con.execute("DELETE FROM backtest.forecasts WHERE run_id=?", [run_id])
        con.execute("DELETE FROM backtest.scores WHERE run_id=?", [run_id])

        if not forecasts.empty:
            fc_ins = forecasts.copy()
            fc_ins["run_id"] = run_id
            con.register("fc_df", fc_ins)
            con.execute("INSERT INTO backtest.forecasts SELECT run_id, model, state, target, cutoff_ds, ds, horizon, yhat, y FROM fc_df")
            con.unregister("fc_df")

        if not scores.empty:
            sc_ins = scores.copy()
            sc_ins["run_id"] = run_id
            con.register("sc_df", sc_ins)
            con.execute("INSERT INTO backtest.scores SELECT run_id, model, target, horizon, mae, rmse, mape, wape, n FROM sc_df")
            con.unregister("sc_df")

        _write_report(args.report_dir, run_id, scores, best, args)

        t = Table(title="Day 24 baseline backtest")
        t.add_column("metric")
        t.add_column("value", justify="right")
        t.add_row("contract", str(contract_name))
        t.add_row("targets", ", ".join(args.targets))
        t.add_row("horizons", ", ".join(map(str, horizons)))
        t.add_row("states", str(len(states)))
        t.add_row("forecast_rows", str(len(forecasts)))
        t.add_row("score_rows", str(len(scores)))
        console.print(t)

        con.execute("UPDATE backtest.runs SET finished_at_utc=?, status=? WHERE run_id=?", [datetime.now(timezone.utc), "success", run_id])
        register_run_finish(con, run_id, "success")
        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        con.execute("UPDATE backtest.runs SET finished_at_utc=?, status=? WHERE run_id=?", [datetime.now(timezone.utc), "failed", run_id])
        register_run_finish(con, run_id, "failed")
        console.print(f"\n[red]ERROR[/red] run_id={run_id}\n{e}")
        return 2
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
