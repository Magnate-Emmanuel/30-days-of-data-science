
import argparse
import json
from pathlib import Path
import pandas as pd
import joblib

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CSV with appointment_id, person_id, and feature columns")
    ap.add_argument("--output", required=True, help="Output CSV path")
    ap.add_argument("--budget_k", type=int, required=True, help="Daily SMS budget K")
    ap.add_argument("--strategy", choices=["risk","uplift"], default="uplift")
    ap.add_argument("--artifacts_dir", default=str(Path(__file__).resolve().parents[1] / "artifacts"))
    args = ap.parse_args()

    artifacts = Path(args.artifacts_dir)
    y0 = joblib.load(artifacts / "day19_outcome_mu0_pipe.joblib")
    y1 = joblib.load(artifacts / "day19_outcome_mu1_pipe.joblib")

    with open(artifacts / "DAY19_metadata.json","r") as f:
        meta = json.load(f)

    X_cols = meta["X_cols"]
    df = pd.read_csv(args.input)

    # minimal checks
    missing = [c for c in X_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in input: {missing}")

    X = df[X_cols].copy()
    mu0 = y0.predict_proba(X)[:,1]
    mu1 = y1.predict_proba(X)[:,1]
    uplift = mu0 - mu1

    out = df[["appointment_id","person_id"]].copy()
    out["p_no_show_no_sms"] = mu0
    out["p_no_show_sms"] = mu1
    out["uplift"] = uplift

    if args.strategy == "risk":
        out["score"] = out["p_no_show_no_sms"]
    else:
        out["score"] = out["uplift"]

    out = out.sort_values("score", ascending=False).reset_index(drop=True)
    out["rank"] = out.index + 1
    out["send_sms"] = (out["rank"] <= args.budget_k).astype(int)

    out.to_csv(args.output, index=False)

if __name__ == "__main__":
    main()
