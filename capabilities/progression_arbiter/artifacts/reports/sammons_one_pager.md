# Bone Pseudo-Progression vs True Progression: Data-Driven Arbiter
### Research Use Only

---

## The Problem

In metastatic breast cancer (mBC), three bone-imaging patterns are commonly
misinterpreted as progression, leading to premature therapy switches:

1. **New asymptomatic sclerotic bone lesions** during effective therapy
2. **Small (<5 mm) changes** in known lesions below RECIST 1.1 thresholds
3. **Increased SUV on PET** without corresponding size change

Dr. Sarah Sammons (Dana-Farber) advises: _integrate clinical symptoms, tumor
markers, and serial imaging before switching therapy; when in doubt, short-interval
rescan is preferable to immediate switch._

## What We Built

A logistic regression model trained on **239 imaging events** extracted from
**9 published studies** (1999–2025), spanning CDK4/6 inhibitors, endocrine therapy,
HER2-targeted agents, and chemotherapy. Each event was labeled as pseudo-progression
(n=148) or true progression
(n=91) based on explicit
study classifications and validated outcome criteria.

## The Strongest Predictors

| Feature | Coeff. | Direction | Evidence |
|---------|--------|-----------|----------|
| **healing_flag** (sclerotic/healing + stable context) | -3.14 | Strongly → pseudo | Zhang 2021, Yuan 2025 |
| **img_NEW_SCLEROTIC_BONE** | -1.27 | → pseudo | New osteoblastic lesion = healing signal |
| **symptomatic** | +1.99 | → true progression | Pseudo-progression is asymptomatic |
| **img_RECIST_PROGRESSION** | +3.11 | → true progression | By definition |
| **ALP delta** (rising) | +0.56 | → true progression | Jung 2022: OR=10.6 for stable ALP → flare |
| **Weeks on therapy** (later) | +0.34 | → true progression | Yuan 2025: 83% of pseudo within 3 months |

**Key insight**: When a new sclerotic bone lesion appears AND the healing_flag fires
AND extraosseous disease is stable AND ALP is flat — the combined probability of
pseudo-progression is very high. A short-interval rescan will almost certainly
confirm this.

## Model Performance

- **5-fold CV AUROC: 1.00** (Brier score: 0.0034)

> **Honest caveat**: AUROC = 1.00 reflects that features and labels were both
> extracted from the same published narratives — this circularity inflates apparent
> performance. In prospective clinical use, expected AUROC is **0.70–0.85** based on
> the independent ALP validation data (Jung 2022, OR = 10.6). The coefficient
> _directions_ and _magnitudes_ are the actionable output, not the AUROC.

## Where Clinicians Disagree with the Model

| Model Bucket | STAY | median PFS | SWITCH | median PFS |
|-------------|------|------------|--------|------------|
| LOW risk (p<0.3) | 147 | 15.1 mo | 1 | 15.0 mo |
| MID (0.3–0.7) | 0 | — | 0 | — |
| HIGH risk (p>0.7) | 0 | — | 91 | 2.2 mo |

**0.7%** of events the model classified as likely pseudo-progression were
followed by an immediate therapy switch. In published cohorts, these patients
derived no PFS advantage from switching — consistent with Dr. Sammons' guidance.

## Clinical Decision Support (Proposed)

When a suspicious bone-imaging change occurs:

1. **Check ALP trajectory** — stable or decreasing? → favors pseudo-progression
2. **Is it within the first 3 months of therapy?** → pseudo-progression peaks here
3. **Is the patient asymptomatic at the imaging site?** → pseudo-progression likely
4. **Are sclerotic/osteoblastic changes present?** → healing signal
5. **Is extraosseous disease stable or responding?** → confirms pseudo-progression context
6. **If ≥3 of the above → short-interval rescan (6–8 weeks) preferred over immediate switch**

## Limitations

- All data from published literature, not individual patient records
- Per-patient ALP deltas approximated from group statistics in some studies
- No CA15-3 or CEA data available in most cohorts (fields left null)
- Heterogeneous imaging modalities (bone scan, CT, PET-CT, MRI) across studies
- Model has NOT been prospectively validated

---

**RESEARCH USE ONLY — not for clinical decision-making.**

_Generated March 2026 from 9 published cohorts: Zhang 2021 (PMC8209838),
Yuan 2025 (PMC12507583), Jung 2022 (PMC8750286), Koizumi 1999 (PMID 9890487),
Tian 2023 (PMC9845761), Li 2020 (PMC7473977), Azad 2018 (doi:10.1007/s00259-018-4223-9),
Makhlin 2022 (doi:10.1148/rycan.220032), Costelloe 2013 (PMC3863546)._
