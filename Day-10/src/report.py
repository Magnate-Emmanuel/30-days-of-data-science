#from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss, log_loss

def clip01(p, eps=1e-15):
    p = np.asarray(p, dtype=float)
    return np.clip(p, eps, 1 - eps)

def compute_metrics(y_true, p):
    y_true = np.asarray(y_true).astype(int)
    p = np.asarray(p).astype(float)
    pc = clip01(p)
    return {
        "prevalence": float(y_true.mean()),
        "mean_p": float(p.mean()),
        "median_p": float(np.median(p)),
        "pr_auc": float(average_precision_score(y_true, p)),
        "roc_auc": float(roc_auc_score(y_true, p)),
        "brier": float(brier_score_loss(y_true, p)),
        "logloss": float(log_loss(y_true, pc, labels=[0, 1])),
    }

def topk(y_true, p, frac):
    y_true = np.asarray(y_true).astype(int)
    p = np.asarray(p).astype(float)
    n = len(y_true)
    k = max(1, int(np.floor(frac * n)))
    idx = np.argsort(-p)[:k]
    return {
        "top_frac": float(frac),
        "k": int(k),
        "captured": int(y_true[idx].sum()),
        "precision_at_k": float(y_true[idx].mean()),
        "threshold": float(np.quantile(p, 1 - frac)),
    }

def distribution_summary(p):
    p = np.asarray(p).astype(float)
    q = np.quantile(p, [0.0, 0.01, 0.05, 0.1, 0.5, 0.9, 0.95, 0.99, 1.0])
    return {
        "mean": float(p.mean()),
        "median": float(np.median(p)),
        "quantiles": {
            "q0": float(q[0]),
            "q1": float(q[1]),
            "q5": float(q[2]),
            "q10": float(q[3]),
            "q50": float(q[4]),
            "q90": float(q[5]),
            "q95": float(q[6]),
            "q99": float(q[7]),
            "q100": float(q[8]),
        },
    }

def write_json(obj, path: Path):
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
