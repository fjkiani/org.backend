"""
Value Synthesizer

Synthesizes research data into actionable insights using LLM.
Generates persona-specific "What This Means" sections.
"""

from typing import Dict, Any, Optional
import json
import re
import logging

from .llm_provider.llm_abstract import get_llm_provider, LLMProvider

logger = logging.getLogger(__name__)


class ValueSynthesizer:
    """Synthesizes research data into actionable insights."""
    
    def __init__(self):
        try:
            self.llm = get_llm_provider(provider=LLMProvider.GROQ)
            self.llm_available = self.llm and self.llm.is_available()
        except Exception as e:
            logger.warning(f"LLM provider not available for value synthesis: {e}")
            self.llm = None
            self.llm_available = False
    
    async def synthesize_insights(
        self,
        query_result: Dict[str, Any],
        persona: str = "patient"
    ) -> Dict[str, Any]:
        """
        Generate "What This Means" insights.
        
        Args:
            query_result: Full Research Intelligence API response
            persona: Target persona (patient, doctor, r&d)
        
        Returns:
        {
            "executive_summary": "...",
            "what_this_means": "...",
            "action_items": [...],
            "confidence": 0.85,
            "recommendations": [...]
        }
        """
        synthesized = query_result.get("synthesized_findings", {})
        moat = query_result.get("moat_analysis", {})
        research_plan = query_result.get("research_plan", {})
        
        # Build prompt for LLM
        prompt = self._build_synthesis_prompt(
            synthesized, moat, research_plan, persona
        )
        
        try:
            if self.llm_available:
                # Call LLM
                response = await self.llm.chat(
                    message=prompt,
                    temperature=0.3,
                    max_tokens=1000
                )
                
                # Parse response
                insights = self._parse_llm_response(response.text, persona)
                return insights
            else:
                # Fallback without LLM
                return self._fallback_insights(synthesized, moat, persona)
        except Exception as e:
            logger.warning(f"Value synthesis LLM call failed: {e}")
            return self._fallback_insights(synthesized, moat, persona)
    
    def _build_synthesis_prompt(
        self,
        synthesized: Dict[str, Any],
        moat: Dict[str, Any],
        research_plan: Dict[str, Any],
        persona: str
    ) -> str:
        """Build LLM prompt for value synthesis."""
        mechanisms = synthesized.get("mechanisms", [])
        evidence_tier = synthesized.get("evidence_tier", "Unknown")
        confidence = synthesized.get("overall_confidence", 0.5)
        question = research_plan.get("primary_question", "")
        
        # Extract mechanism names
        mechanism_names = []
        for mech in mechanisms[:5]:
            if isinstance(mech, dict):
                mechanism_names.append(mech.get("mechanism", ""))
            else:
                mechanism_names.append(str(mech))
        
        if persona == "patient":
            prompt = f"""Based on this research analysis:
- Question: {question}
- Mechanisms found: {len(mechanisms)}
- Mechanism names: {', '.join(mechanism_names[:3])}
- Evidence strength: {evidence_tier}
- Confidence: {confidence:.0%}

Generate a patient-friendly summary that answers:
1. Will this help me? (Yes/No/Maybe with explanation)
2. Is it safe? (Safety assessment)
3. What should I do? (Action items)

Use simple language, avoid jargon. Return JSON:
{{
    "executive_summary": "Brief 2-3 sentence summary",
    "will_this_help": "Clear yes/no/maybe with explanation",
    "is_it_safe": "Safety assessment in simple terms",
    "action_items": ["Action 1", "Action 2", "Action 3"],
    "confidence": {confidence}
}}"""
        elif persona == "doctor":
            prompt = f"""Based on this research analysis:
- Question: {question}
- Mechanisms: {mechanism_names}
- Evidence tier: {evidence_tier}
- Confidence: {confidence:.0%}

Generate clinical insights:
1. Clinical recommendation
2. Evidence quality assessment
3. Safety considerations
4. Next steps

Return JSON:
{{
    "executive_summary": "Brief clinical summary",
    "clinical_recommendation": "Specific recommendation",
    "evidence_quality": "Assessment of evidence quality",
    "safety_considerations": "Safety considerations",
    "next_steps": ["Step 1", "Step 2"],
    "confidence": {confidence}
}}"""
        else:  # r&d
            prompt = f"""Based on this research analysis:
- Question: {question}
- Mechanisms: {mechanism_names}
- Evidence tier: {evidence_tier}

Generate research insights:
1. What's known
2. Knowledge gaps
3. Research opportunities
4. Next research steps

Return JSON:
{{
    "executive_summary": "Brief research summary",
    "whats_known": "What is currently known",
    "knowledge_gaps": ["Gap 1", "Gap 2"],
    "research_opportunities": ["Opportunity 1", "Opportunity 2"],
    "next_steps": ["Step 1", "Step 2"]
}}"""
        
        return prompt
    
    def _parse_llm_response(self, response_text: str, persona: str) -> Dict[str, Any]:
        """Parse LLM response into structured insights."""
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                # Validate required fields
                if "executive_summary" not in parsed:
                    parsed["executive_summary"] = response_text[:500]
                return parsed
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM JSON response")
        
        # Fallback: return simple structure
        return {
            "executive_summary": response_text[:500] if response_text else "Analysis completed.",
            "confidence": 0.5
        }
    
    def _fallback_insights(
        self,
        synthesized: Dict[str, Any],
        moat: Dict[str, Any],
        persona: str
    ) -> Dict[str, Any]:
        """Generate fallback insights without LLM."""
        mechanisms = synthesized.get("mechanisms", [])
        evidence_tier = synthesized.get("evidence_tier", "Unknown")
        confidence = synthesized.get("overall_confidence", 0.5)
        
        if persona == "patient":
            return {
                "executive_summary": f"Based on analysis of {len(mechanisms)} mechanisms, the evidence strength is {evidence_tier}.",
                "will_this_help": f"The evidence suggests this may be {'helpful' if evidence_tier == 'Supported' else 'potentially helpful' if evidence_tier == 'Consider' else 'uncertain'}.",
                "is_it_safe": "Please discuss safety with your doctor before making any decisions.",
                "action_items": [
                    "Discuss these findings with your doctor",
                    "Review the evidence carefully",
                    "Consider your individual circumstances"
                ],
                "confidence": confidence
            }
        elif persona == "doctor":
            return {
                "executive_summary": f"Analysis identified {len(mechanisms)} mechanisms with {evidence_tier} evidence tier.",
                "clinical_recommendation": f"Evidence tier {evidence_tier} suggests {'strong consideration' if evidence_tier == 'Supported' else 'consideration' if evidence_tier == 'Consider' else 'limited evidence'}.",
                "evidence_quality": f"Confidence level: {confidence:.0%}",
                "safety_considerations": "Review toxicity and interaction data before prescribing.",
                "next_steps": [
                    "Review full evidence",
                    "Consider patient-specific factors",
                    "Monitor for safety"
                ],
                "confidence": confidence
            }
        else:  # r&d
            knowledge_gaps = synthesized.get("knowledge_gaps", [])
            return {
                "executive_summary": f"Research analysis completed. {len(mechanisms)} mechanisms identified with {evidence_tier} evidence tier.",
                "whats_known": f"Current understanding includes {len(mechanisms)} key mechanisms.",
                "knowledge_gaps": knowledge_gaps[:5] if knowledge_gaps else ["More research needed on efficacy", "Long-term safety data needed"],
                "research_opportunities": [
                    "Further mechanistic studies",
                    "Clinical trial validation",
                    "Biomarker identification"
                ],
                "next_steps": [
                    "Conduct additional studies",
                    "Validate findings in larger cohorts",
                    "Explore combination therapies"
                ]
            }

