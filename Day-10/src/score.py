#from __future__ import annotations
import numpy as np
import pandas as pd
import joblib

def clip01(p, eps=1e-15):
    p = np.asarray(p, dtype=float)
    return np.clip(p, eps, 1 - eps)

def score_with_artifacts(
    df_for_model: pd.DataFrame,
    base_model_path,
    platt_path,
) -> dict:
    """
    Returns dict with p_raw and p_hat (calibrated).
    """
    base_model = joblib.load(base_model_path)
    platt = joblib.load(platt_path)

    p_raw = base_model.predict_proba(df_for_model)[:, 1]
    z = np.log(clip01(p_raw) / (1 - clip01(p_raw))).reshape(-1, 1)
    p_hat = platt.predict_proba(z)[:, 1]

    return {"p_raw": p_raw, "p_hat": p_hat}
