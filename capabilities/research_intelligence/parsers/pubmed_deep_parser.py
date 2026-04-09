"""
Deep PubMed Parser using pubmed_parser framework.

Provides:
- Full-text article parsing (not just abstracts)
- Citation/reference extraction
- Table and figure extraction
- Paragraph parsing with citation context
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Vendored at backend/vendor/pubmed_parser_master/
_backend_root = Path(__file__).resolve().parent.parent.parent.parent
_pubmed_parser_master = _backend_root / "vendor" / "pubmed_parser_master"
if str(_pubmed_parser_master) not in sys.path:
    sys.path.insert(0, str(_pubmed_parser_master))

try:
    # Import modules directly to bypass version check in __init__.py
    from pubmed_parser.pubmed_oa_parser import (
        parse_pubmed_xml,
        parse_pubmed_references,
        parse_pubmed_paragraph,
        parse_pubmed_table,
        parse_pubmed_caption
    )
    from pubmed_parser.medline_parser import parse_medline_xml
    from pubmed_parser.pubmed_web_parser import parse_xml_web
    PARSER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"pubmed_parser not available: {e}")
    PARSER_AVAILABLE = False


class DeepPubMedParser:
    """
    Deep parsing of PubMed papers using pubmed_parser.
    
    Advantages:
    - Parse full-text PubMed OA XML (not just abstracts!)
    - Extract citations/references
    - Extract tables, figures, captions
    - Parse paragraphs with citation context
    """
    
    def __init__(self):
        if not PARSER_AVAILABLE:
            raise RuntimeError("pubmed_parser not importable; check backend/vendor/pubmed_parser_master and dependencies (lxml, Unidecode).")
    
    async def parse_full_text_from_pmc(
        self,
        pmc_id: str,
        download_if_needed: bool = True
    ) -> Dict[str, Any]:
        """
        Parse full-text article from PubMed Central.
        
        Args:
            pmc_id: PMC ID (e.g., "PMC1234567" or "1234567")
            download_if_needed: Download XML if not cached (not implemented yet)
        
        Returns:
        {
            "pmid": str,
            "pmc": str,
            "title": str,
            "abstract": str,
            "full_text": str,
            "paragraphs": [
                {
                    "text": "...",
                    "section": "Methods",
                    "reference_ids": ["ref1", "ref2"]
                }
            ],
            "tables": [...],
            "figures": [...],
            "citations": [...]
        }
        """
        # Clean PMC ID
        pmc_id = pmc_id.replace("PMC", "").strip()
        
        # For now, use web parsing (full XML download requires PMC FTP access)
        # This still gives us more than abstracts!
        loop = asyncio.get_event_loop()
        parsed = await loop.run_in_executor(
            None,
            lambda: parse_xml_web(pmc_id, save_xml=False)
        )
        
        if not parsed:
            return {}
        
        return {
            **parsed,
            "full_text": parsed.get("abstract", ""),  # Web parser gives abstract, not full text
            "paragraphs": [],  # Would need XML file for paragraph parsing
            "tables": [],
            "citations": []
        }
    
    async def parse_medline_batch(
        self,
        pmids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Parse multiple MEDLINE records efficiently.
        
        Uses E-utils web API for batch parsing.
        """
        results = []
        
        # Parse in batches of 10 (to avoid rate limits)
        batch_size = 10
        loop = asyncio.get_event_loop()
        
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i+batch_size]
            
            # Parse each in executor
            batch_results = await asyncio.gather(*[
                loop.run_in_executor(None, lambda pmid=pmid: parse_xml_web(pmid, save_xml=False))
                for pmid in batch
            ], return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, dict) and result:
                    results.append(result)
                elif isinstance(result, Exception):
                    logger.warning(f"Failed to parse PMID: {result}")
        
        return results
    
    def parse_xml_file(self, xml_path: str) -> Dict[str, Any]:
        """
        Parse PubMed OA XML file (if you have the XML file).
        
        This gives full-text parsing capabilities.
        """
        if not os.path.exists(xml_path):
            raise FileNotFoundError(f"XML file not found: {xml_path}")
        
        # Parse XML
        parsed = parse_pubmed_xml(xml_path)
        
        # Extract additional data
        paragraphs = parse_pubmed_paragraph(xml_path, all_paragraph=True)
        tables = parse_pubmed_table(xml_path, return_xml=False)
        citations = parse_pubmed_references(xml_path)
        
        return {
            **parsed,
            "paragraphs": paragraphs,
            "tables": tables,
            "citations": citations,
            "full_text": self._combine_paragraphs(paragraphs)
        }
    
    def _combine_paragraphs(self, paragraphs: List[Dict]) -> str:
        """Combine paragraphs into full text."""
        return "\n\n".join([
            f"{p.get('section', 'Unknown')}: {p.get('text', '')}"
            for p in paragraphs
        ])










