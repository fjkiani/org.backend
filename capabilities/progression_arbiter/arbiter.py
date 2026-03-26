#!/usr/bin/env python3
"""
Progression Arbiter — Bone Pseudo-Progression Scorer
=====================================================
Standalone scoring module for the Progression Arbiter v1 model.
Loads frozen coefficients and scores individual imaging events.

RESEARCH USE ONLY — not validated for clinical decision-making.

Usage as CLI:
    python arbiter.py score \\
        --imaging NEW_SCLEROTIC_BONE \\
        --therapy CDK46 \\
        --symptomatic false \\
        --pain false \\
        --healing true \\
        --weeks 12 \\
        --alp-delta 5 \\
        --ca153-delta 0

    python arbiter.py batch --input events.json --output scored.json

Usage as library:
    from arbiter import ProgressionArbiter
    model = ProgressionArbiter("models/progression_arbiter_model_v1.json")
    result = model.score(
        imaging_change_type="NEW_SCLEROTIC_BONE",
        therapy_class="CDK46",
        symptomatic=False,
        new_pain_at_site=False,
        healing_flag=True,
        weeks_on_therapy=12,
        alp_delta_pct=5.0,
        ca153_delta_pct=0.0,
    )
    print(result)
    # {'p_true_progression': 0.006, 'risk_bucket': 'LOW', 'recommendation': 'SHORT_INTERVAL_RESCAN', ...}
"""

import json
import math
import argparse
import sys
import os
from typing import Optional, Dict, Any, List


# ── Constants ────────────────────────────────────────────────────

IMAGING_TYPES = [
    "NEW_SCLEROTIC_BONE",
    "SUV_INCREASE_NO_SIZE",
    "SUB_5MM_SIZE_INCREASE",
    "NEW_SOFT_TISSUE_LESION",
    "RECIST_PROGRESSION",
    "STABLE_DISEASE",
    "OTHER_OR_UNCLEAR",
]

THERAPY_CLASSES = [
    "CDK46",
    "HER2",
    "ENDOCRINE",
    "CHEMO",
    "IO",
    "OTHER",
]

RISK_BUCKETS = {
    "LOW": (0.0, 0.3),
    "MID": (0.3, 0.7),
    "HIGH": (0.7, 1.01),
}

RECOMMENDATIONS = {
    "LOW": "SHORT_INTERVAL_RESCAN",
    "MID": "ADDITIONAL_WORKUP_REQUIRED",
    "HIGH": "IMMEDIATE_SWITCH_CONCERN",
}


# ── Model Class ──────────────────────────────────────────────────

class ProgressionArbiter:
    """
    L2-regularized logistic regression model for distinguishing
    bone pseudo-progression from true progression in metastatic
    breast cancer.

    Loads frozen coefficients from a JSON file and scores new events.
    """

    def __init__(self, model_path: str):
        """
        Load a frozen model from JSON.

        Parameters
        ----------
        model_path : str
            Path to progression_arbiter_model_v1.json (or any model
            following the same schema).
        """
        with open(model_path) as f:
            self._model = json.load(f)

        self.intercept = self._model["intercept"]
        self.coefficients = self._model["coefficients"]
        self.model_name = self._model.get("model_name", "unknown")
        self.n_training = self._model.get("n_training", 0)
        self.disclaimer = self._model.get("disclaimer", "RESEARCH USE ONLY")

    def score(
        self,
        imaging_change_type: str,
        therapy_class: str,
        symptomatic: Optional[bool],
        new_pain_at_site: Optional[bool],
        healing_flag: bool,
        weeks_on_therapy: float,
        alp_delta_pct: float = 0.0,
        ca153_delta_pct: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Score a single imaging event.

        Parameters
        ----------
        imaging_change_type : str
            One of: NEW_SCLEROTIC_BONE, SUV_INCREASE_NO_SIZE,
            SUB_5MM_SIZE_INCREASE, NEW_SOFT_TISSUE_LESION,
            RECIST_PROGRESSION, STABLE_DISEASE, OTHER_OR_UNCLEAR
        therapy_class : str
            One of: CDK46, HER2, ENDOCRINE, CHEMO, IO, OTHER
        symptomatic : bool or None
            True/False/None (None → encoded as 0.5 = unknown)
        new_pain_at_site : bool or None
            True/False/None
        healing_flag : bool
            Whether sclerotic/healing language + stable context
        weeks_on_therapy : float
            Weeks since therapy start at time of imaging event
        alp_delta_pct : float
            ALP change from baseline in percent (e.g., +5 means 5% rise)
        ca153_delta_pct : float
            CA15-3 change from baseline in percent

        Returns
        -------
        dict with keys:
            p_true_progression : float   (0.0 to 1.0)
            logit              : float   (raw log-odds)
            risk_bucket        : str     (LOW / MID / HIGH)
            recommendation     : str     (SHORT_INTERVAL_RESCAN / ADDITIONAL_WORKUP_REQUIRED / IMMEDIATE_SWITCH_CONCERN)
            term_contributions : dict    (feature → contribution to logit)
            driving_feature    : str     (feature with largest |contribution|, excluding intercept)
            disclaimer         : str
        """
        terms = {"intercept": self.intercept}

        # Imaging type (one-hot, reference = OTHER_OR_UNCLEAR)
        for img in ["NEW_SCLEROTIC_BONE", "SUV_INCREASE_NO_SIZE",
                     "SUB_5MM_SIZE_INCREASE", "NEW_SOFT_TISSUE_LESION",
                     "RECIST_PROGRESSION", "STABLE_DISEASE"]:
            key = f"img_{img}"
            val = 1.0 if imaging_change_type == img else 0.0
            terms[key] = self.coefficients[key] * val

        # Therapy class (one-hot, reference = OTHER)
        for tx in ["CDK46", "HER2", "ENDOCRINE", "CHEMO", "IO"]:
            key = f"tx_{tx}"
            val = 1.0 if therapy_class == tx else 0.0
            terms[key] = self.coefficients[key] * val

        # Boolean features
        symp_val = 1.0 if symptomatic is True else (0.0 if symptomatic is False else 0.5)
        terms["symptomatic"] = self.coefficients["symptomatic"] * symp_val

        pain_val = 1.0 if new_pain_at_site is True else (0.0 if new_pain_at_site is False else 0.5)
        terms["new_pain_at_site"] = self.coefficients["new_pain_at_site"] * pain_val

        terms["healing_flag"] = self.coefficients["healing_flag"] * (1.0 if healing_flag else 0.0)

        # Continuous features (normalized)
        terms["weeks_since_therapy_start_norm"] = (
            self.coefficients["weeks_since_therapy_start_norm"] * (weeks_on_therapy / 52.0)
        )
        terms["alp_delta_norm"] = self.coefficients["alp_delta_norm"] * (alp_delta_pct / 100.0)
        terms["ca153_delta_norm"] = self.coefficients["ca153_delta_norm"] * (ca153_delta_pct / 100.0)

        # Compute probability
        logit = sum(terms.values())
        p = 1.0 / (1.0 + math.exp(-logit))

        # Risk bucket
        bucket = "MID"
        for name, (lo, hi) in RISK_BUCKETS.items():
            if lo <= p < hi:
                bucket = name
                break

        # Driving feature (largest |contribution|, excluding intercept)
        non_intercept = {k: v for k, v in terms.items() if k != "intercept"}
        driving = max(non_intercept, key=lambda k: abs(non_intercept[k]))

        # Filter zero contributions for cleaner output
        active_terms = {k: round(v, 6) for k, v in terms.items() if abs(v) > 0.0001}

        return {
            "p_true_progression": round(p, 6),
            "logit": round(logit, 6),
            "risk_bucket": bucket,
            "recommendation": RECOMMENDATIONS[bucket],
            "term_contributions": active_terms,
            "driving_feature": driving,
            "driving_feature_contribution": round(non_intercept[driving], 6),
            "disclaimer": self.disclaimer,
        }

    def score_batch(self, events: List[Dict]) -> List[Dict]:
        """
        Score a list of event dicts. Each dict must have the 8
        input keys matching score() parameters.
        """
        results = []
        for i, evt in enumerate(events):
            try:
                result = self.score(
                    imaging_change_type=evt["imaging_change_type"],
                    therapy_class=evt.get("therapy_class", "OTHER"),
                    symptomatic=evt.get("symptomatic"),
                    new_pain_at_site=evt.get("new_pain_at_site"),
                    healing_flag=evt.get("healing_flag", False),
                    weeks_on_therapy=float(evt.get("weeks_on_therapy", evt.get("weeks_since_therapy_start", 0))),
                    alp_delta_pct=float(evt.get("alp_delta_pct", evt.get("alp_delta", 0) or 0)),
                    ca153_delta_pct=float(evt.get("ca153_delta_pct", evt.get("ca153_delta", 0) or 0)),
                )
                result["event_index"] = i
                result["patient_id"] = evt.get("patient_id", f"event_{i}")
                results.append(result)
            except Exception as e:
                results.append({
                    "event_index": i,
                    "patient_id": evt.get("patient_id", f"event_{i}"),
                    "error": str(e),
                })
        return results

    def explain(self, result: Dict) -> str:
        """Return a human-readable explanation of a score result."""
        p = result["p_true_progression"]
        bucket = result["risk_bucket"]
        rec = result["recommendation"].replace("_", " ").lower()
        driver = result["driving_feature"]
        driver_val = result["driving_feature_contribution"]
        direction = "true progression" if driver_val > 0 else "pseudo-progression"

        lines = [
            f"P(true progression) = {p:.1%}  |  Risk bucket: {bucket}",
            f"Recommendation: {rec}",
            f"Driving feature: {driver} ({driver_val:+.4f} → {direction})",
            "",
            "Active contributions:",
        ]
        for feat, val in sorted(
            result["term_contributions"].items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        ):
            tag = "PROG" if val > 0 else "PSEUDO"
            lines.append(f"  {feat:42s}  {val:+.4f}  → {tag}")

        lines.append("")
        lines.append(result["disclaimer"])
        return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────

def _find_model_path():
    """Search common locations for the model JSON."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "models", "progression_arbiter_model_v1.json"),
        os.path.join(os.path.dirname(__file__), "models", "progression_arbiter_model_v1.json"),
        "models/progression_arbiter_model_v1.json",
        "progression_arbiter_model_v1.json",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _parse_bool(val: str) -> Optional[bool]:
    if val.lower() in ("true", "yes", "1", "t"):
        return True
    elif val.lower() in ("false", "no", "0", "f"):
        return False
    elif val.lower() in ("none", "null", "unknown", ""):
        return None
    raise ValueError(f"Cannot parse boolean: {val}")


def cli_score(args, model_path):
    arbiter = ProgressionArbiter(model_path)
    result = arbiter.score(
        imaging_change_type=args.imaging,
        therapy_class=args.therapy,
        symptomatic=_parse_bool(args.symptomatic),
        new_pain_at_site=_parse_bool(args.pain),
        healing_flag=_parse_bool(args.healing),
        weeks_on_therapy=args.weeks,
        alp_delta_pct=args.alp_delta,
        ca153_delta_pct=args.ca153_delta,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(arbiter.explain(result))


def cli_batch(args, model_path):
    arbiter = ProgressionArbiter(model_path)

    with open(args.input) as f:
        events = json.load(f)

    if isinstance(events, dict):
        events = [events]

    results = arbiter.score_batch(events)

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Scored {len(results)} events → {args.output}")

    # Print summary
    buckets = {"LOW": 0, "MID": 0, "HIGH": 0, "ERROR": 0}
    for r in results:
        if "error" in r:
            buckets["ERROR"] += 1
        else:
            buckets[r["risk_bucket"]] += 1
    print(f"  LOW: {buckets['LOW']}  MID: {buckets['MID']}  HIGH: {buckets['HIGH']}  Errors: {buckets['ERROR']}")


def main():
    parser = argparse.ArgumentParser(
        description="Progression Arbiter — Bone pseudo-progression scorer (RESEARCH USE ONLY)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", default=None, help="Path to model JSON (auto-detected if omitted)")

    subparsers = parser.add_subparsers(dest="command")

    # ── score subcommand ──
    sp_score = subparsers.add_parser("score", help="Score a single imaging event")
    sp_score.add_argument("--imaging", required=True, choices=IMAGING_TYPES, help="Imaging change type")
    sp_score.add_argument("--therapy", required=True, choices=THERAPY_CLASSES, help="Therapy class")
    sp_score.add_argument("--symptomatic", required=True, help="Symptomatic (true/false/unknown)")
    sp_score.add_argument("--pain", required=True, help="New pain at site (true/false/unknown)")
    sp_score.add_argument("--healing", required=True, help="Healing flag (true/false)")
    sp_score.add_argument("--weeks", type=float, required=True, help="Weeks on therapy")
    sp_score.add_argument("--alp-delta", type=float, default=0.0, help="ALP delta %% (default 0)")
    sp_score.add_argument("--ca153-delta", type=float, default=0.0, help="CA15-3 delta %% (default 0)")
    sp_score.add_argument("--json", action="store_true", help="Output raw JSON instead of narrative")

    # ── batch subcommand ──
    sp_batch = subparsers.add_parser("batch", help="Score a batch of events from JSON file")
    sp_batch.add_argument("--input", required=True, help="Input JSON file (array of event dicts)")
    sp_batch.add_argument("--output", default="scored_events.json", help="Output JSON file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    model_path = args.model or _find_model_path()
    if not model_path or not os.path.exists(model_path):
        print("ERROR: Could not find model JSON. Use --model to specify path.", file=sys.stderr)
        sys.exit(1)

    if args.command == "score":
        cli_score(args, model_path)
    elif args.command == "batch":
        cli_batch(args, model_path)


if __name__ == "__main__":
    main()
