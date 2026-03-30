# Appendix: Hard Cases — Progression Arbiter v1
### RESEARCH USE ONLY

---

## Vignette A — Symptomatic Sclerotic Lesion (CDK4/6i, Week 6)

A 58-year-old woman with HR+/HER2- mBC on palbociclib + letrozole presents at week 6 with new sclerotic lesions in the thoracic spine on restaging CT. She reports new mid-back pain at the lesion site; ALP is minimally elevated (+5% from baseline).

| Field | Value |
|-------|-------|
| imaging_change_type | NEW_SCLEROTIC_BONE |
| therapy_class | CDK46 |
| symptomatic | True |
| new_pain_at_site | True |
| healing_flag | True |
| weeks_on_therapy | 6 |
| alp_delta_pct | +5% |
| ca153_delta_pct | 0% |

**P(true progression) = 6.2%** — Model recommends short-interval rescan.

The healing_flag (-3.14) and sclerotic imaging signature (-1.27) dominate the score despite strong counter-pull from symptomatic (+1.99) and new pain (+0.58). This is the model's most internally conflicted case: the pseudo-favoring features sum to -4.61 while the progression-favoring features sum to +2.57, but the net logit of -2.72 still falls clearly in the LOW-risk bucket.

- **Obtain serial ALP at 2-week intervals**: if ALP trends down despite pain, this strongly favors osteoblastic healing rather than progression (Jung 2022: OR = 10.6 for stable ALP predicting flare).
- **Confirm extraosseous disease is stable or responding**: if soft-tissue/visceral disease is controlled, continue current therapy and rescan at 6–8 weeks.

---

## Vignette B — Late Sclerosis with Flat ALP (CDK4/6i, Week 36)

A 64-year-old woman with HR+/HER2- mBC has been on ribociclib + fulvestrant for 9 months with excellent clinical response. Surveillance CT at week 36 reveals new sclerotic foci in the pelvis. She is asymptomatic, ALP is essentially unchanged (+3%).

| Field | Value |
|-------|-------|
| imaging_change_type | NEW_SCLEROTIC_BONE |
| therapy_class | CDK46 |
| symptomatic | False |
| new_pain_at_site | False |
| healing_flag | True |
| weeks_on_therapy | 36 |
| alp_delta_pct | +3% |
| ca153_delta_pct | 0% |

**P(true progression) = 0.6%** — Model recommends short-interval rescan (very high confidence pseudo-progression).

Every active feature aligns toward pseudo-progression: healing_flag (-3.14), sclerotic imaging (-1.27), asymptomatic, flat ALP, CDK4/6i therapy. The only countervailing signal is the 36-week timepoint (+0.23), reflecting that pseudo-progression typically peaks within the first 3 months — but at +0.23 it is far too weak to overcome the -5.36 aggregate pseudo-progression signal.

- **Continue current therapy without interruption**: this is the textbook pseudo-progression presentation — sclerotic change in an asymptomatic patient with flat markers on effective CDK4/6i therapy.
- **Schedule confirmatory rescan at 8–12 weeks**: expect lesion stabilization or maturation to dense sclerosis; any new lytic component at that time would warrant reassessment.

---

## Vignette C — Isolated SUV Increase, Asymptomatic (CDK4/6i, Week 10)

A 52-year-old woman with HR+/HER2- mBC on abemaciclib + anastrozole undergoes FDG PET-CT at week 10. A known L3 vertebral lesion shows increased SUV (3.2 → 4.8) without any change in size or morphology. She is asymptomatic with mildly rising ALP (+8%).

| Field | Value |
|-------|-------|
| imaging_change_type | SUV_INCREASE_NO_SIZE |
| therapy_class | CDK46 |
| symptomatic | False |
| new_pain_at_site | False |
| healing_flag | False |
| weeks_on_therapy | 10 |
| alp_delta_pct | +8% |
| ca153_delta_pct | 0% |

**P(true progression) = 48.2%** — Model is indeterminate; additional workup required before any therapy change.

The SUV imaging feature (+0.76) is the sole active signal, offset almost exactly by the intercept (-0.75) and CDK4/6i therapy effect (-0.20). The logit lands at -0.07 — effectively the decision boundary. The model has no healing flag, no symptoms, no pain, and no size change to resolve the ambiguity in either direction.

- **Repeat FDG PET-CT at 6–8 weeks**: if SUV normalizes or stabilizes without size change, pseudo-progression is confirmed; if SUV continues rising or new size increase appears, escalate to biopsy or therapy change.
- **Trend ALP biweekly**: a continued rise above +20% over the next month would shift the model probability above 0.5 and favor true progression; stable or declining ALP would favor pseudo-progression.

---

## When the Model Says It Doesn't Know

Vignette C is the prototypical indeterminate case. When P(true progression) falls in the MID bucket (0.3–0.7), the model's coefficient signals are in near-equilibrium and the output conveys genuine clinical uncertainty rather than a recommendation. In this range, the model explicitly recommends additional workup — serial imaging, ALP trending, and symptom monitoring — over either switching therapy or continuing without surveillance. Isolated SUV increase without size change is a recognized diagnostic gray zone: data from Azad 2018 (NaF/FDG PET, n=22) and Makhlin 2022 (FDG PET-CT, n=23) suggest that approximately 60% of such findings resolve on CDK4/6 inhibitor therapy without morphologic progression, while the remaining ~40% represent early true progression that becomes apparent on the next imaging timepoint. A 6-to-8-week rescan protocol, combined with biweekly ALP trending, is the minimum workup needed to move a MID-bucket case into a HIGH or LOW classification where the model — and the clinician — can act with confidence.

---

**RESEARCH USE ONLY — not for clinical decision-making.**

_Progression Arbiter v1 | March 2026 | Coefficients frozen from 239 events across 9 published cohorts._
_SUV resolution rate: Azad 2018 (doi:10.1007/s00259-018-4223-9), Makhlin 2022 (doi:10.1148/rycan.220032)._
_ALP discriminative power: Jung 2022 (PMC8750286, OR = 10.6, 95% CI 4.4–25.5)._
