from __future__ import annotations

import argparse
import math
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


def _contract_horizons(contract: Dict[str, Any]) -> List[int]:
    f = contract.get("forecast", {}) or {}
    if "horizons" in f and isinstance(f["horizons"], list):
        return [int(x) for x in f["horizons"]]
    if "horizon_days" in f:
        h = int(f["horizon_days"])
        return [1, 7, 14] if h >= 14 else ([1, 7] if h >= 7 else [1])
    return [1, 7, 14]


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS day25;")
    con.execute(
        """CREATE TABLE IF NOT EXISTS day25.runs (
            run_id VARCHAR PRIMARY KEY,
            started_at_utc TIMESTAMP,
            finished_at_utc TIMESTAMP,
            status VARCHAR,
            contract_name VARCHAR,
            targets VARCHAR,
            horizons VARCHAR,
            n_splits INTEGER,
            step_days INTEGER,
            baseline_run_id VARCHAR
        );"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS day25.forecasts (
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
        """CREATE TABLE IF NOT EXISTS day25.scores (
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
    con.execute(
        """CREATE TABLE IF NOT EXISTS day25.vs_baseline (
            run_id VARCHAR,
            model VARCHAR,
            target VARCHAR,
            horizon INTEGER,
            metric VARCHAR,
            value DOUBLE,
            baseline_model VARCHAR,
            baseline_value DOUBLE,
            improvement DOUBLE,
            improvement_pct DOUBLE
        );"""
    )


def _latest_baseline_run_id(con: duckdb.DuckDBPyConnection) -> Optional[str]:
    if not _table_exists(con, "backtest.runs") or not _table_exists(con, "backtest.scores"):
        return None
    row = con.execute(
        """SELECT r.run_id
           FROM backtest.runs r
           WHERE r.status='success'
           ORDER BY r.started_at_utc DESC
           LIMIT 1"""
    ).fetchone()
    return row[0] if row else None


def _fetch_features(con: duckdb.DuckDBPyConnection, targets: List[str], ffill_days: int) -> pd.DataFrame:
    if not _table_exists(con, "gold.state_features"):
        raise RuntimeError("gold.state_features not found. Run Day 23 first.")
    cols = con.execute("PRAGMA table_info('gold.state_features')").df()["name"].tolist()

    base_cols = ["state", "ds", "is_missing", "dow", "week_of_year", "month", "year", "is_weekend", "is_holiday"]
    for c in base_cols:
        if c not in cols:
            raise RuntimeError(f"Expected column {c} missing in gold.state_features. Re-run Day 23.")

    keep = set(base_cols)
    for t in targets:
        ff = f"{t}_ffill{ffill_days}"
        if ff in cols:
            keep.add(ff)
        elif t in cols:
            keep.add(t)
        else:
            raise RuntimeError(f"Target {t} not found in gold.state_features (checked {ff} and {t}).")

        patterns = [f"{t}_lag", f"{t}_d", f"{t}_roll", ff]
        for c in cols:
            if any(c.startswith(p) for p in patterns):
                keep.add(c)

    keep_list = ["state", "ds"] + sorted([c for c in keep if c not in ("state", "ds")])
    sel = []
    for c in keep_list:
        if c in ("state", "ds"):
            sel.append(c)
        else:
            sel.append(f'"{c}"')
    q = "SELECT " + ", ".join(sel) + " FROM gold.state_features ORDER BY state, ds;"
    df = con.execute(q).df()
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def _rolling_cutoffs(ds: pd.Series, n_splits: int, step_days: int, max_h: int) -> List[pd.Timestamp]:
    unique = pd.to_datetime(pd.Series(ds.unique())).sort_values()
    max_ds = unique.iloc[-1]
    last_cutoff = max_ds - pd.Timedelta(days=max_h)
    cutoffs = [last_cutoff - pd.Timedelta(days=step_days * i) for i in range(n_splits)][::-1]
    min_ds = unique.iloc[0]
    return [c for c in cutoffs if c >= min_ds]


def _add_labels(df: pd.DataFrame, target: str, horizon: int, ffill_days: int) -> pd.DataFrame:
    ff = f"{target}_ffill{ffill_days}"
    ycol = ff if ff in df.columns else target
    out = df[["state", "ds"]].copy()
    out["y"] = df.groupby("state")[ycol].shift(-horizon)
    return out


def _fourier_terms(t: np.ndarray, period: float, order: int) -> np.ndarray:
    feats = []
    for k in range(1, order + 1):
        feats.append(np.sin(2 * math.pi * k * t / period))
        feats.append(np.cos(2 * math.pi * k * t / period))
    return np.vstack(feats).T


def _metrics(y: np.ndarray, yhat: np.ndarray) -> Dict[str, float]:
    err = yhat - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    denom = np.where(np.abs(y) < 1e-9, np.nan, np.abs(y))
    mape = float(np.nanmean(np.abs(err) / denom) * 100.0)
    wape = float(np.sum(np.abs(err)) / np.sum(np.abs(y)) * 100.0) if np.sum(np.abs(y)) > 0 else float("nan")
    return {"mae": mae, "rmse": rmse, "mape": mape, "wape": wape}


def _build_forecasts_for(
    df: pd.DataFrame,
    target: str,
    horizon: int,
    cutoffs: List[pd.Timestamp],
    ffill_days: int,
    model_kind: str,
) -> List[Dict[str, Any]]:
    try:
        from sklearn.compose import ColumnTransformer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.ensemble import HistGradientBoostingRegressor
    except Exception as e:
        raise RuntimeError("scikit-learn is required for Day 25. Install with: pip install scikit-learn") from e

    labels = _add_labels(df, target=target, horizon=horizon, ffill_days=ffill_days)
    work = df.merge(labels, on=["state", "ds"], how="left")

    hdelta = pd.Timedelta(days=horizon)

    base_numeric = ["is_missing", "dow", "week_of_year", "month", "year", "is_weekend", "is_holiday"]
    feat_cols = [c for c in work.columns if c.startswith(f"{target}_")]
    numeric_cols = sorted(set(base_numeric + feat_cols))
    cat_cols = ["state"]

    min_ds = work["ds"].min()
    work["_t"] = (work["ds"] - min_ds).dt.days.astype(float)

    if model_kind == "ridge_fourier":
        weekly = _fourier_terms(work["_t"].to_numpy(), period=7.0, order=3)
        yearly = _fourier_terms(work["_t"].to_numpy(), period=365.25, order=3)
        wf = pd.DataFrame(weekly, columns=[f"w_{i}" for i in range(weekly.shape[1])], index=work.index)
        yf = pd.DataFrame(yearly, columns=[f"y_{i}" for i in range(yearly.shape[1])], index=work.index)
        work = pd.concat([work, wf, yf], axis=1)
        numeric_cols = sorted(set(numeric_cols + ["_t"] + list(wf.columns) + list(yf.columns)))
        for k in [1, 7, 14]:
            c = f"{target}_lag{k}"
            if c in work.columns and c not in numeric_cols:
                numeric_cols.append(c)

    pre = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
            ("num", Pipeline([("imp", SimpleImputer(strategy="median"))]), numeric_cols),
        ]
    )

    if model_kind == "gbrt_lag":
        model = HistGradientBoostingRegressor(
            max_depth=6,
            learning_rate=0.06,
            max_iter=400,
            random_state=42,
        )
    elif model_kind == "ridge_fourier":
        model = Ridge(alpha=3.0, random_state=42)
    else:
        raise ValueError(f"Unknown model_kind: {model_kind}")

    pipe = Pipeline([("pre", pre), ("model", model)])

    forecasts: List[Dict[str, Any]] = []
    for cutoff in cutoffs:
        # leakage-safe: ds + h <= cutoff  <=>  ds <= cutoff - h
        train_mask = (work["ds"] <= (cutoff - hdelta)) & work["y"].notna()
        test_mask = (work["ds"] == cutoff) & work["y"].notna()

        train = work.loc[train_mask, cat_cols + numeric_cols + ["y"]]
        test = work.loc[test_mask, cat_cols + numeric_cols + ["y", "ds"]]

        if train.empty or test.empty:
            continue

        X_train = train[cat_cols + numeric_cols]
        y_train = train["y"].to_numpy(dtype=float)

        X_test = test[cat_cols + numeric_cols]
        y_true = test["y"].to_numpy(dtype=float)

        pipe.fit(X_train, y_train)
        yhat = pipe.predict(X_test)

        cutoff_ds = pd.to_datetime(cutoff).date()
        target_dates = (pd.to_datetime(test["ds"]) + hdelta).dt.date.to_numpy()

        for i, st in enumerate(test["state"].tolist()):
            forecasts.append(
                {
                    "model": model_kind,
                    "state": st,
                    "target": target,
                    "cutoff_ds": cutoff_ds,
                    "ds": target_dates[i],
                    "horizon": int(horizon),
                    "yhat": float(yhat[i]),
                    "y": float(y_true[i]),
                }
            )
    return forecasts


def _aggregate_scores(forecasts: pd.DataFrame) -> pd.DataFrame:
    out_rows = []
    for (model, target, h), g in forecasts.groupby(["model", "target", "horizon"], dropna=False):
        y = g["y"].to_numpy(dtype=float)
        yhat = g["yhat"].to_numpy(dtype=float)
        m = _metrics(y, yhat)
        out_rows.append(
            {
                "model": model,
                "target": target,
                "horizon": int(h),
                "mae": m["mae"],
                "rmse": m["rmse"],
                "mape": m["mape"],
                "wape": m["wape"],
                "n": int(len(g)),
            }
        )
    return pd.DataFrame(out_rows).sort_values(["target", "horizon", "rmse"])


def _best_models(scores: pd.DataFrame) -> pd.DataFrame:
    idx = scores.groupby(["target", "horizon"])["rmse"].idxmin()
    return scores.loc[idx].copy().sort_values(["target", "horizon"])


def _join_baselines(con: duckdb.DuckDBPyConnection, baseline_run_id: Optional[str]) -> Optional[pd.DataFrame]:
    if not baseline_run_id:
        return None
    if not _table_exists(con, "backtest.scores"):
        return None
    q = """
    SELECT run_id, model, target, horizon, rmse, wape
    FROM backtest.scores
    WHERE run_id = ?
      AND model IN ('naive_last','seasonal_naive_7','rolling_mean_7','ewma_opt')
    """
    df = con.execute(q, [baseline_run_id]).df()
    return df if not df.empty else None


def _build_vs_baseline(scores: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    base_best = base.sort_values(["target", "horizon", "rmse"]).groupby(["target", "horizon"]).head(1)
    base_best = base_best.rename(columns={"model": "baseline_model", "rmse": "baseline_rmse", "wape": "baseline_wape"})
    merged = scores.merge(
        base_best[["target", "horizon", "baseline_model", "baseline_rmse", "baseline_wape"]],
        on=["target", "horizon"],
        how="left",
    )

    out = []
    for _, r in merged.iterrows():
        for metric, bcol in [("rmse", "baseline_rmse"), ("wape", "baseline_wape")]:
            b = float(r[bcol]) if pd.notna(r[bcol]) else float("nan")
            v = float(r[metric])
            imp = b - v if not math.isnan(b) else float("nan")
            imp_pct = (imp / b * 100.0) if (not math.isnan(b) and b != 0) else float("nan")
            out.append(
                {
                    "model": r["model"],
                    "target": r["target"],
                    "horizon": int(r["horizon"]),
                    "metric": metric,
                    "value": v,
                    "baseline_model": r["baseline_model"] if pd.notna(r["baseline_model"]) else None,
                    "baseline_value": b,
                    "improvement": imp,
                    "improvement_pct": imp_pct,
                }
            )
    return pd.DataFrame(out).sort_values(["target", "horizon", "metric", "model"])


def _write_reports(
    report_dir: Path,
    run_id: str,
    scores: pd.DataFrame,
    best: pd.DataFrame,
    vsb: Optional[pd.DataFrame],
    args: argparse.Namespace,
    baseline_run_id: Optional[str],
) -> None:
    ensure_dir(report_dir)
    scores.to_csv(report_dir / "day25_scores.csv", index=False)
    best.to_csv(report_dir / "day25_best_models.csv", index=False)
    if vsb is not None and not vsb.empty:
        vsb.to_csv(report_dir / "day25_vs_baseline.csv", index=False)

    md = []
    md.append("# Day 25 — Main models backtest summary\n\n")
    md.append(f"Run ID: `{run_id}`\n\n")
    md.append(f"Targets: {', '.join(args.targets)}\n\n")
    md.append(f"Horizons: {', '.join(map(str, args.horizons))}\n\n")
    md.append(f"Splits: n_splits={args.n_splits}, step_days={args.step}\n\n")
    md.append(f"Baseline run_id (Day 24): `{baseline_run_id}`\n\n" if baseline_run_id else "Baseline run_id (Day 24): (not found)\n\n")
    md.append("## Best Day-25 model by target and horizon (lowest RMSE)\n\n")
    md.append(best.to_markdown(index=False) + "\n\n" if not best.empty else "(no results)\n\n")
    if vsb is not None and not vsb.empty:
        md.append("## Improvement vs best Day-24 baseline (positive = better)\n\n")
        rmse = vsb[vsb["metric"] == "rmse"].copy()
        show = rmse[["model", "target", "horizon", "value", "baseline_model", "baseline_value", "improvement", "improvement_pct"]]
        md.append(show.to_markdown(index=False) + "\n\n")
    md.append("## Full Day-25 score table\n\n")
    md.append(scores.to_markdown(index=False) + "\n" if not scores.empty else "(no results)\n")
    (report_dir / "day25_summary.md").write_text("".join(md), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Day 25: main models (GBRT + ridge Fourier) with horizon-specific backtesting.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True)
    r.add_argument("--report-dir", type=Path, required=True)
    r.add_argument("--contract-name", type=str, default=None)
    r.add_argument("--targets", nargs="+", default=["inpatient_beds_used", "staffed_adult_icu_bed_occupancy"])
    r.add_argument("--horizons", nargs="+", type=int, default=None)
    r.add_argument("--n-splits", type=int, default=8)
    r.add_argument("--step", type=int, default=7)
    r.add_argument("--ffill-days", type=int, default=3)
    r.add_argument("--models", nargs="+", default=["gbrt_lag", "ridge_fourier"])
    r.add_argument("--baseline-run-id", type=str, default=None)
    args = p.parse_args(argv)

    run_id = str(uuid.uuid4())
    sha = git_sha()
    cmdline = " ".join(sys.argv)

    con = connect(args.db)
    init_meta(con)
    _ensure_schema(con)

    contract = _load_contract_from_db(con, args.contract_name)
    contract_name = contract.get("name", args.contract_name or "(latest)")

    horizons = args.horizons or _contract_horizons(contract)
    horizons = sorted(set(int(h) for h in horizons))
    args.horizons = horizons

    baseline_run_id = args.baseline_run_id or _latest_baseline_run_id(con)

    con.execute(
        "INSERT INTO day25.runs VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)",
        [
            run_id,
            datetime.now(timezone.utc),
            "running",
            contract_name,
            ",".join(args.targets),
            ",".join(map(str, horizons)),
            int(args.n_splits),
            int(args.step),
            baseline_run_id,
        ],
    )
    register_run_start(con, run_id, sha, cmdline, notes="Day25 main models backtest")

    try:
        df = _fetch_features(con, targets=list(args.targets), ffill_days=int(args.ffill_days))
        cutoffs = _rolling_cutoffs(df["ds"], n_splits=int(args.n_splits), step_days=int(args.step), max_h=max(horizons))

        used_models = [m for m in args.models if m in ("gbrt_lag", "ridge_fourier")]
        if not used_models:
            raise RuntimeError(f"No valid models requested. Got {args.models}")

        all_rows: List[Dict[str, Any]] = []
        for target in args.targets:
            for h in horizons:
                for mk in used_models:
                    all_rows.extend(
                        _build_forecasts_for(
                            df=df,
                            target=target,
                            horizon=int(h),
                            cutoffs=cutoffs,
                            ffill_days=int(args.ffill_days),
                            model_kind=mk,
                        )
                    )

        forecasts = pd.DataFrame(all_rows)
        if forecasts.empty:
            raise RuntimeError("No forecasts produced. Check that gold.state_features has the requested targets and enough history.")

        scores = _aggregate_scores(forecasts)
        best = _best_models(scores)

        base = _join_baselines(con, baseline_run_id) if baseline_run_id else None
        vsb = _build_vs_baseline(scores, base) if base is not None and not base.empty else None

        con.execute("DELETE FROM day25.forecasts WHERE run_id=?", [run_id])
        con.execute("DELETE FROM day25.scores WHERE run_id=?", [run_id])
        con.execute("DELETE FROM day25.vs_baseline WHERE run_id=?", [run_id])

        fc_ins = forecasts.copy()
        fc_ins["run_id"] = run_id
        con.register("fc_df", fc_ins)
        con.execute("INSERT INTO day25.forecasts SELECT run_id, model, state, target, cutoff_ds, ds, horizon, yhat, y FROM fc_df")
        con.unregister("fc_df")

        sc_ins = scores.copy()
        sc_ins["run_id"] = run_id
        con.register("sc_df", sc_ins)
        con.execute("INSERT INTO day25.scores SELECT run_id, model, target, horizon, mae, rmse, mape, wape, n FROM sc_df")
        con.unregister("sc_df")

        if vsb is not None and not vsb.empty:
            vb_ins = vsb.copy()
            vb_ins["run_id"] = run_id
            con.register("vb_df", vb_ins)
            con.execute("INSERT INTO day25.vs_baseline SELECT run_id, model, target, horizon, metric, value, baseline_model, baseline_value, improvement, improvement_pct FROM vb_df")
            con.unregister("vb_df")

        _write_reports(args.report_dir, run_id, scores, best, vsb, args, baseline_run_id)

        t = Table(title="Day 25 main-model backtest")
        t.add_column("metric")
        t.add_column("value", justify="right")
        t.add_row("contract", str(contract_name))
        t.add_row("targets", ", ".join(args.targets))
        t.add_row("horizons", ", ".join(map(str, horizons)))
        t.add_row("models", ", ".join(used_models))
        t.add_row("cutoffs", str(len(cutoffs)))
        t.add_row("forecast_rows", str(len(forecasts)))
        t.add_row("score_rows", str(len(scores)))
        console.print(t)

        con.execute("UPDATE day25.runs SET finished_at_utc=?, status=? WHERE run_id=?", [datetime.now(timezone.utc), "success", run_id])
        register_run_finish(con, run_id, "success")
        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        con.execute("UPDATE day25.runs SET finished_at_utc=?, status=? WHERE run_id=?", [datetime.now(timezone.utc), "failed", run_id])
        register_run_finish(con, run_id, "failed")
        console.print(f"\n[red]ERROR[/red] run_id={run_id}\n{e}")
        return 2
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
