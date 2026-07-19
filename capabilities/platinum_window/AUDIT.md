# Platinum Window Capability — Clinical-Grade Audit

**Generated (UTC):** 2026-07-19T09:03:48Z
**Scope:** `capabilities/platinum_window` @ prior model_version 1.0.2
**Method:** Independent recomputation from shipped artifacts (Cox PH / log-rank via lifelines) — claims were re-derived, not trusted from manifests.
**Disposition:** Research Use Only (RUO). "Clinical-grade" = auditable, tested, provenance-tracked, deterministic — NOT a regulatory clearance.

## Verdict at a glance

| Advertised claim | Status | Evidence |
|---|---|---|
| FAP/CXCL10 fingerprint is prognostic (cross-cohort) | **SUPPORTED** | Pooled cohort-stratified Cox, **6 cohorts, n=1,236, HR 0.677 (95% CI 0.551–0.832), p=2.04e-4** — recomputed, matches manifest exactly |
| 3-tier system separates survival externally | **OVERSTATED** | **5/5 external cohorts with a usable log-rank p FAIL** (GSE32062 p=0.929, GSE102073 p=0.476, GSE17260 p=0.821, GSE26712 p=0.890, GSE49997 p=0.060); 0 hold; all shipped manifests `validation_holds=false` |
| "Validated across 16 cohorts (n=2,444)" | **UNVERIFIED / OVERSTATED** | No shipped artifact demonstrates this. Largest real validation = 6 cohorts / n=1,236 (prognostic only) |
| CXCL12/POSTN predictive model deployed | **MISSING** | Not present in `scorer.py`. Manuscript verdict INCONCLUSIVE (OOD AUROC 0.638, 95% CI 0.513–0.764, p=0.031) |
| Platinum-response labels well-populated | **LOW-N (disclosed)** | Only 9 confirmed-label TCGA patients (5 events); already disclosed in shipped audit |

## The central finding — two different models

The capability advertises one thing and ships another:

- **Deployed `PLATINUM_SCORE`** = elastic-net Cox on **FAP_z (+0.2033) / CXCL10_z (−0.1474)** → this is the **PROGNOSTIC** fingerprint (who does badly on survival). This is the model that is genuinely validated cross-cohort.
- **Manuscript headline** = elastic-net on **CXCL12 (−0.150) / POSTN (−0.104)** → this is the **PREDICTIVE** platinum-response model. It is **absent from the deployed code** and is **INCONCLUSIVE** where tested out-of-distribution.

These are exactly the prognostic-vs-predictive axes the manuscript separates. The capability shipped only the prognostic axis while some advertising language implied predictive/validated performance. This audit corrects that.

## What is genuinely true (defensible claims)

1. **Prognostic fingerprint — VALIDATED cross-cohort.** FAP_z<0 AND CXCL10_z>0 predicts better OS: HR 0.677 (95% CI 0.551–0.832), p=2.04e-4, pooled across 6 cohorts (GSE102073, GSE17260, GSE26712, GSE32062, GSE49997, TCGA-HGSOC), n=1,236. Independently reproduced here.
2. **Tier survival-separation — did NOT replicate externally.** In every external cohort with a usable log-rank statistic (5/5: GSE32062, GSE102073, GSE17260, GSE26712, GSE49997), tier survival-separation was non-significant (all p≥0.05). Three further manifests (CPTAC, MSK2025, stub) carry no usable log-rank p and cannot verify a positive claim. Relabeled discovery/exploratory.
3. **Predictive platinum-response (CXCL12/POSTN) — INCONCLUSIVE / discovery-grade.** Added as a distinct, calibration-gated axis; never asserted as validated.

## Corrective actions applied in this release

- **CA-1** — `config.py` VALIDATION_CTX rewritten to a structured `claim_status` (per-claim evidence + status) replacing the flat "16/2,444 validated".
- **CA-2** — Removed "Validated across 16 independent cohorts (n=2,444)" from scorer; `score_confidence` can no longer assert a 16-cohort validation.
- **CA-3** — Tier outputs annotated `discovery_only=true`; response states tiers did not replicate externally.
- **CA-4** — CXCL12/POSTN predictive model added as `PLATINUM_RESPONSE_SCORE` (verdict INCONCLUSIVE, calibration-required).
- **CA-5** — Audit-invariant test: no API response may assert a claim flagged OVERSTATED/UNVERIFIED here.

## Reproducibility

- Fingerprint Cox: `lifelines.CoxPHFitter`, `strata=[cohort]`, from `artifacts/data/validation/cross_cohort_fingerprint_pooled.csv` (1,236 rows post-dropna). Recomputed HR matches the shipped manifest to 4 decimals.
- External tier log-rank: robust re-scan of all 8 shipped `validation_manifest*.json`, keyed on the presence of a usable log-rank p (metadata-independent). 5 manifests carry a usable p (GSE32062 0.929, GSE102073 0.476, GSE17260 0.821, GSE26712 0.890, GSE49997 0.060) — all non-significant; the remaining 3 (CPTAC, MSK2025, stub) report null/absent statistics and are treated as non-supporting.

_This audit is the evidence basis for the honest-correction, guardrail, and test work in this release._
