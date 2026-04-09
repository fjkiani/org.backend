"""
Heuristics for human vs pre-clinical evidence — complements LLM classification.

PubMed relevance order often buries pharmacoepidemiology / clinical DDI papers below
mechanistic reviews; synthesis also caps how many abstracts are sent to the model.
"""

from __future__ import annotations

from typing import Any, Dict, List


def likely_human_clinical_article(a: Dict[str, Any]) -> bool:
    """
    True if title, abstract, or publication types strongly suggest human /
    observational / clinical pharmacology evidence (not primary animal-only work).
    """
    title = (a.get("title") or "").lower()
    abstract = (a.get("abstract") or "").lower()
    blob = f"{title} {abstract}"
    types = [t.lower() for t in (a.get("publication_types") or [])]

    # Primary animal-only signals in title (choroidal NV in mice, xenografts, etc.)
    animal_title = any(
        s in title
        for s in (
            " in mice",
            " in mouse",
            "mouse model",
            "murine",
            "rat model",
            "xenograft",
            "zebrafish",
            "animal model",
        )
    )

    pubtype_human = any(
        t in types
        for t in (
            "clinical trial",
            "randomized controlled trial",
            "pragmatic clinical trial",
            "multicenter study",
            "observational study",
            "comparative study",
        )
    )
    pubtype_meta = any("meta-analysis" in t or "systematic review" in t for t in types)

    text_human = any(
        s in blob
        for s in (
            "pharmacoepidemiolog",
            "pharmacoepidemiology",
            "cohort study",
            "retrospective cohort",
            "prospective cohort",
            "case-control",
            "case control",
            "observational stud",
            "medicare ",
            "medicaid ",
            "claims data",
            "administrative data",
            "electronic health record",
            "electronic medical record",
            "health care database",
            "population-based",
            "registry stud",
            "healthy volunteer",
            "healthy subjects",
            "human subjects",
            "patients with",
            "patient population",
            "hospitalized patients",
        )
    )

    # Clinical PK / interaction studies in humans (titles often name the drugs + interaction)
    ddi_title = any(
        s in title
        for s in (
            "drug-drug interaction",
            "drug interaction",
            "drug-interaction",
            "drug-drug",
            "pharmacokinetic interaction",
            "pk interaction",
            "clinically relevant interaction",
        )
    )

    if pubtype_human or pubtype_meta:
        return True
    if text_human:
        return True
    if ddi_title and not animal_title:
        return True
    return False


def order_articles_human_first(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stable sort: human-likely articles first, then original PubMed order."""
    return [
        a
        for _, a in sorted(
            enumerate(articles),
            key=lambda ia: (0 if likely_human_clinical_article(ia[1]) else 1, ia[0]),
        )
    ]


def reconcile_synthesis_human_evidence(synthesis: Dict[str, Any], articles: List[Dict[str, Any]]) -> None:
    """
    Adjust counts, tier, and directive when the model misses obvious human /
    observational papers (e.g. pharmacoepidemiology below the abstract fold).
    Mutates `synthesis` in place.
    """
    heuristic_n = sum(1 for a in articles if likely_human_clinical_article(a))
    try:
        declared = int(synthesis.get("human_clinical_papers_found") or 0)
    except (TypeError, ValueError):
        declared = 0

    synthesis["human_clinical_papers_found"] = max(declared, heuristic_n)

    cd = (synthesis.get("clinical_directive") or "").strip()
    if heuristic_n >= 1:
        if "[ABORT]" in cd and "NO HUMAN" in cd.upper():
            synthesis["clinical_directive"] = (
                "[CONSIDER] Human observational, clinical pharmacology, and/or pharmacoepidemiologic "
                "evidence appears in the retrieved set — confirm effect size and applicability; "
                "pharmacist/clinician judgment advised."
            )
        tier = (synthesis.get("evidence_tier") or "").upper()
        if tier == "MECHANISTIC_SPECULATION":
            synthesis["evidence_tier"] = "CONSIDER"

    # Keep preclinical count consistent with upgraded human count
    try:
        pre = int(synthesis.get("preclinical_papers_found") or 0)
    except (TypeError, ValueError):
        pre = 0
    h = int(synthesis["human_clinical_papers_found"])
    max_pre = max(0, len(articles) - h)
    synthesis["preclinical_papers_found"] = min(pre, max_pre)

    # Patch per-paper findings when PMID matches heuristic-human articles
    human_pmids = {a["pmid"] for a in articles if likely_human_clinical_article(a)}
    for f in synthesis.get("findings") or []:
        if not isinstance(f, dict):
            continue
        pmid = str(f.get("pmid") or "")
        if pmid in human_pmids:
            f["is_human_clinical"] = True
            try:
                mt = int(f.get("maturity_tier") or 3)
            except (TypeError, ValueError):
                mt = 3
            f["maturity_tier"] = min(2, mt) if mt > 2 else mt
            tl = (f.get("title") or "").lower()
            if "pharmacoepidem" in tl:
                f["evidence_type"] = "Pharmacoepidemiology"
            elif "drug-drug" in tl or "drug interaction" in tl:
                f["evidence_type"] = "Clinical pharmacology (human DDI/PK)"
