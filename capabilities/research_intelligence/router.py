"""
HTTP API for the ported research_intelligence orchestrator.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .orchestrator import ResearchIntelligenceOrchestrator

router = APIRouter(prefix="/api/v1/research-intelligence", tags=["research-intelligence"])

_orch: Optional[ResearchIntelligenceOrchestrator] = None


def _get_orch() -> ResearchIntelligenceOrchestrator:
    global _orch
    if _orch is None:
        _orch = ResearchIntelligenceOrchestrator()
    return _orch


class ResearchRequest(BaseModel):
    question: str
    context: Dict[str, Any] = Field(default_factory=dict)


@router.get("/health")
async def health() -> Dict[str, Any]:
    o = _get_orch()
    return {"ok": True, "available": o.is_available()}


@router.post("/research")
async def research(body: ResearchRequest) -> Dict[str, Any]:
    o = _get_orch()
    return await o.research_question(body.question, body.context)
