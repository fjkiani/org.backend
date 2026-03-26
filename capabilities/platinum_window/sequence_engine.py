"""
Treatment sequencing engine for the Platinum Window API.
Determines urgency and builds cycle-by-cycle treatment recommendations.

Logic lifted from:
- simulate_intervention.py (INTERVENTION_MODELS, prerequisite checks, urgency)
- clinical_brief_generator.py (build_recommendation, platinum window template)

CrisPRO PLATINUM_WINDOW v1.0 — Research Use Only.
"""

from typing import Dict, List, Optional


def determine_urgency(
    fap_z: float,
    stromal_arm: float,
    platinum_status: str,
    prior_cycles: int,
    immune_access: float,
    window_status: str,
    histotype: str,
    platinum_score: float,
) -> dict:
    """
    Compute urgency state, reason, and trial routing.

    C6 REVISION: Platinum-resistant patients are NOT flat INELIGIBLE.
    Only truly ineligible: non-HGSOC histotype or insufficient data.
    Resistant patients with good fingerprint → CAGE_BREAKING_FIRST (Pub 2).
    """
    # ── Truly INELIGIBLE: PAAD or non-HGSOC ──
    if histotype == "PAAD":
        return {
            "urgency": "INELIGIBLE",
            "urgency_reason": (
                "FAP/CXCL10 fingerprint contraindicated in pancreatic ductal adenocarcinoma "
                "(reversed HR=1.81 in TCGA PAAD). Do not use this score in this indication."
            ),
            "trial_routing": "NONE",
        }

    if histotype != "HGSOC":
        return {
            "urgency": "INELIGIBLE",
            "urgency_reason": (
                "Fingerprint validated in HGSOC only. Other histotypes require "
                "separate validation."
            ),
            "trial_routing": "NONE",
        }

    # ── C6: Platinum-resistant — route to Pub 2 cage-breaking, NOT ineligible ──
    if platinum_status == "resistant":
        if platinum_score > 0.3702:
            return {
                "urgency": "CAGE_BREAKING_FIRST",
                "urgency_reason": (
                    "Platinum resistance suggests window closure. However, "
                    "PLATINUM_SCORE is above threshold — favorable molecular profile. "
                    "Route to Publication 2 cage-breaking protocol. "
                    "Cage architecture scoring recommended (CAGE_TYPE_A/B/C)."
                ),
                "trial_routing": "PUB2_CAGE_BREAKING",
            }
        return {
            "urgency": "CAGE_BREAKING_FIRST",
            "urgency_reason": (
                "Platinum resistance with unfavorable PLATINUM_SCORE. Window never open. "
                "Route to Publication 2 cage-breaking protocol."
            ),
            "trial_routing": "PUB2_CAGE_BREAKING",
        }

    # ── Window already closed → cage-breaking (Pub 2) ──
    if window_status in ("CLOSED", "NEVER_OPEN") or fap_z >= 0.0:
        return {
            "urgency": "CAGE_BREAKING_FIRST",
            "urgency_reason": (
                "Window is closed or closing too fast for standard sequence. "
                "Anti-fibrotic intervention (nintedanib) recommended. "
                "Route to Publication 2 cage-breaking protocol."
            ),
            "trial_routing": "PUB2_CAGE_BREAKING",
        }

    # ── Window OPEN → Pub 1 ──
    # IMMEDIATE: early in treatment, strong signal
    if fap_z < 0.0 and stromal_arm < 0.0 and prior_cycles <= 1:
        return {
            "urgency": "IMMEDIATE",
            "urgency_reason": (
                "Patient is in the PLATINUM_WINDOW. Start Metformin today. "
                "Every cycle without it closes the window. "
                "Dupilumab at Cycle 2. Checkpoint when IMMUNE_ACCESS > 0.40."
            ),
            "trial_routing": "PUB1_PLATINUM_WINDOW",
        }

    # STANDARD: window open but further along
    if fap_z < 0.0 and stromal_arm < 0.0 and prior_cycles <= 3:
        return {
            "urgency": "STANDARD",
            "urgency_reason": (
                "Window still open but closing. Metformin must start this cycle. "
                "Dupilumab can be added next cycle. Monitor FAP trajectory."
            ),
            "trial_routing": "PUB1_PLATINUM_WINDOW",
        }

    # Fallback: window open but stromal arm elevated
    if fap_z < 0.0:
        return {
            "urgency": "STANDARD",
            "urgency_reason": (
                "FAP z-score is negative (window open) but stromal arm is elevated. "
                "Consider concurrent anti-fibrotic. Start Metformin now."
            ),
            "trial_routing": "PUB1_PLATINUM_WINDOW",
        }

    return {
        "urgency": "CAGE_BREAKING_FIRST",
        "urgency_reason": "Default: stromal barrier detected. Anti-fibrotic first.",
        "trial_routing": "PUB2_CAGE_BREAKING",
    }


def build_treatment_sequence(
    urgency: str,
    immune_access: float,
    oct1_status: str,
    window_status: str,
    metformin_eligible: bool,
) -> List[dict]:
    """
    Build the recommended cycle-by-cycle treatment sequence.
    C4: If OCT1 is LOW (metformin_eligible=False), Metformin is removed
    from Cycle 1 and replaced with anti-fibrotic alternative.
    """
    if urgency == "INELIGIBLE":
        return [{
            "cycle": "N/A",
            "drugs": ["standard_of_care"],
            "rationale": "Patient does not meet eligibility for window-based sequencing.",
        }]

    if urgency == "CAGE_BREAKING_FIRST":
        return [
            {
                "cycle": "1",
                "drugs": ["nintedanib_200mg_BID", "carboplatin", "paclitaxel"],
                "rationale": "Anti-fibrotic to break stromal cage.",
            },
            {
                "cycle": "2",
                "drugs": ["metformin_850mg_BID"] if metformin_eligible else ["nintedanib_200mg_BID_continued"],
                "rationale": (
                    "AMPK activation + FAP clock suppression after cage disruption."
                    if metformin_eligible
                    else "Continue anti-fibrotic — OCT1-low, Metformin accumulation uncertain."
                ),
            },
            {
                "cycle": "3",
                "drugs": ["dupilumab_300mg_Q4W"],
                "rationale": "M2 macrophage reprogramming once stromal barrier disrupted.",
            },
            {
                "cycle": "4_or_later",
                "drugs": ["pembrolizumab_200mg_Q3W"],
                "rationale": "Checkpoint amplification after access restored.",
                "condition": "IMMUNE_ACCESS_SCORE > 0.40",
            },
        ]

    # IMMEDIATE or STANDARD — Arm A: exploit the open window
    # C4: OCT1-LOW → remove Metformin from Cycle 1
    if metformin_eligible:
        metformin_label = "metformin_850mg_BID" if oct1_status == "HIGH" else "metformin_500mg_BID"
        cycle1 = {
            "cycle": "1",
            "drugs": ["carboplatin", "paclitaxel", metformin_label],
            "rationale": f"AMPK activation + FAP clock suppression from Cycle 1. OCT1: {oct1_status}.",
        }
    else:
        cycle1 = {
            "cycle": "1",
            "drugs": ["carboplatin", "paclitaxel"],
            "rationale": (
                "Standard chemo backbone. Metformin HELD — OCT1-low, intratumoral "
                "accumulation uncertain. Pending OCT1 IHC confirmation."
            ),
        }

    sequence = [
        cycle1,
        {
            "cycle": "2",
            "drugs": ["dupilumab_300mg_Q4W"],
            "rationale": "M2 reprogramming while FAP still suppressed.",
        },
    ]

    if immune_access > 0.40:
        sequence.append({
            "cycle": "3",
            "drugs": ["pembrolizumab_200mg_Q3W"],
            "rationale": "Checkpoint amplification — IMMUNE_ACCESS_SCORE above 0.40.",
        })
    else:
        sequence.append({
            "cycle": "3_or_4",
            "drugs": ["pembrolizumab_200mg_Q3W"],
            "condition": "IMMUNE_ACCESS_SCORE > 0.40",
            "rationale": "Checkpoint amplification after access restored.",
        })

    return sequence


def compute_confidence(
    histotype: str,
    fingerprint_positive: bool,
    tier: str,
    window_status: str,
) -> dict:
    """Determine confidence tier and caveats."""
    caveats: List[str] = []

    if histotype != "HGSOC":
        caveats.append("Fingerprint validated in HGSOC only.")

    if not fingerprint_positive:
        caveats.append("Molecular fingerprint negative. Window scoring may not apply.")

    if window_status == "NEVER_OPEN":
        caveats.append("No detectable platinum window.")

    if tier == "TIER_2_MIXED":
        caveats.append("Partial tier match. Intervention benefit uncertain.")

    if tier == "TIER_3_ACCESSIBLE":
        caveats.append("Tier 3 — does not match intervention biology.")

    if histotype == "HGSOC" and fingerprint_positive and tier == "TIER_1_TRIPLE":
        confidence = "HIGH"
    elif histotype == "HGSOC" and (fingerprint_positive or tier in ("TIER_1_TRIPLE", "TIER_2_MIXED")):
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {"confidence_tier": confidence, "caveats": caveats}
