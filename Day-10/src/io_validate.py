import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd


@dataclass
class ValidationResult:
    df_for_model: pd.DataFrame
    df_original: pd.DataFrame
    warnings: List[str]
    schema_hash: str
    has_label: bool


def load_contract(contract_path) -> Dict:
    with open(contract_path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_schema_hash(df: pd.DataFrame) -> str:
    parts = [f"{c}:{str(df[c].dtype)}" for c in df.columns]
    payload = "|".join(parts).encode("utf-8")
    return hashlib.md5(payload).hexdigest()


def _missingness_summary(df: pd.DataFrame) -> pd.DataFrame:
    miss = df.isna().sum()
    rate = miss / len(df) if len(df) else miss
    out = pd.DataFrame({"missing_count": miss, "missing_rate": rate})
    return out.sort_values("missing_rate", ascending=False)


def validate_input(df: pd.DataFrame, contract: Dict, mode: str = "score") -> ValidationResult:
    if mode not in {"score", "evaluate"}:
        raise ValueError("mode must be 'score' or 'evaluate'.")

    warnings: List[str] = []

    id_cols = contract["id_cols"]
    feature_cols = contract["feature_cols"]
    numeric_cols = contract["numeric_cols"]
    categorical_cols = contract["categorical_cols"]

    # --- Required ID columns ---
    required_ids = [c for c in id_cols if c != "label"]
    missing_required = [c for c in required_ids if c not in df.columns]
    if missing_required:
        raise ValueError(f"Missing required ID columns: {missing_required}")

    has_label = "label" in df.columns
    if mode == "evaluate" and not has_label:
        raise ValueError("mode='evaluate' requires a 'label' column in the input.")

    # --- Leakage denylist ---
    deny = {"readmitted", "y_readmit_30", "outcome", "target"}
    present_deny = sorted([c for c in df.columns if c in deny])
    if present_deny:
        warnings.append(f"Leakage columns present (will be DROPPED): {present_deny}")
        df = df.drop(columns=present_deny)

    # --- Feature availability ---
    missing_features = [c for c in feature_cols if c not in df.columns]
    if missing_features:
        raise ValueError(
            "Input is missing required feature columns needed by the model. "
            f"Missing: {missing_features[:20]}{'...' if len(missing_features) > 20 else ''}"
        )

    # --- Keep only needed columns ---
    keep = required_ids + feature_cols + (["label"] if has_label else [])
    extra = [c for c in df.columns if c not in keep]
    if extra:
        warnings.append(f"Extra columns ignored (not used by model): {extra[:20]}{'...' if len(extra) > 20 else ''}")
    df = df[keep].copy()

    # --- Basic dtype normalization ---
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in categorical_cols:
        df[c] = df[c].astype("object")

    # --- Missingness warnings ---
    miss = _missingness_summary(df[feature_cols])
    high_miss = miss[miss["missing_rate"] > 0.25]
    if not high_miss.empty:
        warnings.append(f"High missingness (>25%) in features: {high_miss.index.tolist()[:15]}")

    # --- Label checks (if present) ---
    if has_label:
        df["label"] = pd.to_numeric(df["label"], errors="coerce")
        bad = int(df["label"].isna().sum())
        if bad > 0:
            warnings.append(f"Label has {bad} non-numeric/NA values after coercion.")

    schema_hash = compute_schema_hash(df)
    df_for_model = df[feature_cols].copy()

    return ValidationResult(
        df_for_model=df_for_model,
        df_original=df,
        warnings=warnings,
        schema_hash=schema_hash,
        has_label=has_label,
    )
