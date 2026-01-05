#from __future__ import annotations
from pathlib import Path

def find_project_root(start: Path | None = None) -> Path:
    """
    Find repo root by walking upward until we see Day-1 folder.
    """
    p = (start or Path.cwd()).resolve()
    while True:
        if (p / "Day-1").exists():
            return p
        if p == p.parent:
            raise FileNotFoundError("Could not locate project root (expected a Day-1 folder).")
        p = p.parent

def default_paths(project_root: Path) -> dict:
    """
    Centralize important paths so scripts are portable.
    """
    day1_db = project_root / "Day-1" / "data" / "warehouse" / "day1.duckdb"

    day9_art = project_root / "Day-9" / "artifacts"
    base_model = day9_art / "readmit_base_model.joblib"
    platt = day9_art / "readmit_platt_calibrator.joblib"
    contract = day9_art / "readmit_feature_cols.json"
    metadata = day9_art / "readmit_metadata.json"

    return {
        "project_root": project_root,
        "day1_db": day1_db,
        "day9_artifacts_dir": day9_art,
        "base_model_path": base_model,
        "platt_path": platt,
        "contract_path": contract,
        "metadata_path": metadata,
    }
