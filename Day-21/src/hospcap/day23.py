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
from pandas.tseries.holiday import USFederalHolidayCalendar
from rich.console import Console
from rich.table import Table

from .duck import connect, init_meta, register_run_finish, register_run_start
from .duck import describe_table  # type: ignore
from .util import ensure_dir, git_sha

console = Console()


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_exists(con: duckdb.DuckDBPyConnection, fq_table: str) -> bool:
    schema, name = fq_table.split(".")
    return (
        con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=? AND table_name=?",
            [schema, name],
        ).fetchone()[0]
        > 0
    )


def _latest_quality_run_id(con: duckdb.DuckDBPyConnection) -> str:
    if not _table_exists(con, "meta.quality_runs"):
        raise RuntimeError("meta.quality_runs not found. Run Day 22 first.")
    row = con.execute(
        "SELECT run_id FROM meta.quality_runs ORDER BY started_at_utc DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("No rows in meta.quality_runs. Run Day 22 first.")
    return row[0]


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


def _get_thresholds(contract: Dict[str, Any]) -> Tuple[int, int]:
    q = contract.get("quality", {}) or {}
    max_missing_run = int(q.get("max_missing_run", 3))
    min_history_days = int(contract.get("forecast", {}).get("min_history_days", q.get("min_history_days", 180)))
    return max_missing_run, min_history_days


def _dedup_source(con: duckdb.DuckDBPyConnection, source_table: str) -> str:
    # Deduplicate on (state, ds) using most recent _ingested_at; protects against multiple Day-21 runs.
    tmp = "tmp_state_src"
    con.execute(f"DROP TABLE IF EXISTS {tmp};")
    con.execute(
        f"""        CREATE TEMP TABLE {tmp} AS
        SELECT * FROM (
            SELECT
                *,
                ROW_NUMBER() OVER (PARTITION BY state, ds ORDER BY {_q('_ingested_at')} DESC) AS rn
            FROM {source_table}
        )
        WHERE rn = 1;        """
    )
    return tmp


def _build_cohort(con: duckdb.DuckDBPyConnection, source_table: str, quality_run_id: str) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS gold;")
    con.execute("DROP TABLE IF EXISTS gold.state_cohort;")

    if not _table_exists(con, "quality.failures"):
        raise RuntimeError("quality.failures not found. Run Day 22 first.")

    con.execute(
        f"""        CREATE TABLE gold.state_cohort AS
        WITH all_states AS (
            SELECT DISTINCT state FROM {source_table}
        ),
        fails AS (
            SELECT DISTINCT state,
                   STRING_AGG(DISTINCT rule, ', ') AS fail_rules
            FROM quality.failures
            WHERE {_q('_run_id')} = '{quality_run_id}'
            GROUP BY 1
        )
        SELECT
            a.state,
            CASE WHEN f.state IS NULL THEN 1 ELSE 0 END AS is_eligible,
            f.fail_rules,
            '{quality_run_id}'::VARCHAR AS quality_run_id,
            NOW() AS _built_at
        FROM all_states a
        LEFT JOIN fails f USING(state);        """
    )


def _build_daily_panel(con: duckdb.DuckDBPyConnection, src: str, quality_run_id: str) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS gold;")
    con.execute("DROP TABLE IF EXISTS gold.state_daily_panel;")

    con.execute(
        f"""        CREATE TABLE gold.state_daily_panel AS
        WITH eligible AS (
            SELECT state FROM gold.state_cohort WHERE is_eligible = 1
        ),
        bounds AS (
            SELECT s.state, MIN(ds) AS min_ds, MAX(ds) AS max_ds
            FROM {src} s
            JOIN eligible e USING(state)
            GROUP BY 1
        ),
        spine AS (
            SELECT b.state, CAST(t.gs AS DATE) AS ds
            FROM bounds b
            CROSS JOIN generate_series(b.min_ds, b.max_ds, INTERVAL 1 DAY) AS t(gs)
        ),
        obs AS (
            SELECT * FROM {src}
        )
        SELECT
            sp.state,
            sp.ds,
            CASE WHEN o.ds IS NULL THEN 1 ELSE 0 END AS is_missing,
            '{quality_run_id}'::VARCHAR AS quality_run_id,
            o.*
        FROM spine sp
        LEFT JOIN obs o
          ON sp.state = o.state AND sp.ds = o.ds;        """
    )


def _build_holidays(con: duckdb.DuckDBPyConnection) -> None:
    rng = con.execute("SELECT MIN(ds), MAX(ds) FROM gold.state_daily_panel").fetchone()
    if not rng or rng[0] is None or rng[1] is None:
        raise RuntimeError("gold.state_daily_panel has no date bounds.")
    start, end = pd.to_datetime(rng[0]), pd.to_datetime(rng[1])

    cal = USFederalHolidayCalendar()
    hol = cal.holidays(start=start, end=end)
    df = pd.DataFrame({"ds": pd.to_datetime(hol).date})

    con.execute("DROP TABLE IF EXISTS gold.us_federal_holidays;")
    con.execute("CREATE TABLE gold.us_federal_holidays (ds DATE);")
    if len(df) > 0:
        con.register("hol_df", df)
        con.execute("INSERT INTO gold.us_federal_holidays SELECT CAST(ds AS DATE) FROM hol_df;")
        con.unregister("hol_df")


def _available_cols(con: duckdb.DuckDBPyConnection, table: str) -> List[str]:
    return [c for c, _ in describe_table(con, table)]


def _build_features(con: duckdb.DuckDBPyConnection, targets: List[str], max_ffill_days: int) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS gold;")
    con.execute("DROP TABLE IF EXISTS gold.state_features;")

    cols = _available_cols(con, "gold.state_daily_panel")
    present = [t for t in targets if t in cols]
    if not present:
        raise RuntimeError(f"None of the requested targets are present. Requested={targets}.")

    # Base SELECT: calendar + holiday + raw targets + forward-fill (<= max_ffill_days)
    cal_cols = [
        "EXTRACT('dow' FROM p.ds) AS dow",
        "EXTRACT('week' FROM p.ds) AS week_of_year",
        "EXTRACT('month' FROM p.ds) AS month",
        "EXTRACT('year' FROM p.ds) AS year",
        "CASE WHEN EXTRACT('dow' FROM p.ds) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend",
        "CASE WHEN h.ds IS NULL THEN 0 ELSE 1 END AS is_holiday",
    ]


    ffill_exprs: List[str] = []
    for t in present:
        lag_terms = [
            f"LAG({_q(t)}, {k}) OVER (PARTITION BY p.state ORDER BY p.ds)"
            for k in range(1, max_ffill_days + 1)
        ]
        ffill_exprs.append(
            f"COALESCE({_q(t)}, {', '.join(lag_terms)}) AS {_q(f'{t}_ffill{max_ffill_days}')}"
        )

    base_select = [
        "p.state",
        "p.ds",
        "p.is_missing",
        *cal_cols,
        *[_q(t) for t in present],
        *ffill_exprs,
    ]

    # Feature SELECT: lags/rolls computed from the ffill column (now available from base CTE)
    feat_exprs: List[str] = []
    for t in present:
        ff = _q(f"{t}_ffill{max_ffill_days}")
        feat_exprs.extend(
            [
                f"LAG({ff}, 1)  OVER (PARTITION BY state ORDER BY ds) AS {_q(f'{t}_lag1')}",
                f"LAG({ff}, 7)  OVER (PARTITION BY state ORDER BY ds) AS {_q(f'{t}_lag7')}",
                f"LAG({ff}, 14) OVER (PARTITION BY state ORDER BY ds) AS {_q(f'{t}_lag14')}",
                f"LAG({ff}, 21) OVER (PARTITION BY state ORDER BY ds) AS {_q(f'{t}_lag21')}",
                f"({ff} - LAG({ff}, 1) OVER (PARTITION BY state ORDER BY ds)) AS {_q(f'{t}_d1')}",
                f"({ff} - LAG({ff}, 7) OVER (PARTITION BY state ORDER BY ds)) AS {_q(f'{t}_d7')}",
                f"AVG({ff}) OVER (PARTITION BY state ORDER BY ds ROWS BETWEEN 6  PRECEDING AND CURRENT ROW) AS {_q(f'{t}_roll7_mean')}",
                f"AVG({ff}) OVER (PARTITION BY state ORDER BY ds ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS {_q(f'{t}_roll14_mean')}",
                f"AVG({ff}) OVER (PARTITION BY state ORDER BY ds ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS {_q(f'{t}_roll28_mean')}",
                f"STDDEV_POP({ff}) OVER (PARTITION BY state ORDER BY ds ROWS BETWEEN 6  PRECEDING AND CURRENT ROW) AS {_q(f'{t}_roll7_sd')}",
                f"STDDEV_POP({ff}) OVER (PARTITION BY state ORDER BY ds ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS {_q(f'{t}_roll14_sd')}",
                f"STDDEV_POP({ff}) OVER (PARTITION BY state ORDER BY ds ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS {_q(f'{t}_roll28_sd')}",
                f"MAX({ff}) OVER (PARTITION BY state ORDER BY ds ROWS BETWEEN 6  PRECEDING AND CURRENT ROW) AS {_q(f'{t}_roll7_max')}",
                f"MAX({ff}) OVER (PARTITION BY state ORDER BY ds ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS {_q(f'{t}_roll14_max')}",
                f"MAX({ff}) OVER (PARTITION BY state ORDER BY ds ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS {_q(f'{t}_roll28_max')}",
            ]
        )

    sql = f"""
    CREATE TABLE gold.state_features AS
    WITH base AS (
        SELECT
            {",\n            ".join(base_select)}
        FROM gold.state_daily_panel p
        LEFT JOIN gold.us_federal_holidays h
          ON p.ds = h.ds
    )
    SELECT
        base.*,
        {",\n        ".join(feat_exprs)}
    FROM base;
    """
    con.execute(sql)



def _build_model_frame(con: duckdb.DuckDBPyConnection, targets: List[str], max_ffill_days: int) -> None:
    con.execute("DROP TABLE IF EXISTS gold.model_frame;")

    cols = _available_cols(con, "gold.state_features")

    required_cols = []
    for t in targets:
        ff = t + "_ffill" + str(max_ffill_days)
        lag21 = t + "_lag21"
        if ff in cols and lag21 in cols:
            required_cols.extend([_q(ff), _q(lag21)])

    if not required_cols:
        raise RuntimeError("Expected ffill/lag columns not found in gold.state_features.")

    where = " AND ".join([f"{c} IS NOT NULL" for c in required_cols])

    con.execute(
        f"""        CREATE TABLE gold.model_frame AS
        WITH ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (PARTITION BY state ORDER BY ds) AS t_index
            FROM gold.state_features
        )
        SELECT * FROM ranked
        WHERE t_index >= 28
          AND {where};        """
    )


def _write_reports(
    con: duckdb.DuckDBPyConnection,
    report_dir: Path,
    contract_name: str,
    quality_run_id: str,
    targets: List[str],
    max_ffill_days: int,
    max_missing_run: int,
    min_history_days: int,
) -> None:
    ensure_dir(report_dir)

    cohort = con.execute(
        "SELECT state, is_eligible, fail_rules FROM gold.state_cohort ORDER BY is_eligible DESC, state"
    ).df()
    cohort.to_csv(report_dir / "day23_cohort.csv", index=False)

    n_elig = int(cohort["is_eligible"].sum())
    n_excl = int((cohort["is_eligible"] == 0).sum())

    bounds = con.execute(
        "SELECT MIN(ds) AS min_ds, MAX(ds) AS max_ds, COUNT(*) AS n_rows FROM gold.state_daily_panel"
    ).df().iloc[0].to_dict()

    summary = []
    summary.append("# Day 23 — Cohort + Gold build summary\n\n")
    summary.append(f"- Contract: **{contract_name}**\n")
    summary.append(f"- Quality run: `{quality_run_id}`\n")
    summary.append(f"- Thresholds: min_history_days={min_history_days}, max_missing_run={max_missing_run}\n")
    summary.append(f"- Eligible states: **{n_elig}**\n")
    summary.append(f"- Excluded states: **{n_excl}**\n\n")
    summary.append(f"- Panel date range: {bounds.get('min_ds')} to {bounds.get('max_ds')}\n")
    summary.append(f"- Panel rows: {int(bounds.get('n_rows'))}\n\n")

    top_excl = cohort[cohort["is_eligible"] == 0].head(15)
    if not top_excl.empty:
        summary.append("## Excluded states (first 15)\n\n")
        summary.append(top_excl.to_markdown(index=False) + "\n")
    else:
        summary.append("## Excluded states\n\n(none)\n")

    (report_dir / "day23_cohort_summary.md").write_text("".join(summary), encoding="utf-8")

    feats = []
    feats.append("# Day 23 — Feature dictionary\n\n")
    feats.append(f"Targets: {', '.join(targets)}\n\n")
    feats.append("Calendar features: `dow`, `week_of_year`, `month`, `year`, `is_weekend`, `is_holiday`\n\n")
    feats.append(f"Forward fill policy: `*_ffill{max_ffill_days}` = COALESCE(y, lag1..lag{max_ffill_days})\n\n")
    for t in targets:
        feats.append(f"## {t}\n\n")
        feats.append(f"- `{t}_ffill{max_ffill_days}`: forward-filled value (<= {max_ffill_days} days)\n")
        feats.append(f"- `{t}_lag1`, `{t}_lag7`, `{t}_lag14`, `{t}_lag21`: lagged ffill values\n")
        feats.append(f"- `{t}_d1`, `{t}_d7`: deltas on ffill\n")
        feats.append(f"- `{t}_roll7_mean/sd/max`, `{t}_roll14_mean/sd/max`, `{t}_roll28_mean/sd/max`: rolling stats on ffill\n\n")
    (report_dir / "day23_feature_dictionary.md").write_text("".join(feats), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Day 23: build gold tables + engineered features for forecasting.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True, help="Path to DuckDB file.")
    r.add_argument("--report-dir", type=Path, required=True, help="Directory to write Day 23 reports.")
    r.add_argument("--contract-name", type=str, default=None, help="Contract name (defaults to latest).")
    r.add_argument("--quality-run-id", type=str, default=None, help="Quality run_id to use (defaults to latest).")
    r.add_argument("--source-table", type=str, default="silver.hhs_state_timeseries", help="Silver source table.")
    r.add_argument("--targets", nargs="+", default=["inpatient_beds_used", "staffed_adult_icu_bed_occupancy"], help="Targets to feature-engineer.")
    r.add_argument("--max-ffill-days", type=int, default=3, help="Forward-fill up to this many days.")
    args = p.parse_args(argv)

    run_id = str(uuid.uuid4())
    sha = git_sha()
    cmdline = " ".join(sys.argv)

    con = connect(args.db)
    init_meta(con)
    register_run_start(con, run_id, sha, cmdline, notes="Day23 gold + features")

    try:
        contract = _load_contract_from_db(con, args.contract_name)
        contract_name = contract.get("name", args.contract_name or "(latest)")
        max_missing_run, min_history_days = _get_thresholds(contract)

        quality_run_id = args.quality_run_id or _latest_quality_run_id(con)

        if not _table_exists(con, args.source_table):
            raise RuntimeError(f"Source table {args.source_table} not found. Run Day 21 first.")

        src = _dedup_source(con, args.source_table)

        _build_cohort(con, src, quality_run_id)
        _build_daily_panel(con, src, quality_run_id)
        _build_holidays(con)
        _build_features(con, targets=list(args.targets), max_ffill_days=int(args.max_ffill_days))
        _build_model_frame(con, targets=list(args.targets), max_ffill_days=int(args.max_ffill_days))

        _write_reports(
            con=con,
            report_dir=args.report_dir,
            contract_name=contract_name,
            quality_run_id=quality_run_id,
            targets=list(args.targets),
            max_ffill_days=int(args.max_ffill_days),
            max_missing_run=max_missing_run,
            min_history_days=min_history_days,
        )

        n_elig = con.execute("SELECT COUNT(*) FROM gold.state_cohort WHERE is_eligible=1").fetchone()[0]
        n_excl = con.execute("SELECT COUNT(*) FROM gold.state_cohort WHERE is_eligible=0").fetchone()[0]
        panel_rows = con.execute("SELECT COUNT(*) FROM gold.state_daily_panel").fetchone()[0]
        feat_rows = con.execute("SELECT COUNT(*) FROM gold.state_features").fetchone()[0]
        mf_rows = con.execute("SELECT COUNT(*) FROM gold.model_frame").fetchone()[0]

        t = Table(title="Day 23 gold build")
        t.add_column("metric")
        t.add_column("value", justify="right")
        t.add_row("contract", str(contract_name))
        t.add_row("quality_run_id", str(quality_run_id))
        t.add_row("eligible_states", str(n_elig))
        t.add_row("excluded_states", str(n_excl))
        t.add_row("panel_rows", str(panel_rows))
        t.add_row("feature_rows", str(feat_rows))
        t.add_row("model_frame_rows", str(mf_rows))
        console.print(t)

        register_run_finish(con, run_id, "success")
        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        register_run_finish(con, run_id, "failed")
        console.print(f"\n[red]ERROR[/red] run_id={run_id}\n{e}")
        return 2
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
