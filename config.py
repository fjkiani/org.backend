"""
CrisPRO Backend — Configuration & Constants.
All shared constants, auth helpers, and validation context live here.
"""

import os
import hashlib
from fastapi import HTTPException
from pydantic import BaseModel


# ── Version ──────────────────────────────────────────────────────────────────

MODEL_VERSION = "1.1.0"  # clinical-grade hardening: audit corrections + predictive axis + provenance

# ── Disclaimers ──────────────────────────────────────────────────────────────

RUO_DISCLAIMER = (
    "Research Use Only. Not for clinical decision-making "
    "without prospective validation. "
    "CrisPRO PLATINUM_WINDOW v1.0."
)

NORMALIZATION_WARNING = (
    "Input values assumed TPM (Transcripts Per Million). "
    "Reference distribution: TCGA-OV STAR-counts TPM "
    "(n=379-427 HGSOC samples, GDC 2025 release). "
    "Results INVALID if different normalization used "
    "without recalibration. Contact CrisPRO for platform-specific "
    "reference distributions."
)


# ── Validation Context ───────────────────────────────────────────────────────

from typing import Dict, Optional


class ClaimStatus(BaseModel):
    """Per-claim evidence status. See AUDIT.md / audit_ledger.json for full derivation."""
    claim: str
    status: str  # SUPPORTED | NOT_EXTERNALLY_REPLICATED | INCONCLUSIVE | UNVERIFIED
    evidence: str


class ValidationContext(BaseModel):
    # NOTE: cohorts_validated / patients_validated now reflect the ONLY claim that is
    # actually validated cross-cohort — the prognostic fingerprint (6 cohorts, n=1,236).
    # The prior "16 / 2,444 validated" framing was corrected (see AUDIT.md, CA-1/CA-2).
    cohorts_validated: int
    patients_validated: int
    validation_type: str
    data_type: str
    prospective_validation: bool
    clia_validated: bool
    regulatory_status: str
    OCT1_reference_n: int
    OCT1_reference_warning: str
    # Structured, per-claim honesty (replaces the flat overstated numbers).
    claim_status: Optional[Dict[str, ClaimStatus]] = None


VALIDATION_CTX = ValidationContext(
    cohorts_validated=6,
    patients_validated=1236,
    validation_type="retrospective_observational_cross_cohort",
    data_type="bulk_RNAseq",
    prospective_validation=False,
    clia_validated=False,
    regulatory_status="RUO — not for clinical decision-making",
    OCT1_reference_n=113,
    OCT1_reference_warning="Smaller reference sample than other markers. IHC confirmation recommended.",
    claim_status={
        "prognostic_fingerprint": ClaimStatus(
            claim="FAP_z<0 & CXCL10_z>0 fingerprint is prognostic for overall survival (cross-cohort).",
            status="SUPPORTED",
            evidence="Pooled cohort-stratified Cox, 6 cohorts, n=1,236, HR 0.677 (95% CI 0.551-0.832), p=2.04e-4. Independently recomputed from shipped artifacts.",
        ),
        "tier_survival_separation": ClaimStatus(
            claim="The 3-tier (TIER_1/2/3) system separates survival in external cohorts.",
            status="NOT_EXTERNALLY_REPLICATED",
            evidence="All shipped external manifests report validation_holds=false (GSE32062 log-rank p=0.93, GSE102073 p=0.48). Discovery/exploratory only.",
        ),
        "predictive_platinum_response": ClaimStatus(
            claim="CXCL12/POSTN model predicts platinum response.",
            status="INCONCLUSIVE",
            evidence="Out-of-distribution AUROC 0.638 (95% CI 0.513-0.764), p=0.031; nested-CV 0.592+/-0.112; survival-derived label; EPV~0.36. Discovery-grade, calibration-required.",
        ),
    },
)


# ── Auth ─────────────────────────────────────────────────────────────────────

VALID_API_KEYS: set[str] = set()
_raw_keys = os.getenv("VALID_API_KEYS", "")
if _raw_keys:
    VALID_API_KEYS = set(k.strip() for k in _raw_keys.split(",") if k.strip())


def validate_api_key(api_key: str) -> None:
    """Validate an API key. Skips auth in local dev (no VALID_API_KEYS configured)."""
    if not VALID_API_KEYS:
        return  # Local dev mode — no keys configured, allow all requests
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")


def hash_api_key(api_key: Optional[str]) -> str:
    """SHA-256 hash of API key for audit logging.

    Returns a sentinel for absent keys (local dev mode) instead of crashing.
    """
    if not api_key:
        return "no_api_key"
    return hashlib.sha256(api_key.encode()).hexdigest()
