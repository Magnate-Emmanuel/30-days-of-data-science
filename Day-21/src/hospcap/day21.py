from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from .config import DATASETS
from .contracts import load_contract, parse_contract, validate_contract_columns
from .duck import (
    connect,
    init_meta,
    record_file,
    record_schema,
    register_run_finish,
    register_run_start,
    describe_table,
)
from .io import download_csv, write_manifest
from .util import ensure_dir, git_sha

console = Console()

SENTINEL_MISSING = -999999

def _pick_first(candidates: tuple[str, ...], available: List[str]) -> Optional[str]:
    lower_map = {c.lower(): c for c in available}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None

def _is_numeric_type(t: str) -> bool:
    t = t.upper()
    return any(x in t for x in ("INT", "DOUBLE", "FLOAT", "REAL", "DECIMAL", "HUGEINT", "BIGINT", "SMALLINT", "TINYINT"))

def _table_exists(con, fq_table: str) -> bool:
    schema, name = fq_table.split(".")
    return con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=? AND table_name=?",
        [schema, name],
    ).fetchone()[0] > 0

def _describe_select(con, sql: str):
    # returns [(name, type), ...]
    rows = con.execute(f"DESCRIBE {sql}").fetchall()
    return [(r[0], r[1]) for r in rows]

def _ensure_same_columns(existing_cols, incoming_cols, table_name: str):
    ex_names = [c for c, _ in existing_cols]
    in_names = [c for c, _ in incoming_cols]
    if ex_names != in_names:
        raise RuntimeError(
            f"Schema drift detected for {table_name}.\n"
            f"Existing columns: {ex_names[:40]}{' ...' if len(ex_names)>40 else ''}\n"
            f"Incoming columns: {in_names[:40]}{' ...' if len(in_names)>40 else ''}"
        )

def _create_or_append_bronze(con, table: str, csv_path: Path, run_id: str) -> None:
    stage_sql = f"""(
        SELECT
            *,
            '{run_id}'::VARCHAR AS _run_id,
            NOW() AS _ingested_at
        FROM read_csv_auto('{csv_path.as_posix()}', header=true, sample_size=-1)
    )"""

    incoming = _describe_select(con, f"SELECT * FROM {stage_sql}")

    if not _table_exists(con, table):
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM {stage_sql};")
    else:
        existing = describe_table(con, table)
        _ensure_same_columns(existing, incoming, table)
        con.execute(f"INSERT INTO {table} SELECT * FROM {stage_sql};")

def _q(name: str) -> str:
    # DuckDB identifier quoting (handles hyphens, spaces, etc.)
    return '"' + name.replace('"', '""') + '"'

def _create_or_append_silver(con, bronze_table: str, silver_table: str, dataset_key: str, run_id: str) -> None:
    cols = describe_table(con, bronze_table)
    col_names = [c for c, _ in cols]

    if dataset_key == "state":
        date_col = _pick_first(DATASETS[dataset_key].date_candidates, col_names) or "date"
        key_col = "state" if "state" in col_names else _pick_first(("state",), col_names)
    else:
        date_col = _pick_first(DATASETS[dataset_key].date_candidates, col_names) or "collection_week"
        key_col = _pick_first(DATASETS[dataset_key].key_candidates, col_names)

    if key_col is None:
        raise RuntimeError(f"Could not find a facility key column among {DATASETS[dataset_key].key_candidates}.")

    select_exprs = []
    for name, typ in cols:
        if name == date_col:
            select_exprs.append(f"TRY_CAST({_q(name)} AS DATE) AS ds")
        elif _is_numeric_type(typ):
            select_exprs.append(f"NULLIF({_q(name)}, {SENTINEL_MISSING}) AS {_q(name)}")
        else:
            select_exprs.append(f"{_q(name)}")

    stage_sql = f"""(
        SELECT
            {", ".join(select_exprs)}
        FROM {bronze_table}
        WHERE {_q("_run_id")} = '{run_id}'
    )"""

    incoming = _describe_select(con, f"SELECT * FROM {stage_sql}")

    if not _table_exists(con, silver_table):
        con.execute(f"CREATE TABLE {silver_table} AS SELECT * FROM {stage_sql};")
    else:
        existing = describe_table(con, silver_table)
        _ensure_same_columns(existing, incoming, silver_table)
        con.execute(f"INSERT INTO {silver_table} SELECT * FROM {stage_sql};")

    # Integrity checks for THIS run only
    bad_ds = con.execute(f"SELECT COUNT(*) FROM {silver_table} WHERE {_q('_run_id')}='{run_id}' AND ds IS NULL").fetchone()[0]
    if bad_ds > 0:
        raise RuntimeError(f"{silver_table}: {bad_ds} rows have NULL ds (date parsing failed) for run_id={run_id}.")

    bad_key = con.execute(
        f"SELECT COUNT(*) FROM {silver_table} WHERE {_q('_run_id')}='{run_id}' AND {_q(key_col)} IS NULL"
    ).fetchone()[0]
    if bad_key > 0:
        raise RuntimeError(f"{silver_table}: {bad_key} rows have NULL key column {key_col} for run_id={run_id}.")

    dups = con.execute(
        f"""SELECT COUNT(*) FROM (
            SELECT {_q(key_col)}, ds, COUNT(*) c
            FROM {silver_table}
            WHERE {_q('_run_id')}='{run_id}'
            GROUP BY 1,2
            HAVING c>1
        )"""
    ).fetchone()[0]
    if dups > 0:
        raise RuntimeError(f"{silver_table}: found duplicate (key, ds) pairs ({dups}) for run_id={run_id}.")


def _register_contract(con, contract_path: Path) -> None:
    d = load_contract(contract_path)
    contract = parse_contract(d)
    yaml_text = contract_path.read_text(encoding="utf-8")

    con.execute(
        "INSERT INTO meta.forecast_contracts VALUES (?, ?, ?, ?)",
        [contract.name, contract.version, yaml_text, datetime.now(timezone.utc)],
    )

    # Validate required targets vs available columns
    cols = [c for c, _ in describe_table(con, contract.source_table)]
    ok, missing = validate_contract_columns(cols, contract)

    if not ok:
        preview = ", ".join(cols[:40]) + (" ..." if len(cols) > 40 else "")
        raise RuntimeError(
            "Contract validation failed: none of the required targets were found in source table.\n"
            f"Required targets: {contract.required_targets}\n"
            f"Missing: {missing}\n"
            f"Available columns (first 40): {preview}"
        )

def _print_summary(con) -> None:
    t = Table(title="Day 21 ingestion summary")
    t.add_column("table")
    t.add_column("rows", justify="right")
    t.add_column("min_ds", justify="right")
    t.add_column("max_ds", justify="right")

    for tbl in ["silver.hhs_state_timeseries", "silver.hhs_facility_weekly"]:
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=? AND table_name=?",
            tbl.split("."),
        ).fetchone()[0]
        if not exists:
            continue
        rows = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        mn, mx = con.execute(f"SELECT MIN(ds), MAX(ds) FROM {tbl}").fetchone()
        t.add_row(tbl, str(rows), str(mn), str(mx))
    console.print(t)

def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()

    p = argparse.ArgumentParser(description="Day 21: ingest HealthData.gov hospital capacity datasets into DuckDB.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True, help="Path to DuckDB file.")
    r.add_argument("--data-dir", type=Path, required=True, help="Directory to store raw snapshots.")
    r.add_argument("--datasets", nargs="+", default=["state"], choices=list(DATASETS.keys()), help="Datasets to ingest.")
    PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Day-21/
    r.add_argument("--contract", type=Path, default=PROJECT_ROOT / "contracts" / "forecasting_contract_v1.yml", help="Forecast contract YAML.",)
    r.add_argument("--max-mb", type=int, default=None, help="Abort if a download exceeds this size (MB).")
    r.add_argument("--mode", choices=["replace", "append"], default="replace",
               help="replace (idempotent) or append (keep multiple runs in tables)")


    args = p.parse_args(argv)

    run_id = str(uuid.uuid4())
    sha = git_sha()
    cmdline = " ".join(sys.argv)

    con = connect(args.db)
    init_meta(con)
    register_run_start(con, run_id, sha, cmdline, notes="Day21 ingestion")

    try:
        token = None
        # Optional Socrata app token
        import os
        token = os.getenv("HHS_DATA_APP_TOKEN") or None
        headers = {"X-App-Token": token} if token else None

        # Download + manifest per dataset
        for key in args.datasets:
            spec = DATASETS[key]
            snap_dir = args.data_dir / "raw" / spec.dataset_id / run_id
            ensure_dir(snap_dir)
            csv_path = snap_dir / f"{spec.dataset_id}.csv"
            manifest_path = snap_dir / f"{spec.dataset_id}.manifest.json"

            console.print(f"\n[bold]Dataset:[/bold] {spec.name} ({spec.dataset_id})")
            manifest = download_csv(spec.download_url, csv_path, headers=headers, max_mb=args.max_mb)
            write_manifest(manifest, manifest_path)

            record_file(con, run_id, spec.key, spec.dataset_id, spec.download_url, manifest)

            # Load bronze and promote to silver
            _create_or_append_bronze(con, spec.table_bronze, csv_path, run_id)
            record_schema(con, run_id, spec.key, spec.table_bronze)

            _create_or_append_silver(con, spec.table_bronze, spec.table_silver, dataset_key=spec.key, run_id=run_id)
            record_schema(con, run_id, spec.key, spec.table_silver)

        # Register and validate contract (expects state silver table)
        if args.contract.exists():
            _register_contract(con, args.contract)
        else:
            console.print(f"[yellow]Contract file not found at {args.contract}; skipping registration.[/yellow]")

        register_run_finish(con, run_id, "success")
        _print_summary(con)
        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        register_run_finish(con, run_id, "failed")
        console.print(f"\n[red]FAILED[/red] run_id={run_id}\n{e}")
        return 1
    finally:
        con.close()

if __name__ == "__main__":
    raise SystemExit(main())
