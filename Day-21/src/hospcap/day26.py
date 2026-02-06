from __future__ import annotations

import argparse
import inspect
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
        sql = (
            "SELECT yaml_text FROM meta.forecast_contracts "
            "WHERE contract_name = ? "
            "ORDER BY registered_at_utc DESC "
            "LIMIT 1"
        )
        row = con.execute(sql, [contract_name]).fetchone()
    else:
        sql = "SELECT yaml_text FROM meta.forecast_contracts ORDER BY registered_at_utc DESC LIMIT 1"
        row = con.execute(sql).fetchone()

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
    con.execute("CREATE SCHEMA IF NOT EXISTS day26;")
    con.execute(
        "CREATE TABLE IF NOT EXISTS day26.runs ("
        "run_id VARCHAR PRIMARY KEY,"
        "started_at_utc TIMESTAMP,"
        "finished_at_utc TIMESTAMP,"
        "status VARCHAR,"
        "contract_name VARCHAR,"
        "targets VARCHAR,"
        "horizons VARCHAR,"
        "quantiles VARCHAR,"
        "n_splits INTEGER,"
        "step_days INTEGER,"
        "notes VARCHAR"
        ");"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS day26.quantile_forecasts ("
        "run_id VARCHAR,"
        "method VARCHAR,"
        "model VARCHAR,"
        "state VARCHAR,"
        "target VARCHAR,"
        "cutoff_ds DATE,"
        "ds DATE,"
        "horizon INTEGER,"
        "q DOUBLE,"
        "yhat DOUBLE,"
        "y DOUBLE"
        ");"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS day26.calibration ("
        "run_id VARCHAR,"
        "target VARCHAR,"
        "horizon INTEGER,"
        "method VARCHAR,"
        "coverage_80 DOUBLE,"
        "mean_width_80 DOUBLE,"
        "pinball_q10 DOUBLE,"
        "pinball_q50 DOUBLE,"
        "pinball_q90 DOUBLE,"
        "n INTEGER"
        ");"
    )


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


def _label_series(df: pd.DataFrame, target: str, horizon: int, ffill_days: int) -> pd.Series:
    ff = f"{target}_ffill{ffill_days}"
    ycol = ff if ff in df.columns else target
    return df.groupby("state")[ycol].shift(-horizon)


def _pinball(y: np.ndarray, yhat: np.ndarray, q: float) -> float:
    u = y - yhat
    return float(np.mean(np.maximum(q * u, (q - 1.0) * u)))


def _champion_method(target: str, horizon: int) -> str:
    if target == "inpatient_beds_used" and int(horizon) == 7:
        return "naive_conformal"
    return "gbrt_quantile"


def _fit_predict_quantiles(
    work: pd.DataFrame,
    horizon: int,
    cutoff: pd.Timestamp,
    quantiles: List[float],
    feature_cols: List[str],
) -> Tuple[str, List[Dict[str, Any]]]:
    try:
        from sklearn.compose import ColumnTransformer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder
        from sklearn.impute import SimpleImputer
        from sklearn.ensemble import HistGradientBoostingRegressor, GradientBoostingRegressor
    except Exception as e:
        raise RuntimeError("scikit-learn is required for Day 26. Install with: pip install scikit-learn") from e

    cat_cols = ["state"]
    numeric_cols = [c for c in feature_cols if c != "state"]

    pre = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
            ("num", Pipeline([("imp", SimpleImputer(strategy="median"))]), numeric_cols),
        ]
    )

    supports_quantile_param = "quantile" in inspect.signature(HistGradientBoostingRegressor).parameters

    hdelta = pd.Timedelta(days=horizon)
    train_mask = (work["ds"] <= (cutoff - hdelta)) & work["y"].notna()
    test_mask = (work["ds"] == cutoff) & work["y"].notna()

    train = work.loc[train_mask, feature_cols + ["y"]]
    test = work.loc[test_mask, feature_cols + ["y", "ds"]]
    if train.empty or test.empty:
        return ("gbrt_quantile", [])

    X_train = train[feature_cols]
    y_train = train["y"].to_numpy(dtype=float)
    X_test = test[feature_cols]
    y_true = test["y"].to_numpy(dtype=float)

    rows: List[Dict[str, Any]] = []
    for q in quantiles:
        if supports_quantile_param:
            model = HistGradientBoostingRegressor(
                loss="quantile",
                quantile=float(q),
                max_depth=6,
                learning_rate=0.06,
                max_iter=400,
                random_state=42,
            )
            model_name = "hgb_quantile"
        else:
            model = GradientBoostingRegressor(
                loss="quantile",
                alpha=float(q),
                n_estimators=400,
                learning_rate=0.06,
                max_depth=3,
                random_state=42,
            )
            model_name = "gbr_quantile"

        pipe = Pipeline([("pre", pre), ("model", model)])
        pipe.fit(X_train, y_train)
        yhat = pipe.predict(X_test)

        cutoff_ds = pd.to_datetime(cutoff).date()
        target_dates = (pd.to_datetime(test["ds"]) + hdelta).dt.date.to_numpy()

        for i, st in enumerate(test["state"].tolist()):
            rows.append(
                {
                    "model": model_name,
                    "state": st,
                    "cutoff_ds": cutoff_ds,
                    "ds": target_dates[i],
                    "horizon": int(horizon),
                    "q": float(q),
                    "yhat": float(yhat[i]),
                    "y": float(y_true[i]),
                }
            )
    return ("gbrt_quantile", rows)


def _naive_conformal_quantiles(
    df: pd.DataFrame,
    target: str,
    horizon: int,
    cutoff: pd.Timestamp,
    quantiles: List[float],
    ffill_days: int,
) -> Tuple[str, List[Dict[str, Any]]]:
    hdelta = pd.Timedelta(days=horizon)

    ff = f"{target}_ffill{ffill_days}"
    ycol = ff if ff in df.columns else target

    w = df[["state", "ds", ycol]].copy()
    w["y_future"] = w.groupby("state")[ycol].shift(-horizon)

    calib_mask = (w["ds"] <= (cutoff - hdelta)) & w["y_future"].notna() & w[ycol].notna()
    calib = w.loc[calib_mask].copy()
    if calib.empty:
        return ("naive_conformal", [])

    abs_resid = np.abs((calib["y_future"] - calib[ycol]).to_numpy(dtype=float))

    q_sorted = sorted(set(float(q) for q in quantiles))
    rows: List[Dict[str, Any]] = []

    test_mask = (w["ds"] == cutoff) & w["y_future"].notna() & w[ycol].notna()
    test = w.loc[test_mask, ["state", "ds", ycol, "y_future"]].copy()
    if test.empty:
        return ("naive_conformal", [])

    point = test[ycol].to_numpy(dtype=float)
    y_true = test["y_future"].to_numpy(dtype=float)
    target_dates = (pd.to_datetime(test["ds"]) + hdelta).dt.date.to_numpy()
    cutoff_ds = pd.to_datetime(cutoff).date()

    widths: Dict[float, float] = {}
    for q in q_sorted:
        if abs(q - 0.5) < 1e-9:
            widths[q] = 0.0
        elif q < 0.5:
            central = 1.0 - 2.0 * q
            central = min(max(central, 0.0), 0.999)
            widths[q] = float(np.quantile(abs_resid, central))
        else:
            ql = 1.0 - q
            central = 1.0 - 2.0 * ql
            central = min(max(central, 0.0), 0.999)
            widths[q] = float(np.quantile(abs_resid, central))

    for i, st in enumerate(test["state"].tolist()):
        for q in q_sorted:
            if abs(q - 0.5) < 1e-9:
                yhat = point[i]
            elif q < 0.5:
                yhat = point[i] - widths[q]
            else:
                yhat = point[i] + widths[q]
            rows.append(
                {
                    "model": "naive_last",
                    "state": st,
                    "cutoff_ds": cutoff_ds,
                    "ds": target_dates[i],
                    "horizon": int(horizon),
                    "q": float(q),
                    "yhat": float(yhat),
                    "y": float(y_true[i]),
                }
            )

    return ("naive_conformal", rows)


def _compute_calibration(forecasts: pd.DataFrame, quantiles: List[float]) -> pd.DataFrame:
    qs = sorted(set(float(q) for q in quantiles))
    q_lo = max([q for q in qs if q < 0.5], default=None)
    q_hi = min([q for q in qs if q > 0.5], default=None)
    if q_lo is None or q_hi is None:
        raise RuntimeError("Need both a lower and upper quantile (e.g., 0.1 and 0.9) to compute interval coverage/width.")

    wide = forecasts.pivot_table(
        index=["method", "model", "state", "target", "horizon", "cutoff_ds", "ds"],
        columns="q",
        values="yhat",
        aggfunc="first",
    ).reset_index()

    y = forecasts.groupby(["method", "model", "state", "target", "horizon", "cutoff_ds", "ds"])["y"].first().reset_index()
    wide = wide.merge(y, on=["method", "model", "state", "target", "horizon", "cutoff_ds", "ds"], how="left")
    wide = wide.rename(columns={"y": "y_true"})

    lo = wide[q_lo].to_numpy(dtype=float)
    hi = wide[q_hi].to_numpy(dtype=float)
    ytrue = wide["y_true"].to_numpy(dtype=float)

    within = (ytrue >= lo) & (ytrue <= hi)
    width = (hi - lo)

    out = []
    for (target, horizon, method), _g in wide.groupby(["target", "horizon", "method"]):
        g2 = forecasts[(forecasts["target"] == target) & (forecasts["horizon"] == horizon) & (forecasts["method"] == method)]
        yv = g2["y"].to_numpy(dtype=float)

        p10 = g2[g2["q"] == q_lo]["yhat"].to_numpy(dtype=float)
        p50 = g2[g2["q"] == (0.5 if 0.5 in qs else q_lo)]["yhat"].to_numpy(dtype=float)
        p90 = g2[g2["q"] == q_hi]["yhat"].to_numpy(dtype=float)

        pb10 = _pinball(yv, p10, q_lo) if len(p10) == len(yv) else float("nan")
        pb50 = _pinball(yv, p50, 0.5 if 0.5 in qs else q_lo) if len(p50) == len(yv) else float("nan")
        pb90 = _pinball(yv, p90, q_hi) if len(p90) == len(yv) else float("nan")

        idx = (wide["target"] == target) & (wide["horizon"] == horizon) & (wide["method"] == method)
        cov = float(np.mean(within[idx.to_numpy()])) if idx.any() else float("nan")
        mw = float(np.mean(width[idx.to_numpy()])) if idx.any() else float("nan")
        n = int(idx.sum())
        out.append(
            {
                "target": target,
                "horizon": int(horizon),
                "method": method,
                "coverage_80": cov,
                "mean_width_80": mw,
                "pinball_q10": pb10,
                "pinball_q50": pb50,
                "pinball_q90": pb90,
                "n": n,
            }
        )
    return pd.DataFrame(out).sort_values(["target", "horizon", "method"])


def _write_reports(report_dir: Path, run_id: str, calib: pd.DataFrame, forecasts: pd.DataFrame, args: argparse.Namespace) -> None:
    ensure_dir(report_dir)
    calib.to_csv(report_dir / "day26_calibration.csv", index=False)
    sample = forecasts.sort_values(["target", "horizon", "cutoff_ds", "state", "q"]).head(200)
    sample.to_csv(report_dir / "day26_forecast_samples.csv", index=False)

    md = []
    md.append("# Day 26 — Probabilistic forecast summary\n\n")
    md.append(f"Run ID: `{run_id}`\n\n")
    md.append(f"Targets: {', '.join(args.targets)}\n\n")
    md.append(f"Horizons: {', '.join(map(str, args.horizons))}\n\n")
    md.append(f"Quantiles: {', '.join(map(str, args.quantiles))}\n\n")
    md.append(f"Splits: n_splits={args.n_splits}, step_days={args.step}\n\n")
    md.append("## Champion method policy\n\n")
    md.append("- inpatient_beds_used @ h=7: naive_conformal (baseline champion from Day 25)\n")
    md.append("- all other target/horizon: gbrt_quantile\n\n")
    md.append("## Calibration (interval coverage + width; lower is better for pinball)\n\n")
    md.append(calib.to_markdown(index=False) + "\n\n")
    md.append("Notes:\n")
    md.append("- coverage_80 is empirical coverage of [P10, P90]. Ideal ≈ 0.80.\n")
    md.append("- mean_width_80 is average (P90 − P10); smaller is sharper but should not under-cover.\n")
    md.append("- pinball losses summarize quantile accuracy (lower is better).\n")
    (report_dir / "day26_summary.md").write_text("".join(md), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Day 26: probabilistic forecasts (quantiles + conformal intervals).")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True)
    r.add_argument("--report-dir", type=Path, required=True)
    r.add_argument("--contract-name", type=str, default=None)
    r.add_argument("--targets", nargs="+", default=["inpatient_beds_used", "staffed_adult_icu_bed_occupancy"])
    r.add_argument("--horizons", nargs="+", type=int, default=None)
    r.add_argument("--quantiles", nargs="+", type=float, default=[0.1, 0.5, 0.9])
    r.add_argument("--n-splits", type=int, default=8)
    r.add_argument("--step", type=int, default=7)
    r.add_argument("--ffill-days", type=int, default=3)
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

    qs = sorted(set(float(q) for q in args.quantiles))
    args.quantiles = qs

    con.execute(
        "INSERT INTO day26.runs VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            run_id,
            datetime.now(timezone.utc),
            "running",
            contract_name,
            ",".join(args.targets),
            ",".join(map(str, horizons)),
            ",".join(map(lambda x: f"{x:g}", qs)),
            int(args.n_splits),
            int(args.step),
            "Day26 probabilistic forecasts (GBRT quantiles + conformal for inpatient h=7)",
        ],
    )
    register_run_start(con, run_id, sha, cmdline, notes="Day26 probabilistic forecasts")

    try:
        df = _fetch_features(con, targets=list(args.targets), ffill_days=int(args.ffill_days))
        cutoffs = _rolling_cutoffs(df["ds"], n_splits=int(args.n_splits), step_days=int(args.step), max_h=max(horizons))

        all_rows: List[Dict[str, Any]] = []

        for target in args.targets:
            for h in horizons:
                method = _champion_method(target, int(h))

                work = df.copy()
                work["y"] = _label_series(work, target=target, horizon=int(h), ffill_days=int(args.ffill_days))

                base_numeric = ["is_missing", "dow", "week_of_year", "month", "year", "is_weekend", "is_holiday"]
                feat_cols = [c for c in work.columns if c.startswith(f"{target}_")]
                feature_cols = ["state"] + sorted(set(base_numeric + feat_cols))

                if method == "gbrt_quantile":
                    for cutoff in cutoffs:
                        _mname, rows = _fit_predict_quantiles(
                            work=work,
                            horizon=int(h),
                            cutoff=cutoff,
                            quantiles=qs,
                            feature_cols=feature_cols,
                        )
                        for rr in rows:
                            rr.update({"method": "gbrt_quantile", "target": target})
                        all_rows.extend(rows)

                elif method == "naive_conformal":
                    for cutoff in cutoffs:
                        _mname, rows = _naive_conformal_quantiles(
                            df=df,
                            target=target,
                            horizon=int(h),
                            cutoff=cutoff,
                            quantiles=qs,
                            ffill_days=int(args.ffill_days),
                        )
                        for rr in rows:
                            rr.update({"method": "naive_conformal", "target": target})
                        all_rows.extend(rows)
                else:
                    raise RuntimeError(f"Unknown method: {method}")

        forecasts = pd.DataFrame(all_rows)
        if forecasts.empty:
            raise RuntimeError("No probabilistic forecasts produced. Check targets/horizons and gold.state_features content.")

        calib = _compute_calibration(forecasts, qs)

        con.execute("DELETE FROM day26.quantile_forecasts WHERE run_id=?", [run_id])
        con.execute("DELETE FROM day26.calibration WHERE run_id=?", [run_id])

        ins = forecasts.copy()
        ins["run_id"] = run_id
        ins = ins[["run_id", "method", "model", "state", "target", "cutoff_ds", "ds", "horizon", "q", "yhat", "y"]]
        con.register("q_df", ins)
        con.execute(
            "INSERT INTO day26.quantile_forecasts "
            "SELECT run_id, method, model, state, target, cutoff_ds, ds, horizon, q, yhat, y FROM q_df"
        )
        con.unregister("q_df")

        ins2 = calib.copy()
        ins2["run_id"] = run_id
        ins2 = ins2[["run_id", "target", "horizon", "method", "coverage_80", "mean_width_80", "pinball_q10", "pinball_q50", "pinball_q90", "n"]]
        con.register("c_df", ins2)
        con.execute(
            "INSERT INTO day26.calibration "
            "SELECT run_id, target, horizon, method, coverage_80, mean_width_80, pinball_q10, pinball_q50, pinball_q90, n FROM c_df"
        )
        con.unregister("c_df")

        _write_reports(args.report_dir, run_id, calib, forecasts, args)

        t = Table(title="Day 26 probabilistic forecasts")
        t.add_column("metric")
        t.add_column("value", justify="right")
        t.add_row("contract", str(contract_name))
        t.add_row("targets", ", ".join(args.targets))
        t.add_row("horizons", ", ".join(map(str, horizons)))
        t.add_row("quantiles", ", ".join(map(lambda x: f"{x:g}", qs)))
        t.add_row("cutoffs", str(len(cutoffs)))
        t.add_row("rows", str(len(forecasts)))
        t.add_row("calib_rows", str(len(calib)))
        console.print(t)

        con.execute(
            "UPDATE day26.runs SET finished_at_utc=?, status=? WHERE run_id=?",
            [datetime.now(timezone.utc), "success", run_id],
        )
        register_run_finish(con, run_id, "success")
        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        con.execute(
            "UPDATE day26.runs SET finished_at_utc=?, status=? WHERE run_id=?",
            [datetime.now(timezone.utc), "failed", run_id],
        )
        register_run_finish(con, run_id, "failed")
        console.print(f"\n[red]ERROR[/red] run_id={run_id}\n{e}")
        return 2
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
