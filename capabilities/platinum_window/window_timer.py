"""
FAP-based Platinum Window timing engine.
Implements the biological clock model from caf_window_timing_simulation.py.

Each platinum cycle pushes FAP z-score upward by a weighted CAF-2/CAF-3 delta.
When FAP_z crosses 0.0, the stromal cage closes and the window shuts.

Reports BOTH unsuppressed (no metformin) and suppressed (with metformin) timelines.
Metformin suppression (40% default) is transport-gated via OCT1 status.

CrisPRO PLATINUM_WINDOW v1.0 — Research Use Only.
"""

from typing import Optional

# Validated toy model parameters from caf_window_timing_simulation.py
CAF2_FAP_DELTA_PER_CYCLE = 0.180
CAF3_FAP_DELTA_PER_CYCLE = 0.119
CAF2_WEIGHT = 0.60
CAF3_WEIGHT = 0.40
WINDOW_CLOSE_THRESHOLD = 0.0
MAX_CYCLES = 10
WEEKS_PER_CYCLE = 3.0  # Standard q3w chemotherapy

# Metformin FAP suppression — from caf_window_timing_simulation.py sweep
METFORMIN_SUPPRESSION_DEFAULT = 0.40  # 40% suppression of per-cycle FAP delta


def _per_cycle_delta(suppression: float = 0.0) -> float:
    """Weighted per-cycle FAP z-score increment, with optional metformin suppression."""
    raw = (CAF2_FAP_DELTA_PER_CYCLE * CAF2_WEIGHT) + (CAF3_FAP_DELTA_PER_CYCLE * CAF3_WEIGHT)
    return raw * (1.0 - suppression)


def cycles_until_window_closes(
    fap_z_start: float,
    suppression: float = 0.0,
) -> int:
    """
    Compute how many additional cycles before the window closes.
    Returns 0 if already closed (FAP_z >= threshold).
    Lifted from caf_window_timing_simulation.py L43-63.
    """
    if fap_z_start >= WINDOW_CLOSE_THRESHOLD:
        return 0

    delta = _per_cycle_delta(suppression)
    if delta <= 0:
        return MAX_CYCLES  # suppression halts or reverses the clock

    cur = fap_z_start
    cycles = 0
    while cur < WINDOW_CLOSE_THRESHOLD and cycles < MAX_CYCLES:
        cur += delta
        cycles += 1
    return cycles


def determine_window_status(
    fap_z: float,
    stromal_arm: float,
    platinum_status: str,
    prior_cycles: int,
) -> str:
    """
    Determine window status: OPEN, CLOSING, CLOSED, or NEVER_OPEN.

    Logic:
    - NEVER_OPEN: platinum resistant or FAP_z >> 0 (no window ever existed)
    - CLOSED: FAP_z >= 0 (cage already erected)
    - CLOSING: FAP_z < 0 but few cycles remain (<= 2)
    - OPEN: FAP_z < 0 and sufficient cycles remain
    """
    if platinum_status == "resistant":
        return "NEVER_OPEN"

    if fap_z >= WINDOW_CLOSE_THRESHOLD:
        if fap_z > 1.0:
            return "NEVER_OPEN"
        return "CLOSED"

    remaining = cycles_until_window_closes(fap_z)
    if remaining <= 2:
        return "CLOSING"

    return "OPEN"


def compute_timing(
    fap_z: float,
    prior_cycles: int,
    platinum_status: str,
    stromal_arm: float,
    oct1_status: str = "LOW",
) -> dict:
    """
    Compute all window timing fields for the API response.
    Reports BOTH unsuppressed AND metformin-suppressed timelines.
    Metformin suppression is gated by OCT1 status (transport viability).
    """
    window_status = determine_window_status(fap_z, stromal_arm, platinum_status, prior_cycles)

    if window_status in ("CLOSED", "NEVER_OPEN"):
        return {
            "window_status": window_status,
            "cycles_until_window_closes": 0 if window_status == "CLOSED" else None,
            "cycles_remaining": None,
            "weeks_remaining": None,
            "intervention_deadline": (
                "Window closed. Cage-breaking strategy required (nintedanib/anti-fibrotic first)."
                if window_status == "CLOSED"
                else "Patient ineligible — platinum resistant or no detectable window."
            ),
        }

    # Unsuppressed timeline (worst case: no metformin)
    cycles_unsuppressed = cycles_until_window_closes(fap_z)

    # Suppressed timeline (with metformin, transport-gated)
    suppression = METFORMIN_SUPPRESSION_DEFAULT if oct1_status == "HIGH" else 0.0
    cycles_suppressed = cycles_until_window_closes(fap_z, suppression=suppression)

    # Report the suppressed timeline as the primary (patient IS getting metformin per the treatment sequence)
    remaining = max(0, cycles_suppressed - prior_cycles) if prior_cycles > 0 else cycles_suppressed
    weeks = round(remaining * WEEKS_PER_CYCLE, 1)

    if window_status == "CLOSING":
        deadline = f"URGENT: Start Metformin THIS cycle. Only {remaining} cycle(s) remaining."
    else:
        deadline = f"Start Metformin before Cycle {prior_cycles + 2}"

    # Add metformin extension info to deadline
    if suppression > 0 and cycles_suppressed > cycles_unsuppressed:
        delta_cycles = cycles_suppressed - cycles_unsuppressed
        deadline += f" (Metformin extends window by +{delta_cycles} cycle(s) via OCT1 transport)"

    return {
        "window_status": window_status,
        "cycles_until_window_closes": cycles_suppressed,  # WITH metformin (if OCT1 HIGH)
        "cycles_remaining": remaining,
        "weeks_remaining": weeks,
        "intervention_deadline": deadline,
    }
