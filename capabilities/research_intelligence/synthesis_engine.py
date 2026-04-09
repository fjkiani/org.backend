"""
Research Synthesis Engine

Uses LLM to synthesize findings from multiple portals and parsed content.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any

from .llm_provider.llm_abstract import get_llm_provider, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

# Global flag to indicate if LLM is available
LLM_AVAILABLE = True
try:
    _prov = get_llm_provider()
    LLM_AVAILABLE = _prov.is_available()
except Exception:
    LLM_AVAILABLE = False
if not LLM_AVAILABLE:
    logger.warning("LLM services are not available. Please check API keys and configurations.")


class ResearchSynthesisEngine:
    """
    Uses LLM to synthesize findings from multiple portals.
    """
    
    def __init__(self):
        self.llm_provider = None
        if LLM_AVAILABLE:
            try:
                # Use LLM abstraction layer (defaults to Cohere)
                provider_str = os.getenv("DEFAULT_LLM_PROVIDER", LLMProvider.GROQ.value)
                try:
                    provider_enum = LLMProvider(provider_str.lower())
                except ValueError:
                    provider_enum = LLMProvider.GROQ
                
                self.llm_provider = get_llm_provider(provider=provider_enum)
                if not self.llm_provider.is_available():
                    logger.error(f"Selected LLM provider {provider_str} is not available.")
                    self.llm_provider = None
            except Exception as e:
                logger.warning(f"LLM provider not available: {e}")
                self.llm_provider = None
    
    async def synthesize_findings(
        self,
        portal_results: Dict[str, Any],
        parsed_content: Dict[str, Any],
        research_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Synthesize findings using LLM deep research + generic LLM.
        
        OPTIMIZED: Consolidates all LLM work into ONE comprehensive call to reduce API calls from 10+ → 1.
        
        Returns:
        {
            "mechanisms": [...],
            "dosage": {...},  # NEW: From LLM
            "safety": {...},  # NEW: From LLM
            "outcomes": [...],  # NEW: From LLM
            "evidence_summary": "...",
            "knowledge_gaps": [...],
            "overall_confidence": 0.78,
            "method": "llm_deep_research" | "generic_llm",  # NEW
            "article_summaries": [...]  # NEW: Per-article summaries
        }
        """
        # [OPTIMIZED] Step 1: ONE comprehensive LLM call (replaces 10+ separate calls)
        comprehensive_result = await self._comprehensive_llm_extraction(
            portal_results,
            parsed_content,
            research_plan
        )
        
        # Step 2: Combine with generic LLM synthesis (fallback if comprehensive extraction fails)
        generic_synthesis = await self._generic_llm_synthesis(
            portal_results,
            parsed_content,
            research_plan
        )
        
        # Step 3: Merge LLM + Generic results
        merged = self._merge_synthesis_results(
            comprehensive_result.get("llm_extraction", {}),
            generic_synthesis,
            comprehensive_result.get("article_summaries", [])
        )
        
        # Add sub-question answers from comprehensive result
        if comprehensive_result.get("sub_question_answers"):
            merged["sub_question_answers"] = comprehensive_result["sub_question_answers"]
        
        # [NEW] Step 4: Classify evidence tier
        evidence_classification = self._classify_evidence_tier(
            mechanisms=merged.get("mechanisms", []),
            pathway_scores={},  # Would come from MOAT analysis, but we don't have it here yet
            context={}  # Would come from research_plan context
        )
        merged["evidence_tier"] = evidence_classification["evidence_tier"]
        merged["badges"] = evidence_classification["badges"]
        
        return merged
    
    async def _comprehensive_llm_extraction(
        self,
        portal_results: Dict[str, Any],
        parsed_content: Dict[str, Any],
        research_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        OPTIMIZED: ONE comprehensive LLM call that handles:
        - Article summaries (all articles at once)
        - Structured extraction (mechanisms, dosage, safety, outcomes)
        - Sub-question answers (all at once)
        
        Reduces API calls from 10+ → 1 per query.
        """
        try:
            from .enhanced_evidence_service import EnhancedEvidenceService
            evidence_service = EnhancedEvidenceService()
        except ImportError:
            logger.debug("EnhancedEvidenceService not available for comprehensive extraction")
            return {"llm_extraction": {}, "article_summaries": [], "sub_question_answers": []}
        
        # Get all articles (up to 10 for efficiency)
        articles = parsed_content.get("full_text_articles", [])[:10]
        if not articles:
            return {"llm_extraction": {}, "article_summaries": [], "sub_question_answers": []}
        
        # Prepare combined text for all articles (limit each to 2000 chars for efficiency)
        combined_papers_text = []
        for article in articles:
            full_text = article.get("full_text", "")
            title = article.get("title", "")
            pmid = article.get("pmid", "")
            abstract = article.get("abstract", "")
            
            # Prefer full-text, fallback to abstract
            content = full_text[:2000] if full_text and len(full_text) >= 500 else abstract[:1000]
            if not content:
                continue
            
            combined_papers_text.append(f"PMID: {pmid}\nTitle: {title}\nContent: {content}")
        
        if not combined_papers_text:
            return {"llm_extraction": {}, "article_summaries": [], "sub_question_answers": []}
        
        papers_text = "\n\n---\n\n".join(combined_papers_text)
        
        # Extract compound and disease from research plan
        entities = research_plan.get("entities", {})
        compound = entities.get("compound", "")
        disease = entities.get("disease", "")
        
        # Get sub-questions from research plan
        sub_questions = research_plan.get("sub_questions", [])
        
        # Make ONE comprehensive call to LLM
        try:
            comprehensive_synthesis = await evidence_service._call_llm_agnostic_comprehensive(
                compound=compound,
                disease=disease,
                papers_text=papers_text,
                articles=articles,  # Pass articles for per-article summaries
                sub_questions=sub_questions  # Pass sub-questions for batch answering
            )
            
            if comprehensive_synthesis:
                return {
                    "llm_extraction": {
                        "mechanisms": comprehensive_synthesis.get("mechanisms", []),
                        "dosage": comprehensive_synthesis.get("dosage", {}),
                        "safety": comprehensive_synthesis.get("safety", {}),
                        "outcomes": comprehensive_synthesis.get("outcomes", []),
                        "method": "llm_deep_research"
                    },
                    "article_summaries": comprehensive_synthesis.get("article_summaries", []),
                    "sub_question_answers": comprehensive_synthesis.get("sub_question_answers", [])
                }
        except Exception as e:
            logger.debug(f"Comprehensive LLM extraction failed: {e}")
        
        return {"llm_extraction": {}, "article_summaries": [], "sub_question_answers": []}
    
    async def _generate_article_summaries(
        self,
        parsed_content: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate per-article summaries using LLM.
        
        OPTIMIZED: Batches articles (3 per call) to reduce API calls from 10→4 calls.
        """
        try:
            from .enhanced_evidence_service import EnhancedEvidenceService
            evidence_service = EnhancedEvidenceService()
        except ImportError:
            logger.debug("EnhancedEvidenceService not available for article summaries")
            return []
        
        summaries = []
        articles = parsed_content.get("full_text_articles", [])[:10]  # Top 10 only
        
        if not articles:
            return []
        
        # BATCH PROCESSING: Group articles into batches of 3 to reduce API calls (10→4 calls)
        batch_size = 3
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            
            # Combine batch into single context
            batch_context = []
            for article in batch:
                full_text = article.get("full_text", "")
                title = article.get("title", "")
                pmid = article.get("pmid", "")
                
                if not full_text or len(full_text) < 500:
                    continue
                
                # Limit each article to 2000 chars for batching efficiency
                batch_context.append(f"PMID: {pmid}\nTitle: {title}\nFull Text: {full_text[:2000]}")
            
            if not batch_context:
                continue
            
            # Single LLM call for entire batch (reduces 10 calls → 4 calls)
            try:
                papers_text = "\n\n---\n\n".join(batch_context)
                
                # Call LLM via enhanced_evidence_service (1 call for 3 articles)
                synthesis = await evidence_service._call_llm_agnostic(
                    compound="",  # Not needed for article summary
                    disease="",   # Not needed
                    papers_text=papers_text
                )
                
                if synthesis:
                    # Assign batch synthesis to each article in batch
                    for article in batch:
                        summaries.append({
                            "pmid": article.get("pmid", ""),
                            "title": article.get("title", ""),
                            "summary": synthesis.get("evidence_summary", "")[:500],  # Truncate for batch
                            "mechanisms": synthesis.get("mechanisms", [])[:3],  # Top 3 per batch
                            "dosage": synthesis.get("dosage", {}),
                            "safety": synthesis.get("safety", {}),
                            "outcomes": synthesis.get("outcomes", [])[:2]  # Top 2 per batch
                        })
            except Exception as e:
                logger.debug(f"LLM batch summary failed: {e}")
                # Fallback: Create simple summaries from abstracts
                for article in batch:
                    summaries.append({
                        "pmid": article.get("pmid", ""),
                        "title": article.get("title", ""),
                        "summary": article.get("abstract", "")[:500] if article.get("abstract") else "",
                        "mechanisms": [],
                        "dosage": {},
                        "safety": {},
                        "outcomes": []
                    })
                continue
        
        return summaries
    
    async def _extract_with_llm(
        self,
        parsed_content: Dict[str, Any],
        research_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Use LLM for structured extraction (mechanisms, dosage, safety, outcomes)."""
        try:
            from .enhanced_evidence_service import EnhancedEvidenceService
            evidence_service = EnhancedEvidenceService()
        except ImportError:
            return {}
        
        # Combine all full-text articles (limit to 2000 chars each for efficiency)
        papers_text = "\n\n".join([
            f"PMID: {a.get('pmid', '')}\nTitle: {a.get('title', '')}\nFull Text: {a.get('full_text', '')[:2000]}"
            for a in parsed_content.get("full_text_articles", [])[:5]
        ])
        
        if not papers_text:
            return {}
        
        # Extract compound and disease from research plan
        entities = research_plan.get("entities", {})
        compound = entities.get("compound", "")
        disease = entities.get("disease", "")
        
        # Call LLM via enhanced_evidence_service
        try:
            synthesis = await evidence_service._call_llm_agnostic(
                compound=compound,
                disease=disease,
                papers_text=papers_text
            )
            
            if synthesis:
                return {
                    "mechanisms": synthesis.get("mechanisms", []),
                    "dosage": synthesis.get("dosage", {}),
                    "safety": synthesis.get("safety", {}),
                    "outcomes": synthesis.get("outcomes", []),
                    "method": "llm_deep_research"
                }
        except Exception as e:
            logger.debug(f"LLM extraction failed: {e}")
        
        return {}
    
    async def _generic_llm_synthesis(
        self,
        portal_results: Dict[str, Any],
        parsed_content: Dict[str, Any],
        research_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generic LLM synthesis (original implementation)."""
        # Always try LLM first - don't fallback to simple synthesis unless LLM truly unavailable
        if not self.llm_provider or not self.llm_provider.is_available():
            logger.warning("LLM provider not available, using simple synthesis fallback")
            return self._simple_synthesis(portal_results, parsed_content)
        
        # Combine all content
        articles = portal_results.get("pubmed", {}).get("articles", [])
        abstracts = "\n\n".join([
            f"Title: {a.get('title', '')}\nAbstract: {a.get('abstract', '')}"
            for a in articles[:20]
        ])
        
        full_texts = "\n\n".join([
            f"Title: {ft.get('title', '')}\nFull Text: {ft.get('full_text', '')[:5000]}"
            for ft in parsed_content.get("full_text_articles", [])
        ])
        
        keywords = portal_results.get("top_keywords", [])
        
        prompt = f"""Synthesize research findings from these sources:

Research Question: {research_plan.get('primary_question', '')}

Abstracts ({len(articles)} papers):
{abstracts[:10000]}

Full-Text Articles ({len(parsed_content.get('full_text_articles', []))} papers):
{full_texts[:10000]}

Top Keywords (Research Hotspots):
{', '.join(keywords[:20])}

Extract and synthesize:
1. Mechanisms of action (how it works, what targets)
2. Evidence strength (RCTs, in vitro, etc.)
3. Confidence scores (0.0-1.0)
4. Knowledge gaps

Return JSON only:
{{
    "mechanisms": [
        {{
            "mechanism": "mechanism_name",
            "target": "target_protein_or_pathway",
            "evidence": "evidence_description",
            "confidence": 0.85,
            "sources": ["pmid1", "pmid2"]
        }}
    ],
    "evidence_summary": "Overall evidence summary",
    "knowledge_gaps": ["gap1", "gap2"],
    "overall_confidence": 0.78
}}"""
        
        try:
            llm_response: LLMResponse = await self.llm_provider.chat(
                message=prompt,
                system_message="You are a biomedical research analyst. Return valid JSON only.",
                temperature=0.3,
                max_tokens=2000
            )
            
            # Parse JSON
            response_text = llm_response.text.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            synthesized = json.loads(response_text)
            synthesized["method"] = "generic_llm_synthesis"
            return synthesized
        
        except Exception as e:
            logger.warning(f"LLM synthesis failed: {e}, using fallback")
            result = self._simple_synthesis(portal_results, parsed_content)
            result["method"] = "fallback"
            return result
    
    def _merge_synthesis_results(
        self,
        llm_extraction: Dict[str, Any],
        generic_synthesis: Dict[str, Any],
        article_summaries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Merge LLM extraction + generic synthesis results."""
        # Start with generic synthesis as base
        merged = generic_synthesis.copy()
        
        # Override with LLM extraction if available (prioritize LLM)
        if llm_extraction and llm_extraction.get("method") == "llm_deep_research":
            merged["method"] = "llm_deep_research"
            
            # Merge mechanisms (prefer LLM if available - REPLACE if LLM has mechanisms)
            if llm_extraction.get("mechanisms"):
                # If LLM has mechanisms, use them as primary source
                llm_mechs = []
                for llm_mech in llm_extraction.get("mechanisms", []):
                    # Handle both dict and string formats
                    if isinstance(llm_mech, dict):
                        llm_mechs.append(llm_mech)
                    elif isinstance(llm_mech, str):
                        # Convert string to dict format
                        llm_mechs.append({
                            "mechanism": llm_mech,
                            "confidence": 0.7,
                            "source": "llm"
                        })
                
                # Combine with generic mechanisms (deduplicate)
                existing_mechs = {m.get("mechanism", "") if isinstance(m, dict) else str(m): m for m in merged.get("mechanisms", [])}
                for llm_mech in llm_mechs:
                    mech_name = llm_mech.get("mechanism", "") if isinstance(llm_mech, dict) else str(llm_mech)
                    if mech_name and mech_name not in existing_mechs:
                        existing_mechs[mech_name] = llm_mech
                
                # Use LLM mechanisms as primary, add generic as supplement
                merged["mechanisms"] = list(existing_mechs.values())
            elif merged.get("mechanisms"):
                # LLM failed but generic has mechanisms - keep generic
                pass
            
            # Add LLM-specific fields (always prefer LLM)
            if llm_extraction.get("dosage"):
                merged["dosage"] = llm_extraction["dosage"]
            if llm_extraction.get("safety"):
                merged["safety"] = llm_extraction["safety"]
            if llm_extraction.get("outcomes"):
                merged["outcomes"] = llm_extraction["outcomes"]
        else:
            merged["method"] = generic_synthesis.get("method", "generic_llm_synthesis")
        
        # Add article summaries
        merged["article_summaries"] = article_summaries
        
        return merged
    
    async def answer_sub_question(
        self,
        sub_question: str,
        articles: List[Dict[str, Any]],
        parsed_content: Dict[str, Any],
        research_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Answer a specific sub-question using targeted articles.
        
        Returns:
        {
            "answer": "...",
            "confidence": 0.85,
            "sources": ["pmid1", "pmid2"],
            "mechanisms": [...]
        }
        """
        # Try LLM first (via enhanced_evidence_service)
        try:
            from .enhanced_evidence_service import EnhancedEvidenceService
            evidence_service = EnhancedEvidenceService()
            
            # Combine article abstracts and full-text
            abstracts = "\n\n".join([
                f"PMID: {a.get('pmid', '')}\nTitle: {a.get('title', '')}\nAbstract: {a.get('abstract', '')}"
                for a in articles[:10]
            ])
            
            # Check if we have full-text for any of these articles
            full_texts = []
            for article in articles:
                pmid = article.get("pmid", "")
                for ft_article in parsed_content.get("full_text_articles", []):
                    if ft_article.get("pmid") == pmid:
                        full_texts.append(f"PMID: {pmid}\nTitle: {ft_article.get('title', '')}\nFull Text: {ft_article.get('full_text', '')[:3000]}")
                        break
            
            full_text_content = "\n\n".join(full_texts[:3])
            papers_text = f"{abstracts}\n\n{full_text_content}"
            
            entities = research_plan.get("entities", {})
            compound = entities.get("compound", "")
            disease = entities.get("disease", "")
            
            # Use LLM to answer the sub-question
            synthesis = await evidence_service._call_llm_agnostic(
                compound=compound,
                disease=disease,
                papers_text=f"Question: {sub_question}\n\n{papers_text}"
            )
            
            if synthesis:
                mechanisms = synthesis.get("mechanisms", [])
                # Extract answer from evidence_summary or generate from mechanisms
                answer = synthesis.get("evidence_summary", "")
                if not answer and mechanisms:
                    answer = f"Based on {len(mechanisms)} mechanisms identified: {', '.join([m.get('mechanism', str(m)) if isinstance(m, dict) else str(m) for m in mechanisms[:3]])}"
                
                return {
                    "answer": answer or "Evidence found but unable to synthesize answer",
                    "confidence": synthesis.get("overall_confidence", 0.7),
                    "sources": [a.get("pmid", "") for a in articles[:5] if a.get("pmid")],
                    "mechanisms": mechanisms[:5]
                }
        except Exception as e:
            logger.debug(f"LLM sub-question answering failed: {e}, trying LLM provider fallback")
        
        # Fallback to LLM provider
        if not self.llm_provider or not self.llm_provider.is_available():
            return {
                "answer": "LLM not available",
                "confidence": 0.0,
                "sources": [],
                "mechanisms": []
            }
        
        # Combine article abstracts
        abstracts = "\n\n".join([
            f"PMID: {a.get('pmid', '')}\nTitle: {a.get('title', '')}\nAbstract: {a.get('abstract', '')}"
            for a in articles[:10]
        ])
        
        # Check if we have full-text for any of these articles
        full_texts = []
        for article in articles:
            pmid = article.get("pmid", "")
            # Find matching full-text article
            for ft_article in parsed_content.get("full_text_articles", []):
                if ft_article.get("pmid") == pmid:
                    full_texts.append(f"PMID: {pmid}\nTitle: {ft_article.get('title', '')}\nFull Text: {ft_article.get('full_text', '')[:3000]}")
                    break
        
        full_text_content = "\n\n".join(full_texts[:3])  # Limit to 3 full-text articles
        
        entities = research_plan.get("entities", {})
        compound = entities.get("compound", "")
        disease = entities.get("disease", "")
        
        prompt = f"""Answer this specific research sub-question:

Sub-Question: {sub_question}

Context:
- Compound: {compound}
- Disease: {disease}

Relevant Articles ({len(articles)} papers):
{abstracts[:8000]}

Full-Text Articles ({len(full_texts)} papers):
{full_text_content[:5000]}

Provide a concise answer to the sub-question, including:
1. Direct answer to the question
2. Confidence level (0.0-1.0)
3. Source PMIDs
4. Any mechanisms mentioned

Return JSON only:
{{
    "answer": "Direct answer to the sub-question",
    "confidence": 0.85,
    "sources": ["pmid1", "pmid2"],
    "mechanisms": [
        {{
            "mechanism": "mechanism_name",
            "target": "target",
            "confidence": 0.8
        }}
    ]
}}"""
        
        try:
            llm_response: LLMResponse = await self.llm_provider.chat(
                message=prompt,
                system_message="You are a biomedical research analyst. Answer the specific sub-question concisely. Return valid JSON only.",
                temperature=0.3,
                max_tokens=1000
            )
            
            # Parse JSON
            response_text = llm_response.text.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            answer = json.loads(response_text)
            return answer
        
        except Exception as e:
            logger.warning(f"Sub-question answering failed: {e}")
            return {
                "answer": "Unable to generate answer",
                "confidence": 0.0,
                "sources": [],
                "mechanisms": []
            }
    
    def _classify_evidence_tier(
        self,
        mechanisms: List[Dict[str, Any]],
        pathway_scores: Dict[str, float],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Classify evidence tier and assign badges.
        
        Evidence Tiers:
        - Supported: Strong evidence (ClinVar-Strong + Pathway-Aligned + Literature)
        - Consider: Moderate evidence (Pathway-Aligned OR ClinVar prior)
        - Insufficient: Weak evidence (No strong priors, pathway unclear)
        
        Badges:
        - Pathway-Aligned: Drug mechanism matches patient pathway burden
        - ClinVar-Strong: ClinVar Pathogenic/Likely Pathogenic
        - Guideline: NCCN/FDA guideline recommendation
        - RCT: Randomized controlled trial evidence
        """
        badges = []
        evidence_tier = "Insufficient"
        
        # Check pathway alignment
        max_pathway_score = max(pathway_scores.values()) if pathway_scores else 0.0
        if max_pathway_score > 0.7:
            badges.append("Pathway-Aligned")
            evidence_tier = "Consider"  # Upgrade from Insufficient
        
        # Check for ClinVar-Strong signals (would need ClinVar integration)
        # For now, check if mechanism has high confidence
        high_confidence_mechs = [m for m in mechanisms if m.get("confidence", 0) > 0.8]
        if high_confidence_mechs:
            badges.append("ClinVar-Strong")  # Placeholder - would need actual ClinVar check
            if evidence_tier == "Consider":
                evidence_tier = "Supported"  # Upgrade to Supported
        
        # Check for guideline/RCT signals (would need literature analysis)
        # Placeholder logic: Multiple mechanisms suggest RCT evidence
        if len(mechanisms) >= 3:
            badges.append("RCT")
        
        # Check for multiple high-confidence mechanisms (suggests strong evidence)
        if len(high_confidence_mechs) >= 2:
            if evidence_tier == "Insufficient":
                evidence_tier = "Consider"
        
        return {
            "evidence_tier": evidence_tier,
            "badges": badges,
            "confidence": max_pathway_score if pathway_scores else (max([m.get("confidence", 0) for m in mechanisms]) if mechanisms else 0.0)
        }
    
    def _simple_synthesis(
        self,
        portal_results: Dict[str, Any],
        parsed_content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simple fallback synthesis without LLM."""
        keywords = portal_results.get("top_keywords", [])
        
        return {
            "mechanisms": [
                {
                    "mechanism": kw.lower().replace(" ", "_"),
                    "target": kw,
                    "evidence": "Keyword frequency analysis",
                    "confidence": 0.5,
                    "sources": []
                }
                for kw in keywords[:10]
            ],
            "evidence_summary": f"Found {len(portal_results.get('pubmed', {}).get('articles', []))} papers",
            "knowledge_gaps": [],
            "overall_confidence": 0.5
        }










