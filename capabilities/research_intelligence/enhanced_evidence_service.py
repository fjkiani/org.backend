"""
Minimal EnhancedEvidenceService for research_intelligence — Diffbot + Groq extraction.

Replaces oncology api.services.enhanced_evidence_service for methods used by
synthesis_engine and orchestrator only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from .llm_provider.llm_abstract import get_llm_provider

logger = logging.getLogger(__name__)

LLM_AVAILABLE = True
try:
    _probe = get_llm_provider()
    if not _probe.is_available():
        LLM_AVAILABLE = False
except Exception:
    LLM_AVAILABLE = False


class EnhancedEvidenceService:
    def __init__(self) -> None:
        self.diffbot_rate_limited = False

    async def _extract_full_text_with_diffbot(self, paper_url: str) -> Optional[str]:
        if self.diffbot_rate_limited:
            return None
        token = os.environ.get("DIFFBOT_TOKEN", "").strip()
        if not token:
            return None

        api_url = "https://api.diffbot.com/v3/article"
        params = {
            "token": token,
            "url": paper_url,
            "fields": "title,author,date,siteName,tags,text",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(api_url, params=params)
                if r.status_code == 429:
                    self.diffbot_rate_limited = True
                    logger.warning("Diffbot rate limit (429); skipping further Diffbot calls.")
                    return None
                r.raise_for_status()
                js = r.json()
            obj = (js.get("objects") or [None])[0]
            if obj and obj.get("text"):
                return str(obj.get("text"))[:10000]
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                self.diffbot_rate_limited = True
            logger.debug("Diffbot HTTP error for %s: %s", paper_url[:80], e.response.status_code)
            return None
        except Exception as e:
            logger.debug("Diffbot extraction error for %s: %s", paper_url[:80], e)
            return None

    async def _call_llm_agnostic(
        self,
        compound: str,
        disease: str,
        papers_text: str,
    ) -> Optional[Dict[str, Any]]:
        if not LLM_AVAILABLE:
            logger.warning("LLM not available for evidence extraction")
            return None
        try:
            provider = get_llm_provider()
            if not provider.is_available():
                return None

            pause = float(os.environ.get("RESEARCH_INTEL_LLM_PAUSE_S", "0.2"))
            await asyncio.sleep(pause)

            system_message = (
                "You are a biomedical research analyst. Extract structured information from research papers."
            )
            prompt = f"""Read these research papers about {compound} for {disease} and extract structured information.

Papers:
{papers_text[:8000]}

Extract and return a JSON object with this exact structure:
{{
  "mechanisms": [
    {{
      "mechanism": "brief_name",
      "description": "how it works",
      "confidence": 0.85
    }}
  ],
  "dosage": {{
    "recommended_dose": "extracted dose or empty string",
    "evidence": "quote supporting dose"
  }},
  "safety": {{
    "concerns": ["list of safety concerns or empty"],
    "monitoring": ["what to monitor or empty"]
  }},
  "outcomes": [
    {{
      "outcome": "survival improvement",
      "details": "what the papers say"
    }}
  ]
}}

Return ONLY valid JSON, no markdown formatting."""

            max_retries = 3
            response_text: Optional[str] = None
            for attempt in range(max_retries):
                try:
                    llm_response = await provider.chat(
                        message=prompt,
                        system_message=system_message,
                        max_tokens=2000,
                        temperature=0.0,
                    )
                    response_text = llm_response.text
                    break
                except Exception as e:
                    error_str = str(e).lower()
                    if (
                        "429" in error_str or "quota" in error_str or "rate limit" in error_str
                    ) and attempt < max_retries - 1:
                        delay = (2**attempt) * 2.0
                        logger.warning(
                            "LLM rate limit (attempt %s/%s); retry in %.1fs",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error("LLM error: %s", e)
                        raise

            if not response_text:
                return None

            response_text = response_text.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            parsed = json.loads(response_text)
            mechanisms: List[str] = []
            if isinstance(parsed.get("mechanisms"), list):
                for mech in parsed.get("mechanisms", []):
                    if isinstance(mech, dict):
                        mechanisms.append(mech.get("mechanism", ""))
                    elif isinstance(mech, str):
                        mechanisms.append(mech)

            return {
                "mechanisms": mechanisms[:10],
                "dosage": parsed.get("dosage", {}).get("recommended_dose", "")
                if isinstance(parsed.get("dosage"), dict)
                else parsed.get("dosage", ""),
                "safety": parsed.get("safety", {}).get("concerns", [])
                if isinstance(parsed.get("safety"), dict)
                else parsed.get("safety", []),
                "outcomes": [
                    o.get("outcome", "") if isinstance(o, dict) else str(o)
                    for o in parsed.get("outcomes", [])
                ],
                "evidence_summary": parsed.get("evidence_summary", ""),
                "overall_confidence": parsed.get("overall_confidence", 0.7),
            }
        except Exception as e:
            logger.error("LLM extraction error: %s", e)
            return None

    async def _call_llm_agnostic_comprehensive(
        self,
        compound: str,
        disease: str,
        papers_text: str,
        articles: Optional[List[Dict[str, Any]]] = None,
        sub_questions: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not LLM_AVAILABLE:
            return None
        try:
            provider = get_llm_provider()
            if not provider.is_available():
                return None

            pause = float(os.environ.get("RESEARCH_INTEL_LLM_PAUSE_S", "0.2"))
            await asyncio.sleep(pause)

            system_message = (
                "You are a biomedical research analyst. Extract comprehensive information from research papers."
            )
            prompt_parts: List[str] = [
                f"Read these research papers about {compound} for {disease} and extract comprehensive information.",
                "",
                "Papers:",
                papers_text[:12000],
                "",
                "Extract and return a JSON object with this exact structure:",
            ]

            json_structure: Dict[str, Any] = {
                "mechanisms": [
                    {"mechanism": "brief_name", "description": "how it works", "confidence": 0.85}
                ],
                "dosage": {
                    "recommended_dose": "extracted dose or empty string",
                    "evidence": "quote supporting dose",
                },
                "safety": {
                    "concerns": ["list of safety concerns or empty"],
                    "monitoring": ["what to monitor or empty"],
                },
                "outcomes": [{"outcome": "survival improvement", "details": "what the papers say"}],
            }

            if articles:
                json_structure["article_summaries"] = [
                    {
                        "pmid": "article_pmid",
                        "title": "article_title",
                        "summary": "brief_summary",
                        "mechanisms": ["mech1"],
                        "dosage": {},
                        "safety": {},
                        "outcomes": [],
                    }
                ]
                prompt_parts.append(
                    "For each article provided, generate a brief summary, extract its key mechanisms, "
                    "dosage, safety, and outcomes, and include them in an 'article_summaries' array."
                )

            if sub_questions:
                json_structure["sub_question_answers"] = [
                    {
                        "sub_question": "question text",
                        "answer": "direct answer",
                        "confidence": 0.85,
                        "sources": ["pmid1", "pmid2"],
                        "mechanisms": ["mech1"],
                    }
                ]
                prompt_parts.append(f"Answer these sub-questions: {', '.join(sub_questions[:5])}")
                prompt_parts.append("Include answers in a 'sub_question_answers' array.")

            prompt_parts.append(json.dumps(json_structure, indent=2))
            prompt_parts.append("Return ONLY valid JSON, no markdown formatting.")
            prompt = "\n".join(prompt_parts)

            max_retries = 3
            response_text: Optional[str] = None
            for attempt in range(max_retries):
                try:
                    llm_response = await provider.chat(
                        message=prompt,
                        system_message=system_message,
                        max_tokens=4096,
                        temperature=0.0,
                    )
                    response_text = llm_response.text
                    break
                except Exception as e:
                    error_str = str(e).lower()
                    if (
                        "429" in error_str or "quota" in error_str or "rate limit" in error_str
                    ) and attempt < max_retries - 1:
                        delay = (2**attempt) * 2.0
                        logger.warning(
                            "LLM rate limit comprehensive (attempt %s/%s); retry in %.1fs",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error("LLM error: %s", e)
                        raise

            if not response_text:
                return None

            response_text = response_text.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            parsed = json.loads(response_text)
            mechanisms: List[str] = []
            if isinstance(parsed.get("mechanisms"), list):
                for mech in parsed.get("mechanisms", []):
                    if isinstance(mech, dict):
                        mechanisms.append(mech.get("mechanism", ""))
                    elif isinstance(mech, str):
                        mechanisms.append(mech)

            result: Dict[str, Any] = {
                "mechanisms": mechanisms[:10],
                "dosage": parsed.get("dosage", {}).get("recommended_dose", "")
                if isinstance(parsed.get("dosage"), dict)
                else parsed.get("dosage", ""),
                "safety": parsed.get("safety", {}).get("concerns", [])
                if isinstance(parsed.get("safety"), dict)
                else parsed.get("safety", []),
                "outcomes": [
                    o.get("outcome", "") if isinstance(o, dict) else str(o)
                    for o in parsed.get("outcomes", [])
                ],
                "evidence_summary": parsed.get("evidence_summary", ""),
                "overall_confidence": parsed.get("overall_confidence", 0.7),
            }

            if "article_summaries" in parsed:
                result["article_summaries"] = parsed["article_summaries"]
            if "sub_question_answers" in parsed:
                result["sub_question_answers"] = parsed["sub_question_answers"]

            return result
        except Exception as e:
            logger.error("Comprehensive LLM extraction error: %s", e)
            return None
