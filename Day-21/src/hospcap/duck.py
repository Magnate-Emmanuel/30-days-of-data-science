from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb

def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    # deterministic-ish settings
    con.execute("PRAGMA threads=4;")
    con.execute("PRAGMA preserve_insertion_order=false;")
    # schemas
    con.execute("CREATE SCHEMA IF NOT EXISTS meta;")
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze;")
    con.execute("CREATE SCHEMA IF NOT EXISTS silver;")
    return con

def init_meta(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""

        CREATE TABLE IF NOT EXISTS meta.runs (
            run_id VARCHAR PRIMARY KEY,
            started_at_utc TIMESTAMP,
            finished_at_utc TIMESTAMP,
            status VARCHAR,
            git_sha VARCHAR,
            command VARCHAR,
            notes VARCHAR
        );

        CREATE TABLE IF NOT EXISTS meta.files (
            run_id VARCHAR,
            dataset_key VARCHAR,
            dataset_id VARCHAR,
            url VARCHAR,
            local_path VARCHAR,
            nbytes BIGINT,
            sha256 VARCHAR,
            fetched_at_utc TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS meta.schemas (
            run_id VARCHAR,
            dataset_key VARCHAR,
            table_name VARCHAR,
            column_name VARCHAR,
            column_type VARCHAR
        );

        CREATE TABLE IF NOT EXISTS meta.forecast_contracts (
            contract_name VARCHAR,
            version INTEGER,
            yaml_text VARCHAR,
            registered_at_utc TIMESTAMP
        );
    """)

def register_run_start(con: duckdb.DuckDBPyConnection, run_id: str, git_sha: Optional[str], command: str, notes: str = "") -> None:
    con.execute(
        "INSERT INTO meta.runs VALUES (?, ?, NULL, ?, ?, ?, ?)",
        [run_id, datetime.now(timezone.utc), "running", git_sha, command, notes],
    )

def register_run_finish(con: duckdb.DuckDBPyConnection, run_id: str, status: str) -> None:
    con.execute(
        "UPDATE meta.runs SET finished_at_utc=?, status=? WHERE run_id=?",
        [datetime.now(timezone.utc), status, run_id],
    )

def record_file(con: duckdb.DuckDBPyConnection, run_id: str, dataset_key: str, dataset_id: str, url: str, manifest: Dict) -> None:
    con.execute(
        "INSERT INTO meta.files VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            run_id,
            dataset_key,
            dataset_id,
            url,
            manifest["path"],
            manifest["nbytes"],
            manifest["sha256"],
            manifest["fetched_at_utc"],
        ],
    )

def describe_table(con: duckdb.DuckDBPyConnection, table_name: str) -> List[Tuple[str, str]]:
    # Returns [(name, type), ...]
    rows = con.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    # pragma columns: cid, name, type, notnull, dflt_value, pk
    return [(r[1], r[2]) for r in rows]

def record_schema(con: duckdb.DuckDBPyConnection, run_id: str, dataset_key: str, table_name: str) -> None:
    cols = describe_table(con, table_name)
    con.executemany(
        "INSERT INTO meta.schemas VALUES (?, ?, ?, ?, ?)",
        [(run_id, dataset_key, table_name, c, t) for c, t in cols],
    )
