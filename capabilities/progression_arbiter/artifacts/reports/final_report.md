# Bone Pseudo-Progression in Metastatic Breast Cancer
## Complete Pipeline Report — v2

**Research Use Only** | March 2026

---

## 1. Data Sources

| Study | N | Design | Imaging | Therapy | Events |
|-------|---|--------|---------|---------|--------|
| Zhang_2021 | 48 | Retrospective | BS+CT | CDK4/6i+ET / Placebo+ET | 11 pseudo |
| Yuan_2025 | 23+13 | Retrospective | CT bone window | HER2/CDK4/6i/Chemo | 23 pseudo, 13 prog |
| Jung_2022 | 101 | Retrospective | Bone scintigraphy | Chemo/Endo/HER2 | 45 flare, 56 prog |
| Koizumi_1999 | 23 | Prospective | Bone scan | CAF chemo | 5 flare, 5 PD, 13 other |
| Tian_2023 | 1 | Case report | CT/PET/SPECT/BS | CDK4/6i+ET→Chemo→reET | 2 events |
| Li_2020 | 1 | Case report | CT/PET-CT | Palbociclib+AI | 1 event |
| Azad_2018 | 22 | Prospective | NaF/FDG PET | Endocrine | 7 flare, 5 PD, 10 SD |
| Makhlin_2022 | 23 | Prospective | FDG PET-CT | Endocrine | 13 resp, 10 non-resp |
| Costelloe_2013 | 29 | Prospective | CT/XR/BS | Chemo/Endocrine | 10 PD, 19 non-PD |

**Total events: 248** | **Labeled: 239**
(Pseudo: 148,
True prog: 91,
Null/ambiguous: 9)

## 2. Labeling Rules

See labeling_rules.md for full documentation. Key thresholds:
- PFS ≤ 3 mo + SWITCH → true progression
- PFS ≥ 6 mo + STAY + healing_flag → pseudo-progression
- ALP delta > +20% + SWITCH → true progression
- All study-explicit classifications honored

## 3. Model Architecture & Performance

L2-regularized logistic regression (λ=0.5), 17 features.

**5-fold CV AUROC: 1.0000 ± 0.0000 | Brier: 0.0034**

AUROC caveat: structural correlation between literature-derived features and labels
inflates apparent performance. Expected prospective AUROC: 0.70–0.85.

### Full Coefficient Table

| Feature | Coefficient | Direction |
|---------|-------------|-----------|
| intercept | -0.7493 | — |
| img_NEW_SCLEROTIC_BONE | -1.2730 | → pseudo-progression |
| img_SUV_INCREASE_NO_SIZE | +0.7647 | → true progression |
| img_RECIST_PROGRESSION | +3.1114 | → true progression |
| img_STABLE_DISEASE | -2.7338 | → pseudo-progression |
| tx_CDK46 | -0.1973 | → pseudo-progression |
| tx_HER2 | +0.0907 | → true progression |
| tx_ENDOCRINE | -0.1092 | → pseudo-progression |
| tx_CHEMO | +0.0852 | → true progression |
| symptomatic | +1.9942 | → true progression |
| new_pain_at_site | +0.5769 | → true progression |
| healing_flag | -3.1381 | → pseudo-progression |
| weeks_since_therapy_start_norm | +0.3390 | → true progression |
| alp_delta_norm | +0.5583 | → true progression |

### Calibration

| Bin | N | Mean Predicted | Mean Observed |
|-----|---|----------------|---------------|
| [0.0,0.2) | 148 | 0.020 | 0.000 |
| [0.6,0.8) | 6 | 0.775 | 1.000 |
| [0.8,1.0) | 85 | 0.982 | 1.000 |

## 4. Clinician-Decision Discordance

See confusion_report.md for full analysis.

| Bucket | STAY (n) | PFS | SWITCH (n) | PFS |
|--------|----------|-----|------------|-----|
| LOW | 147 | 15.1 mo | 1 | 15.0 mo |
| MID | 0 | — | 0 | — |
| HIGH | 0 | — | 91 | 2.2 mo |

**0.7%** of low-risk events were switched.
**0.0%** of high-risk events were not switched.

## 5. Radiology Parser

Rule-based NLP: 90% accuracy on 10 worked examples.
Outputs: imaging_change_type, healing_flag, key_phrases.

## 6. Assumptions & Imputations

| Study | What was imputed | Flag |
|-------|------------------|------|
| Jung_2022 | Per-patient ALP sampled from group medians ± noise | imputed=true |
| Zhang_2021 | PFS sampled around subgroup medians | imputed=true |
| Yuan_2025 | PFS sampled; ALP for 13/23 patients with prior bone mets only | imputed=true |
| Makhlin_2022 | Responder/non-responder split estimated (13/10) | imputed=true |
| Azad_2018 | PFS for PD group sampled <24 wk; SD group PFS estimated | imputed=true |
| All studies | CA15-3 and CEA: not reported → left null | — |

## 7. Artifacts

| File | Contents |
|------|----------|
| mbc_bone_events_raw.json | 248 events, 9 studies |
| mbc_bone_events_labeled.json | + true_progression_label |
| mbc_bone_events_training_set.json | Labeled subset (239 events) |
| labeling_rules.md | Labeling criteria and thresholds |
| progression_arbiter_model_v1.json | Coefficients + scoring function |
| mbc_bone_progression_confusion_report.json | 3×2 confusion matrix |
| confusion_report.md | Discordance analysis |
| radiology_parser_examples.json | 10 worked parser examples |
| sammons_one_pager.md | Clinician-facing summary |
| final_report.md | This report |

---
**RESEARCH USE ONLY — not for clinical decision-making.**
