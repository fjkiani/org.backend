"""
Research Question Formulator

Uses LLM to decompose natural language questions into structured research plans.
"""

import json
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

try:
    from .llm_provider.llm_abstract import get_llm_provider

    _p = get_llm_provider()
    LLM_AVAILABLE = _p.is_available()
except Exception:
    LLM_AVAILABLE = False


class ResearchQuestionFormulator:
    """
    Uses LLM to decompose natural language questions into structured research plan.
    """
    
    def __init__(self):
        self.llm = None
        if LLM_AVAILABLE:
            try:
                from .llm_provider.llm_abstract import get_llm_provider

                self.llm = get_llm_provider()
                if not self.llm.is_available():
                    self.llm = None
            except Exception as e:
                logger.warning(f"LLM service not available: {e}")
    
    async def formulate_research_plan(
        self,
        question: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Decompose question into structured research plan.
        
        Input: "How do purple potatoes help with ovarian cancer?"
        
        Output:
        {
            "primary_question": "...",
            "entities": {
                "compound": "purple potatoes",
                "active_compounds": ["anthocyanins", "cyanidin"],
                "disease": "ovarian cancer",
                "mechanisms_of_interest": ["angiogenesis", "inflammation"]
            },
            "sub_questions": [...],
            "portal_queries": {
                "pubmed": [...]
            }
        }
        """
        if not self.llm:
            # Fallback: Simple extraction without LLM
            return self._simple_formulation(question, context)
        
        prompt = f"""Decompose this research question into a structured research plan:

Question: {question}
Context: {json.dumps(context, indent=2)}

Extract:
1. Primary question
2. Key entities (compound, disease, mechanisms)
3. Sub-questions to answer
4. PubMed search queries (use advanced syntax)

Return JSON only:
{{
    "primary_question": "...",
    "entities": {{
        "compound": "...",
        "active_compounds": [...],
        "disease": "...",
        "mechanisms_of_interest": [...]
    }},
    "sub_questions": [
        "What active compounds are in [compound]?",
        "What mechanisms do [active_compounds] target?",
        "What evidence exists for [compound] in [disease]?"
    ],
    "portal_queries": {{
        "pubmed": [
            "[compound] AND [disease]",
            "[active_compound] AND [disease] AND angiogenesis"
        ]
    }}
}}"""
        
        try:
            llm_resp = await self.llm.chat(
                prompt=prompt,
                system_message="You are a biomedical research analyst. Return valid JSON only.",
                temperature=0.3,
                max_tokens=1500,
            )
            response = llm_resp.text.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            plan = json.loads(response)
            return plan
        
        except Exception as e:
            logger.warning(f"LLM formulation failed: {e}, using fallback")
            return self._simple_formulation(question, context)
    
    def _simple_formulation(
        self,
        question: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Simple fallback formulation without LLM.
        
        Improved extraction: tries to find compound names, not just first word.
        """
        import re
        
        disease = context.get("disease", "cancer").replace("_", " ")
        
        # Check context first for compound/drug (more reliable than extracting from question)
        compound = context.get("compound") or context.get("drug") or context.get("food")
        if compound and compound.lower() not in ["unknown", "unknown drug", "unknown compound"]:
            # Use compound from context
            pass  # compound is already set, skip extraction
        else:
            compound = None  # Will be extracted from question below
        
        # Better compound extraction: look for common patterns (only if not in context)
        question_lower = question.lower()
        question_original = question
        
        # Common compound patterns (specific compounds first)
        compound_patterns = [
            r"(purple\s+potatoes?|sweet\s+potatoes?)",
            r"(vitamin\s+[A-Z])",
            r"(green\s+tea|EGCG)",
            r"(curcumin|turmeric)",
            r"(platinum\s+resistance|platinum)",
            r"(BRCA1|BRCA2|BRCA)",
        ]
        
        compound = None
        for pattern in compound_patterns:
            match = re.search(pattern, question_lower, re.IGNORECASE)
            if match:
                # Extract from original question to preserve capitalization
                start, end = match.span()
                compound = question_original[start:end].strip()
                break
        
        # Pattern: "How do/does X help/interact/target..." - extract X (stop at action verb)
        # Use non-greedy match to stop at first action verb
        action_verbs = r"(?:help|target|prevent|interact|work|affect|inhibit|activate|with|in)"
        if not compound:
            match = re.search(rf"(?:how\s+)?(?:do|does)\s+([^?]+?)\s+{action_verbs}", question_lower)
            if match:
                potential = match.group(1).strip()
                # Extract only the compound name (first 1-2 words, stop at action verbs)
                words = potential.split()
                compound_words = []
                stop_at = {"interact", "help", "target", "prevent", "work", "affect", "inhibit", "activate", "with", "in", "the", "a", "an", "for"}
                for word in words:
                    if word.lower() in stop_at:
                        break  # Stop at first action verb or stop word
                    compound_words.append(word)
                    if len(compound_words) >= 2:  # Compound names are usually 1-2 words
                        break
                if compound_words:
                    compound = " ".join(compound_words)
        
        # Pattern: "What compounds/foods X..." - extract X (the thing being asked about)
        if not compound:
            match = re.search(r"what\s+(?:compounds|foods)\s+([^?]+)", question_lower)
            if match:
                potential = match.group(1).strip()
                words = [w for w in potential.split() if w.lower() not in ["the", "a", "an", "help", "prevent", "target"]]
                if words:
                    compound = " ".join(words[:3])
        
        # Pattern: "What X help/prevent..." - extract X (but not if it's "compounds" or "foods")
        if not compound:
            match = re.search(r"what\s+([^?]+?)\s+(?:help|prevent|target)", question_lower)
            if match:
                potential = match.group(1).strip()
                # Skip if it's just "compounds" or "foods"
                if potential.lower() not in ["compounds", "foods"]:
                    words = [w for w in potential.split() if w.lower() not in ["the", "a", "an", "compounds", "foods"]]
                    if words:
                        compound = " ".join(words[:3])
        
        # Pattern: "What mechanisms does X target" - extract X
        if not compound:
            match = re.search(r"what\s+mechanisms\s+does\s+([^?]+?)\s+target", question_lower)
            if match:
                compound = match.group(1).strip()
        
        # Final fallback: extract meaningful words (skip question words)
        if not compound:
            stop_words = {"how", "do", "does", "what", "compounds", "foods", "help", "with", "the", "a", "an", "in", "for", "and", "or"}
            words = [w for w in question.split() if w.lower() not in stop_words]
            if len(words) >= 2:
                compound = " ".join(words[:3])
            elif words:
                compound = words[0]
            else:
                compound = "unknown"
        
        # Clean up compound name
        compound = compound.strip().title() if compound else "unknown"
        
        # Normalize disease names for PubMed (remove abbreviations, expand common terms)
        disease_normalized = disease
        disease_mappings = {
            "ovarian cancer hgs": "ovarian cancer",
            "ovarian_cancer_hgs": "ovarian cancer",
            "breast cancer": "breast cancer",
            "breast_cancer": "breast cancer",
            "general cancer": "cancer",
            "general_cancer": "cancer",
        }
        
        if disease.lower() in disease_mappings:
            disease_normalized = disease_mappings[disease.lower()]
        elif "cancer" in disease.lower():
            # Extract main cancer type (e.g., "ovarian cancer" from "ovarian cancer hgs")
            parts = disease.lower().split()
            if "cancer" in parts:
                cancer_idx = parts.index("cancer")
                disease_normalized = " ".join(parts[:cancer_idx + 1])
        
        # Build better PubMed queries with normalized disease names
        pubmed_queries = [
            f'"{compound}" AND {disease_normalized}',
            f"{compound} AND {disease_normalized}",
        ]
        
        # Add cancer-specific query if disease is cancer-related
        if "cancer" in disease_normalized.lower():
            pubmed_queries.append(f"{compound} AND cancer")
        
        # Add broader query without quotes for better matching
        pubmed_queries.append(f"{compound} AND ({disease_normalized} OR cancer)")
        
        return {
            "primary_question": question,
            "entities": {
                "compound": compound,
                "disease": disease,
                "mechanisms_of_interest": []
            },
            "sub_questions": [
                f"What mechanisms does {compound} target?",
                f"What evidence exists for {compound} in {disease}?"
            ],
            "portal_queries": {
                "pubmed": pubmed_queries
            }
        }










