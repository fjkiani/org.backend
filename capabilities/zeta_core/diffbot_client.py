"""
Optional Diffbot Article API — fetches HTML full-text extracts for PMC / DOI pages.

Set DIFFBOT_TOKEN in the environment. Without it, this module is a no-op.

Docs: https://docs.diffbot.com/reference/article
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger("crispro.zeta_core.diffbot")

DIFFBOT_ARTICLE_URL = "https://api.diffbot.com/v3/article"


def _pmc_html_url(pmcid: str) -> Optional[str]:
    if not pmcid or str(pmcid).strip().upper() in ("", "NA", "N/A"):
        return None
    raw = str(pmcid).strip().upper()
    if raw.startswith("PMC"):
        num = raw[3:].strip()
    else:
        num = raw
    if not num.isdigit():
        return None
    return f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{num}/"


def _doi_url(doi: str) -> Optional[str]:
    d = (doi or "").strip()
    if not d:
        return None
    return f"https://doi.org/{quote(doi.strip(), safe=':/')}"


def _pick_article_url(article: Dict[str, Any]) -> Optional[str]:
    pmc = _pmc_html_url(article.get("pmcid") or "")
    if pmc:
        return pmc
    return _doi_url(article.get("doi") or "")


def fetch_diffbot_text(page_url: str, token: str, timeout: int = 55) -> Optional[str]:
    try:
        r = requests.get(
            DIFFBOT_ARTICLE_URL,
            params={"token": token, "url": page_url},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("Diffbot request failed for %s: %s", page_url[:80], e)
        return None

    if data.get("error"):
        logger.warning("Diffbot API error: %s", data.get("error"))
        return None

    objs: List[dict] = data.get("objects") or []
    if not objs:
        return None

    text = (objs[0].get("text") or "").strip()
    return text or None


def enrich_articles_diffbot(
    articles: List[Dict[str, Any]],
    *,
    max_articles: Optional[int] = None,
    max_chars_per: Optional[int] = None,
    pause_s: float = 0.25,
) -> int:
    """
    Mutates each article dict: sets `diffbot_text` (clipped) when extraction succeeds.
    Returns number of successful enrichments.
    """
    token = (os.environ.get("DIFFBOT_TOKEN") or "").strip()
    if not token:
        return 0

    if max_articles is None:
        max_articles = int(os.environ.get("ZETA_CORE_DIFFBOT_MAX", "4"))
    if max_chars_per is None:
        max_chars_per = int(os.environ.get("ZETA_CORE_DIFFBOT_CHARS", "6000"))

    done = 0
    for art in articles:
        if done >= max_articles:
            break
        if art.get("diffbot_text"):
            continue
        url = _pick_article_url(art)
        if not url:
            continue

        text = fetch_diffbot_text(url, token)
        time.sleep(pause_s)

        if not text:
            continue
        if len(text) > max_chars_per:
            text = text[: max_chars_per - 1].rstrip() + "…"
        art["diffbot_text"] = text
        art["diffbot_source_url"] = url
        done += 1

    return done
