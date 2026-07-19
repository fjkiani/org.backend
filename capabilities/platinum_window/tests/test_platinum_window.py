"""
Clinical-grade test suite for the Platinum Window capability.

Coverage:
  - unit tests (scorer primitives, predictive axis, window timer, sequence engine)
  - integration tests (both endpoints via FastAPI TestClient)
  - golden / determinism tests (frozen demo output, byte-stable scores)
  - calibration-gating tests (predictive thresholded call gated on normalization)
  - audit-invariant tests (no response asserts a claim the ledger flags OVERSTATED)
  - honesty/RUO guardrail tests (no '16 cohort validated' language leaks)

Run: pytest capabilities/platinum_window/tests -q
Research Use Only.
"""

import json
import math
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from capabilities.platinum_window.router import router, load_reference
from capabilities.platinum_window.scorer import (
    z_score,
    determine_fingerprint,
    determine_oct1_status,
    classify_tier,
    compute_immune_access,
    compute_platinum_score,
    compute_all_scores,
    _validate_gene_values,
)
from capabilities.platinum_window.predictive_axis import (
    compute_platinum_response_score,
    predictive_model_fingerprint,
    PREDICTIVE_COEFFICIENTS,
    PREDICTIVE_INTERCEPT,
)

CAP = Path(__file__).resolve().parent.parent


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    load_reference()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(scope="module")
def ref():
    d = json.loads((CAP / "reference" / "tcga_hgsoc_stats.json").read_text())
    genes = d["genes"]
    rm = {g: v["mean"] for g, v in genes.items() if v.get("mean") is not None}
    rs = {g: v["std"] for g, v in genes.items() if v.get("std") is not None}
    return rm, rs


@pytest.fixture
def valid_payload():
    return {
        "FAP": 50.0, "CXCL10": 15000.0, "CXCL9": 8000.0, "CXCL11": 4000.0,
        "CXCR3": 600.0, "ACTA2": 500.0, "POSTN": 200.0, "CXCL12": 300.0,
        "CXCR4": 500.0, "SLC22A1": 200.0,
        "platinum_status": "sensitive", "prior_platinum_cycles": 0, "histotype": "HGSOC",
    }


@pytest.fixture(scope="module")
def ledger():
    return json.loads((CAP / "audit_ledger.json").read_text())


# ── Unit: scorer primitives ──────────────────────────────────────────────────

def test_zscore_basic():
    assert z_score(10.0, 5.0, 2.5) == 2.0
    assert z_score(5.0, 5.0, 0.0) == 0.0  # zero std guard


def test_fingerprint_logic():
    assert determine_fingerprint(-0.5, 0.5) is True     # FAP low, CXCL10 high
    assert determine_fingerprint(0.5, 0.5) is False     # FAP high
    assert determine_fingerprint(-0.5, -0.5) is False   # CXCL10 low


def test_oct1_gate():
    assert determine_oct1_status(0.1) == "HIGH"
    assert determine_oct1_status(-0.1) == "LOW"
    assert determine_oct1_status(0.0) == "LOW"


def test_tier_classification():
    tier, refined = classify_tier(-0.5, -0.5, 0.5, True)
    assert tier == "TIER_1_TRIPLE" and refined == "TIER_1A_ACCESSIBLE"
    tier, refined = classify_tier(-0.5, -0.5, -0.5, True)
    assert tier == "TIER_1_TRIPLE" and refined == "TIER_1B_CAGED"
    tier, refined = classify_tier(0.5, 0.5, 0.5, False)
    assert tier == "TIER_3_ACCESSIBLE" and refined is None


def test_immune_access_formula():
    # 0.60*tcell - 0.40*stromal
    assert compute_immune_access(1.0, 0.0) == pytest.approx(0.60)
    assert compute_immune_access(0.0, 1.0) == pytest.approx(-0.40)


def test_platinum_score_monotonic():
    # higher FAP_z (bad) should lower PLATINUM_SCORE (worse survival)
    low = compute_platinum_score(-0.5, 0.5)["PLATINUM_SCORE"]
    high = compute_platinum_score(0.5, -0.5)["PLATINUM_SCORE"]
    assert low > high


def test_input_validation_rejects_nan_inf_negative():
    with pytest.raises(ValueError):
        _validate_gene_values({"FAP": float("nan")})
    with pytest.raises(ValueError):
        _validate_gene_values({"FAP": float("inf")})
    with pytest.raises(ValueError):
        _validate_gene_values({"FAP": -1.0})
    # None is allowed (not measured)
    _validate_gene_values({"CXCL10": None})


# ── Unit: predictive axis ────────────────────────────────────────────────────

def test_predictive_uses_frozen_coeffs():
    assert PREDICTIVE_COEFFICIENTS["CXCL12"] == pytest.approx(-0.14972954829, abs=1e-9)
    assert PREDICTIVE_COEFFICIENTS["POSTN"] == pytest.approx(-0.10359314419, abs=1e-9)
    assert PREDICTIVE_INTERCEPT == pytest.approx(0.0628711804, abs=1e-9)


def test_predictive_probability_in_range():
    out = compute_platinum_response_score({"CXCL12": 300.0, "POSTN": 200.0}, input_is_log2=False)
    p = out["PLATINUM_RESPONSE_SCORE"]
    assert 0.0 <= p <= 1.0
    assert out["platinum_response_verdict"] == "INCONCLUSIVE"


def test_predictive_calibration_gate():
    raw = compute_platinum_response_score({"CXCL12": 300.0, "POSTN": 200.0},
                                          normalization="raw", input_is_log2=False)
    cal = compute_platinum_response_score({"CXCL12": 300.0, "POSTN": 200.0},
                                          normalization="quantile_to_reference", input_is_log2=False)
    # probability identical; call gated
    assert raw["PLATINUM_RESPONSE_SCORE"] == cal["PLATINUM_RESPONSE_SCORE"]
    assert raw["platinum_response_call"] is None
    assert cal["platinum_response_call"] in ("sensitive", "resistant")
    assert raw["platinum_response_calibration_required"] is True


def test_predictive_missing_genes_returns_none():
    out = compute_platinum_response_score({"CXCL12": 300.0}, input_is_log2=False)  # POSTN missing
    assert out["PLATINUM_RESPONSE_SCORE"] is None
    assert out["platinum_response_call"] is None


def test_predictive_fingerprint_stable():
    # frozen model fingerprint must be deterministic
    assert predictive_model_fingerprint() == predictive_model_fingerprint()
    assert len(predictive_model_fingerprint()) == 64


# ── Integration: endpoints ───────────────────────────────────────────────────

def test_demo_endpoint_200(client):
    r = client.get("/api/v1/platinum-window/demo")
    assert r.status_code == 200
    d = r.json()
    assert "PLATINUM_SCORE" in d
    assert "PLATINUM_RESPONSE_SCORE" in d
    assert d["platinum_response_verdict"] == "INCONCLUSIVE"


def test_score_endpoint_200(client, valid_payload):
    r = client.post("/api/v1/platinum-window/score", json=valid_payload)
    assert r.status_code == 200


def test_score_endpoint_no_apikey_local_dev(client, valid_payload):
    # regression: hash_api_key(None) used to 500 the endpoint
    r = client.post("/api/v1/platinum-window/score", json=valid_payload)
    assert r.status_code == 200


def test_score_negative_expression_422(client, valid_payload):
    bad = dict(valid_payload); bad["POSTN"] = -5.0
    assert client.post("/api/v1/platinum-window/score", json=bad).status_code == 422


def test_calibration_gate_via_api(client, valid_payload):
    raw = client.post("/api/v1/platinum-window/score", json=valid_payload).json()
    cal_payload = dict(valid_payload); cal_payload["normalization"] = "quantile_to_reference"
    cal = client.post("/api/v1/platinum-window/score", json=cal_payload).json()
    assert raw["platinum_response_call"] is None
    assert cal["platinum_response_call"] in ("sensitive", "resistant")


# ── Golden / determinism ─────────────────────────────────────────────────────

def _strip_volatile(d):
    d = dict(d)
    d.pop("timestamp_utc", None)
    d.pop("computation_ms", None)
    return d


def test_determinism_byte_stable(client):
    a = _strip_volatile(client.get("/api/v1/platinum-window/demo").json())
    b = _strip_volatile(client.get("/api/v1/platinum-window/demo").json())
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_golden_demo_key_values(client):
    """Freeze the demo scoring output so accidental coefficient/logic drift is caught."""
    d = client.get("/api/v1/platinum-window/demo").json()
    assert d["PLATINUM_SCORE"] == pytest.approx(0.7877, abs=1e-3)
    assert d["fingerprint_positive"] is True
    assert d["TIER"] == "TIER_1_TRIPLE"
    assert d["PLATINUM_RESPONSE_SCORE"] == pytest.approx(0.2913, abs=1e-3)
    assert d["model_version"] == "1.1.0"


def test_provenance_block_present(client):
    d = client.get("/api/v1/platinum-window/demo").json()
    p = d["provenance"]
    assert p["git_sha"]
    assert p["reference_cohort_sha256"]
    assert p["prognostic_model"]["fingerprint_sha256"]
    assert p["predictive_model"]["fingerprint_sha256"]


# ── Honesty / RUO guardrails ─────────────────────────────────────────────────

def test_no_16_cohort_claim_in_response(client, valid_payload):
    """No response may assert a 16-cohort / 2444 validation (audit correction CA-1/CA-2)."""
    d = client.post("/api/v1/platinum-window/score", json=valid_payload).json()
    blob = json.dumps(d)
    assert "VALIDATED_16_COHORTS" not in blob
    assert "n2444" not in blob
    # corrected honest counts
    assert d["validation_context"]["cohorts_validated"] == 6
    assert d["validation_context"]["patients_validated"] == 1236


def test_tier_flagged_discovery_only(client):
    d = client.get("/api/v1/platinum-window/demo").json()
    assert d["tier_discovery_only"] is True
    assert "did not replicate" in d["tier_validation_note"].lower() or \
           "exploratory" in d["tier_validation_note"].lower()


def test_ruo_disclaimer_present(client):
    d = client.get("/api/v1/platinum-window/demo").json()
    assert "Research Use Only" in d["ruo_disclaimer"]


def test_validation_context_claim_status(client):
    d = client.get("/api/v1/platinum-window/demo").json()
    cs = d["validation_context"]["claim_status"]
    assert cs["prognostic_fingerprint"]["status"] == "SUPPORTED"
    assert cs["tier_survival_separation"]["status"] == "NOT_EXTERNALLY_REPLICATED"
    assert cs["predictive_platinum_response"]["status"] == "INCONCLUSIVE"


# ── Audit-invariant: response must not contradict the ledger ─────────────────

def test_audit_invariant_no_overstated_claim_asserted(client, valid_payload, ledger):
    """
    If the ledger marks a claim OVERSTATED/UNVERIFIED, the API response must NOT contain
    language asserting it as validated. We check the two concrete overstated artifacts:
    the '16/2444 validated' framing and any 'tier validated externally' assertion.
    """
    d = client.post("/api/v1/platinum-window/score", json=valid_payload).json()
    blob = json.dumps(d).lower()
    # ledger sanity
    statuses = {k: v["status"] for k, v in ledger["claims"].items()}
    assert statuses["C2_tier_survival_separation"] == "OVERSTATED"
    assert statuses["C3_advertised_16_cohorts_2444"] == "UNVERIFIED_OVERSTATED"
    # response must not assert those overstated claims as fact
    assert "16 independent cohorts" not in blob
    assert "2,444" not in blob and "2444" not in blob
    # tier must be explicitly de-risked, not asserted validated
    assert d["tier_discovery_only"] is True


def test_ledger_fingerprint_claim_supported(ledger):
    c1 = ledger["claims"]["C1_fingerprint_prognostic_pooled"]
    assert c1["status"] == "SUPPORTED"
    assert c1["recomputed_HR"] == pytest.approx(0.6768, abs=1e-3)
    assert c1["recomputed_p"] < 1e-3


def test_ledger_tier_failure_covers_all_usable_cohorts(ledger):
    """Tier claim must record every external cohort with a usable log-rank p (5), all failing."""
    c2 = ledger["claims"]["C2_tier_survival_separation"]
    assert c2["status"] == "OVERSTATED"
    assert c2["external_cohorts_with_usable_logrank_p"] == 5
    assert c2["external_cohorts_where_separation_fails"] == 5
    assert c2["n_cohorts_holds"] == 0
    # every listed failing cohort has p >= 0.05
    per = c2["per_cohort"]
    usable = [v for v in per.values() if v.get("has_usable_logrank_p")]
    assert len(usable) == 5
    assert all(v["logrank_p"] >= 0.05 for v in usable)
