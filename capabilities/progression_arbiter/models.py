"""
Pydantic v2 request/response models for the Progression Arbiter.
Bone pseudo-progression vs true progression scoring.
RESEARCH USE ONLY.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enums (match arbiter.py constants exactly) ───────────────────────────────

class ImagingChangeType(str, Enum):
    NEW_SCLEROTIC_BONE = "NEW_SCLEROTIC_BONE"
    SUV_INCREASE_NO_SIZE = "SUV_INCREASE_NO_SIZE"
    SUB_5MM_SIZE_INCREASE = "SUB_5MM_SIZE_INCREASE"
    NEW_SOFT_TISSUE_LESION = "NEW_SOFT_TISSUE_LESION"
    RECIST_PROGRESSION = "RECIST_PROGRESSION"
    STABLE_DISEASE = "STABLE_DISEASE"
    OTHER_OR_UNCLEAR = "OTHER_OR_UNCLEAR"


class TherapyClass(str, Enum):
    CDK46 = "CDK46"
    HER2 = "HER2"
    ENDOCRINE = "ENDOCRINE"
    CHEMO = "CHEMO"
    IO = "IO"
    OTHER = "OTHER"


class RiskBucket(str, Enum):
    LOW = "LOW"
    MID = "MID"
    HIGH = "HIGH"


class Recommendation(str, Enum):
    SHORT_INTERVAL_RESCAN = "SHORT_INTERVAL_RESCAN"
    ADDITIONAL_WORKUP_REQUIRED = "ADDITIONAL_WORKUP_REQUIRED"
    IMMEDIATE_SWITCH_CONCERN = "IMMEDIATE_SWITCH_CONCERN"


# ── Request ──────────────────────────────────────────────────────────────────

class ArbiterScoreRequest(BaseModel):
    """POST /api/v1/progression-arbiter/score request body."""
    imaging_change_type: ImagingChangeType
    therapy_class: TherapyClass
    symptomatic: Optional[bool] = Field(None, description="True/False/null (null = unknown)")
    new_pain_at_site: Optional[bool] = Field(None, description="True/False/null")
    healing_flag: bool = Field(..., description="Sclerotic/healing context + stable extraosseous")
    weeks_on_therapy: float = Field(..., ge=0, description="Weeks since current therapy start")
    alp_delta_pct: float = Field(0.0, description="ALP change from baseline (%)")
    ca153_delta_pct: float = Field(0.0, description="CA15-3 change from baseline (%)")


class RadiologyParseRequest(BaseModel):
    """POST /api/v1/progression-arbiter/parse-report request body."""
    text: str = Field(..., min_length=1, description="Radiology report text")


# ── Response ─────────────────────────────────────────────────────────────────

class ArbiterScoreResponse(BaseModel):
    """Score result from the Progression Arbiter."""
    p_true_progression: float
    logit: float
    risk_bucket: RiskBucket
    recommendation: Recommendation
    term_contributions: Dict[str, float]
    driving_feature: str
    driving_feature_contribution: float
    explanation: str
    disclaimer: str


class RadiologyParseResponse(BaseModel):
    """Parsed radiology report result."""
    imaging_change_type: str
    healing_flag: bool
    key_phrases: List[str]
    confidence: str
