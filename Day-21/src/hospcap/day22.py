from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pandas as pd
import yaml
from rich.console import Console
from rich.table import Table

from .duck import connect, init_meta, register_run_finish, register_run_start
from .duck import describe_table  # type: ignore
from .util import git_sha, ensure_dir

console = Console()

# -----------------------------
# Contract loading (from DuckDB)
# -----------------------------
def _load_contract_from_db(con: duckdb.DuckDBPyConnection, contract_name: Optional[str]) -> Dict[str, Any]:
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
        raise RuntimeError(
            "No forecasting contract found in meta.forecast_contracts.\n"
            "Run Day 21 with --contract to register one."
        )

    return yaml.safe_load(row[0])

def _get_quality_thresholds(contract: Dict[str, Any]) -> Tuple[int, int, List[int]]:
    q = contract.get("quality", {}) or {}
    max_missing_run = int(q.get("max_missing_run", 3))
    min_history_days = int(contract.get("forecast", {}).get("min_history_days", q.get("min_history_days", 90)))
    sentinel = q.get("sentinel_missing_values", [-999999])
    sentinel_vals = [int(x) for x in sentinel] if isinstance(sentinel, list) else [int(sentinel)]
    return max_missing_run, min_history_days, sentinel_vals

def _targets_present(con: duckdb.DuckDBPyConnection, table: str, preferred: List[str]) -> List[str]:
    cols = [c for c, _ in describe_table(con, table)]
    return [t for t in preferred if t in cols]

# -----------------------------
# Quality SQL builders
# -----------------------------
def _create_quality_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS quality;")
    con.execute("""

        CREATE TABLE IF NOT EXISTS meta.quality_runs (
            run_id VARCHAR PRIMARY KEY,
            started_at_utc TIMESTAMP,
            finished_at_utc TIMESTAMP,
            status VARCHAR,
            contract_name VARCHAR,
            strict BOOLEAN,
            max_missing_run INTEGER,
            min_history_days INTEGER,
            n_fail_states INTEGER,
            n_warn_states INTEGER
        );

    """)

def _build_state_gaps(con: duckdb.DuckDBPyConnection, source_table: str, run_id: str) -> None:
    con.execute("DROP TABLE IF EXISTS quality.state_gaps;")
    con.execute(f"""

        CREATE TABLE quality.state_gaps AS
        WITH bounds AS (
            SELECT state, MIN(ds) AS min_ds, MAX(ds) AS max_ds
            FROM {source_table}
            GROUP BY 1
        ),
        spine AS (
        SELECT b.state, CAST(t.gs AS DATE) AS ds
            FROM bounds b
            CROSS JOIN generate_series(b.min_ds, b.max_ds, INTERVAL 1 DAY) AS t(gs)
        ),
        obs AS (
            SELECT state, ds FROM {source_table}
        )
        SELECT
            s.state,
            s.ds,
            CASE WHEN o.ds IS NULL THEN 1 ELSE 0 END AS is_missing,
            '{run_id}'::VARCHAR AS _run_id,
            NOW() AS _computed_at
        FROM spine s
        LEFT JOIN obs o
          ON s.state = o.state AND s.ds = o.ds;

    """)

def _build_state_metrics(con: duckdb.DuckDBPyConnection, source_table: str, run_id: str) -> None:
    con.execute("DROP TABLE IF EXISTS quality.state_metrics;")
    con.execute(f"""

        CREATE TABLE quality.state_metrics AS
        WITH bounds AS (
            SELECT state, MIN(ds) AS min_ds, MAX(ds) AS max_ds, COUNT(*) AS n_obs
            FROM {source_table}
            GROUP BY 1
        ),
        gaps AS (
            SELECT state, COUNT(*) AS n_days, SUM(is_missing) AS n_missing
            FROM quality.state_gaps
            GROUP BY 1
        ),
        missing_only AS (
            SELECT
                state,
                ds,
                (ds - CAST(ROW_NUMBER() OVER (PARTITION BY state ORDER BY ds) AS INTEGER)) AS grp
            FROM quality.state_gaps
            WHERE is_missing = 1
        ),
        runs AS (
            SELECT state, grp, COUNT(*) AS run_len
            FROM missing_only
            GROUP BY 1,2
        ),
        max_run AS (
            SELECT state, COALESCE(MAX(run_len), 0) AS max_missing_run
            FROM runs
            GROUP BY 1
        )
        SELECT
            b.state,
            b.min_ds,
            b.max_ds,
            b.n_obs,
            g.n_days,
            g.n_missing,
            ROUND(g.n_missing * 1.0 / NULLIF(g.n_days,0), 6) AS missing_rate,
            mr.max_missing_run,
            DATE_DIFF('day', b.min_ds, b.max_ds) + 1 AS history_days,
            '{run_id}'::VARCHAR AS _run_id,
            NOW() AS _computed_at
        FROM bounds b
        JOIN gaps g USING(state)
        JOIN max_run mr USING(state);

    """)

def _build_failures(con: duckdb.DuckDBPyConnection, run_id: str, max_missing_run: int, min_history_days: int) -> None:
    con.execute("DROP TABLE IF EXISTS quality.failures;")
    con.execute(f"""

        CREATE TABLE quality.failures AS
        SELECT
            state,
            CASE
              WHEN history_days < {min_history_days} THEN 'history_days_below_min'
              WHEN max_missing_run > {max_missing_run} THEN 'max_missing_run_exceeded'
            END AS rule,
            history_days,
            max_missing_run,
            missing_rate,
            '{run_id}'::VARCHAR AS _run_id,
            NOW() AS _computed_at
        FROM quality.state_metrics
        WHERE history_days < {min_history_days}
           OR max_missing_run > {max_missing_run};

    """)

def _build_drift(con: duckdb.DuckDBPyConnection, source_table: str, run_id: str, targets: List[str]) -> None:
    con.execute("DROP TABLE IF EXISTS quality.state_drift;")
    if not targets:
        con.execute("CREATE TABLE quality.state_drift AS SELECT NULL::VARCHAR AS state, NULL::VARCHAR AS target, NULL::DOUBLE AS mean_shift_sd, NULL::DOUBLE AS sd_ratio, NULL::INTEGER AS n_recent, NULL::INTEGER AS n_prior, ?::VARCHAR AS _run_id, NOW() AS _computed_at WHERE FALSE;", [run_id])
        return

    drift_sql_parts = []
    for t in targets:
        drift_sql_parts.append(f"""

            SELECT
                state,
                '{t}' AS target,
                CASE WHEN sd_prior > 0 THEN ABS(mean_recent - mean_prior) / sd_prior ELSE NULL END AS mean_shift_sd,
                CASE WHEN sd_prior > 0 THEN sd_recent / sd_prior ELSE NULL END AS sd_ratio,
                n_recent,
                n_prior,
                '{run_id}'::VARCHAR AS _run_id,
                NOW() AS _computed_at
            FROM (
                WITH bounds AS (
                    SELECT state, MAX(ds) AS max_ds
                    FROM {source_table}
                    GROUP BY 1
                ),
                w AS (
                    SELECT s.state, s.ds, s."{t}" AS y, b.max_ds,
                        CASE
                          WHEN s.ds BETWEEN b.max_ds - INTERVAL 27 DAY AND b.max_ds THEN 'recent'
                          WHEN s.ds BETWEEN b.max_ds - INTERVAL 55 DAY AND b.max_ds - INTERVAL 28 DAY THEN 'prior'
                          ELSE NULL
                        END AS win
                    FROM {source_table} s
                    JOIN bounds b USING(state)
                    WHERE s.ds >= b.max_ds - INTERVAL 55 DAY AND s."{t}" IS NOT NULL
                )
                SELECT
                    state,
                    AVG(CASE WHEN win='recent' THEN y END) AS mean_recent,
                    STDDEV_POP(CASE WHEN win='recent' THEN y END) AS sd_recent,
                    SUM(CASE WHEN win='recent' THEN 1 ELSE 0 END) AS n_recent,
                    AVG(CASE WHEN win='prior' THEN y END) AS mean_prior,
                    STDDEV_POP(CASE WHEN win='prior' THEN y END) AS sd_prior,
                    SUM(CASE WHEN win='prior' THEN 1 ELSE 0 END) AS n_prior
                FROM w
                GROUP BY 1
            )

        """)
    unioned = "\nUNION ALL\n".join(drift_sql_parts)
    con.execute(f"CREATE TABLE quality.state_drift AS {unioned};")

def _build_outliers(con: duckdb.DuckDBPyConnection, source_table: str, run_id: str, targets: List[str]) -> None:
    con.execute("DROP TABLE IF EXISTS quality.outliers;")
    if not targets:
        con.execute("CREATE TABLE quality.outliers AS SELECT NULL::VARCHAR AS state, NULL::DATE AS ds, NULL::VARCHAR AS target, NULL::DOUBLE AS dy, NULL::DOUBLE AS z, ?::VARCHAR AS _run_id, NOW() AS _computed_at WHERE FALSE;", [run_id])
        return

    outlier_parts = []
    for t in targets:
        outlier_parts.append(f"""

            WITH x AS (
                SELECT
                    state,
                    ds,
                    "{t}" AS y,
                    ("{t}" - LAG("{t}") OVER (PARTITION BY state ORDER BY ds)) AS dy
                FROM {source_table}
                WHERE "{t}" IS NOT NULL
            ),
            m AS (
                SELECT state, QUANTILE_CONT(dy, 0.5) AS med_dy
                FROM x
                WHERE dy IS NOT NULL
                GROUP BY 1
            ),
            d AS (
                SELECT x.state, x.ds, x.dy, m.med_dy, ABS(x.dy - m.med_dy) AS absdev
                FROM x
                JOIN m USING(state)
                WHERE x.dy IS NOT NULL
            ),
            mad AS (
                SELECT state, QUANTILE_CONT(absdev, 0.5) AS mad
                FROM d
                GROUP BY 1
            )
            SELECT
                d.state,
                d.ds,
                '{t}' AS target,
                d.dy,
                CASE WHEN mad.mad > 0 THEN d.absdev / (1.4826 * mad.mad) ELSE NULL END AS z,
                '{run_id}'::VARCHAR AS _run_id,
                NOW() AS _computed_at
            FROM d
            JOIN mad USING(state)
            WHERE mad.mad > 0
              AND (d.absdev / (1.4826 * mad.mad)) >= 6

        """)
    unioned = "\nUNION ALL\n".join(outlier_parts)
    con.execute(f"CREATE TABLE quality.outliers AS {unioned};")

# -----------------------------
# Report
# -----------------------------
def _write_report(con: duckdb.DuckDBPyConnection, report_dir: Path, run_id: str, max_missing_run: int, min_history_days: int) -> Path:
    ensure_dir(report_dir)

    metrics = con.execute("""SELECT state, history_days, max_missing_run, missing_rate
                             FROM quality.state_metrics
                             ORDER BY max_missing_run DESC, missing_rate DESC
                             LIMIT 15""").df()

    fails = con.execute("""SELECT state, rule, history_days, max_missing_run, missing_rate
                            FROM quality.failures
                            ORDER BY rule, max_missing_run DESC""").df()

    drift = con.execute("""SELECT state, target, mean_shift_sd, sd_ratio, n_recent, n_prior
                            FROM quality.state_drift
                            WHERE (mean_shift_sd IS NOT NULL AND mean_shift_sd >= 3)
                               OR (sd_ratio IS NOT NULL AND (sd_ratio >= 2 OR sd_ratio <= 0.5))
                            ORDER BY mean_shift_sd DESC NULLS LAST, ABS(sd_ratio-1) DESC NULLS LAST
                            LIMIT 25""").df()

    outliers = con.execute("""SELECT state, ds, target, dy, z
                              FROM quality.outliers
                              ORDER BY z DESC
                              LIMIT 25""").df()

    # Save CSV summary for dashboards
    con.execute("""COPY (SELECT * FROM quality.state_metrics) TO ? (HEADER, DELIMITER ',');""", [str(report_dir / "day22_state_metrics.csv")])

    md_path = report_dir / "day22_quality_report.md"

    def _df_md(df: pd.DataFrame) -> str:
        if df.empty:
            return "(none)\n"
        return df.to_markdown(index=False) + "\n"

    md = []
    md.append("# Day 22 — Quality Report\n\n")
    md.append(f"Run ID: `{run_id}`\n\n")
    md.append(f"Generated (UTC): {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}\n\n")
    md.append("## Gate thresholds\n\n")
    md.append(f"- min_history_days: **{min_history_days}**\n")
    md.append(f"- max_missing_run: **{max_missing_run}**\n\n")
    md.append("## Worst states by missing runs / missing rate (top 15)\n\n")
    md.append(_df_md(metrics))
    md.append("\n## Failing states (hard violations)\n\n")
    md.append(_df_md(fails))
    md.append("\n## Drift warnings (last 28d vs prior 28d)\n\n")
    md.append(_df_md(drift))
    md.append("\n## Outlier day-to-day changes (robust z >= 6)\n\n")
    md.append(_df_md(outliers))

    md_path.write_text("".join(md), encoding="utf-8")
    return md_path

# -----------------------------
# CLI
# -----------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Day 22: time-series quality checks + EDA summaries.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True, help="Path to DuckDB file.")
    r.add_argument("--contract-name", type=str, default=None, help="Contract name in meta.forecast_contracts (defaults to latest).")
    r.add_argument("--report-dir", type=Path, required=True, help="Directory to write Day 22 reports.")
    r.add_argument("--strict", action="store_true", help="Fail the run if any hard gates are violated.")
    r.add_argument("--source-table", type=str, default="silver.hhs_state_timeseries", help="Silver table to validate.")
    r.add_argument("--drift-targets", nargs="+", default=["inpatient_beds_used", "icu_beds_used"], help="Targets to run drift checks on.")
    r.add_argument("--outlier-targets", nargs="+", default=["inpatient_beds_used", "icu_beds_used"], help="Targets to run outlier checks on.")
    args = p.parse_args(argv)

    run_id = str(uuid.uuid4())
    sha = git_sha()
    cmdline = " ".join(sys.argv)

    con = connect(args.db)
    init_meta(con)
    _create_quality_schema(con)

    con.execute(
        "INSERT INTO meta.quality_runs VALUES (?, ?, NULL, ?, ?, ?, NULL, NULL, 0, 0)",
        [run_id, datetime.now(timezone.utc), "running", args.contract_name or "(latest)", bool(args.strict)],
    )

    register_run_start(con, run_id, sha, cmdline, notes="Day22 quality")

    try:
        schema, name = args.source_table.split(".")
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=? AND table_name=?",
            [schema, name],
        ).fetchone()[0]
        if not exists:
            raise RuntimeError(f"Source table {args.source_table} not found. Run Day 21 first.")

        contract = _load_contract_from_db(con, args.contract_name)
        max_missing_run, min_history_days, _sent = _get_quality_thresholds(contract)

        _build_state_gaps(con, args.source_table, run_id)
        _build_state_metrics(con, args.source_table, run_id)
        _build_failures(con, run_id, max_missing_run=max_missing_run, min_history_days=min_history_days)

        drift_targets = _targets_present(con, args.source_table, list(args.drift_targets))
        outlier_targets = _targets_present(con, args.source_table, list(args.outlier_targets))
        _build_drift(con, args.source_table, run_id, drift_targets)
        _build_outliers(con, args.source_table, run_id, outlier_targets)

        n_fail = con.execute("SELECT COUNT(DISTINCT state) FROM quality.failures").fetchone()[0]
        n_warn = con.execute(
            """SELECT COUNT(DISTINCT state) FROM quality.state_drift
                WHERE (mean_shift_sd IS NOT NULL AND mean_shift_sd >= 3)
                   OR (sd_ratio IS NOT NULL AND (sd_ratio >= 2 OR sd_ratio <= 0.5))"""
        ).fetchone()[0]

        con.execute(
            """UPDATE meta.quality_runs
                SET finished_at_utc=?, status=?, max_missing_run=?, min_history_days=?, n_fail_states=?, n_warn_states=?
                WHERE run_id=?""",
            [datetime.now(timezone.utc), "success" if (not args.strict or n_fail == 0) else "failed", max_missing_run, min_history_days, n_fail, n_warn, run_id],
        )

        report_path = _write_report(con, args.report_dir, run_id, max_missing_run, min_history_days)

        t = Table(title="Day 22 quality gates")
        t.add_column("metric")
        t.add_column("value", justify="right")
        t.add_row("contract", str(args.contract_name or "(latest)")) 
        t.add_row("min_history_days", str(min_history_days))
        t.add_row("max_missing_run", str(max_missing_run))
        t.add_row("fail_states", str(n_fail))
        t.add_row("warn_states", str(n_warn))
        console.print(t)
        console.print(f"Report: {report_path}")

        if args.strict and n_fail > 0:
            register_run_finish(con, run_id, "failed")
            console.print("\n[red]FAILED[/red] strict mode: hard quality gates violated.")
            return 1

        register_run_finish(con, run_id, "success")
        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        con.execute("UPDATE meta.quality_runs SET finished_at_utc=?, status=? WHERE run_id=?", [datetime.now(timezone.utc), "error", run_id])
        register_run_finish(con, run_id, "failed")
        console.print(f"\n[red]ERROR[/red] run_id={run_id}\n{e}")
        return 2
    finally:
        con.close()

if __name__ == "__main__":
    raise SystemExit(main())
