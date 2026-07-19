"""
Predictive platinum-response axis for the Platinum Window capability.

This module is DISTINCT from the prognostic PLATINUM_SCORE (FAP/CXCL10 elastic-net
Cox in scorer.py). It implements the manuscript's CXCL12/POSTN Core-13 elastic-net
LOGISTIC model that predicts platinum SENSITIVITY (a response label), not survival.

Provenance (frozen, discovery-only):
- Model:        Core-13 elastic-net logistic (C=0.1, l1_ratio=0.7, saga, class_weight=balanced)
- Non-zero:     CXCL12 (-0.14972954829), POSTN (-0.10359314419); intercept 0.0628711804
- Scaler:       per-gene training mean/std frozen from GSE30161 (n=58) log2 space
- Threshold:    frozen Youden J = 0.4152970707 (from training; NOT recalibrated to your data)
- Train label:  PFI-derived platinum sensitivity (PFI>=180d = sensitive) — survival-derived (leakage risk)
- Train balance: 48 sensitive / 10 resistant (EPV ~0.36 — low)

VERDICT (from live-fire out-of-distribution test on GSE63885, n=75):
- AUROC 0.638 (95% CI 0.513-0.764), p=0.031; nested-CV 0.592 +/- 0.112.
- 0/28 single genes survive FDR<0.05 out-of-distribution.
- STATUS: INCONCLUSIVE. Discovery-grade. NOT validated. NOT for clinical routing.

Calibration gate:
- The continuous probability/ranking is emitted unconditionally (it is monotone in the
  linear predictor and safe to rank on).
- A THRESHOLDED sensitive/resistant CALL is emitted ONLY when the caller supplies
  reference-quantile-normalized input (normalization="quantile_to_reference"), because the
  frozen Youden threshold was set in the training distribution and does not transfer to an
  arbitrary platform/normalization without recalibration.

CrisPRO PLATINUM_WINDOW — Research Use Only.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Dict, Optional

# ── Frozen Core-13 predictive model (CXCL12/POSTN non-zero) ───────────────────
# Values are the canonical frozen manuscript coefficients. Kept inline (not read
# from artifacts at request time) so scoring is deterministic and dependency-free.

PREDICTIVE_MODEL_NAME = "core13_elasticnet_logistic"
PREDICTIVE_MODEL_STATUS = "FROZEN_DISCOVERY_ONLY"
PREDICTIVE_VERDICT = "INCONCLUSIVE"

# Non-zero coefficients only (all other Core-13 genes have coefficient 0.0).
PREDICTIVE_COEFFICIENTS: Dict[str, float] = {
    "CXCL12": -0.14972954829000132,
    "POSTN": -0.10359314418707691,
}
PREDICTIVE_INTERCEPT = 0.0628711803949403
PREDICTIVE_FROZEN_THRESHOLD_YOUDEN = 0.4152970707274718

# Per-gene training scaler (GSE30161, log2 space). Only genes with non-zero
# coefficients matter for scoring, but both are required for a valid call.
PREDICTIVE_SCALER_MEAN: Dict[str, float] = {
    "CXCL12": 4.381967241379311,
    "POSTN": 3.974105172413793,
}
PREDICTIVE_SCALER_SCALE: Dict[str, float] = {
    "CXCL12": 0.7905776882560323,
    "POSTN": 1.7117571284202044,
}

# Out-of-distribution performance (frozen, from live-fire on GSE63885).
PREDICTIVE_OOD_EVIDENCE = {
    "test_cohort": "GSE63885",
    "n": 75,
    "auroc": 0.6385,
    "auroc_ci95": [0.5128, 0.7641],
    "delong_p": 0.0308,
    "nested_cv_auroc_mean": 0.592,
    "nested_cv_auroc_sd": 0.112,
    "verdict": "INCONCLUSIVE",
    "note": (
        "Single positive out-of-distribution signal at nominal significance; wide CI, "
        "low sensitivity at frozen threshold, survival-derived training label. "
        "Discovery-grade. Not validated. Not for clinical routing."
    ),
}


def predictive_model_fingerprint() -> str:
    """Deterministic SHA-256 over the frozen predictive model spec (for provenance)."""
    payload = json.dumps(
        {
            "name": PREDICTIVE_MODEL_NAME,
            "coefficients": PREDICTIVE_COEFFICIENTS,
            "intercept": PREDICTIVE_INTERCEPT,
            "threshold": PREDICTIVE_FROZEN_THRESHOLD_YOUDEN,
            "scaler_mean": PREDICTIVE_SCALER_MEAN,
            "scaler_scale": PREDICTIVE_SCALER_SCALE,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _sigmoid(x: float) -> float:
    # Numerically stable logistic.
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def compute_platinum_response_score(
    gene_values: Dict[str, Optional[float]],
    normalization: str = "raw",
    input_is_log2: bool = True,
) -> Dict[str, object]:
    """
    Compute the predictive PLATINUM_RESPONSE_SCORE (probability of platinum SENSITIVITY).

    Parameters
    ----------
    gene_values : dict
        Must contain CXCL12 and POSTN. Values are expression in log2 space by default
        (the training scaler was fit in log2 space). If input_is_log2 is False, a log2(x+1)
        transform is applied before scaling.
    normalization : str
        "quantile_to_reference" unlocks a thresholded sensitive/resistant CALL. Any other
        value (default "raw") returns the probability/ranking but suppresses the call.
    input_is_log2 : bool
        Whether the provided CXCL12/POSTN are already log2-transformed.

    Returns
    -------
    dict with:
        PLATINUM_RESPONSE_SCORE            : float in [0,1] (P(sensitive)) or None if inputs missing
        platinum_response_verdict          : "INCONCLUSIVE"
        platinum_response_call             : "sensitive" | "resistant" | None (None unless calibrated)
        platinum_response_calibration_required : bool
        platinum_response_calibrated       : bool
        platinum_response_axis_note        : str
        platinum_response_model            : provenance sub-dict
    """
    required = ["CXCL12", "POSTN"]
    missing = [g for g in required if gene_values.get(g) is None]

    base = {
        "platinum_response_verdict": PREDICTIVE_VERDICT,
        "platinum_response_calibration_required": True,
        "platinum_response_model": {
            "name": PREDICTIVE_MODEL_NAME,
            "status": PREDICTIVE_MODEL_STATUS,
            "non_zero_coefficients": PREDICTIVE_COEFFICIENTS,
            "intercept": PREDICTIVE_INTERCEPT,
            "frozen_threshold_youden": PREDICTIVE_FROZEN_THRESHOLD_YOUDEN,
            "train_cohort": "GSE30161 (n=58, PFI-derived label, EPV~0.36)",
            "ood_evidence": PREDICTIVE_OOD_EVIDENCE,
            "model_fingerprint_sha256": predictive_model_fingerprint(),
        },
        "platinum_response_axis_note": (
            "PREDICTIVE platinum-response axis (CXCL12/POSTN), distinct from the prognostic "
            "PLATINUM_SCORE (FAP/CXCL10 survival). Verdict INCONCLUSIVE / discovery-grade. "
            "Provided for research ranking only; do NOT use for clinical routing."
        ),
    }

    if missing:
        base.update({
            "PLATINUM_RESPONSE_SCORE": None,
            "platinum_response_call": None,
            "platinum_response_calibrated": False,
            "platinum_response_axis_note": (
                base["platinum_response_axis_note"]
                + f" Score not computed: missing required gene(s) {missing}."
            ),
        })
        return base

    # Linear predictor in scaled space.
    lp = PREDICTIVE_INTERCEPT
    for gene, coef in PREDICTIVE_COEFFICIENTS.items():
        raw = float(gene_values[gene])
        if not input_is_log2:
            raw = math.log2(raw + 1.0)
        mean = PREDICTIVE_SCALER_MEAN[gene]
        scale = PREDICTIVE_SCALER_SCALE[gene]
        z = (raw - mean) / scale if scale > 0 else 0.0
        lp += coef * z

    prob = _sigmoid(lp)

    # Thresholded call ONLY when calibrated to the reference distribution.
    calibrated = (normalization == "quantile_to_reference")
    if calibrated:
        call = "sensitive" if prob >= PREDICTIVE_FROZEN_THRESHOLD_YOUDEN else "resistant"
    else:
        call = None

    base.update({
        "PLATINUM_RESPONSE_SCORE": round(prob, 4),
        "platinum_response_call": call,
        "platinum_response_calibrated": calibrated,
    })
    return base
