#!/usr/bin/env python3
"""
Radiology Report Parser — Rule-Based NLP
==========================================
Extracts imaging_change_type, healing_flag, and key_phrases
from free-text radiology reports.

RESEARCH USE ONLY — not validated for clinical use.

Usage as CLI:
    python radiology_parser.py "New sclerotic lesion in L3 vertebral body"

    python radiology_parser.py --file reports.json --output parsed.json

Usage as library:
    from radiology_parser import parse_radiology_report
    result = parse_radiology_report("New sclerotic lesion in L3")
    # {'imaging_change_type': 'NEW_SCLEROTIC_BONE', 'healing_flag': True, 'key_phrases': [...]}
"""

import re
import json
import argparse
import sys
from typing import Dict, List, Any


# ── Pattern Definitions ──────────────────────────────────────────

# Each pattern: (compiled_regex, imaging_change_type, healing_flag_override)
# healing_flag_override: True/False/None (None = don't override, use secondary rules)

PATTERNS = [
    # RECIST progression — must check first (high specificity)
    (re.compile(
        r"(?:RECIST|measurable).{0,30}(?:progression|PD)|"
        r"(?:≥\s*20%|greater than 20%|>20%).{0,20}(?:increase|growth|enlarg)|"
        r"unequivocal.{0,20}(?:new|progression)|"
        r"new.{0,15}(?:extra.?osseous|visceral|soft.?tissue).{0,15}(?:lesion|met)",
        re.I,
    ), "RECIST_PROGRESSION", False),

    # New sclerotic / osteoblastic bone lesions → healing signal
    (re.compile(
        r"(?:new|interval).{0,25}(?:sclerotic|osteoblastic|blastic).{0,15}(?:lesion|foc|change|area|densit)|"
        r"(?:sclerotic|osteoblastic|blastic).{0,15}(?:new|appeared|developed)|"
        r"(?:healing|reparative).{0,15}(?:sclerosis|ossification|bone)",
        re.I,
    ), "NEW_SCLEROTIC_BONE", True),

    # SUV increase without size change
    (re.compile(
        r"(?:SUV|FDG|metabolic|tracer).{0,30}(?:increas|uptake|intensit|avid)|"
        r"(?:increas|elevat|higher).{0,20}(?:SUV|FDG|uptake|metabolic)|"
        r"SUV\s*(?:max)?\s*(?:increased|rose|from)",
        re.I,
    ), "SUV_INCREASE_NO_SIZE", None),

    # Sub-5mm size increase (below RECIST threshold)
    (re.compile(
        r"(?:minimal|mild|subtle|slight|small|marginal).{0,20}(?:increase|enlarg|growth|change).{0,15}(?:size|dimension)|"
        r"(?:1|2|3|4)\s*mm.{0,15}(?:increase|enlarg|growth)|"
        r"(?:increase|enlarg).{0,10}(?:1|2|3|4)\s*mm|"
        r"sub.?(?:centimeter|5\s*mm).{0,15}(?:increase|change|growth)|"
        r"(?:increase|growth).{0,10}(?:less than|<)\s*5\s*mm",
        re.I,
    ), "SUB_5MM_SIZE_INCREASE", False),

    # Stable disease
    (re.compile(
        r"(?:stable|unchanged|no.{0,5}change|no.{0,5}interval.{0,5}change|"
        r"no.{0,5}significant.{0,5}change|no.{0,5}new|"
        r"stable.{0,10}disease|SD\b)",
        re.I,
    ), "STABLE_DISEASE", None),
]

# Anti-patterns: if matched, PREVENT certain classifications
ANTI_PATTERNS = {
    "SUV_INCREASE_NO_SIZE": re.compile(
        r"(?:size|dimension|diameter).{0,20}(?:increas|enlarg|grow)|"
        r"(?:increas|enlarg|grow).{0,20}(?:size|dimension|diameter)|"
        r"(?:lytic|destruction|pathologic.{0,5}fracture)",
        re.I,
    ),
    "STABLE_DISEASE": re.compile(
        r"(?:new|additional|further|increas|enlarg|progression|worsen)",
        re.I,
    ),
}

# Secondary healing-flag rules (applied if primary didn't set it)
HEALING_PATTERNS = re.compile(
    r"(?:sclerotic|osteoblastic|blastic|healing|reparative|"
    r"sclerosis|ossification|bone.{0,5}formation|"
    r"treated.{0,10}appearance|post.?treatment.{0,10}change)|"
    r"(?:resolv|improv|decreas).{0,15}(?:lytic|osteolytic)",
    re.I,
)

ANTI_HEALING_PATTERNS = re.compile(
    r"(?:new.{0,10}lytic|osteolytic.{0,10}(?:new|progress|worsen)|"
    r"pathologic.{0,5}fracture|cortical.{0,10}destruction|"
    r"(?:expansion|enlargement).{0,10}(?:lytic|destructive))",
    re.I,
)


# ── Parser Function ──────────────────────────────────────────────

def parse_radiology_report(text: str) -> Dict[str, Any]:
    """
    Parse a free-text radiology report snippet and extract:
    - imaging_change_type (str)
    - healing_flag (bool)
    - key_phrases (list of matched strings)
    - confidence (str: high/medium/low)

    Parameters
    ----------
    text : str
        Radiology report text (can be a snippet or full report).

    Returns
    -------
    dict
    """
    if not text or not text.strip():
        return {
            "imaging_change_type": "OTHER_OR_UNCLEAR",
            "healing_flag": False,
            "key_phrases": [],
            "confidence": "low",
        }

    text_clean = text.strip()
    matched_type = None
    healing_override = None
    key_phrases = []

    # Try each pattern in priority order
    for pattern, img_type, heal_flag in PATTERNS:
        match = pattern.search(text_clean)
        if match:
            # Check anti-patterns
            if img_type in ANTI_PATTERNS:
                anti = ANTI_PATTERNS[img_type].search(text_clean)
                if anti:
                    continue  # Skip this match, try next pattern

            matched_type = img_type
            healing_override = heal_flag
            key_phrases.append(match.group(0).strip())
            break

    if matched_type is None:
        matched_type = "OTHER_OR_UNCLEAR"

    # Determine healing flag
    if healing_override is not None:
        healing_flag = healing_override
    else:
        has_healing = bool(HEALING_PATTERNS.search(text_clean))
        has_anti = bool(ANTI_HEALING_PATTERNS.search(text_clean))
        healing_flag = has_healing and not has_anti

    # Extract additional key phrases
    for pattern, _, _ in PATTERNS:
        for m in pattern.finditer(text_clean):
            phrase = m.group(0).strip()
            if phrase not in key_phrases:
                key_phrases.append(phrase)

    # Confidence
    if matched_type == "OTHER_OR_UNCLEAR":
        confidence = "low"
    elif len(key_phrases) >= 2:
        confidence = "high"
    else:
        confidence = "medium"

    return {
        "imaging_change_type": matched_type,
        "healing_flag": healing_flag,
        "key_phrases": key_phrases[:5],  # cap at 5
        "confidence": confidence,
    }


def parse_batch(reports: List[str]) -> List[Dict]:
    """Parse a list of report strings."""
    return [parse_radiology_report(r) for r in reports]


# ── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Radiology Report Parser — bone pseudo-progression NLP (RESEARCH USE ONLY)",
    )
    parser.add_argument("text", nargs="?", help="Radiology report text to parse")
    parser.add_argument("--file", help="JSON file with array of report strings")
    parser.add_argument("--output", default="parsed_reports.json", help="Output JSON file (batch mode)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    if args.file:
        with open(args.file) as f:
            reports = json.load(f)
        results = parse_batch(reports)
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Parsed {len(results)} reports → {args.output}")
    elif args.text:
        result = parse_radiology_report(args.text)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"  Type:     {result['imaging_change_type']}")
            print(f"  Healing:  {result['healing_flag']}")
            print(f"  Phrases:  {result['key_phrases']}")
            print(f"  Confidence: {result['confidence']}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
