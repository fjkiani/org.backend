"""
Zeta-Core PubMed Client
ESearch + EFetch — pulls titles, abstracts, publication types, MeSH, authors.
Self-contained: no Flask dependency.
"""

import os
import re
import time
import requests
import xml.etree.ElementTree as ET

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_EMAIL = os.environ.get("NCBI_USER_EMAIL", "research-agent@crispro.org")
NCBI_API_KEY = os.environ.get("NCBI_USER_API_KEY", "")

STOP_WORDS = {
    "what","is","the","evidence","for","in","of","and","or","with","a","an","does",
    "do","how","why","when","between","clinical","studies","study","on","which","are",
    "its","can","will","would","should","has","have","that","this","these","those",
    "from","by","at","as","be","been","being","was","were","to","it","if","than",
    "show","shows","shown","showing","affect","cause","causes","using","used","use",
    "increased","decreased","effects","effect","role","impact","associated","patients",
    "cancer","tumor","tumors","cell","cells","inhibit","inhibition","activity",
}


def _base_params():
    p = {"tool": "ZetaCoreResearchAgent", "email": NCBI_EMAIL}
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY
    return p


def _clean(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def esearch(query: str, max_results: int = 20) -> tuple[list, int]:
    params = _base_params()
    params.update({"db": "pubmed", "term": query, "retmode": "json",
                   "retmax": str(max_results), "sort": "relevance"})
    for attempt in range(3):
        try:
            if attempt:
                time.sleep(1.5 * attempt)
            time.sleep(0.12)
            r = requests.get(f"{EUTILS_BASE}/esearch.fcgi", params=params, timeout=30)
            r.raise_for_status()
            result = r.json().get("esearchresult", {})
            pmids = result.get("idlist", [])
            total = int(result.get("count", 0))
            if pmids or total == 0:
                return pmids, total
        except Exception as e:
            last_err = e
    raise RuntimeError(f"ESearch failed: {last_err}")


def efetch_abstracts(pmids: list) -> dict:
    if not pmids:
        return {}
    params = _base_params()
    params.update({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
    r = requests.get(f"{EUTILS_BASE}/efetch.fcgi", params=params, timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    articles = {}
    for art in root.findall(".//PubmedArticle"):
        try:
            pmid = art.findtext(".//MedlineCitation/PMID", "").strip()
            if not pmid:
                continue
            title = _clean(art.findtext(".//ArticleTitle", ""))
            abstract_parts = art.findall(".//Abstract/AbstractText")
            pieces = []
            for p in abstract_parts:
                text = _clean("".join(p.itertext()))
                if text:
                    label = p.get("Label", "")
                    pieces.append((_clean(label + ": ") if label else "") + text)
            abstract = " ".join(pieces)
            journal = _clean(art.findtext(".//Journal/Title") or art.findtext(".//MedlineTA") or "")
            year_elem = art.find(".//PubDate/Year")
            year = year_elem.text.strip() if year_elem is not None else ""
            if not year:
                med = art.findtext(".//PubDate/MedlineDate", "")
                m = re.search(r"\d{4}", med)
                year = m.group() if m else ""
            pub_types = [_clean("".join(pt.itertext())) for pt in art.findall(".//PublicationType")]
            mesh_terms = [_clean(m.findtext("DescriptorName", "")) for m in art.findall(".//MeshHeading") if m.findtext("DescriptorName")]
            pmcid, doi = "NA", ""
            for aid in art.findall(".//ArticleIdList/ArticleId"):
                id_type = aid.get("IdType", "")
                val = "".join(aid.itertext()).strip()
                if id_type == "pmc":
                    pmcid = val
                elif id_type == "doi":
                    doi = val
            authors = []
            for author in art.findall(".//Author")[:5]:
                last = author.findtext("LastName", "")
                first = author.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {first}".strip())
            articles[pmid] = {"pmid": pmid, "title": title, "abstract": abstract,
                              "journal": journal, "year": year, "publication_types": pub_types,
                              "mesh_headings": mesh_terms[:10], "pmcid": pmcid,
                              "doi": doi, "authors": authors}
        except Exception:
            continue
    return articles


def search_pubmed(query: str, max_results: int = 15) -> tuple[list, int]:
    pmids, total = esearch(query, max_results)
    if not pmids:
        return [], total
    arts = efetch_abstracts(pmids)
    return [arts[p] for p in pmids if p in arts], total


def build_simple_query(question: str, genes: list, compound: str, disease: str) -> str:
    parts = []
    if genes:
        parts.append(f"({' OR '.join(g + '[tiab]' for g in genes)})" if len(genes) > 1 else genes[0] + "[tiab]")
    if compound:
        parts.append(compound.strip() + "[tiab]")
    if disease:
        parts.append('"' + " ".join(disease.strip().split()[:3]) + '"[tiab]')
    words = [w for w in re.sub(r"[^a-z0-9\s]", " ", question.lower()).split()
             if len(w) > 3 and w not in STOP_WORDS]
    extra = [w + "[tiab]" for w in words[:2 if parts else 5]]
    unique = list(dict.fromkeys(parts + extra))
    return " AND ".join(unique[:4]) + " AND english[lang]"


def build_keyword_query(question: str) -> str:
    words = [w for w in re.sub(r"[^a-z0-9\s-]", " ", question.lower()).split()
             if len(w) > 3 and w not in STOP_WORDS]
    return " AND ".join(w + "[tiab]" for w in words[:3]) + " AND english[lang]"
