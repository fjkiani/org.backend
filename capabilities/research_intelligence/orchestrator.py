"""
Research Intelligence Orchestrator

Combines all portals + parsers + LLM + MOAT for comprehensive research intelligence.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

# Load .env file before initializing portals
env_file = None
try:
    from dotenv import load_dotenv
    # Repo root: capabilities/research_intelligence -> backend -> repo
    env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        # Fallback: try current directory
        load_dotenv()
except ImportError:
    pass

from .portals.pubmed_enhanced import EnhancedPubMedPortal
from .parsers.pubmed_deep_parser import DeepPubMedParser
from .question_formulator import ResearchQuestionFormulator
from .synthesis_engine import ResearchSynthesisEngine
from .moat_integrator import MOATIntegrator

logger = logging.getLogger(__name__)

# Log .env loading status after logger is initialized
if env_file and env_file.exists():
    logger.info(f"✅ Loaded .env from {env_file}")
    email_set = os.getenv('NCBI_USER_EMAIL')
    logger.debug(f"NCBI_USER_EMAIL: {'SET' if email_set else 'NOT SET'}")


class ResearchIntelligenceOrchestrator:
    """
    Orchestrates multi-portal research with deep parsing and LLM synthesis.
    """
    
    def __init__(self):
        # Portals
        try:
            self.pubmed = EnhancedPubMedPortal()
        except Exception as e:
            logger.warning(f"EnhancedPubMedPortal not available: {e}")
            self.pubmed = None
        
        try:
            from .portals.project_data_sphere import ProjectDataSpherePortal
            self.project_data_sphere = ProjectDataSpherePortal()
        except Exception as e:
            logger.warning(f"ProjectDataSpherePortal not available: {e}")
            self.project_data_sphere = None
        
        try:
            from .portals.gdc_portal import GDCPortal
            self.gdc = GDCPortal()
        except Exception as e:
            logger.warning(f"GDCPortal not available: {e}")
            self.gdc = None
        
        # Parsers
        try:
            self.pubmed_parser = DeepPubMedParser()
        except Exception as e:
            logger.warning(f"DeepPubMedParser not available: {e}")
            self.pubmed_parser = None
        
        try:
            from .parsers.pharmacogenomics_parser import PharmacogenomicsParser
            self.pharmacogenomics_parser = PharmacogenomicsParser()
        except Exception as e:
            logger.warning(f"PharmacogenomicsParser not available: {e}")
            self.pharmacogenomics_parser = None
        
        # LLM Services (always available - has fallbacks)
        self.question_formulator = ResearchQuestionFormulator()
        self.synthesis_engine = ResearchSynthesisEngine()
        
        # MOAT
        self.moat_integrator = MOATIntegrator()
    
    def is_available(self) -> bool:
        """Check if orchestrator has minimum required components."""
        # Need at least one portal or parser, or LLM services (which have fallbacks)
        return self.pubmed is not None or self.pubmed_parser is not None or True  # LLM services always available
    
    async def research_question(
        self,
        question: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Full research pipeline for a question.
        
        Args:
            question: Natural language question (e.g., "How do purple potatoes help with ovarian cancer?")
            context: Patient context (disease, treatment_line, biomarkers)
        
        Returns:
        {
            "research_plan": {...},
            "portal_results": {...},
            "parsed_content": {...},
            "synthesized_findings": {...},
            "moat_analysis": {...},
            "provenance": {...}  # NEW: Complete provenance tracking
        }
        """
        import uuid
        from datetime import datetime
        
        # Generate run ID for reproducibility
        run_id = str(uuid.uuid4())
        methods_used = []
        
        # [1] Formulate research plan (LLM)
        research_plan = await self.question_formulator.formulate_research_plan(question, context)
        methods_used.append("question_formulation")
        
        # [2] Query portals (parallel)
        portal_results = await self._query_portals(research_plan)
        if portal_results.get("pubmed"):
            methods_used.append("pubmed_search")
        if portal_results.get("project_data_sphere"):
            methods_used.append("project_data_sphere")
        if portal_results.get("gdc"):
            methods_used.append("gdc_query")
        
        # [3] Deep parse top papers
        parsed_content = await self._deep_parse_top_papers(portal_results)
        if parsed_content.get("diffbot_count", 0) > 0:
            methods_used.append("diffbot_extraction")
        if parsed_content.get("pubmed_parser_count", 0) > 0:
            methods_used.append("pubmed_parser")
        if parsed_content.get("pharmacogenomics_cases"):
            methods_used.append("pharmacogenomics_extraction")
        
        # [4] LLM synthesis
        synthesized_findings = await self.synthesis_engine.synthesize_findings(
            portal_results,
            parsed_content,
            research_plan
        )
        if synthesized_findings.get("method") == "llm_deep_research":
            methods_used.append("llm_deep_research")
        else:
            methods_used.append("generic_llm_synthesis")
        
        # [NEW] [5] Answer sub-questions individually
        # OPTIMIZED: Check if sub-question answers are already available from comprehensive LLM extraction
        sub_question_answers = synthesized_findings.get("sub_question_answers", [])
        if not sub_question_answers:
            # Fallback: Answer sub-questions separately if not in comprehensive result
            sub_question_answers = await self._answer_sub_questions(
                research_plan,
                portal_results,
                parsed_content
            )
        if sub_question_answers:
            methods_used.append("sub_question_answering")
        
        # [6] MOAT analysis
        moat_analysis = await self.moat_integrator.integrate_with_moat(
            synthesized_findings,
            context
        )
        
        # [NEW] [7] Clinical trial recommendations (mechanism fit ranking)
        trial_recommendations = await self._get_clinical_trial_recommendations(
            synthesized_findings,
            moat_analysis,
            context
        )
        if trial_recommendations:
            moat_analysis["trial_recommendations"] = trial_recommendations
            methods_used.append("trial_recommendations")
        
        # [NEW] [8] Drug interaction checker
        drug_interactions = await self._check_drug_interactions(
            synthesized_findings,
            context,
            research_plan
        )
        if drug_interactions:
            moat_analysis["drug_interactions"] = drug_interactions
            methods_used.append("drug_interaction_check")
        
        # [NEW] [9] Citation network analysis
        citation_network = await self._analyze_citation_network(
            portal_results,
            parsed_content
        )
        if citation_network:
            moat_analysis["citation_network"] = citation_network
            methods_used.append("citation_network_analysis")
        
        # Track MOAT methods used
        if moat_analysis.get("cross_resistance"):
            methods_used.append("cross_resistance_analysis")
        if moat_analysis.get("toxicity_mitigation"):
            methods_used.append("toxicity_mitigation")
        if moat_analysis.get("sae_features"):
            methods_used.append("sae_feature_extraction")
        if moat_analysis.get("toxicity_risk"):
            methods_used.append("toxicity_risk_assessment")
        if moat_analysis.get("dosing_guidance"):
            methods_used.append("dosing_guidance")
        if moat_analysis.get("mechanism_vector"):
            methods_used.append("spe_framework")
        
        # [NEW] Build complete provenance
        provenance = {
            "run_id": run_id,
            "profile": context.get("profile", "baseline"),
            "methods": list(set(methods_used)),  # Deduplicate
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "inputs_snapshot": {
                "question": question,
                "context_keys": list(context.keys()),
                "disease": context.get("disease"),
                "treatment_line": context.get("treatment_line")
            },
            "output_summary": {
                "articles_parsed": parsed_content.get("parsed_count", 0),
                "mechanisms_found": len(synthesized_findings.get("mechanisms", [])),
                "sub_questions_answered": len(sub_question_answers),
                "moat_signals_extracted": len([k for k in moat_analysis.keys() if k not in ["pathways", "mechanisms", "pathway_scores", "treatment_line_analysis", "biomarker_analysis", "overall_confidence"]])
            }
        }
        
        return {
            "research_plan": research_plan,
            "portal_results": portal_results,
            "parsed_content": parsed_content,
            "synthesized_findings": synthesized_findings,
            "article_summaries": synthesized_findings.get("article_summaries", []),  # NEW: Per-article summaries
            "sub_question_answers": sub_question_answers,  # NEW: Individual sub-question answers
            "moat_analysis": moat_analysis,
            "provenance": provenance  # NEW
        }
    
    async def _get_clinical_trial_recommendations(
        self,
        synthesized_findings: Dict[str, Any],
        moat_analysis: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Get clinical trial recommendations based on mechanism fit.
        
        Returns:
        [
            {
                "nct_id": "NCT001",
                "title": "Trial Title",
                "mechanism_fit_score": 0.85,
                "mechanism_alignment": "HIGH",
                "rationale": "..."
            },
            ...
        ]
        """
        try:
            from api.services.clinical_trial_search_service import ClinicalTrialSearchService
            trial_service = ClinicalTrialSearchService()
        except Exception as e:
            logger.debug(f"ClinicalTrialSearchService not available: {e}")
            return []
        
        mechanisms = synthesized_findings.get("mechanisms", [])
        if not mechanisms:
            return []
        
        # Build search query from mechanisms
        mechanism_names = [m.get("mechanism", "") if isinstance(m, dict) else str(m) for m in mechanisms[:3]]
        query = f"{' '.join(mechanism_names)} AND {context.get('disease', 'cancer')}"
        
        # Search for trials
        try:
            disease_category = context.get("disease", "").replace("_", " ")
            trial_results = await trial_service.search_trials(
                query=query,
                disease_category=disease_category,
                top_k=20,
                min_score=0.5
            )
            
            if not trial_results.get("success"):
                return []
            
            trials = trial_results.get("data", {}).get("found_trials", [])
            if not trials:
                return []
            
            # Rank trials by mechanism fit
            sae_mechanism_vector = moat_analysis.get("sae_features", {}).get("mechanism_vector")
            if not sae_mechanism_vector:
                # Compute from mechanisms
                pathway_scores = moat_analysis.get("pathway_scores", {})
                sae_mechanism_vector = [
                    pathway_scores.get("dna_repair", 0.0),
                    pathway_scores.get("mapk", 0.0),
                    pathway_scores.get("pi3k", 0.0),
                    pathway_scores.get("vegf", 0.0),
                    pathway_scores.get("her2", 0.0),
                    0.0,  # IO
                    0.0   # Efflux
                ]
            
            # Rank using mechanism fit ranker
            ranked_trials = await self.moat_integrator.rank_trials_by_mechanism_fit(
                mechanisms=mechanisms,
                trials=trials,
                sae_mechanism_vector=sae_mechanism_vector
            )
            
            # Format for output
            recommendations = []
            for trial in ranked_trials[:10]:  # Top 10
                recommendations.append({
                    "nct_id": trial.get("nct_id", ""),
                    "title": trial.get("title", ""),
                    "mechanism_fit_score": trial.get("mechanism_fit_score", 0.0),
                    "mechanism_alignment": trial.get("mechanism_alignment_level", "UNKNOWN"),
                    "combined_score": trial.get("combined_score", 0.0),
                    "rationale": f"Mechanism fit: {trial.get('mechanism_fit_score', 0.0):.0%}"
                })
            
            return recommendations
        except Exception as e:
            logger.warning(f"Clinical trial recommendations failed: {e}")
            return []
    
    async def _check_drug_interactions(
        self,
        synthesized_findings: Dict[str, Any],
        context: Dict[str, Any],
        research_plan: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Check for drug interactions based on pathway overlap and pharmacogenomics.
        
        Returns:
        {
            "interactions": [
                {
                    "drug1": "curcumin",
                    "drug2": "tamoxifen",
                    "interaction_type": "pathway_overlap",
                    "severity": "MODERATE",
                    "mechanism": "CYP2D6 inhibition",
                    "recommendation": "..."
                }
            ],
            "warnings": [...]
        }
        """
        interactions = []
        warnings = []
        
        # Extract compound from research plan or context
        if research_plan:
            entities = research_plan.get("entities", {})
            compound = entities.get("compound", "")
        else:
            compound = context.get("compound", "")
        
        # Get prior therapies from context
        prior_therapies = context.get("prior_therapies", [])
        
        if not compound or not prior_therapies:
            return {"interactions": [], "warnings": []}
        
        # Check pathway overlap interactions
        mechanisms = synthesized_findings.get("mechanisms", [])
        mechanism_pathways = set()
        for mech in mechanisms:
            mech_name = mech.get("mechanism", "").lower() if isinstance(mech, dict) else str(mech).lower()
            # Map to pathways
            if "cyp" in mech_name or "cytochrome" in mech_name:
                mechanism_pathways.add("CYP")
            if "p-gp" in mech_name or "pgp" in mech_name or "efflux" in mech_name:
                mechanism_pathways.add("P-gp")
            if "ugt" in mech_name:
                mechanism_pathways.add("UGT")
        
        # Known drug-pathway interactions
        known_interactions = {
            "tamoxifen": {"CYP2D6": "MODERATE", "pathway": "Estrogen receptor"},
            "letrozole": {"CYP2A6": "LOW", "pathway": "Aromatase"},
            "carboplatin": {"DNA repair": "HIGH", "pathway": "DDR"},
            "paclitaxel": {"P-gp": "MODERATE", "pathway": "Efflux"}
        }
        
        for prior_drug in prior_therapies:
            prior_lower = prior_drug.lower()
            for known_drug, interaction_info in known_interactions.items():
                if known_drug.lower() in prior_lower:
                    # Check if compound affects same pathway
                    for pathway in mechanism_pathways:
                        if pathway in interaction_info.get("pathway", "").upper():
                            interactions.append({
                                "drug1": compound,
                                "drug2": prior_drug,
                                "interaction_type": "pathway_overlap",
                                "severity": interaction_info.get("CYP2D6") or interaction_info.get("DNA repair") or "MODERATE",
                                "mechanism": f"{pathway} pathway overlap",
                                "recommendation": f"Monitor for {interaction_info.get('pathway', 'interaction')} when combining {compound} with {prior_drug}"
                            })
        
        # Check pharmacogenomics interactions
        germline_genes = context.get("germline_genes", [])
        if germline_genes:
            for gene in germline_genes:
                if "CYP" in gene or "DPYD" in gene or "UGT" in gene:
                    warnings.append({
                        "type": "pharmacogenomics",
                        "gene": gene,
                        "message": f"{gene} variant may affect metabolism of {compound}",
                        "recommendation": "Consider pharmacogenomics testing"
                    })
        
        return {
            "interactions": interactions,
            "warnings": warnings
        }
    
    async def _analyze_citation_network(
        self,
        portal_results: Dict[str, Any],
        parsed_content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze citation network from PubMed articles.
        
        Returns:
        {
            "key_papers": [
                {
                    "pmid": "12345678",
                    "title": "...",
                    "citation_count": 150,
                    "influence_score": 0.85
                }
            ],
            "trends": {
                "publication_years": [2020: 10, 2021: 15, ...],
                "top_journals": ["Nature", "Cell", ...]
            },
            "knowledge_gaps": ["...", "..."]
        }
        """
        articles = portal_results.get("pubmed", {}).get("articles", [])
        if not articles:
            return {}
        
        # Extract key papers (high citation count or recent)
        key_papers = []
        publication_years = {}
        journals = {}
        
        for article in articles[:50]:  # Top 50
            pmid = article.get("pmid", "")
            title = article.get("title", "")
            year = article.get("publication_date", "")
            journal = article.get("journal", "")
            
            # Extract year
            if year:
                try:
                    year_int = int(year.split("-")[0] if "-" in year else year[:4])
                    publication_years[year_int] = publication_years.get(year_int, 0) + 1
                except:
                    pass
            
            # Track journals
            if journal:
                journals[journal] = journals.get(journal, 0) + 1
            
            # Estimate citation count from available metadata (if available)
            citation_count = article.get("citation_count", 0)
            
            # Key papers: high citations or recent (2020+)
            if citation_count > 50 or (year and int(year.split("-")[0] if "-" in year else year[:4]) >= 2020):
                key_papers.append({
                    "pmid": pmid,
                    "title": title[:100],
                    "citation_count": citation_count,
                    "year": year,
                    "journal": journal,
                    "influence_score": min(citation_count / 100.0, 1.0) if citation_count > 0 else 0.5
                })
        
        # Sort by influence
        key_papers.sort(key=lambda x: x.get("influence_score", 0), reverse=True)
        
        # Top journals
        top_journals = sorted(journals.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Identify knowledge gaps (years with low publication count)
        if publication_years:
            recent_years = [y for y in publication_years.keys() if y >= 2020]
            if recent_years:
                avg_recent = sum(publication_years[y] for y in recent_years) / len(recent_years)
                knowledge_gaps = []
                for year in range(2020, 2025):
                    if publication_years.get(year, 0) < avg_recent * 0.5:
                        knowledge_gaps.append(f"Low publication activity in {year}")
        
        return {
            "key_papers": key_papers[:10],  # Top 10
            "trends": {
                "publication_years": dict(sorted(publication_years.items())),
                "top_journals": [{"journal": j, "count": c} for j, c in top_journals]
            },
            "knowledge_gaps": knowledge_gaps if 'knowledge_gaps' in locals() else []
        }
    
    async def _query_portals(
        self,
        research_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Query all portals in parallel."""
        # Initialize portal_results
        portal_results = {
            "keyword_analysis": {},
            "top_keywords": []
        }
        
        # [1] Query PubMed
        if not self.pubmed:
            portal_results["pubmed"] = {"articles": [], "error": "PubMed portal not available"}
        else:
            pubmed_queries = research_plan.get("portal_queries", {}).get("pubmed", [])
        
        if not pubmed_queries:
            # Fallback: use primary question
            primary_question = research_plan.get("primary_question", "")
            entities = research_plan.get("entities", {})
            compound = entities.get("compound", "")
            disease = entities.get("disease", "")
            
            if compound and disease:
                query = f"{compound} AND {disease}"
            else:
                query = primary_question
            
            pubmed_queries = [query]
        
        # Query PubMed with analysis
        try:
            query = pubmed_queries[0] if pubmed_queries else ""
            if not query:
                logger.warning("No PubMed query available, using fallback")
                portal_results["pubmed"] = {"articles": [], "error": "No query available"}
            else:
                pubmed_results = await self.pubmed.search_with_analysis(
                    query=query,
                    max_results=1000,
                    analyze_keywords=True,
                    include_trends=True
                )
                
                top_keywords = self.pubmed.get_top_keywords(pubmed_results, top_n=20)
                
                portal_results["pubmed"] = pubmed_results
                portal_results["keyword_analysis"] = pubmed_results.get("keyword_analysis", {})
                portal_results["top_keywords"] = top_keywords
        except Exception as e:
            logger.error(f"PubMed query failed: {e}", exc_info=True)
            portal_results["pubmed"] = {"articles": [], "error": str(e)}
        
        # [2] Query Project Data Sphere
        if self.project_data_sphere:
            try:
                entities = research_plan.get("entities", {})
                disease = entities.get("disease", "")
                if disease:
                    pds_results = await self.project_data_sphere.search_cohorts(
                        disease=disease,
                        max_results=10
                    )
                    portal_results["project_data_sphere"] = pds_results
            except Exception as e:
                logger.warning(f"Project Data Sphere query failed: {e}")
                portal_results["project_data_sphere"] = {"cohorts": [], "error": str(e)}
        
        # [3] Query GDC
        if self.gdc:
            try:
                entities = research_plan.get("entities", {})
                compound = entities.get("compound", "")
                
                # Extract pharmacogenes from research findings (if available)
                # For now, query common pharmacogenes
                pharmacogenes = ["DPYD", "UGT1A1", "TPMT"]
                gdc_results = {}
                
                for gene in pharmacogenes:
                    gdc_results[gene] = await self.gdc.query_pharmacogene_variants(gene=gene)
                
                portal_results["gdc"] = gdc_results
            except Exception as e:
                logger.warning(f"GDC query failed: {e}")
                portal_results["gdc"] = {"variants": [], "error": str(e)}
        
        return portal_results
    
    async def _deep_parse_top_papers(
        self,
        portal_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Parse full-text for top papers using Diffbot + pubmed_parser.
        
        Strategy:
        1. Try Diffbot first (works for ANY URL, not just PMC)
        2. Fallback to pubmed_parser for PMC articles
        """
        articles = portal_results.get("pubmed", {}).get("articles", [])
        
        if not articles:
            return {
                "full_text_articles": [],
                "parsed_count": 0,
                "diffbot_count": 0,
                "pubmed_parser_count": 0
            }
        
        # Get top 10 papers
        top_papers = articles[:10]
        
        # Import Diffbot service
        diffbot_service = None
        try:
            from .enhanced_evidence_service import EnhancedEvidenceService

            diffbot_service = EnhancedEvidenceService()
        except ImportError:
            logger.debug("Diffbot service not available, using pubmed_parser only")
        
        parsed_articles = []
        
        # Try Diffbot first (works for ANY URL, not just PMC)
        for article in top_papers[:5]:
            pmid = article.get("pmid", "")
            pmc = article.get("pmc", "")
            title = article.get("title", "")
            
            # Prefer PMC URL (full-text more likely)
            if pmc:
                url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc}/"
            elif pmid:
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            else:
                continue
        
            # Try Diffbot extraction
            if diffbot_service:
                try:
                    full_text = await diffbot_service._extract_full_text_with_diffbot(url)
                    if full_text and len(full_text) > 500:  # Minimum content threshold
                        parsed_articles.append({
                            "pmid": pmid,
                            "pmc": pmc,
                            "title": title,
                            "full_text": full_text,
                            "source": "diffbot",
                            "has_full_text": True
                        })
                        continue  # Success, skip pubmed_parser
                except Exception as e:
                    logger.debug(f"Diffbot failed for {url}: {e}")
            
            # Fallback to pubmed_parser (PMC only)
            if pmc and self.pubmed_parser:
                try:
                    pmc_id = pmc.replace("PMC", "").strip()
                    full_text = await self.pubmed_parser.parse_full_text_from_pmc(pmc_id)
                    body = (
                        full_text.get("full_text", "")
                        if isinstance(full_text, dict)
                        else (full_text or "")
                    )
                    if body:
                        parsed_articles.append({
                            "pmid": pmid,
                            "pmc": pmc,
                            "title": title,
                            "full_text": body,
                            "source": "pubmed_parser",
                            "has_full_text": True
                        })
                except Exception as e:
                    logger.debug(f"pubmed_parser failed for PMC{pmc}: {e}")
        
        # [NEW] Parse pharmacogenomics cases
        pharmacogenomics_cases = []
        if self.pharmacogenomics_parser and self.pubmed:
            try:
                # Extract compound from research plan (would need to pass research_plan)
                # For now, use context if available
                # This would be enhanced to extract from research_plan
                pass  # Placeholder - would need research_plan passed to this method
            except Exception as e:
                logger.debug(f"Pharmacogenomics case extraction skipped: {e}")
        
        return {
            "full_text_articles": parsed_articles,
            "parsed_count": len(parsed_articles),
            "diffbot_count": sum(1 for a in parsed_articles if a.get("source") == "diffbot"),
            "pubmed_parser_count": sum(1 for a in parsed_articles if a.get("source") == "pubmed_parser"),
            "pharmacogenomics_cases": pharmacogenomics_cases  # NEW
        }
    
    async def _answer_sub_questions(
        self,
        research_plan: Dict[str, Any],
        portal_results: Dict[str, Any],
        parsed_content: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Answer each sub-question with targeted research.
        
        Returns:
        [
            {
                "sub_question": "What is the mechanism of action?",
                "answer": "...",
                "confidence": 0.85,
                "sources": ["pmid1", "pmid2"],
                "mechanisms": [...]
            },
            ...
        ]
        """
        sub_questions = research_plan.get("sub_questions", [])
        if not sub_questions:
            return []
        
        answers = []
        
        for sub_q in sub_questions[:5]:  # Limit to 5 sub-questions
            # Build targeted PubMed query for this sub-question
            query = self._build_sub_question_query(sub_q, research_plan)
            
            # Search PubMed for this specific sub-question
            try:
                if self.pubmed:
                    sub_results = await self.pubmed.search_with_analysis(
                        query=query,
                        max_results=50,  # Smaller for focused queries
                        analyze_keywords=False
                    )
                    
                    # Synthesize answer using LLM
                    answer = await self.synthesis_engine.answer_sub_question(
                        sub_question=sub_q,
                        articles=sub_results.get("articles", [])[:10],
                        parsed_content=parsed_content,
                        research_plan=research_plan
                    )
                    
                    answers.append({
                        "sub_question": sub_q,
                        "answer": answer.get("answer", ""),
                        "confidence": answer.get("confidence", 0.5),
                        "sources": answer.get("sources", []),
                        "mechanisms": answer.get("mechanisms", [])
                    })
                else:
                    answers.append({
                        "sub_question": sub_q,
                        "answer": "Unable to answer - PubMed portal not available",
                        "confidence": 0.0,
                        "sources": [],
                        "mechanisms": []
                    })
            except Exception as e:
                logger.warning(f"Failed to answer sub-question '{sub_q}': {e}")
                answers.append({
                    "sub_question": sub_q,
                    "answer": "Unable to answer",
                    "confidence": 0.0,
                    "sources": [],
                    "mechanisms": []
                })
        
        return answers
    
    def _build_sub_question_query(self, sub_question: str, research_plan: Dict[str, Any]) -> str:
        """Build targeted PubMed query for a sub-question."""
        entities = research_plan.get("entities", {})
        compound = entities.get("compound", "")
        disease = entities.get("disease", "")
        
        # Extract key terms from sub-question
        sub_q_lower = sub_question.lower()
        
        if "mechanism" in sub_q_lower or "how does" in sub_q_lower:
            query = f"{compound} AND {disease} AND (mechanism OR pathway OR target)"
        elif "outcome" in sub_q_lower or "efficacy" in sub_q_lower or "response" in sub_q_lower:
            query = f"{compound} AND {disease} AND (outcome OR efficacy OR response OR survival)"
        elif "dosage" in sub_q_lower or "dose" in sub_q_lower:
            query = f"{compound} AND {disease} AND (dosage OR dose OR dosing)"
        elif "safety" in sub_q_lower or "toxicity" in sub_q_lower or "adverse" in sub_q_lower:
            query = f"{compound} AND {disease} AND (safety OR toxicity OR adverse OR side effect)"
        elif "evidence" in sub_q_lower or "exists" in sub_q_lower or "study" in sub_q_lower:
            query = f"{compound} AND {disease} AND (evidence OR clinical OR trial OR study)"
        else:
            # Generic query - extract key terms instead of appending full sub-question
            # Remove question words and extract meaningful terms
            stop_words = {"what", "how", "does", "do", "is", "are", "for", "with", "in", "the", "a", "an", "this", "that"}
            words = [w for w in sub_question.split() if w.lower() not in stop_words and len(w) > 2]
            if words:
                # Use first 3 meaningful words as search terms
                key_terms = " OR ".join(words[:3])
                query = f"{compound} AND {disease} AND ({key_terms})"
            else:
                # Fallback to compound and disease only
                query = f"{compound} AND {disease}"
        
        return query

