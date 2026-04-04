"""
Zeta-Core Router — /api/v1/zeta-core/*

Endpoints:
  POST /api/v1/zeta-core/parse-context   → AI-extract disease/drug/genes from free text
  POST /api/v1/zeta-core/analyze         → SSE streaming: query → PubMed → Gemini synthesis

Auto-discovered by capabilities/__init__.py — no changes to main.py needed.
"""

import json
import os
import logging
import re
import time

import requests
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .pubmed_client import search_pubmed, build_simple_query, build_keyword_query
from .prompts import QUERY_FORMULATION_PROMPT, build_synthesis_prompt

logger = logging.getLogger("crispro.zeta_core")

router = APIRouter(prefix="/api/v1/zeta-core", tags=["Zeta-Core Evidence Engine"])

# ── Gemini setup ──────────────────────────────────────────────────────────────

GEMINI_BASE = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_KEY  = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
GEMINI_MODEL = os.environ.get("ZETA_CORE_GEMINI_MODEL", "gemini-2.5-flash")


def _gemini_generate(prompt: str, max_tokens: int = 512, json_mode: bool = False,
                     thinking_budget: int = 0) -> str:
    """Call Gemini generateContent. Returns .text or raises."""
    url = f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    generation_config: dict = {"maxOutputTokens": max_tokens}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"
    if thinking_budget == 0:
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Empty candidates from Gemini")
    text = ""
    for part in candidates[0].get("content", {}).get("parts", []):
        text += part.get("text", "")
    return text.strip()


# ── Parse-context endpoint ────────────────────────────────────────────────────

class ParseContextRequest(BaseModel):
    question: str


@router.post("/parse-context")
def parse_context(req: ParseContextRequest):
    prompt = f"""Extract clinical research context from this question. Return ONLY a JSON object with simple string values.

Question: {req.question}

Return exactly this JSON:
{{"disease":"","compound":"","treatmentLine":"","genes":[],"suggestedQuestion":"","queryHint":""}}

Rules:
- disease: specific disease name only (e.g. ovarian cancer)
- compound: generic drug name only (e.g. olaparib)
- treatmentLine: e.g. 2nd line platinum-resistant, or empty
- genes: array of gene symbols e.g. ["BRCA1","TP53"] only if clearly relevant
- suggestedQuestion: precise searchable version of the question
- queryHint: brief plain text hint about what this search will find"""

    try:
        raw = _gemini_generate(prompt, max_tokens=256, json_mode=True, thinking_budget=0)
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {}
        return json.loads(m.group())
    except Exception as e:
        logger.error(f"[parse-context] error: {e}")
        return {}


# ── Badge injector ────────────────────────────────────────────────────────────

def inject_badges(articles: list, synthesis: dict, context: dict) -> list:
    badges = set(synthesis.get("badges", []))
    all_pre_clinical = True

    for art in articles:
        types = [t.lower() for t in art.get("publication_types", [])]
        abstract = art.get("abstract", "").lower()
        title = art.get("title", "").lower()

        pre_clinical_signals = ["in vitro", "cell line", "mouse model", "rat model",
                                "animal model", "xenograft", "murine", "in vivo animal"]
        is_pre_clinical = any(s in abstract or s in title for s in pre_clinical_signals)
        is_human = not is_pre_clinical

        if is_human:
            all_pre_clinical = False

        if is_human and any(t in ("randomized controlled trial", "clinical trial") for t in types):
            badges.add("RCT")
        if is_human and any("meta-analysis" in t or "systematic review" in t for t in types):
            badges.add("Meta-Analysis")

        if re.search(r"cyp[0-9][a-z][0-9]|p-glycoprotein|abc transporter|bcrp|mrp[0-9]", abstract):
            badges.add("Pathway-Aligned")

        genes = context.get("genes", [])
        if genes and re.search("|".join(re.escape(g) for g in genes), title + " " + abstract, re.I):
            badges.add("Mechanism-Match")

        compound = (context.get("compound") or "").lower()
        if is_human and compound and compound in abstract:
            if re.search(r"inhibit|interact", abstract) and re.search(r"auc|pharmacokinetic|pk|exposure|clearance", abstract):
                badges.add("PATHWAY-BLOCK")

    if all_pre_clinical:
        badges.discard("PATHWAY-BLOCK")
        badges.discard("RCT")
        badges.add("Pre-Clinical Only")

    if synthesis.get("evidence_tier") == "MECHANISTIC_SPECULATION":
        badges.add("Pre-Clinical Only")
        badges.discard("RCT")

    return list(badges)


# ── Main analyze endpoint (SSE) ───────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    question: str
    context: dict = {}
    maxResults: int = 12


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    question = req.question.strip()
    context = req.context
    max_results = min(req.maxResults, 20)

    if not question:
        return {"error": "question required"}

    async def stream():
        # ── Step 1: Formulate query ──
        yield _sse("step", {"type": "query_formulating", "message": "Formulating PubMed search query…"})

        ctx_parts = []
        for k, v in context.items():
            if v and (not isinstance(v, list) or v):
                ctx_parts.append(f"{k}: {', '.join(v) if isinstance(v, list) else v}")
        context_str = f"Context: {'; '.join(ctx_parts)}" if ctx_parts else ""

        try:
            gemini_query = _gemini_generate(
                QUERY_FORMULATION_PROMPT.format(question=question, context_str=context_str),
                max_tokens=512, thinking_budget=0
            )
            gemini_query = re.sub(r"^```[\w]*\n?", "", gemini_query).rstrip("` \n")
            if not gemini_query:
                gemini_query = build_simple_query(question, context.get("genes", []),
                                                   context.get("compound", ""), context.get("disease", ""))
        except Exception:
            gemini_query = build_simple_query(question, context.get("genes", []),
                                               context.get("compound", ""), context.get("disease", ""))

        yield _sse("step", {"type": "query_ready", "query": gemini_query, "message": "Query formulated"})

        # ── Step 2: PubMed search with 3-level fallback ──
        yield _sse("step", {"type": "pubmed_searching", "query": gemini_query, "message": "Searching PubMed…"})

        articles, total_found, final_query = [], 0, gemini_query

        try:
            articles, total_found = search_pubmed(gemini_query, max_results)
        except Exception as e:
            yield _sse("step", {"type": "pubmed_error", "message": f"PubMed error: {e}"})

        if not articles:
            simple_q = build_simple_query(question, context.get("genes", []),
                                          context.get("compound", ""), context.get("disease", ""))
            yield _sse("step", {"type": "query_fallback", "attempt": 1, "query": simple_q,
                                "message": "0 results — trying simplified query…"})
            try:
                articles, total_found = search_pubmed(simple_q, max_results)
                if articles:
                    final_query = simple_q
            except Exception:
                pass

        if not articles:
            kw_q = build_keyword_query(question)
            yield _sse("step", {"type": "query_fallback", "attempt": 2, "query": kw_q,
                                "message": "Still 0 — trying keyword-only search…"})
            try:
                articles, total_found = search_pubmed(kw_q, max_results)
                if articles:
                    final_query = kw_q
            except Exception:
                pass

        if not articles:
            yield _sse("step", {"type": "no_results", "message": "No results on any query variant"})
            yield _sse("result", {
                "question": question, "pubmedQuery": final_query, "totalFound": 0,
                "articlesRetrieved": 0,
                "clinical_directive": "[ABORT] NO PUBMED RESULTS — BROADEN SEARCH TERMS.",
                "human_clinical_papers_found": 0, "preclinical_papers_found": 0,
                "articles": [], "findings": [], "pmids": [], "synthesized_mechanisms": [],
                "evidence_tier": "INSUFFICIENT", "badges": [],
                "cynical_summary": "No PubMed results matched any query variant. Try broader terms.",
                "dosage_signals": None, "safety_signals": [], "drug_interactions": [],
                "knowledge_gaps": ["No literature found for this query"], "papers_discarded": [],
            })
            return

        yield _sse("step", {
            "type": "pubmed_results",
            "count": len(articles), "total": total_found,
            "papers": [{"pmid": a["pmid"], "title": a["title"],
                        "journal": a.get("journal", ""), "year": a.get("year", "")}
                       for a in articles],
            "message": f"Retrieved {len(articles)} abstracts ({total_found:,} total on PubMed)",
        })

        # ── Step 3: Gemini synthesis ──
        yield _sse("step", {"type": "synthesis_start", "paper_count": len(articles),
                            "message": f"Zeta-Core classifying {len(articles)} papers by evidence maturity…"})

        synthesis_msgs = [
            "Separating human clinical data from pre-clinical noise…",
            "Extracting PK/PD data points and AUC values…",
            "Building evidence tier classification…",
            "Generating clinical directive…",
            "Writing cynical summary…",
            "Finalizing DDI kill-chain…",
        ]

        synthesis_result = None
        synthesis_error = None

        import threading

        done_event = threading.Event()
        result_holder: list = []
        error_holder: list = []

        def run_synthesis():
            try:
                prompt = build_synthesis_prompt(question, context, articles)
                raw = _gemini_generate(prompt, max_tokens=8192, json_mode=True)
                cleaned = re.sub(r"^```json\n?", "", raw).rstrip("` \n")
                result_holder.append(json.loads(cleaned))
            except Exception as e:
                error_holder.append(e)
            finally:
                done_event.set()

        t = threading.Thread(target=run_synthesis, daemon=True)
        t.start()

        msg_idx = 0
        elapsed = 0
        while not done_event.wait(timeout=2.0):
            yield _sse("step", {"type": "synthesis_tick", "elapsed": elapsed,
                                "message": synthesis_msgs[min(msg_idx, len(synthesis_msgs) - 1)]})
            msg_idx += 1
            elapsed += 2

        if error_holder:
            synthesis_result = {
                "clinical_directive": "[ABORT] SYNTHESIS ENGINE DEGRADED — MANUAL PHARMACIST REVIEW REQUIRED.",
                "findings": [], "pmids": [a["pmid"] for a in articles],
                "synthesized_mechanisms": [], "evidence_tier": "INSUFFICIENT",
                "human_clinical_papers_found": 0, "preclinical_papers_found": 0,
                "badges": [], "dosage_signals": None, "safety_signals": [],
                "drug_interactions": [], "knowledge_gaps": ["LLM synthesis failed"],
                "cynical_summary": f"Synthesis engine error: {error_holder[0]}",
            }
        else:
            synthesis_result = result_holder[0]

        # ── Step 4: Badge injection ──
        final_badges = inject_badges(articles, synthesis_result, context)

        yield _sse("step", {"type": "synthesis_done", "message": "Synthesis complete — building result…"})

        yield _sse("result", {
            "question": question,
            "pubmedQuery": final_query,
            "totalFound": total_found,
            "articlesRetrieved": len(articles),
            "clinical_directive": synthesis_result.get("clinical_directive",
                "[ABORT] NO CLINICAL DIRECTIVE GENERATED — MANUAL PHARMACIST REVIEW REQUIRED."),
            "human_clinical_papers_found": synthesis_result.get("human_clinical_papers_found", 0),
            "preclinical_papers_found": synthesis_result.get("preclinical_papers_found", 0),
            "articles": [{"pmid": a["pmid"], "title": a["title"], "year": a.get("year", ""),
                          "journal": a.get("journal", ""), "authors": a.get("authors", []),
                          "pmcid": a.get("pmcid", ""), "doi": a.get("doi", ""),
                          "abstract": a.get("abstract", "")[:500]}
                         for a in articles],
            "findings": synthesis_result.get("findings", []),
            "pmids": synthesis_result.get("pmids", [a["pmid"] for a in articles]),
            "synthesized_mechanisms": synthesis_result.get("synthesized_mechanisms", []),
            "evidence_tier": synthesis_result.get("evidence_tier", "INSUFFICIENT"),
            "badges": final_badges,
            "dosage_signals": synthesis_result.get("dosage_signals"),
            "safety_signals": synthesis_result.get("safety_signals", []),
            "drug_interactions": synthesis_result.get("drug_interactions", []),
            "knowledge_gaps": synthesis_result.get("knowledge_gaps", []),
            "papers_discarded": synthesis_result.get("papers_discarded", []),
            "cynical_summary": synthesis_result.get("cynical_summary", ""),
        })

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
