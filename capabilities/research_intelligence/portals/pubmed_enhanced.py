"""
Enhanced PubMed Portal using pubmearch framework.

Provides:
- Advanced PubMed search with batch retrieval
- Keyword hotspot analysis
- Trend tracking
- Publication count analysis
"""

import os
import sys
import json
import tempfile
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)

# Vendored at backend/vendor/ (parent of the pubmearch package)
_backend_root = Path(__file__).resolve().parent.parent.parent.parent
_vendor = _backend_root / "vendor"
if str(_vendor) not in sys.path:
    sys.path.insert(0, str(_vendor))

try:
    from pubmearch.pubmed_searcher import PubMedSearcher
    from pubmearch.analyzer import PubMedAnalyzer
    PUBMEARCH_AVAILABLE = True
except ImportError as e:
    logger.warning(f"pubmearch not available: {e}")
    PUBMEARCH_AVAILABLE = False


class EnhancedPubMedPortal:
    """
    Enhanced PubMed portal using pubmearch framework.
    
    Advantages over current implementation:
    - Advanced search syntax support
    - Batch retrieval (handles 1000+ results)
    - Keyword hotspot analysis
    - Trend tracking
    - Publication count analysis
    """
    
    def __init__(self, email: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize enhanced PubMed portal.
        
        Args:
            email: NCBI email (defaults to NCBI_USER_EMAIL env var)
            api_key: NCBI API key (defaults to NCBI_USER_API_KEY env var)
        """
        if not PUBMEARCH_AVAILABLE:
            raise RuntimeError("pubmearch not importable; check backend/vendor/pubmearch and dependencies (biopython).")
        
        self.email = email or os.getenv('NCBI_USER_EMAIL')
        self.api_key = api_key or os.getenv('NCBI_USER_API_KEY')
        
        if not self.email:
            raise ValueError("NCBI_USER_EMAIL must be set")
        
        self.searcher = PubMedSearcher(email=self.email, api_key=self.api_key)
        self.analyzer = PubMedAnalyzer()
    
    async def search_with_analysis(
        self,
        query: str,
        date_range: Optional[Tuple[str, str]] = None,
        max_results: int = 1000,
        analyze_keywords: bool = True,
        include_trends: bool = True
    ) -> Dict[str, Any]:
        """
        Search PubMed and return results + keyword analysis.
        
        Args:
            query: PubMed search query (advanced syntax supported)
            date_range: Optional tuple (start_date, end_date) in YYYY/MM/DD format
            max_results: Maximum results to retrieve (default: 1000)
            analyze_keywords: Whether to analyze keywords (default: True)
            include_trends: Whether to include trend analysis (default: True)
        
        Returns:
        {
            "articles": List[Dict],  # Article data
            "keyword_analysis": {
                "top_keywords": [...],  # Research hotspots
                "trends": {...}  # Trend data over time
            },
            "publication_counts": {...},  # Publication count analysis
            "query_used": str,
            "article_count": int
        }
        """
        # Run search in executor (Bio.Entrez is blocking)
        loop = asyncio.get_event_loop()
        articles = await loop.run_in_executor(
            None,
            lambda: self.searcher.search(
                advanced_search=query,
                date_range=date_range,
                max_results=max_results
            )
        )
        
        result = {
            "articles": articles,
            "query_used": query,
            "article_count": len(articles)
        }
        
        # Analyze keywords if requested
        if analyze_keywords and articles:
            try:
                keyword_analysis = await loop.run_in_executor(
                    None,
                    lambda: self.analyzer.analyze_research_keywords(
                        articles,
                        top_n=20,
                        include_trends=include_trends
                    )
                )
                
                pub_counts = await loop.run_in_executor(
                    None,
                    lambda: self.analyzer.analyze_publication_count(articles, months_per_period=3)
                )
                
                result["keyword_analysis"] = keyword_analysis
                result["publication_counts"] = pub_counts
            except Exception as e:
                logger.warning(f"Keyword analysis failed: {e}")
                result["keyword_analysis"] = {}
                result["publication_counts"] = {}
        
        return result
    
    def get_top_keywords(self, analysis_result: Dict[str, Any], top_n: int = 10) -> List[str]:
        """
        Extract top keywords from analysis result.
        
        Useful for mechanism discovery.
        """
        if "keyword_analysis" not in analysis_result:
            return []
        
        top_keywords = analysis_result["keyword_analysis"].get("top_keywords", [])
        return [kw["keyword"] for kw in top_keywords[:top_n]]
    
    async def search_pharmacogenomics_cases(
        self,
        gene: str,
        drug: str,
        max_results: int = 50
    ) -> List[Dict]:
        """
        Search PubMed for pharmacogenomics case reports.
        
        Args:
            gene: Pharmacogene symbol (e.g., "DPYD", "UGT1A1", "TPMT")
            drug: Drug name (e.g., "fluoropyrimidine", "irinotecan")
            max_results: Maximum number of results to return
        
        Returns:
            List of PubMed results with abstracts
        """
        query = f'"{gene} deficiency" AND "{drug}" AND "case report"'
        results = await self.search_with_analysis(
            query=query,
            max_results=max_results,
            analyze_keywords=False
        )
        return results.get("articles", [])










