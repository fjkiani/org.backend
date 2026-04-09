"""
Zeta-Core Prompts — query formulation + Groq/Llama synthesis.

Groq on-demand tier caps prompt size (~12k TPM). Keep synthesis input small.
"""

import os
from typing import Optional

# Caps for synthesis prompt (override via env if your Groq tier allows more)
_SYNTH_MAX_ARTICLES = int(os.environ.get("ZETA_CORE_SYNTHESIS_MAX_ARTICLES", "12"))
_SYNTH_ABSTRACT_CHARS = int(os.environ.get("ZETA_CORE_SYNTHESIS_ABSTRACT_CHARS", "380"))
_SYNTH_TITLE_CHARS = int(os.environ.get("ZETA_CORE_SYNTHESIS_TITLE_CHARS", "180"))
# When Diffbot full-text excerpt exists, use this cap (keeps Groq prompt small)
_SYNTH_FULLTEXT_CHARS = int(os.environ.get("ZETA_CORE_SYNTH_FULLTEXT_CHARS", "420"))
_SYNTH_ABSTRACT_WITH_FULLTEXT = int(os.environ.get("ZETA_CORE_SYNTH_ABSTRACT_WITH_FT", "200"))

QUERY_FORMULATION_PROMPT = """[COMMAND]: Convert this research question into a PubMed boolean search query.

Question: "{question}"
{context_str}

[RULES]:
- Use [tiab], [MeSH Terms], [pt] field tags
- Include synonyms joined with OR
- For drug interactions add CYP/enzyme terms if relevant
- Always add english[lang]
- Maximum 3 AND clauses for precision — prefer broader over specific
- Do NOT use AND clauses that would return 0 results (avoid over-specified multi-term combos)

[OUTPUT]: Return ONLY the raw PubMed query string, nothing else. No explanation."""


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def build_synthesis_prompt(
    question: str,
    context: dict,
    articles: list,
    *,
    max_articles: Optional[int] = None,
) -> str:
    ctx_parts = []
    for k, v in context.items():
        if v and (not isinstance(v, list) or v):
            ctx_parts.append(f"{k}: {', '.join(v) if isinstance(v, list) else v}")
    context_block = "\n".join(ctx_parts) if ctx_parts else "None provided"

    total = len(articles)
    cap = max_articles if max_articles is not None else _SYNTH_MAX_ARTICLES
    cap = max(1, min(cap, total)) if total else 0
    use = articles[:cap]
    omitted = total - len(use)

    def _paper_block(i: int, a: dict) -> str:
        base = (
            f"[{i+1}] PMID:{a['pmid']} ({a.get('year','?')}) — {_clip(a.get('journal',''), 80)}\n"
            f"Title: {_clip(a.get('title',''), _SYNTH_TITLE_CHARS)}\n"
            f"PubTypes: {', '.join(a.get('publication_types',[])[:3]) or '?'}\n"
        )
        ft = (a.get("diffbot_text") or "").strip()
        if ft:
            return (
                base
                + f"Abstract: {_clip(a.get('abstract','') or 'Not available.', _SYNTH_ABSTRACT_WITH_FULLTEXT)}\n"
                + f"Full text excerpt (Diffbot from {a.get('diffbot_source_url', 'source')}): "
                + _clip(ft, _SYNTH_FULLTEXT_CHARS)
            )
        return base + f"Abstract: {_clip(a.get('abstract','') or 'Not available.', _SYNTH_ABSTRACT_CHARS)}"

    abstract_block = "\n\n".join(_paper_block(i, a) for i, a in enumerate(use))

    scope_note = ""
    if omitted > 0:
        scope_note = f"\nNOTE: {len(use)} of {total} retrieved abstracts shown (shortened for model limits). Synthesize from these; cite only PMIDs you see.\n"

    return f"""You are ZETA-CORE, the clinical evidence synthesis engine for CrisPRO.org.
You are ruthlessly evidence-based. You never conflate pre-clinical data with clinical evidence.
You prioritize human data, dismiss animal models as noise unless no human data exists.

RESEARCH QUESTION: {_clip(question, 500)}
CLINICAL CONTEXT: {_clip(context_block, 400)}
{scope_note}
LITERATURE ({len(use)} papers shown, {total} retrieved; some may include Diffbot full-text excerpts):
{abstract_block}

TIERS: (1) Human RCT / human PK / definitive clinical outcomes → SUPPORTED; (2) Human observational, pharmacoepidemiology, registry/claims studies, clinical DDI case series, meta-analyses/systematic reviews that synthesize human data, expert reviews centered on human PK/DDI → CONSIDER; (3) Primary evidence is in vitro, cell lines, or animal models → MECHANISTIC_SPECULATION. INSUFFICIENT if irrelevant.

HUMAN vs PRE-CLINICAL: Use PubTypes + title + abstract together.
- Count as HUMAN (Tier 1–2): Clinical Trial, RCT, Observational Study, Meta-Analysis, Comparative Study; text mentioning patients, cohorts, pharmacoepidemiology, medicare/claims/EHR, population-based studies, healthy volunteers in PK studies, drug–drug interaction studies in humans, or titles like "Pharmacoepidemiologic study" / "drug-drug interaction".
- Do NOT label as pre-clinical only because PublicationType includes "Review". Many reviews summarize human DDI/PK; if they discuss human populations or clinical outcomes, use Tier 2 and is_human_clinical=true.
- Tier 3 ONLY when the paper's primary contribution is non-human (e.g. mice, xenografts, cell lines, in vitro enzyme assays) AND it does not report human patient/population data.

DIRECTIVE: If ANY paper in the LITERATURE block is Tier 1–2 → "[DIRECTIVE] …" with PMIDs and honest uncertainty. Use "[ABORT] NO HUMAN CLINICAL DATA — MANUAL PHARMACIST REVIEW REQUIRED." ONLY when every paper in the block is Tier 3 / non-human primary evidence.

BADGES: RCT/Meta-Analysis = human only. Pathway-Aligned/CYP OK any tier. Mechanism-Match = gene fit. PATHWAY-BLOCK = human PK AUC data. Pre-Clinical Only if all Tier 3.

Return ONLY this exact JSON (no markdown, no backticks):
{{
  "clinical_directive": "string",
  "findings": [
    {{
      "pmid": "string",
      "title": "string",
      "year": "string",
      "journal": "string",
      "finding": "string (2–3 sentence precise summary of what this paper found relevant to the question)",
      "evidence_type": "RCT|Cohort|Case Report|Meta-Analysis|Pharmacoepidemiology|Observational|Clinical pharmacology (human DDI/PK)|In Vitro|Animal|Review|Other",
      "maturity_tier": 1,
      "is_human_clinical": true,
      "confidence": 0.0,
      "relevance_score": 0,
      "key_data_point": "string (quantified outcome if available, else empty)"
    }}
  ],
  "pmids": ["string"],
  "synthesized_mechanisms": [
    {{
      "mechanism": "string",
      "target": "string",
      "evidence_strength": "Strong|Moderate|Weak|Insufficient",
      "supporting_pmids": ["string"],
      "clinical_relevance": "string"
    }}
  ],
  "evidence_tier": "SUPPORTED|CONSIDER|MECHANISTIC_SPECULATION|INSUFFICIENT",
  "human_clinical_papers_found": 0,
  "preclinical_papers_found": 0,
  "badges": [],
  "dosage_signals": null,
  "safety_signals": [],
  "drug_interactions": [
    {{
      "drug_a": "string",
      "drug_b": "string",
      "mechanism": "string",
      "clinical_impact": "string",
      "evidence_source": "Human Clinical|Pre-Clinical Only",
      "auc_change": "string or null",
      "source_pmid": "string"
    }}
  ],
  "knowledge_gaps": ["string"],
  "papers_discarded": [
    {{
      "pmid": "string",
      "reason": "string"
    }}
  ],
  "cynical_summary": "string (3–5 sentences: what the evidence actually shows, what is missing, honest verdict, no hedging, no marketing language)"
}}"""
