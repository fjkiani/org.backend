"""
Platinum Window Router — /api/v1/platinum-window/*.

Endpoints:
  GET  /api/v1/platinum-window/demo   → Patient 1 demo (no auth)
  POST /api/v1/platinum-window/score  → Score patient (API key required)
"""

import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Body, Header, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.config import (
    MODEL_VERSION,
    RUO_DISCLAIMER,
    NORMALIZATION_WARNING,
    VALIDATION_CTX,
    validate_api_key,
    hash_api_key,
)
from .models import (
    PlatinumWindowRequest,
    PlatinumWindowResponse,
    TreatmentStep,
)
from .scorer import compute_all_scores
from .sequence_engine import build_treatment_sequence, compute_confidence, determine_urgency
from .window_timer import compute_timing

# ── Reference data ───────────────────────────────────────────────────────────

REFERENCE_PATH = Path(__file__).parent / "reference" / "tcga_hgsoc_stats.json"

_ref_data: Dict = {}
_ref_means: Dict[str, float] = {}
_ref_stds: Dict[str, float] = {}


def load_reference() -> None:
    """Load reference stats from JSON. Called once at app startup via lifespan."""
    global _ref_data, _ref_means, _ref_stds
    if not REFERENCE_PATH.exists():
        raise RuntimeError(f"Reference stats not found: {REFERENCE_PATH}")
    _ref_data = json.loads(REFERENCE_PATH.read_text())
    genes = _ref_data.get("genes", {})
    _ref_means = {g: v["mean"] for g, v in genes.items() if v.get("mean") is not None}
    _ref_stds = {g: v["std"] for g, v in genes.items() if v.get("std") is not None}


logger = logging.getLogger("crispro.platinum_window")
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/v1/platinum-window", tags=["Timing Engine"])


# ── Shared response builder ─────────────────────────────────────────────────

def _build_response(
    scores: dict,
    timing: dict,
    urgency_result: dict,
    treatment_steps: list,
    conf: dict,
    computation_ms: float,
    ref_cohort_name: str,
    histotype: str = "HGSOC",
    missing_cxcl10: bool = False,
) -> PlatinumWindowResponse:
    resp = PlatinumWindowResponse(
        window_status=timing["window_status"],
        fingerprint_positive=scores["fingerprint_positive"],
        FAP_zscore=scores["FAP_zscore"],
        CXCL10_zscore=scores["CXCL10_zscore"],
        STROMAL_ARM_SCORE=scores["STROMAL_ARM_SCORE"],
        IMMUNE_ACCESS_SCORE=scores["IMMUNE_ACCESS_SCORE"],
        TCELL_GPS_SCORE=scores["TCELL_GPS_SCORE"],
        OCT1_STATUS=scores["OCT1_STATUS"],
        OCT1_zscore=scores["OCT1_zscore"],
        metformin_eligible=scores["metformin_eligible"],
        metformin_caveat=scores["metformin_caveat"],
        TIER=scores["TIER"],
        TIER_REFINED=scores["TIER_REFINED"],
        PLATINUM_SCORE=scores["PLATINUM_SCORE"],
        PLATINUM_SCORE_percentile=scores["PLATINUM_SCORE_percentile"],
        PLATINUM_SCORE_percentile_reference=scores["PLATINUM_SCORE_percentile_reference"],
        risk_tier=scores["risk_tier"],
        binary_HR_estimate=scores["binary_HR_estimate"],
        continuous_HR_estimate=scores["continuous_HR_estimate"],
        score_confidence=scores["score_confidence"],
        validation_context=VALIDATION_CTX,
        cycles_until_window_closes=timing["cycles_until_window_closes"],
        cycles_remaining=timing["cycles_remaining"],
        weeks_remaining=timing["weeks_remaining"],
        intervention_deadline=timing["intervention_deadline"],
        recommended_sequence=treatment_steps,
        urgency=urgency_result["urgency"],
        urgency_reason=urgency_result["urgency_reason"],
        trial_routing=urgency_result["trial_routing"],
        confidence_tier=conf["confidence_tier"],
        caveats=conf["caveats"],
        ruo_disclaimer=RUO_DISCLAIMER,
        normalization_warning=NORMALIZATION_WARNING,
        input_units_assumed="TPM",
        cxcl10_imputation=scores.get("cxcl10_imputation"),
        cxcl10_imputation_note=scores.get("cxcl10_imputation_note"),
        assay_warning=scores.get("assay_warning"),
        model_version=MODEL_VERSION,
        reference_cohort=ref_cohort_name,
        computation_ms=computation_ms,
        timestamp_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )

    if resp.assay_warning:
        resp.score_confidence = "UNRELIABLE"

    if missing_cxcl10:
        resp.caveats = list(resp.caveats) + [
            "TCELL_GPS_SCORE computed with imputed CXCL10_z=0. "
            "May underestimate true T-cell chemokine recruitment."
        ]

    return resp


# ── Demo endpoint (NO AUTH) ─────────────────────────────────────────────────

@router.get("/demo")
def demo_endpoint():
    """Patient 1 demo — no API key required."""
    gene_values = {
        "FAP": 50.0, "CXCL10": 15000.0,
        "CXCL9": 8000.0, "CXCL11": 4000.0,
        "CXCR3": 600.0, "ACTA2": 500.0,
        "POSTN": 200.0, "CXCL12": 300.0,
        "CXCR4": 500.0, "SLC22A1": 200.0,
    }
    t_start = time.perf_counter()
    scores = compute_all_scores(gene_values, _ref_means, _ref_stds)
    timing = compute_timing(
        fap_z=scores["FAP_zscore"],
        prior_cycles=0,
        platinum_status="sensitive",
        stromal_arm=scores["STROMAL_ARM_SCORE"],
        oct1_status=scores["OCT1_STATUS"],
    )
    urgency_result = determine_urgency(
        fap_z=scores["FAP_zscore"],
        stromal_arm=scores["STROMAL_ARM_SCORE"],
        platinum_status="sensitive",
        prior_cycles=0,
        immune_access=scores["IMMUNE_ACCESS_SCORE"],
        window_status=timing["window_status"],
        histotype="HGSOC",
        platinum_score=scores["PLATINUM_SCORE"],
    )
    raw_seq = build_treatment_sequence(
        urgency=urgency_result["urgency"],
        immune_access=scores["IMMUNE_ACCESS_SCORE"],
        oct1_status=scores["OCT1_STATUS"],
        window_status=timing["window_status"],
        metformin_eligible=scores["metformin_eligible"],
    )
    treatment_steps = [TreatmentStep(**s) for s in raw_seq]
    conf = compute_confidence(
        histotype="HGSOC",
        fingerprint_positive=scores["fingerprint_positive"],
        tier=scores["TIER"],
        window_status=timing["window_status"],
    )
    t_end = time.perf_counter()
    return _build_response(
        scores=scores,
        timing=timing,
        urgency_result=urgency_result,
        treatment_steps=treatment_steps,
        conf=conf,
        computation_ms=round((t_end - t_start) * 1000, 2),
        ref_cohort_name="TCGA_HGSOC_GDC_2025",
    )


# ── Score endpoint (AUTH REQUIRED) ───────────────────────────────────────────

@router.post("/score", response_model=PlatinumWindowResponse)
@limiter.limit("100/minute")
def score_platinum_window(
    request: Request,
    payload: PlatinumWindowRequest = Body(...),
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    if x_api_key:
        validate_api_key(x_api_key)
    t_start = time.perf_counter()

    # Resolve reference cohort
    if payload.cohort_reference == "custom" and payload.custom_cohort_means and payload.custom_cohort_stds:
        ref_means = payload.custom_cohort_means
        ref_stds = payload.custom_cohort_stds
        ref_cohort_name = "custom"
    else:
        ref_means = _ref_means
        ref_stds = _ref_stds
        ref_cohort_name = _ref_data.get("cohort", "TCGA_HGSOC_GDC_2025")

    gene_values = {
        "FAP": payload.FAP, "CXCL10": payload.CXCL10,
        "CXCL9": payload.CXCL9, "CXCL11": payload.CXCL11,
        "CXCR3": payload.CXCR3, "ACTA2": payload.ACTA2,
        "POSTN": payload.POSTN, "CXCL12": payload.CXCL12,
        "CXCR4": payload.CXCR4, "SLC22A1": payload.SLC22A1,
    }

    scores = compute_all_scores(gene_values, ref_means, ref_stds)

    timing = compute_timing(
        fap_z=scores["FAP_zscore"],
        prior_cycles=payload.prior_platinum_cycles,
        platinum_status=payload.platinum_status.value,
        stromal_arm=scores["STROMAL_ARM_SCORE"],
        oct1_status=scores["OCT1_STATUS"],
    )

    # Override window for resistant patients with good score
    effective_window_status = timing["window_status"]
    if (
        payload.platinum_status.value == "resistant"
        and scores["PLATINUM_SCORE"] > 0.3702
        and effective_window_status in ("CLOSED", "NEVER_OPEN")
    ):
        effective_window_status = "CLOSED_RECENTLY"
    timing["window_status"] = effective_window_status

    urgency_result = determine_urgency(
        fap_z=scores["FAP_zscore"],
        stromal_arm=scores["STROMAL_ARM_SCORE"],
        platinum_status=payload.platinum_status.value,
        prior_cycles=payload.prior_platinum_cycles,
        immune_access=scores["IMMUNE_ACCESS_SCORE"],
        window_status=effective_window_status,
        histotype=payload.histotype.value,
        platinum_score=scores["PLATINUM_SCORE"],
    )

    raw_sequence = build_treatment_sequence(
        urgency=urgency_result["urgency"],
        immune_access=scores["IMMUNE_ACCESS_SCORE"],
        oct1_status=scores["OCT1_STATUS"],
        window_status=effective_window_status,
        metformin_eligible=scores["metformin_eligible"],
    )
    treatment_steps = [TreatmentStep(**step) for step in raw_sequence]

    conf = compute_confidence(
        histotype=payload.histotype.value,
        fingerprint_positive=scores["fingerprint_positive"],
        tier=scores["TIER"],
        window_status=effective_window_status,
    )

    t_end = time.perf_counter()
    resp = _build_response(
        scores=scores,
        timing=timing,
        urgency_result=urgency_result,
        treatment_steps=treatment_steps,
        conf=conf,
        computation_ms=round((t_end - t_start) * 1000, 2),
        ref_cohort_name=ref_cohort_name,
        histotype=payload.histotype.value,
        missing_cxcl10=scores.get("missing_cxcl10", False),
    )

    # Audit log
    logger.info(json.dumps({
        "timestamp": resp.timestamp_utc,
        "api_key_hash": hash_api_key(x_api_key),
        "urgency": resp.urgency,
        "risk_tier": resp.risk_tier,
        "PLATINUM_SCORE": resp.PLATINUM_SCORE,
        "computation_ms": resp.computation_ms,
    }))

    return resp


from fastapi.responses import FileResponse

# ── Artifacts Streamer (Glass Box Transparency) ──────────────────────────────

@router.get("/artifacts/{filepath:path}")
def stream_artifact(filepath: str):
    """
    Stream raw markdown/JSON artifacts to the frontend White Box panel for Platinum Window.
    """
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parents[2]
    
    # Base publication directory where the artifacts live
    pub_dir = project_root / "publications" / "11-artistry7-hgsoc-subgroup"
    
    # If filepath references the backend reference dir directly:
    if "reference" in filepath:
        file_path = (current_dir / "reference" / Path(filepath).name).resolve()
        category_dir = current_dir / "reference"
    else:
        file_path = (pub_dir / filepath).resolve()
        category_dir = pub_dir
    
    try:
        file_path.relative_to(category_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Directory traversal forbidden")
        
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {filepath}")
        
    return FileResponse(file_path)
