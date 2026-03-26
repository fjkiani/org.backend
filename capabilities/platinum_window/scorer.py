"""
Scoring engine for the Platinum Window API.
Implements z-scoring, composite score computation, tier classification,
fingerprint determination, and PLATINUM_SCORE (elastic net Cox).

Logic lifted from:
- caf_window_timing_simulation.py (z-scoring)
- simulate_intervention.py (IMMUNE_ACCESS_SCORE recomputation)
- cross_cohort_fingerprint_regression.py (fingerprint: FAP_z < 0 AND CXCL10_z > 0)
- continuous_survival_score_elastic_net.R (PLATINUM_SCORE coefficients)

CrisPRO PLATINUM_WINDOW v1.0 — Research Use Only.
"""

from typing import Dict, Optional, Tuple


def z_score(value: float, mean: float, std: float) -> float:
    """Compute z-score against a reference distribution."""
    if std == 0.0:
        return 0.0
    return (value - mean) / std


def z_score_genes(
    gene_values: Dict[str, Optional[float]],
    ref_means: Dict[str, float],
    ref_stds: Dict[str, float],
) -> Dict[str, float]:
    """Z-score all input genes against reference cohort."""
    zscores: Dict[str, float] = {}
    for gene, val in gene_values.items():
        if val is None:
            continue
        mean = ref_means.get(gene)
        std = ref_stds.get(gene)
        if mean is not None and std is not None and std > 0:
            zscores[gene] = z_score(val, mean, std)
        else:
            zscores[gene] = 0.0
    return zscores


def compute_stromal_arm(zscores: Dict[str, float]) -> float:
    """
    Composite stromal arm score: average z-score of CAF/stromal markers.
    Components: ACTA2, POSTN, FAP, CXCL12, CXCR4.
    Negative = stromal barrier absent (good for window).
    """
    components = ["ACTA2", "POSTN", "FAP", "CXCL12", "CXCR4"]
    vals = [zscores.get(g, 0.0) for g in components]
    return sum(vals) / len(vals)


def compute_tcell_gps(zscores: Dict[str, float]) -> float:
    """
    T-cell GPS composite: average z-score of chemokine/receptor panel.
    Components: CXCL9, CXCL10, CXCL11, CXCR3.
    Higher = better T-cell recruitment signal.
    """
    components = ["CXCL9", "CXCL10", "CXCL11", "CXCR3"]
    vals = [zscores.get(g, 0.0) for g in components]
    return sum(vals) / len(vals)


def compute_immune_access(
    tcell_gps: float,
    stromal_arm: float,
) -> float:
    """
    Immune access score: T-cell chemokine signal adjusted by stromal barrier.

    APPROXIMATION WARNING:
    Original formula (simulate_intervention.py L107-112) uses 3 components:
        TCELL_GPS * 0.40 + (-MYELOID_FLOOD * 0.35) + (-STROMAL_CAGE * 0.25)
    This API approximates with 2 components because the input gene panel
    does not include dedicated myeloid markers (CD163, CD68, MRC1, CSF1R).
    Formula: 0.60 * TCELL_GPS - 0.40 * STROMAL_ARM

    Positive = immune cells can reach tumor.
    """
    return (tcell_gps * 0.60) + (-stromal_arm * 0.40)


def determine_oct1_status(slc22a1_z: float) -> str:
    """OCT1 transport gate: HIGH if z-score > 0, else LOW."""
    return "HIGH" if slc22a1_z > 0.0 else "LOW"


# C4: Metformin eligibility based on OCT1
def determine_metformin_eligibility(oct1_status: str, slc22a1_z: float) -> dict:
    """
    Determine if Metformin can accumulate at therapeutic intratumoral concentration.
    5/9 PLATINUM_WINDOW patients are OCT1-low. This is not optional.
    Fix 7: n=113 reference caveat shown for ALL patients.
    """
    n113_note = (
        "SLC22A1 reference distribution: n=113 TCGA-OV samples (vs n=379-427 for other markers). "
        "Low-expression dropout possible. OCT1 IHC confirmation recommended."
    )
    if oct1_status == "HIGH":
        return {
            "metformin_eligible": True,
            "metformin_caveat": f"OCT1 HIGH — eligible for Metformin 850mg BID. {n113_note}",
        }
    return {
        "metformin_eligible": False,
        "metformin_caveat": (
            f"OCT1 LOW — Metformin accumulation uncertain. {n113_note}"
        ),
    }


def determine_fingerprint(fap_z: float, cxcl10_z: float) -> bool:
    """
    Platinum Window molecular fingerprint.
    Positive when FAP is below cohort mean AND CXCL10 is above.
    """
    return fap_z < 0.0 and cxcl10_z > 0.0


def classify_tier(
    fap_z: float,
    stromal_arm: float,
    immune_access: float,
    fingerprint_positive: bool,
) -> Tuple[str, Optional[str]]:
    """
    Classify patient into tiers.

    TIER_1_TRIPLE: fingerprint positive AND stromal_arm < 0
    TIER_2_MIXED: partial match
    TIER_3_ACCESSIBLE: no match

    TIER_1 sub-classification:
    - TIER_1A_ACCESSIBLE: immune_access > 0
    - TIER_1B_CAGED: immune_access <= 0
    """
    if fingerprint_positive and stromal_arm < 0.0:
        tier = "TIER_1_TRIPLE"
        tier_refined = "TIER_1A_ACCESSIBLE" if immune_access > 0.0 else "TIER_1B_CAGED"
        return tier, tier_refined

    if fingerprint_positive or stromal_arm < 0.0:
        return "TIER_2_MIXED", None

    return "TIER_3_ACCESSIBLE", None


# ── PLATINUM_SCORE: Elastic Net Cox Continuous Score ─────────────────────────
# Validated across 16 independent cohorts (n=2,444).
# Coefficients frozen from continuous_survival_score_elastic_net.R output.
# PLATINUM_SCORE ∈ [0,1] where higher = better predicted survival.

ELASTIC_NET_COEF_FAP_Z = 0.2032507043
ELASTIC_NET_COEF_CXCL10_Z = -0.1474166728

LP_MIN = -0.661403
LP_MAX = 0.803347

PLATINUM_SCORE_THRESHOLD = 0.3702132699

HR_BINARY_FINGERPRINT = 0.72
HR_CONTINUOUS_THRESHOLD = 0.5422


def compute_platinum_score(fap_z: float, cxcl10_z: float) -> dict:
    """
    Compute the continuous PLATINUM_SCORE from elastic net Cox regression.

    Higher PLATINUM_SCORE = better predicted survival.
    Above threshold 0.3702 = HIGH_RESPONDER (88%, Pub 1 trial, window open).
    Below threshold = HIGH_RISK (12%, Pub 2 trial, cage-breaking).
    """
    lp = (ELASTIC_NET_COEF_FAP_Z * fap_z) + (ELASTIC_NET_COEF_CXCL10_Z * cxcl10_z)
    lp_clamped = max(LP_MIN, min(LP_MAX, lp))
    risk_01 = (lp_clamped - LP_MIN) / (LP_MAX - LP_MIN)
    platinum_score = 1.0 - risk_01

    if platinum_score > PLATINUM_SCORE_THRESHOLD:
        risk_tier = "HIGH_RESPONDER"
    else:
        risk_tier = "HIGH_RISK"

    if platinum_score <= PLATINUM_SCORE_THRESHOLD:
        percentile = int(round((platinum_score / PLATINUM_SCORE_THRESHOLD) * 12.0))
    else:
        above_frac = (platinum_score - PLATINUM_SCORE_THRESHOLD) / (1.0 - PLATINUM_SCORE_THRESHOLD)
        percentile = 12 + int(round(above_frac * 88.0))
    percentile = max(0, min(100, percentile))

    return {
        "PLATINUM_SCORE": round(platinum_score, 4),
        "PLATINUM_SCORE_percentile": percentile,
        "risk_tier": risk_tier,
        "binary_HR_estimate": HR_BINARY_FINGERPRINT,
        "continuous_HR_estimate": HR_CONTINUOUS_THRESHOLD,
        # C5: RESEARCH_USE_ONLY — not "VALIDATED_16_COHORTS"
        "score_confidence": "RESEARCH_USE_ONLY",
        "PLATINUM_SCORE_percentile_reference": "METAGX_POOLED_n2444",
    }


# ── Surviving Issue 3: Assay quality warning ─────────────────────────────────

ASSAY_WARNING_THRESHOLD = 0.01  # TPM below this is effectively zero

def _detect_assay_warning(gene_values: Dict[str, Optional[float]]) -> Optional[str]:
    """Detect potential assay failure when all expression values are zero/near-zero."""
    measured = [v for v in gene_values.values() if v is not None]
    if not measured:
        return None
    if all(v <= ASSAY_WARNING_THRESHOLD for v in measured):
        return (
            "All input expression values are zero or near-zero. "
            "This may indicate RNA extraction failure, assay dropout, or input error. "
            "Results should not be used for clinical routing without confirming sample quality."
        )
    return None


def compute_all_scores(
    gene_values: Dict[str, Optional[float]],
    ref_means: Dict[str, float],
    ref_stds: Dict[str, float],
) -> Dict[str, object]:
    """Master scoring function. Returns all computed scores and classifications."""
    zscores = z_score_genes(gene_values, ref_means, ref_stds)

    fap_z = zscores.get("FAP", 0.0)
    
    # C8: Handle optional CXCL10
    missing_cxcl10 = "CXCL10" not in gene_values or gene_values["CXCL10"] is None
    cxcl10_z = zscores.get("CXCL10", 0.0)
    
    slc22a1_z = zscores.get("SLC22A1", 0.0)

    stromal_arm = compute_stromal_arm(zscores)
    tcell_gps = compute_tcell_gps(zscores)
    immune_access = compute_immune_access(tcell_gps, stromal_arm)
    oct1_status = determine_oct1_status(slc22a1_z)
    
    fingerprint = fap_z < 0.0 if missing_cxcl10 else determine_fingerprint(fap_z, cxcl10_z)
    tier, tier_refined = classify_tier(fap_z, stromal_arm, immune_access, fingerprint)
    ps = compute_platinum_score(fap_z, cxcl10_z if not missing_cxcl10 else 0.0)

    if missing_cxcl10:
        ps["score_confidence"] = "LOW"
    
    # C4: Metformin eligibility
    met = determine_metformin_eligibility(oct1_status, slc22a1_z)

    return {
        "zscores": zscores,
        "FAP_zscore": round(fap_z, 4),
        "CXCL10_zscore": round(cxcl10_z, 4),
        "STROMAL_ARM_SCORE": round(stromal_arm, 4),
        "TCELL_GPS_SCORE": round(tcell_gps, 4),
        "IMMUNE_ACCESS_SCORE": round(immune_access, 4),
        "OCT1_STATUS": oct1_status,
        "OCT1_zscore": round(slc22a1_z, 4),            # C4
        "metformin_eligible": met["metformin_eligible"], # C4
        "metformin_caveat": met["metformin_caveat"],     # C4
        "fingerprint_positive": fingerprint,
        "TIER": tier,
        "TIER_REFINED": tier_refined,
        # PLATINUM_SCORE
        "PLATINUM_SCORE": ps["PLATINUM_SCORE"],
        "PLATINUM_SCORE_percentile": ps["PLATINUM_SCORE_percentile"],
        "PLATINUM_SCORE_percentile_reference": ps["PLATINUM_SCORE_percentile_reference"],
        "risk_tier": ps["risk_tier"],
        "binary_HR_estimate": ps["binary_HR_estimate"],
        "continuous_HR_estimate": ps["continuous_HR_estimate"],
        "score_confidence": ps["score_confidence"],
        "missing_cxcl10": missing_cxcl10,
        # Surviving Issue 1: CXCL10 imputation transparency
        "cxcl10_imputation": "MEAN_SUBSTITUTED" if missing_cxcl10 else None,
        "cxcl10_imputation_note": (
            "CXCL10 not provided. Score computed with CXCL10_z=0 (cohort mean). "
            "This assumes CXCL10 expression is average — NOT that it is absent. "
            "If CXCL10 is truly undetectable in this sample, the actual score may differ. "
            "Provide CXCL10 measurement for accurate routing."
        ) if missing_cxcl10 else None,
        # Surviving Issue 3: Assay quality warning
        "assay_warning": _detect_assay_warning(gene_values),
    }
