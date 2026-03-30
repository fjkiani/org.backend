# Labeling Rules — true_progression_label ∈ {0, 1, null}

## Label = 0 (Pseudo-Progression / Flare / Healing)
| # | Rule | Studies Applied |
|---|------|----------------|
| 0a | Study **explicitly** identifies event as pseudo-progression, flare, or osteoblastic healing | Zhang_2021 (pseudo group), Yuan_2025 (pseudo group), Jung_2022 (flare group), Koizumi_1999 (flare), Li_2020 |
| 0b | Imaging improved/stabilized on follow-up, decision=STAY, PFS from event ≥ 6.0 months, healing_flag=true | Azad_2018 flare, Makhlin_2022 responders |
| 0c | imaging_change_type = STABLE_DISEASE and decision = STAY | Koizumi_1999 (NC, PR), Azad_2018 (SD), Costelloe_2013 (non-PD) |
| 0d | Tian_2023 event 1: sclerotic change + 59% breast tumor reduction → retrospectively confirmed pseudo | Tian_2023 |

## Label = 1 (True Progression)
| # | Rule | Studies Applied |
|---|------|----------------|
| 1a | Study **explicitly** confirms progression for the event | Jung_2022 (progression group), Koizumi_1999 (PD), Yuan_2025 (progression group) |
| 1b | PFS from event ≤ 3.0 months AND decision = SWITCH | Yuan_2025 progression events, Azad_2018 PD |
| 1c | imaging_change_type = RECIST_PROGRESSION AND decision = SWITCH | Costelloe_2013 (PD by MDA) |
| 1d | ALP delta > +20% AND decision = SWITCH | Applied to events meeting both criteria |

## Label = null (Ambiguous / Insufficient)
- Tian_2023 event 2: osteolytic worsening on 2L chemo, later reversed — genuinely ambiguous
- Makhlin_2022 non-responders with PFS 5.0–8.0 months — borderline
- Any event not matching above rules

## Thresholds
| Parameter | Value | Source |
|-----------|-------|--------|
| PFS cutoff for true progression | ≤ 3.0 months | Clinical: very short PFS post-switch = confirmed failure |
| PFS cutoff for pseudo-progression | ≥ 6.0 months | Conservative: sustained benefit = benign imaging change |
| ALP delta threshold | > +20% | Jung 2022: progression median delta +19%; OR=10.6 for stable ALP → flare |
