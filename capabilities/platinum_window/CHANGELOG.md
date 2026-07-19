# Changelog — Platinum Window capability

## [1.1.0] — Clinical-grade hardening + audit + predictive axis

### Audited & corrected (honesty)
- **Removed the "validated across 16 independent cohorts (n=2,444)" claim** — not backed by any
  shipped artifact. Corrected `config.VALIDATION_CTX` to honest counts (6 cohorts / n=1,236) with a
  structured per-claim `claim_status` (SUPPORTED / NOT_EXTERNALLY_REPLICATED / INCONCLUSIVE).
- **Tier survival-separation relabeled `discovery_only`** — did not replicate externally
  (GSE32062 log-rank p=0.93, GSE102073 p=0.48; all shipped external manifests `validation_holds=false`).
- Added `AUDIT.md` + machine-readable `audit_ledger.json` (independent recompute; the prognostic
  fingerprint Cox HR 0.677, p=2.04e-4 was reproduced exactly from shipped artifacts).
- `PLATINUM_SCORE_percentile_reference` corrected from `METAGX_POOLED_n2444` to
  `PROGNOSTIC_FINGERPRINT_6COHORT_n1236`.

### Added (predictive axis)
- New **`PLATINUM_RESPONSE_SCORE`** (predictive platinum-sensitivity probability) from the frozen
  manuscript Core-13 CXCL12/POSTN elastic-net logistic model (`predictive_axis.py`), distinct from
  the prognostic `PLATINUM_SCORE`. Verdict **INCONCLUSIVE**.
- **Calibration gate:** thresholded `platinum_response_call` is emitted only when
  `normalization="quantile_to_reference"`; otherwise probability/ranking only.

### Added (production hardening)
- `provenance.py` — response `provenance` block: git SHA + reference-cohort SHA-256 + audit-ledger
  SHA-256 + prognostic/predictive model fingerprints.
- Input validation: NaN / inf / non-numeric rejected with HTTP 422 (negative already blocked by schema).
- Determinism guarantee + frozen golden test.
- Enriched audit log with `model_version` + `git_sha` (no gene values / PHI logged).

### Fixed
- **`hash_api_key(None)` 500 crash** in the no-auth local-dev path of `/score` (pre-existing bug).

### Tests
- New `tests/test_platinum_window.py`: 26 tests (unit / integration / golden-determinism /
  calibration-gating / honesty-guardrail / audit-invariant). Coverage 88% overall.

### Version
- `MODEL_VERSION` 1.0.2 → 1.1.0.

---

## [1.0.2] — prior baseline
- Prognostic PLATINUM_SCORE (FAP/CXCL10 elastic-net Cox), tier system, window timer, sequence engine,
  CXCL10 imputation transparency, assay-failure warning, OCT1/metformin gating, artifact streamer.
