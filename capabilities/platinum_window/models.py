"""
Pydantic v2 request/response models for Platinum Window Clinical Decision Support API.
CrisPRO PLATINUM_WINDOW v1.0 — Research Use Only.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from backend.config import ValidationContext


# ── Enums ────────────────────────────────────────────────────────────────────

class PlatinumStatus(str, Enum):
    SENSITIVE = "sensitive"
    RESISTANT = "resistant"
    NAIVE = "naive"


class Histotype(str, Enum):
    HGSOC = "HGSOC"
    PAAD = "PAAD"
    OTHER = "other"


class WindowStatus(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    CLOSED_RECENTLY = "CLOSED_RECENTLY"   # C6: resistant but good score
    NEVER_OPEN = "NEVER_OPEN"


class Urgency(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    STANDARD = "STANDARD"
    CAGE_BREAKING_FIRST = "CAGE_BREAKING_FIRST"
    INELIGIBLE = "INELIGIBLE"


class OCT1Status(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class Tier(str, Enum):
    TIER_1_TRIPLE = "TIER_1_TRIPLE"
    TIER_2_MIXED = "TIER_2_MIXED"
    TIER_3_ACCESSIBLE = "TIER_3_ACCESSIBLE"


class TierRefined(str, Enum):
    TIER_1A_ACCESSIBLE = "TIER_1A_ACCESSIBLE"
    TIER_1B_CAGED = "TIER_1B_CAGED"


class ConfidenceTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CohortReference(str, Enum):
    TCGA = "TCGA"
    CUSTOM = "custom"


# ── Request ──────────────────────────────────────────────────────────────────

class PlatinumWindowRequest(BaseModel):
    """POST /api/v1/platinum-window/score request body."""

    # Required gene expression values (TPM/FPKM from RNA-seq or normalized intensity)
    FAP: float = Field(..., ge=0.0, description="Fibroblast Activation Protein expression")
    CXCL10: Optional[float] = Field(None, ge=0.0, description="T-cell GPS chemokine (optional)")
    CXCL9: float = Field(..., ge=0.0, description="T-cell GPS chemokine (secondary)")
    CXCL11: float = Field(..., ge=0.0, description="T-cell GPS chemokine (secondary)")
    CXCR3: float = Field(..., ge=0.0, description="T-cell GPS receptor")
    ACTA2: float = Field(..., ge=0.0, description="Stromal/CAF marker")
    POSTN: float = Field(..., ge=0.0, description="CAF marker")
    CXCL12: float = Field(..., ge=0.0, description="Stromal cage marker")
    CXCR4: float = Field(..., ge=0.0, description="Stromal cage marker")
    SLC22A1: float = Field(..., ge=0.0, description="OCT1 — Metformin transport gate")

    # Required clinical fields
    platinum_status: PlatinumStatus
    prior_platinum_cycles: int = Field(..., ge=0, description="Number of platinum cycles already administered")
    histotype: Histotype

    # Optional cohort reference for z-scoring
    cohort_reference: CohortReference = CohortReference.TCGA
    custom_cohort_means: Optional[Dict[str, float]] = None
    custom_cohort_stds: Optional[Dict[str, float]] = None


# ── Response sub-models ──────────────────────────────────────────────────────

class TreatmentStep(BaseModel):
    cycle: str
    drugs: List[str]
    rationale: str
    condition: Optional[str] = None


class PlatinumWindowResponse(BaseModel):
    """POST /api/v1/platinum-window/score response body."""

    # Core output
    window_status: WindowStatus
    fingerprint_positive: bool

    # Z-scores
    FAP_zscore: float
    CXCL10_zscore: float
    STROMAL_ARM_SCORE: float
    IMMUNE_ACCESS_SCORE: float
    TCELL_GPS_SCORE: float
    OCT1_STATUS: OCT1Status
    OCT1_zscore: float
    metformin_eligible: bool
    metformin_caveat: Optional[str] = None

    # Tier
    TIER: Tier
    TIER_REFINED: Optional[TierRefined] = None

    # PLATINUM_SCORE — continuous elastic net Cox
    PLATINUM_SCORE: float
    PLATINUM_SCORE_percentile: int
    PLATINUM_SCORE_percentile_reference: str
    risk_tier: str
    binary_HR_estimate: float
    continuous_HR_estimate: float
    score_confidence: str
    validation_context: ValidationContext

    # Window timing
    cycles_until_window_closes: Optional[int] = None
    cycles_remaining: Optional[int] = None
    weeks_remaining: Optional[float] = None
    intervention_deadline: str

    # Treatment sequence
    recommended_sequence: List[TreatmentStep]

    # Urgency
    urgency: Urgency
    urgency_reason: str
    trial_routing: str

    # Confidence
    confidence_tier: ConfidenceTier
    caveats: List[str]
    ruo_disclaimer: str

    # Normalization safety
    normalization_warning: str
    input_units_assumed: str

    # CXCL10 imputation transparency
    cxcl10_imputation: Optional[str] = None
    cxcl10_imputation_note: Optional[str] = None

    # Assay quality warning
    assay_warning: Optional[str] = None

    # Audit trail
    model_version: str
    reference_cohort: str
    computation_ms: float
    timestamp_utc: str
