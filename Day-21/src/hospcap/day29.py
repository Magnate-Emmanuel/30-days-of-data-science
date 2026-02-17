from __future__ import annotations

import argparse
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
from rich.console import Console
from rich.table import Table

from .duck import connect, init_meta, register_run_finish, register_run_start
from .util import ensure_dir, git_sha

console = Console()

RUNID_RE = re.compile(r"run_id=([0-9a-fA-F\-]{36})")


def _snip(s: str, n: int = 4000) -> str:
    if s is None:
        return ""
    s = s.strip()
    if len(s) <= n:
        return s
    return s[: n // 2] + "\n...\n" + s[-n // 2 :]


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS day29;")
    con.execute(
        """CREATE TABLE IF NOT EXISTS day29.runs (
            run_id VARCHAR PRIMARY KEY,
            started_at_utc TIMESTAMP,
            finished_at_utc TIMESTAMP,
            status VARCHAR,
            contract_name VARCHAR,
            db_path VARCHAR,
            targets VARCHAR,
            horizons VARCHAR,
            n_splits INTEGER,
            step_days INTEGER,
            quantiles VARCHAR,
            p_trigger DOUBLE,
            c_false_alarm DOUBLE,
            c_missed DOUBLE,
            day23_status VARCHAR,
            day25_run_id VARCHAR,
            day26_run_id VARCHAR,
            day27_run_id VARCHAR,
            day28_run_id VARCHAR,
            notes VARCHAR
        );"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS day29.step_logs (
            run_id VARCHAR,
            step VARCHAR,
            started_at_utc TIMESTAMP,
            finished_at_utc TIMESTAMP,
            status VARCHAR,
            cmd VARCHAR,
            stdout_snip VARCHAR,
            stderr_snip VARCHAR
        );"""
    )


def _log_step_start(db_path: Path, pipeline_run_id: str, step: str, started: datetime, cmd_str: str) -> None:
    con = connect(db_path)
    try:
        init_meta(con)
        _ensure_schema(con)
        con.execute(
            "INSERT INTO day29.step_logs VALUES (?, ?, ?, NULL, ?, ?, ?, ?)",
            [pipeline_run_id, step, started, "running", cmd_str, "", ""],
        )
    finally:
        con.close()


def _log_step_finish(db_path: Path, pipeline_run_id: str, step: str, started: datetime, status: str, stdout: str, stderr: str) -> None:
    con = connect(db_path)
    try:
        con.execute(
            """UPDATE day29.step_logs
               SET finished_at_utc=?, status=?, stdout_snip=?, stderr_snip=?
               WHERE run_id=? AND step=? AND started_at_utc=?""",
            [datetime.now(timezone.utc), status, _snip(stdout), _snip(stderr), pipeline_run_id, step, started],
        )
    finally:
        con.close()


def _run_step(
    db_path: Path,
    pipeline_run_id: str,
    step: str,
    cmd: List[str],
    cwd: Optional[Path] = None,
) -> Tuple[str, str, Optional[str]]:
    """
    IMPORTANT (Windows): DuckDB places an OS file lock on the DB while a process has an open connection.
    Therefore, this function opens a short-lived connection ONLY to write logs, then closes it before
    spawning subprocess steps (day23/day25/day26/day27/day28).
    """
    started = datetime.now(timezone.utc)
    cmd_str = " ".join(cmd)
    _log_step_start(db_path, pipeline_run_id, step, started, cmd_str)

    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )

    out = p.stdout or ""
    err = p.stderr or ""
    status = "success" if p.returncode == 0 else "failed"
    _log_step_finish(db_path, pipeline_run_id, step, started, status, out, err)

    run_id_match = RUNID_RE.findall(out + "\n" + err)
    sub_run_id = run_id_match[-1] if run_id_match else None

    if p.returncode != 0:
        raise RuntimeError(
            f"Step {step} failed\nCMD: {cmd_str}\n\nSTDOUT:\n{_snip(out)}\n\nSTDERR:\n{_snip(err)}"
        )

    return status, out, sub_run_id


def _write_summary(report_dir: Path, run_id: str, sub: Dict[str, Optional[str]], args: argparse.Namespace) -> None:
    ensure_dir(report_dir)
    md = []
    md.append("# Day 29 — Pipeline run summary\n\n")
    md.append(f"Run ID: `{run_id}`\n\n")
    md.append("## Parameters\n\n")
    md.append(f"- contract_name: `{args.contract_name}`\n")
    md.append(f"- targets: `{', '.join(args.targets)}`\n")
    md.append(f"- horizons: `{', '.join(map(str, args.horizons))}`\n")
    md.append(f"- n_splits: `{args.n_splits}`, step_days: `{args.step}`\n")
    md.append(f"- quantiles: `{', '.join(map(lambda x: f'{x:g}', args.quantiles))}`\n")
    md.append(f"- p_trigger: `{args.p_trigger}`, costs: false_alarm={args.c_false_alarm}, missed={args.c_missed}\n\n")

    md.append("## Sub-runs\n\n")
    rows = [
        ("Day 25 (main models)", sub.get("day25_run_id")),
        ("Day 26 (probabilistic)", sub.get("day26_run_id")),
        ("Day 27 (monitoring)", sub.get("day27_run_id")),
        ("Day 28 (alerts)", sub.get("day28_run_id")),
    ]
    md.append("| step | run_id |\n|---|---|\n")
    for label, rid in rows:
        md.append(f"| {label} | `{rid or ''}` |\n")
    md.append("\n")

    md.append("## Where to look\n\n")
    md.append("- Step logs in DuckDB: `day29.step_logs`\n")
    md.append("- Day 28 dashboard-ready alerts: `Day-29/reports/alerts_dashboard.csv`\n")
    md.append("- Full step reports under `Day-29/reports/day23 ... day28`\n")

    (report_dir / "day29_summary.md").write_text("".join(md), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Day 29: packaged pipeline (gold -> models -> quantiles -> monitoring -> alerts)."
    )
    subp = p.add_subparsers(dest="cmd", required=True)

    r = subp.add_parser("run")
    r.add_argument("--db", type=Path, required=True)
    r.add_argument("--report-dir", type=Path, required=True)
    r.add_argument("--contract-name", type=str, default=None)

    r.add_argument("--targets", nargs="+", default=["inpatient_beds_used", "staffed_adult_icu_bed_occupancy"])
    r.add_argument("--horizons", nargs="+", type=int, default=[1, 7, 14])
    r.add_argument("--n-splits", type=int, default=8)
    r.add_argument("--step", type=int, default=7)
    r.add_argument("--quantiles", nargs="+", type=float, default=[0.1, 0.5, 0.9])
    r.add_argument("--ffill-days", type=int, default=3)

    r.add_argument("--p-trigger", type=float, default=0.6)
    r.add_argument("--inpatient-util-threshold", type=float, default=0.85)
    r.add_argument("--icu-util-threshold", type=float, default=0.80)
    r.add_argument("--c-false-alarm", type=float, default=1.0)
    r.add_argument("--c-missed", type=float, default=5.0)

    r.add_argument("--skip-gold", action="store_true")
    r.add_argument("--skip-monitoring", action="store_true")

    args = p.parse_args(argv)

    run_id = str(uuid.uuid4())
    sha = git_sha()
    cmdline = " ".join(sys.argv)

    contract_name = args.contract_name or "(latest)"

    # Init DB + register run, then CLOSE connection before spawning subprocesses (Windows lock).
    con = connect(args.db)
    try:
        init_meta(con)
        _ensure_schema(con)
        con.execute(
            "INSERT INTO day29.runs VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                datetime.now(timezone.utc),
                "running",
                contract_name,
                str(args.db),
                ", ".join(args.targets),
                ", ".join(map(str, args.horizons)),
                int(args.n_splits),
                int(args.step),
                ", ".join(map(lambda x: f"{float(x):g}", args.quantiles)),
                float(args.p_trigger),
                float(args.c_false_alarm),
                float(args.c_missed),
                None,
                None,
                None,
                None,
                None,
                "Day29 packaged pipeline",
            ],
        )
        register_run_start(con, run_id, sha, cmdline, notes="Day29 packaged pipeline")
    finally:
        con.close()

    # Reports: keep everything under Day-29/reports/*
    report_dir = Path(args.report_dir)
    step_dirs = {
        "day23": report_dir / "day23",
        "day25": report_dir / "day25",
        "day26": report_dir / "day26",
        "day27": report_dir / "day27",
        "day28": report_dir / "day28",
    }
    for d in step_dirs.values():
        ensure_dir(d)

    sub_runs: Dict[str, Optional[str]] = {"day25_run_id": None, "day26_run_id": None, "day27_run_id": None, "day28_run_id": None}

    try:
        # Day 23 (gold/features) — optional but recommended for reproducibility
        if args.skip_gold:
            day23_status = "skipped"
        else:
            cmd23 = [
                sys.executable,
                "-m",
                "hospcap.day23",
                "run",
                "--db",
                str(args.db),
                "--report-dir",
                str(step_dirs["day23"]),
                "--contract-name",
                contract_name,
            ]
            st, _, _ = _run_step(args.db, run_id, "day23", cmd23)
            day23_status = st

        # Day 25 (main models)
        cmd25 = [
            sys.executable,
            "-m",
            "hospcap.day25",
            "run",
            "--db",
            str(args.db),
            "--report-dir",
            str(step_dirs["day25"]),
            "--contract-name",
            contract_name,
            "--targets",
            *args.targets,
            "--horizons",
            *map(str, args.horizons),
            "--n-splits",
            str(args.n_splits),
            "--step",
            str(args.step),
        ]
        _, _, day25_run_id = _run_step(args.db, run_id, "day25", cmd25)
        sub_runs["day25_run_id"] = day25_run_id

        # Day 26 (probabilistic)
        cmd26 = [
            sys.executable,
            "-m",
            "hospcap.day26",
            "run",
            "--db",
            str(args.db),
            "--report-dir",
            str(step_dirs["day26"]),
            "--contract-name",
            contract_name,
            "--targets",
            *args.targets,
            "--horizons",
            *map(str, args.horizons),
            "--quantiles",
            *map(lambda x: f"{float(x):g}", args.quantiles),
            "--n-splits",
            str(args.n_splits),
            "--step",
            str(args.step),
            "--ffill-days",
            str(args.ffill_days),
        ]
        _, _, day26_run_id = _run_step(args.db, run_id, "day26", cmd26)
        sub_runs["day26_run_id"] = day26_run_id

        # Day 27 (monitoring) — optional
        if args.skip_monitoring:
            day27_run_id = None
        else:
            cmd27 = [
                sys.executable,
                "-m",
                "hospcap.day27",
                "run",
                "--db",
                str(args.db),
                "--report-dir",
                str(step_dirs["day27"]),
                "--contract-name",
                contract_name,
                "--day26-run-id",
                str(day26_run_id or ""),
            ]
            _, _, day27_run_id = _run_step(args.db, run_id, "day27", cmd27)
            sub_runs["day27_run_id"] = day27_run_id

        # Day 28 (decision layer alerts)
        cmd28 = [
            sys.executable,
            "-m",
            "hospcap.day28",
            "run",
            "--db",
            str(args.db),
            "--report-dir",
            str(step_dirs["day28"]),
            "--contract-name",
            contract_name,
            "--day26-run-id",
            str(day26_run_id or ""),
            "--p-trigger",
            str(args.p_trigger),
            "--inpatient-util-threshold",
            str(args.inpatient_util_threshold),
            "--icu-util-threshold",
            str(args.icu_util_threshold),
            "--c-false-alarm",
            str(args.c_false_alarm),
            "--c-missed",
            str(args.c_missed),
        ]
        _, _, day28_run_id = _run_step(args.db, run_id, "day28", cmd28)
        sub_runs["day28_run_id"] = day28_run_id

        # Convenience copy: dashboard alerts into Day-29 root
        alerts_csv = step_dirs["day28"] / "day28_alerts.csv"
        if alerts_csv.exists():
            (report_dir / "alerts_dashboard.csv").write_bytes(alerts_csv.read_bytes())

        _write_summary(report_dir, run_id, sub_runs, args)

        # Final DB update (open short-lived connection)
        con2 = connect(args.db)
        try:
            con2.execute(
                """UPDATE day29.runs
                   SET finished_at_utc=?, status=?, day23_status=?, day25_run_id=?, day26_run_id=?, day27_run_id=?, day28_run_id=?
                   WHERE run_id=?""",
                [
                    datetime.now(timezone.utc),
                    "success",
                    day23_status,
                    sub_runs["day25_run_id"],
                    sub_runs["day26_run_id"],
                    sub_runs["day27_run_id"],
                    sub_runs["day28_run_id"],
                    run_id,
                ],
            )
            register_run_finish(con2, run_id, "success")
        finally:
            con2.close()

        t = Table(title="Day 29 packaged pipeline")
        t.add_column("metric")
        t.add_column("value", justify="right")
        t.add_row("contract", contract_name)
        t.add_row("targets", ", ".join(args.targets))
        t.add_row("horizons", ", ".join(map(str, args.horizons)))
        t.add_row("day25_run_id", str(sub_runs["day25_run_id"]))
        t.add_row("day26_run_id", str(sub_runs["day26_run_id"]))
        t.add_row("day28_run_id", str(sub_runs["day28_run_id"]))
        console.print(t)

        console.print(f"\n[green]OK[/green] run_id={run_id}")
        return 0

    except Exception as e:
        con3 = connect(args.db)
        try:
            con3.execute(
                "UPDATE day29.runs SET finished_at_utc=?, status=? WHERE run_id=?",
                [datetime.now(timezone.utc), "failed", run_id],
            )
            register_run_finish(con3, run_id, "failed")
        finally:
            con3.close()
        console.print(f"\n[red]ERROR[/red] run_id={run_id}\n{e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
