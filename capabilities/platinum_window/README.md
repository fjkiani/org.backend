# Platinum Window Capability

**Version:** 1.1.0 · **Disposition:** Research Use Only (RUO) · **Indication scope:** HGSOC (high-grade serous ovarian carcinoma)

A FastAPI capability that scores bulk RNA-seq expression against the CrisPRO Stromal Cage
biology to time the "platinum window" — the interval during which the tumor stroma is
permissive to immune access and platinum-based therapy. It exposes **two distinct axes**
that must not be conflated:

| Axis | Model | What it answers | Validation status |
|---|---|---|---|
| **PLATINUM_SCORE** (prognostic) | Elastic-net Cox on **FAP_z / CXCL10_z** | Who is likely to do worse on survival | **SUPPORTED** cross-cohort: 6 cohorts, n=1,236, HR 0.677 (95% CI 0.551–0.832), p=2.04e-4 |
| **PLATINUM_RESPONSE_SCORE** (predictive) | Core-13 elastic-net logistic on **CXCL12 / POSTN** | Probability of platinum *sensitivity* | **INCONCLUSIVE** / discovery-grade: OOD AUROC 0.638 (95% CI 0.513–0.764), p=0.031 |

> The prognostic axis (survival) and the predictive axis (response) are separate models
> answering separate questions. This separation is deliberate and is enforced in code,
> in the response schema, and in the test suite.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/platinum-window/demo` | none | Patient-1 demo (frozen golden output) |
| `POST` | `/api/v1/platinum-window/score` | API key (rate-limited 100/min) | Score a sample |
| `GET` | `/api/v1/platinum-window/artifacts/{path}` | none | Glass-box artifact streamer (traversal-guarded) |

### Request (POST /score) — key fields
- Required expression (raw, non-negative; TPM assumed): `FAP, CXCL9, CXCL11, CXCR3, ACTA2, POSTN, CXCL12, CXCR4, SLC22A1`; `CXCL10` optional (imputed with transparency).
- Clinical: `platinum_status`, `prior_platinum_cycles`, `histotype`.
- `normalization`: `"raw"` (default) or `"quantile_to_reference"`. **Only `quantile_to_reference` unlocks a thresholded predictive `platinum_response_call`** — the frozen Youden threshold does not transfer to arbitrary normalizations without recalibration.

### Response — notable fields
- Prognostic: `PLATINUM_SCORE`, `risk_tier`, `PLATINUM_SCORE_percentile` (reference: `PROGNOSTIC_FINGERPRINT_6COHORT_n1236`).
- Predictive: `PLATINUM_RESPONSE_SCORE` (probability), `platinum_response_verdict="INCONCLUSIVE"`, `platinum_response_call` (null unless calibrated), `platinum_response_calibration_required=true`.
- Tiers: `TIER`, `TIER_REFINED`, `tier_discovery_only=true` (tiers did **not** replicate externally).
- Governance: `validation_context.claim_status` (per-claim evidence + status), `provenance` (git SHA + model/artifact SHA-256), `ruo_disclaimer`, `normalization_warning`.

## Honesty & guardrails
This capability was audited (see `AUDIT.md` / `audit_ledger.json`). Corrections applied in v1.1.0:
- The prior "validated across 16 cohorts (n=2,444)" claim is **not** backed by any shipped artifact and was removed. Honest counts (6 cohorts / n=1,236, prognostic only) are used.
- Tier survival-separation **did not replicate** in every external cohort with a usable log-rank statistic (5/5: GSE32062 p=0.93, GSE102073 p=0.48, GSE17260 p=0.82, GSE26712 p=0.89, GSE49997 p=0.06) and is flagged `discovery_only`.
- The predictive CXCL12/POSTN model is labeled INCONCLUSIVE and gated behind calibration.
- An audit-invariant test asserts no response can present an overstated claim as fact.

## Reproducibility
Scoring is deterministic and dependency-free at request time (no RNG, no network). Identical
inputs + identical `model_version` yield byte-identical scores (enforced by `test_determinism_byte_stable`
and a frozen golden test). Every response carries a `provenance` block for traceability.

## Tests
```
pytest capabilities/platinum_window/tests -q      # 26 tests
```

## Indication caveat
The FAP/CXCL10 fingerprint direction is **reversed in PAAD** (pancreatic; HR ~1.81 in TCGA-PAAD)
and is contraindicated there. This capability is scoped to HGSOC only; `histotype=PAAD` is routed INELIGIBLE.

_Research Use Only. Not for clinical decision-making without prospective validation._
