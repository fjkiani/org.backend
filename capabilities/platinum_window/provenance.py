"""
Provenance & reproducibility for the Platinum Window capability.

Emits a deterministic provenance block that ties every response to:
  - the code revision (git SHA, best-effort),
  - the frozen model coefficients (SHA-256 of the prognostic + predictive specs),
  - the reference cohort file (SHA-256),
  - the audit ledger (SHA-256),
  - the model_version.

The block is computed once at import (cheap, deterministic) and reused. Nothing here
depends on request content, so identical inputs always yield identical provenance.

CrisPRO PLATINUM_WINDOW — Research Use Only.
"""

from __future__ import annotations

import hashlib
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from .predictive_axis import (
    predictive_model_fingerprint,
    PREDICTIVE_MODEL_NAME,
)
from .scorer import (
    ELASTIC_NET_COEF_FAP_Z,
    ELASTIC_NET_COEF_CXCL10_Z,
    PLATINUM_SCORE_THRESHOLD,
    LP_MIN,
    LP_MAX,
)

_CAP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CAP_DIR.parents[1]


def _sha256_file(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()
    except Exception:
        return None


def _git_sha() -> str:
    """Best-effort short git SHA of the working tree. Falls back to 'unknown'."""
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def prognostic_model_fingerprint() -> str:
    """Deterministic SHA-256 over the frozen PROGNOSTIC model spec."""
    payload = (
        f"prognostic_elasticnet_cox|FAP_z={ELASTIC_NET_COEF_FAP_Z}|"
        f"CXCL10_z={ELASTIC_NET_COEF_CXCL10_Z}|thr={PLATINUM_SCORE_THRESHOLD}|"
        f"lp_min={LP_MIN}|lp_max={LP_MAX}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@lru_cache(maxsize=1)
def build_provenance(model_version: str) -> Dict[str, object]:
    """Assemble the provenance block. Cached (deterministic, request-independent)."""
    ref_path = _CAP_DIR / "reference" / "tcga_hgsoc_stats.json"
    ledger_path = _CAP_DIR / "audit_ledger.json"
    return {
        "model_version": model_version,
        "git_sha": _git_sha(),
        "reference_cohort_file": ref_path.name,
        "reference_cohort_sha256": _sha256_file(ref_path),
        "audit_ledger_sha256": _sha256_file(ledger_path),
        "prognostic_model": {
            "name": "prognostic_elasticnet_cox_FAP_CXCL10",
            "fingerprint_sha256": prognostic_model_fingerprint(),
        },
        "predictive_model": {
            "name": PREDICTIVE_MODEL_NAME,
            "fingerprint_sha256": predictive_model_fingerprint(),
        },
        "reproducibility_note": (
            "Scoring is deterministic and dependency-free (no RNG, no network). "
            "Identical inputs + identical model_version yield byte-identical scores."
        ),
    }
