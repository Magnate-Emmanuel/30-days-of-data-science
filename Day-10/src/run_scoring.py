#from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path

import duckdb
import pandas as pd
import numpy as np

from config import find_project_root, default_paths
from io_validate import load_contract, validate_input
from score import score_with_artifacts
from report import compute_metrics, topk, distribution_summary, write_json

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def now_run_id():
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{ts}"

def write_run_log(path: Path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description="Day 10: Readmission scoring pipeline (local deployment-style).")
    parser.add_argument("--input", required=True, help="Path to input CSV to score.")
    parser.add_argument("--output", required=True, help="Output directory for scored files and reports.")
    parser.add_argument("--mode", default="auto", choices=["auto", "score", "evaluate"],
                        help="auto = evaluate if label exists else score.")
    parser.add_argument("--write_duckdb", action="store_true", help="Write scored outputs to Day-1 DuckDB.")
    args = parser.parse_args()

    project_root = find_project_root()
    paths = default_paths(project_root)

    input_path = Path(args.input).resolve()
    out_dir = Path(args.output).resolve()
    ensure_dir(out_dir)

    run_id = now_run_id()

    # ---- Preconditions ----
    required_artifacts = [
        paths["base_model_path"], paths["platt_path"], paths["contract_path"]
    ]
    missing = [str(p) for p in required_artifacts if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(f"Missing required artifacts: {missing}")

    # ---- Load input ----
    df_in = pd.read_csv(input_path)
    contract = load_contract(paths["contract_path"])

    # ---- Decide mode ----
    if args.mode == "auto":
        mode = "evaluate" if "label" in df_in.columns else "score"
    else:
        mode = args.mode

    # ---- Validate ----
    vr = validate_input(df_in, contract, mode=mode)

    # ---- Score ----
    preds = score_with_artifacts(vr.df_for_model, paths["base_model_path"], paths["platt_path"])
    # ensure 1D numeric arrays (avoid numpy.ndarray cells in pandas)
    p_raw = np.asarray(preds["p_raw"]).reshape(-1)
    p_hat = np.asarray(preds["p_hat"]).reshape(-1)
    
    df_scored = vr.df_original.copy()
    df_scored["p_raw"] = p_raw
    df_scored["p_hat"] = p_hat


    # rank + deciles
    df_scored = df_scored.sort_values("p_hat", ascending=False).reset_index(drop=True)
    df_scored["rank"] = df_scored.index + 1
    # store decile as integer 1..10 (DuckDB-safe)
    df_scored["risk_decile"] = pd.qcut(
        df_scored["p_hat"], q=10, labels=False, duplicates="drop"
    ) + 1
    df_scored["risk_decile"] = df_scored["risk_decile"].astype("Int64")


    # ---- Outputs ----
    scored_csv = out_dir / "scored.csv"
    df_scored.to_csv(scored_csv, index=False)

    # top-K targeting files
    top_fracs = [0.01, 0.05, 0.10, 0.20]
    topk_files = []
    for frac in top_fracs:
        n = len(df_scored)
        k = max(1, int(frac * n))
        df_top = df_scored.head(k).copy()
        outp = out_dir / f"ranked_top_{int(frac*100)}pct.csv"
        df_top.to_csv(outp, index=False)
        topk_files.append(str(outp))

    # ---- Summary JSON ----
    summary = {
        "run_id": run_id,
        "mode": mode,
        "input": str(input_path),
        "rows": int(len(df_scored)),
        "schema_hash": vr.schema_hash,
        "warnings": vr.warnings,
        "probability_distribution": distribution_summary(df_scored["p_hat"].to_numpy()),
        "outputs": {
            "scored_csv": str(scored_csv),
            "topk_files": topk_files,
        }
    }

    # Optional evaluation if label exists and mode=evaluate
    if mode == "evaluate":
        y = df_scored["label"].astype(int).to_numpy()
        p = df_scored["p_hat"].to_numpy()
        summary["metrics"] = compute_metrics(y, p)
        summary["topk_metrics"] = [topk(y, p, f) for f in top_fracs]

    summary_json = out_dir / "summary.json"
    write_json(summary, summary_json)

    # ---- Run log ----
    log_lines = []
    log_lines.append(f"run_id: {run_id}")
    log_lines.append(f"timestamp_local: {dt.datetime.now().isoformat(timespec='seconds')}")
    log_lines.append(f"mode: {mode}")
    log_lines.append(f"input: {input_path}")
    log_lines.append(f"rows_scored: {len(df_scored)}")
    log_lines.append(f"schema_hash: {vr.schema_hash}")
    if vr.warnings:
        log_lines.append("warnings:")
        log_lines.extend([f"  - {w}" for w in vr.warnings])
    else:
        log_lines.append("warnings: none")
    log_lines.append(f"wrote: {scored_csv}")
    log_lines.append(f"wrote: {summary_json}")
    for f in topk_files:
        log_lines.append(f"wrote: {f}")

    run_log = out_dir / "run_log.txt"
    write_run_log(run_log, log_lines)

    # ---- DuckDB writeback (optional) ----
    if args.write_duckdb:
        db_path = paths["day1_db"]
        con = duckdb.connect(str(db_path))

        # Create latest scored table
        df_scored_db = df_scored.copy()
        # if any categorical dtype remains, cast to string
        for c in df_scored_db.columns:
            if str(df_scored_db[c].dtype) == "category":
                df_scored_db[c] = df_scored_db[c].astype(str)
                
        con.register("scored_df", df_scored_db)

        con.execute("CREATE OR REPLACE TABLE gold_diabetes_scored_latest AS SELECT * FROM scored_df")

        # Append run metadata table
        con.execute("""
        CREATE TABLE IF NOT EXISTS gold_diabetes_scored_runs (
            run_id VARCHAR,
            timestamp_local VARCHAR,
            input_path VARCHAR,
            mode VARCHAR,
            rows_scored BIGINT,
            schema_hash VARCHAR,
            warnings_json VARCHAR
        )
        """)
        warnings_json = json.dumps(vr.warnings)
        con.execute("""
            INSERT INTO gold_diabetes_scored_runs
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            run_id,
            dt.datetime.now().isoformat(timespec="seconds"),
            str(input_path),
            mode,
            int(len(df_scored)),
            vr.schema_hash,
            warnings_json
        ])
        con.close()
        log_lines.append(f"duckdb_writeback: {db_path}")
        write_run_log(run_log, log_lines)

    print("DONE ✅")
    print("scored.csv  ->", scored_csv)
    print("summary.json->", summary_json)
    print("run_log.txt ->", run_log)
    if args.write_duckdb:
        print("DuckDB table: gold_diabetes_scored_latest (replaced)")
        print("DuckDB table: gold_diabetes_scored_runs (appended)")

if __name__ == "__main__":
    main()
