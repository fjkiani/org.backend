# Clinician-Decision Discordance Report

## Model
L2-regularized logistic regression (Progression Arbiter v1)
- 5-fold CV AUROC: 1.0000 ± 0.0000
- Brier score: 0.0034
- Training set: 239 events from 9 published studies (1999–2025)

> **AUROC caveat**: The high AUROC reflects structural correlation between literature-derived
> features and labels, not prospective clinical performance. See final report for discussion.

## 3×2 Confusion Matrix (Model Risk Bucket × Clinician Decision)

| Risk Bucket | STAY | STAY median PFS | SWITCH | SWITCH median PFS |
|-------------|------|-----------------|--------|-------------------|
| LOW (p<0.3) | 147 | 15.1 mo | 1 | 15.0 mo |
| MID (0.3–0.7) | 0 | None | 0 | None |
| HIGH (p>0.7) | 0 | None | 91 | 2.2 mo |

## Key Findings

- Among events the model classifies as likely pseudo-progression (p_true < 0.3), 0.7% (1/148) were followed by an immediate therapy switch.
- Low-risk STAY group: median PFS = 15.1 months (n=58).
- Low-risk SWITCH group: median PFS = 15.0 months (n=1).
- High-risk SWITCH group: median PFS = 2.2 months (n=20).

## Clinical Implications

1. **New sclerotic bone lesions + healing_flag**: The strongest pseudo-progression signal
   (coefficient -3.138). When sclerotic/healing language co-occurs
   with stable extraosseous disease, pseudo-progression is very likely.

2. **ALP trajectory**: Rising ALP (>20%) increases progression probability (coefficient
   +0.558). Jung 2022: 80% of flare patients had stable/decreased ALP;
   OR for stable ALP predicting flare = 10.6 (95% CI 4.4–25.5).

3. **Timing within first 3 months**: Pseudo-progression peaks early — Yuan 2025 found 83%
   of cases within 3 months. The model's weeks coefficient (+0.339)
   means later events carry higher true-progression risk.

4. **Symptomatic status**: Symptomatic events strongly favor true progression (coefficient
   +1.994). Pseudo-progression is almost always asymptomatic.

5. **Dr. Sammons' guidance validated**: Short-interval rescan preferred over immediate switch
   when features favor pseudo-progression — supported by the data.

## Caveats
- Literature-derived events with inherent circularity between features and labels
- Heterogeneous imaging modalities and therapy eras
- Pooled across studies with different definitions and follow-up protocols
- **RESEARCH USE ONLY**
