# Provenance — Platinum Window capability

Traceability from deployed code → frozen models → shipped artifacts → manuscript → literature.
Everything below is anchored to real artifacts on disk or to the foundational-biology manuscript;
no performance number here is invented.

## 1. Two models, two questions (do not conflate)

### 1a. Prognostic — `PLATINUM_SCORE` (deployed, validated)
- **Code:** `scorer.py :: compute_platinum_score` (elastic-net Cox linear predictor).
- **Coefficients (frozen):** `FAP_z = +0.2032507043`, `CXCL10_z = −0.1474166728`; LP∈[−0.661403, 0.803347]; threshold 0.3702132699.
- **Model fingerprint:** emitted per-response as `provenance.prognostic_model.fingerprint_sha256`.
- **Evidence (SUPPORTED):** pooled cohort-stratified Cox on the fingerprint (FAP_z<0 AND CXCL10_z>0):
  **HR 0.677 (95% CI 0.551–0.832), p=2.04e-4**, 6 cohorts, n=1,236.
  - Artifact: `artifacts/data/validation/cross_cohort_fingerprint_regression.json` and
    `.../cross_cohort_fingerprint_pooled.csv` (1,236 rows).
  - Cohorts: GSE102073 (n=85), GSE17260 (n=110), GSE26712 (n=185), GSE32062 (n=260), GSE49997 (n=171), TCGA-HGSOC (n=427).
  - **Independently reproduced** in this audit (see `AUDIT.md` / `audit_ledger.json`, claim C1) to 4 decimals.

### 1b. Predictive — `PLATINUM_RESPONSE_SCORE` (added v1.1.0, INCONCLUSIVE)
- **Code:** `predictive_axis.py :: compute_platinum_response_score` (Core-13 elastic-net logistic).
- **Coefficients (frozen, non-zero):** `CXCL12 = −0.14972954829`, `POSTN = −0.10359314419`; intercept 0.0628711804; Youden threshold 0.4152970707.
- **Scaler (frozen, log2 space, GSE30161):** CXCL12 mean 4.3820 / sd 0.7906; POSTN mean 3.9741 / sd 1.7118.
- **Model fingerprint:** `provenance.predictive_model.fingerprint_sha256` (also inline in the axis note).
- **Evidence (INCONCLUSIVE):** out-of-distribution live-fire on **GSE63885 (n=75)**: AUROC **0.638 (95% CI 0.513–0.764), p=0.031**; nested-CV 0.592±0.112; 0/28 single genes survive FDR<0.05 OOD.
  - Source: foundational-biology manuscript (CrisPRO Stromal Cage v1) + frozen coefficient artifact `crispro_stromal_cage_v1_coefficients.json`.
  - Training label is PFI-derived (survival) → leakage risk for a response model; EPV≈0.36 (10 events). Discovery-grade by construction.

## 2. Tiers — discovery only (did NOT replicate externally)
- **Code:** `scorer.py :: classify_tier`; response `tier_discovery_only=true`.
- **Evidence:** external tier survival-separation fails in every tested cohort — 5/5 external cohorts with a usable log-rank p fail (GSE32062 p=0.929 n=260, GSE102073 p=0.476 n=85, GSE17260 p=0.821, GSE26712 p=0.890, GSE49997 p=0.060); all `validation_manifest*.json` report `validation_holds=false`.
- Relabeled per audit corrective action CA-3.

## 3. Reference distribution
- **Code:** `reference/tcga_hgsoc_stats.json` (loaded at startup); SHA-256 emitted as `provenance.reference_cohort_sha256`.
- **Cohort:** TCGA-HGSOC GDC 2025, n=427 (SLC22A1/OCT1 reference n=113 — smaller; IHC confirmation advised).

## 4. Composite-score approximation (disclosed)
- `IMMUNE_ACCESS_SCORE` uses a 2-component approximation (`0.60·TCELL_GPS − 0.40·STROMAL_ARM`) because
  dedicated myeloid markers (CD163/CD68/MRC1/CSF1R) are absent from the input panel; the original
  3-component formula weighted a myeloid-flood term. Documented in `scorer.py :: compute_immune_access`.

## 5. Literature anchors (foundational biology)

**CXCL12 / stromal exclusion (supports predictive coefficient sign, negative = better response):**
- D'Alterio et al. 2022; Chen et al. 2019 (PNAS); Popple et al. 2012 (BJC); Zhang et al. 2020 (296-patient HGSOC); Qi et al. 2025; Lee et al. 2017; Wang et al. 2024.

**POSTN / CAF-driven resistance (supports predictive coefficient sign):**
- De Oliveira Macena et al. 2024; Nabi-Afjadi et al. 2025; Takatsu et al. 2023; Yoshikawa et al. 2023; Chen et al. 2026.

**FAP / CAF barrier (supports prognostic fingerprint; direction reversed in PAAD):**
- Wei et al. 2025; Grout et al. 2022; Udinotti et al. 2025; Xiao et al. 2023; Zhao et al. 2022 (HR 2.56, 95% CI 1.69–3.87); Corvigno et al. 2025 (HGSOC-specific, key).

**Illustrative platinum-resistant salvage context (used only as a cautionary example, no rescue claim):**
- ARTISTRY-7 (NCT05092360 / GOG-3063 / ENGOT-OV68): Phase 3 nemvaleukin alfa + pembrolizumab vs chemo in
  platinum-resistant ovarian cancer, 456 pts; **failed** interim OS (10.1 vs 9.8 mo, HR 0.98); program halted (2025).

## 6. Governance
- Frozen PRODUCT ranker `fit = clip((p·t)/‖t‖₂, 0, 1)` is a mechanism-fit ranker and is **NOT** an outcome
  model; it is **not** used in this capability's scoring and is not introduced here.
- All outputs are Research Use Only. "Clinical-grade" in this release = auditable, tested,
  provenance-tracked, deterministic engineering — not a regulatory clearance.

## 7. Cross-references
- `AUDIT.md` — human-readable audit.
- `audit_ledger.json` — machine-readable claim→evidence→status ledger.
- `CHANGELOG.md` — v1.0.2 → v1.1.0 changes.
- Manuscript: CrisPRO Stromal Cage product line — foundational biology dossier v1.
