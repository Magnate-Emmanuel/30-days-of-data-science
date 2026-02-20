from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pandas as pd
from rich.console import Console
from rich.table import Table

from .duck import connect, init_meta, register_run_finish, register_run_start
from .util import ensure_dir, git_sha

console = Console()


def _table_exists(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    q = """
    SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema = ? AND table_name = ?
    """
    return con.execute(q, [schema, table]).fetchone()[0] > 0


def _schema_exists(con: duckdb.DuckDBPyConnection, schema: str) -> bool:
    q = "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = ?"
    return con.execute(q, [schema]).fetchone()[0] > 0


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS day30;")
    con.execute(
        """CREATE TABLE IF NOT EXISTS day30.runs (
            run_id VARCHAR PRIMARY KEY,
            started_at_utc TIMESTAMP,
            finished_at_utc TIMESTAMP,
            status VARCHAR,
            db_path VARCHAR,
            contract_name VARCHAR,
            day29_run_id VARCHAR,
            alerts_exported INTEGER,
            notes VARCHAR
        );"""
    )


def _latest_success_day29(con: duckdb.DuckDBPyConnection) -> Optional[str]:
    if not (_schema_exists(con, "day29") and _table_exists(con, "day29", "runs")):
        return None
    row = con.execute(
        """SELECT run_id
           FROM day29.runs
           WHERE status='success'
           ORDER BY finished_at_utc DESC
           LIMIT 1"""
    ).fetchone()
    return row[0] if row else None


def _safe_df(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    try:
        return con.execute(sql).df()
    except Exception:
        return pd.DataFrame()


def _detect_run_ids(con: duckdb.DuckDBPyConnection, day29_run_id: str) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {"day25_run_id": None, "day26_run_id": None, "day27_run_id": None, "day28_run_id": None}
    if not (_schema_exists(con, "day29") and _table_exists(con, "day29", "runs")):
        return out
    row = con.execute(
        """SELECT day25_run_id, day26_run_id, day27_run_id, day28_run_id
           FROM day29.runs WHERE run_id = ?""",
        [day29_run_id],
    ).fetchone()
    if row:
        out["day25_run_id"], out["day26_run_id"], out["day27_run_id"], out["day28_run_id"] = row
    return out


def _export_alerts(con: duckdb.DuckDBPyConnection, report_dir: Path, day28_run_id: Optional[str], limit: Optional[int]) -> int:
    ensure_dir(report_dir)
    if not (_schema_exists(con, "day28") and _table_exists(con, "day28", "alerts")):
        (report_dir / "alerts_dashboard.csv").write_text("", encoding="utf-8")
        return 0

    where = ""
    params: List[Any] = []
    if day28_run_id:
        where = "WHERE run_id = ?"
        params.append(day28_run_id)

    lim = f"LIMIT {int(limit)}" if limit else ""
    df = con.execute(f"SELECT * FROM day28.alerts {where} {lim}", params).df()
    out_path = report_dir / "alerts_dashboard.csv"
    df.to_csv(out_path, index=False)
    return int(len(df))


def _metrics_summary(con: duckdb.DuckDBPyConnection, report_dir: Path, run_ids: Dict[str, Optional[str]]) -> pd.DataFrame:
    rows: List[Tuple[str, Any]] = []

    # Day 25 scores
    if _schema_exists(con, "day25") and _table_exists(con, "day25", "scores"):
        rid = run_ids.get("day25_run_id")
        w = f"WHERE run_id='{rid}'" if rid else ""
        s = _safe_df(con, f"SELECT model, target, horizon, rmse, mae, mape, wape FROM day25.scores {w}")
        if not s.empty:
            best = s.sort_values(["target", "horizon", "rmse"]).groupby(["target", "horizon"]).head(1)
            for _, r in best.iterrows():
                h = int(r["horizon"])
                rows.append((f"best_model:{r['target']}@h{h}", r["model"]))
                rows.append((f"rmse:{r['target']}@h{h}", float(r["rmse"])))
                rows.append((f"mae:{r['target']}@h{h}", float(r["mae"])))

    # Day 27 coverage/drift (if present)
    if _schema_exists(con, "day27") and _table_exists(con, "day27", "interval_coverage"):
        rid = run_ids.get("day27_run_id")
        w = f"WHERE run_id='{rid}'" if rid else ""
        cov = _safe_df(con, f"SELECT target, horizon, coverage_80, coverage_90 FROM day27.interval_coverage {w}")
        if not cov.empty:
            for _, r in cov.iterrows():
                h = int(r["horizon"])
                rows.append((f"coverage80:{r['target']}@h{h}", float(r["coverage_80"])))
                rows.append((f"coverage90:{r['target']}@h{h}", float(r["coverage_90"])))

    if _schema_exists(con, "day27") and _table_exists(con, "day27", "drift"):
        rid = run_ids.get("day27_run_id")
        w = f"WHERE run_id='{rid}'" if rid else ""
        drift = _safe_df(con, f"SELECT COUNT(*) AS n_drift FROM day27.drift {w}")
        if not drift.empty:
            rows.append(("drift_flags_count", int(drift["n_drift"].iloc[0])))

    # Day 28 alert metrics (if present)
    if _schema_exists(con, "day28") and _table_exists(con, "day28", "alert_metrics"):
        rid = run_ids.get("day28_run_id")
        w = f"WHERE run_id='{rid}'" if rid else ""
        m = _safe_df(con, f"SELECT * FROM day28.alert_metrics {w}")
        if not m.empty:
            for col in ["alerts_total", "alerts_red", "alerts_amber", "alerts_yellow", "total_cost"]:
                if col in m.columns:
                    v = m[col].iloc[0]
                    rows.append((col, float(v) if col in ["total_cost"] else int(v)))

    df = pd.DataFrame(rows, columns=["metric", "value"])
    ensure_dir(report_dir)
    df.to_csv(report_dir / "metrics_summary.csv", index=False)
    return df


def _write_final_report(
    report_dir: Path,
    run_id: str,
    db_path: Path,
    contract_name: str,
    day29_run_id: str,
    run_ids: Dict[str, Optional[str]],
    alerts_exported: int,
) -> None:
    ensure_dir(report_dir)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = []
    md.append("# Day 30 — Hospital capacity forecasting + surge alerting (final report)\n\n")
    md.append(f"Generated: {now}\n\n")
    md.append(f"Day 30 run_id: `{run_id}`\n\n")
    md.append(f"Database: `{db_path}`\n\n")
    md.append(f"Contract: `{contract_name}`\n\n")
    md.append(f"Packaged pipeline (Day 29) run_id: `{day29_run_id}`\n\n")

    md.append("## What this system does\n\n")
    md.append(
        "This build treats hospital capacity forecasting as an operations analytics product. "
        "It forecasts utilization for key targets over multiple horizons, quantifies uncertainty, "
        "and produces early-warning alerts with concrete staffing/transfer triggers.\n\n"
    )

    md.append("## Pipeline overview\n\n")
    md.append(
        "The pipeline is contract-driven and reproducible: ingest (Day 21), quality gates (Day 22), "
        "gold feature panel (Day 23), baseline backtests (Day 24), main models (Day 25), "
        "probabilistic forecasts (Day 26), monitoring (Day 27), decision layer alerts (Day 28), "
        "and a single-command runner (Day 29).\n\n"
    )

    md.append("## Linked sub-runs\n\n")
    md.append("| step | run_id |\n|---|---|\n")
    md.append(f"| Day 25 main models | `{run_ids.get('day25_run_id') or ''}` |\n")
    md.append(f"| Day 26 probabilistic | `{run_ids.get('day26_run_id') or ''}` |\n")
    md.append(f"| Day 27 monitoring | `{run_ids.get('day27_run_id') or ''}` |\n")
    md.append(f"| Day 28 alerts | `{run_ids.get('day28_run_id') or ''}` |\n\n")

    md.append("## Outputs\n\n")
    md.append(f"- Dashboard-ready alerts exported: `{alerts_exported}` rows → `alerts_dashboard.csv`\n")
    md.append("- Metrics summary → `metrics_summary.csv`\n\n")

    md.append("## Notes and limitations\n\n")
    md.append(
        "Capacity series can contain reporting gaps and definitional shifts. The project therefore "
        "leans heavily on explicit data-quality gates and monitoring. For production use, you would additionally "
        "maintain facility-level forecasting, incorporate exogenous drivers (weather, outbreaks), and tune thresholds "
        "and costs with local operational leadership.\n"
    )

    (report_dir / "day30_final_report.md").write_text("".join(md), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Day 30: final report + dashboard-ready outputs + story drafts.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True)
    r.add_argument("--report-dir", type=Path, required=True)
    r.add_argument("--contract-name", type=str, default="hospcap_state_daily_v1")
    r.add_argument("--day29-run-id", type=str, default=None)
    r.add_argument("--alerts-limit", type=int, default=None)

    args = ap.parse_args(argv)

    run_id = str(uuid.uuid4())
    sha = git_sha()
    cmdline = " ".join(sys.argv)

    con = connect(args.db)
    try:
        init_meta(con)
        _ensure_schema(con)

        day29_run_id = args.day29_run_id or _latest_success_day29(con)
        if not day29_run_id:
            raise RuntimeError("Could not locate a successful day29 run_id. Run Day 29 first (or pass --day29-run-id).")

        run_ids = _detect_run_ids(con, day29_run_id)

        con.execute(
            "INSERT INTO day30.runs VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
            [run_id, datetime.now(timezone.utc), "running", str(args.db), args.contract_name, day29_run_id, None, "Day30 final report"],
        )
        register_run_start(con, run_id, sha, cmdline, notes="Day30 final report")

        alerts_exported = _export_alerts(con, args.report_dir, run_ids.get("day28_run_id"), args.alerts_limit)
        _metrics_summary(con, args.report_dir, run_ids)
        _write_final_report(args.report_dir, run_id, args.db, args.contract_name, day29_run_id, run_ids, alerts_exported)

        con.execute(
            "UPDATE day30.runs SET finished_at_utc=?, status=?, alerts_exported=? WHERE run_id=?",
            [datetime.now(timezone.utc), "success", int(alerts_exported), run_id],
        )
        register_run_finish(con, run_id, "success")

        t = Table(title="Day 30 finalization")
        t.add_column("metric")
        t.add_column("value", justify="right")
        t.add_row("day29_run_id", str(day29_run_id))
        t.add_row("alerts_exported", str(alerts_exported))
        console.print(t)
        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        try:
            con.execute(
                "UPDATE day30.runs SET finished_at_utc=?, status=? WHERE run_id=?",
                [datetime.now(timezone.utc), "failed", run_id],
            )
            register_run_finish(con, run_id, "failed")
        except Exception:
            pass
        console.print(f"\n[red]ERROR[/red] run_id={run_id}\n{e}")
        return 2
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
