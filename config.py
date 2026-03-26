"""
CrisPRO Backend — Configuration & Constants.
All shared constants, auth helpers, and validation context live here.
"""

import os
import hashlib
from fastapi import HTTPException
from pydantic import BaseModel


# ── Version ──────────────────────────────────────────────────────────────────

MODEL_VERSION = "1.0.0"

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

class ValidationContext(BaseModel):
    cohorts_validated: int
    patients_validated: int
    validation_type: str
    data_type: str
    prospective_validation: bool
    clia_validated: bool
    regulatory_status: str
    OCT1_reference_n: int
    OCT1_reference_warning: str


VALIDATION_CTX = ValidationContext(
    cohorts_validated=16,
    patients_validated=2444,
    validation_type="retrospective_observational",
    data_type="bulk_RNAseq",
    prospective_validation=False,
    clia_validated=False,
    regulatory_status="RUO — not for clinical decision-making",
    OCT1_reference_n=113,
    OCT1_reference_warning="Smaller reference sample than other markers. IHC confirmation recommended.",
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


def hash_api_key(api_key: str) -> str:
    """SHA-256 hash of API key for audit logging."""
    return hashlib.sha256(api_key.encode()).hexdigest()
