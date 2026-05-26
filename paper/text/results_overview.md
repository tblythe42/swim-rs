# Example 4 Results Overview

## Study Design

- 159 US flux tower sites across 6 land cover classes, calibration period 1987–2025.
- 8 soil/vegetation parameters per site calibrated with PEST++ IES (200 realizations, 3 iterations)
  against USGS SSEBop NHM ETf derived from Landsat.
- Validated against energy-balance-corrected flux tower ET (ET_corr).
- Paired evaluation: SWIM and SSEBop scored on the identical set of valid days or months at each
  site so that neither model benefits from a larger or more favorable sample.
- 317,351 total paired daily observations across all sites; median 1,227 paired days per site.

## Daily ET (159 sites)

- SWIM median R² = 0.47 vs SSEBop median R² = 0.42. SWIM outperforms SSEBop at 60% of sites
  (95/159).
- SWIM median RMSE = 1.01 mm/day vs SSEBop 1.09 mm/day.
- SWIM is nearly unbiased at the network level (median bias +0.02 mm/day). SSEBop shows a
  small dry bias (median −0.04 mm/day).
- 72% of sites have positive SWIM R² (115/159) vs 72% for SSEBop (114/159).

## Monthly ET (143 sites)

- SWIM median R² = 0.56 vs SSEBop median R² = 0.52. SWIM outperforms at 66% of sites (95/143).
- SWIM median RMSE = 20.9 mm/month vs SSEBop 25.0 mm/month.
- SWIM has a small wet bias (median +0.3 mm/month) vs SSEBop dry bias (median −0.8 mm/month).
- 77% of sites have positive SWIM R² (111/145) vs 70% for SSEBop (102/145).

## Performance by Land Cover

### Croplands (59 sites)

Strongest category for SWIM. Daily R² 0.62 vs 0.60, monthly R² 0.75 vs 0.70. SWIM wins 59%
of sites daily, 62% monthly. SSEBop has a dry bias in croplands (median −0.23 mm/day) while
SWIM has a small wet bias (+0.21 mm/day).

### Evergreen Forests (18 sites)

Largest relative improvement over SSEBop. Daily R² 0.41 vs 0.04, monthly R² 0.58 vs 0.08.
SWIM wins 83% of sites daily, 89% monthly. SSEBop carries a substantial wet bias (+0.33 mm/day)
at forest sites, likely reflecting energy balance closure issues in the SSEBop ETf calibration
target, while SWIM is nearly unbiased (−0.05 mm/day).

### Grasslands (30 sites)

Competitive at the daily step. SSEBop has a marginally higher median R² (0.41 vs 0.40), yet SWIM
wins at 67% of sites daily and 66% monthly. Monthly R² is also close (SWIM 0.56 vs SSEBop 0.53).
SWIM has smaller bias at both timescales.

### Mixed Forests (14 sites)

Daily R² 0.60 vs 0.53, monthly R² 0.69 vs 0.64. Win rate is 50% at both timescales. Both models
carry a positive (wet) bias (~0.5 mm/day), likely reflecting underestimation in flux tower ET_corr
at forested sites with incomplete energy balance closure.

### Shrublands (29 sites)

Both models produce near-zero or negative median daily R² values (SWIM −0.02, SSEBop −0.13). SWIM
wins 48% of sites daily but 71% monthly (monthly R² 0.22 vs −0.01). Both models have low absolute
skill in arid shrublands, but SWIM captures more of the seasonal signal at the monthly timescale.

### Wetland/Riparian (9 sites)

SSEBop substantially outperforms SWIM at these sites (daily R² 0.43 vs −0.12). The soil water
balance fundamentally cannot represent groundwater-subsidized ET — precipitation-driven water inputs
are insufficient to explain the observed flux. SWIM wins at only 4 of 9 sites (44%).

## SWIM Weaknesses

- **Wetland and riparian sites.** SWIM's daily median R² is −0.12 and monthly median R² is −0.44
  across the 9 wetland/riparian sites, while SSEBop achieves positive R² at these sites (0.43 daily,
  0.54 monthly). The model's precipitation-driven soil water balance cannot account for lateral
  groundwater inflows that subsidize ET at these sites. This is a structural limitation: without an
  explicit groundwater term, SWIM will systematically underestimate ET wherever shallow water tables
  supply a significant fraction of plant water use.

- **Shrubland skill.** Both models produce near-zero or negative median daily R² in shrublands
  (SWIM −0.02, SSEBop −0.13), and SWIM's daily win rate is only 48%. At the monthly timescale
  SWIM recovers (win rate 71%), but daily shrubland ET dynamics — low fluxes with episodic pulses
  in shallow soils — remain a challenge for the soil water balance.

- **Positive bias in mixed forests.** Both SWIM and SSEBop overestimate ET relative to flux towers
  at mixed forest sites (median bias ~+0.5 mm/day). While this likely reflects energy balance closure
  problems at forest towers rather than a pure model error, it means SWIM does not correct for this
  known observational artifact and inherits whatever bias exists in the SSEBop ETf calibration target
  at these sites.

- **Aggregation-dependent win rate.** SWIM's site-level win rate increases slightly from 60% daily
  to 66% monthly. While monthly aggregation narrows the median R² gap, it reduces noise enough that
  SWIM's process-based continuity wins at a slightly higher fraction of sites.

- **Mean R² strongly negative for both models.** The mean R² across the 159-site daily cohort is
  −0.30 for SWIM and −0.69 for SSEBop, driven by a handful of sites with extremely negative R²
  values (e.g., US-xJR, US-xNW). Median is the appropriate aggregate for this heterogeneous network,
  but the heavy tail of poor-performing sites indicates that neither model generalizes well to every
  flux environment without site-specific diagnosis.

- **Spatial generalization untested.** SWIM is calibrated against SSEBop ETf and validated against
  flux tower ET — two fully independent data streams. However, the 8 parameters are tuned per site,
  so performance at locations outside the 159-site calibration network remains untested. Whether
  the calibrated parameter distributions transfer to ungauged sites (e.g., via regionalization on
  soil or land cover attributes) is an open question.

---

# Example 5 Results Overview

## Study Design

- 59 US cropland flux tower sites (1 site excluded for data quality), calibration period 1995–2025.
- Same 8 soil/vegetation parameters per site as Example 4, calibrated with PEST++ IES (200
  realizations, 3 iterations) against the mean ETf of a 6-model OpenET ensemble: SSEBop, SIMS,
  geeSEBAL, eeMETRIC, PT-JPL, and DisALEXI, all derived from Landsat.
- Validated against energy-balance-corrected flux tower ET (ET_corr). Benchmark comparison is
  against the Volk 3x3 OpenET daily ET extractions (actual ET from the same 6 models plus their
  ensemble mean), which are fully independent of the container-stored ETf used for calibration.
- Paired evaluation: SWIM and the OpenET ensemble scored on the identical set of valid days or
  months at each site.
- 81,393 total paired daily observations across all sites; median 1,064 paired days per site.

## Relationship to Example 4

Example 5 tests whether calibrating against an ensemble of ET models rather than a single model
improves performance on croplands — the land cover class where remote sensing ET is most mature.
The site set is a cropland-only subset (59 sites) of the broader 159-site Example 4 network.
Key differences: (1) 6-model ensemble calibration target vs single SSEBop, (2) croplands only vs
all land cover, (3) validation benchmark is the Volk 3x3 OpenET product (actual ET) rather than
interpolated SSEBop ETf × ETo.

## Daily ET (58 paired sites)

- SWIM median R² = 0.65 vs ensemble median R² = 0.57. SWIM outperforms the ensemble at 71% of
  sites (41/58).
- SWIM median RMSE = 1.14 mm/day vs ensemble 1.19 mm/day.
- SWIM is nearly unbiased (median bias −0.01 mm/day). The ensemble also has low bias (median
  −0.09 mm/day).
- 90% of sites have positive SWIM R² (52/58) vs 78% for the ensemble (45/58).

## Daily ET — SWIM vs Individual OpenET Models

SWIM outperforms every individual OpenET model by a wide margin at the daily timescale:

- vs SSEBop (median R² 0.38): SWIM wins 88% of sites (51/58)
- vs geeSEBAL (median R² 0.43): SWIM wins 88% of sites (51/58)
- vs eeMETRIC (median R² 0.35): SWIM wins 88% of sites (51/58)
- vs DisALEXI (median R² 0.45): SWIM wins 84% of sites (49/58)
- vs PT-JPL (median R² 0.55): SWIM wins 81% of sites (47/58)
- vs SIMS (median R² 0.51): SWIM wins 79% of sites (34/43 with valid data)

The ensemble mean (median R² 0.57) is the strongest individual comparator, outperforming any
single model, but SWIM still beats it at 71% of sites.

## Monthly ET (33 paired sites)

- SWIM median R² = 0.85 vs ensemble median R² = 0.86. Performance is essentially equivalent at
  the monthly timescale. SWIM wins at 52% of sites (17/33).
- SWIM median RMSE = 21.5 mm/month vs ensemble 19.6 mm/month. The ensemble has slightly lower
  RMSE.
- SWIM is dramatically less biased: median bias +0.3 mm/month vs ensemble −6.7 mm/month.
- 100% of sites have positive SWIM monthly R² (33/33) vs 97% for the ensemble (32/33).

## Monthly ET — SWIM vs Individual OpenET Models

At the monthly timescale, SWIM still outperforms most individual models but the margin narrows
against the top-performing ones:

- vs SSEBop (median R² 0.71): SWIM wins 88% (29/33)
- vs geeSEBAL (median R² 0.71): SWIM wins 91% (30/33)
- vs eeMETRIC (median R² 0.76): SWIM wins 82% (27/33)
- vs PT-JPL (median R² 0.85): SWIM wins 76% (25/33)
- vs DisALEXI (median R² 0.77): SWIM wins 64% (21/33)
- vs SIMS (median R² 0.86): SWIM wins 64% (21/33)

SIMS and PT-JPL are the most competitive individual models at the monthly timescale.

## SWIM Weaknesses (Example 5)

- **Monthly performance converges with the ensemble.** SWIM's daily advantage (median R² 0.65 vs
  0.57) largely disappears at the monthly timescale (0.85 vs 0.86). The ensemble's slightly higher
  monthly median R² and lower monthly RMSE suggest that at seasonal aggregations the direct sampling
  advantage of 6 independent satellite retrievals can match or exceed what a calibrated process
  model achieves. SWIM's value-add at the monthly scale is primarily bias correction, not variance
  explained.

- **Ensemble bias advantage at the daily step.** While both models have small daily bias, the
  ensemble's median bias (−0.09 mm/day) is slightly closer to zero than SWIM's (−0.01 mm/day) at
  the daily level — though this reverses dramatically at the monthly level where SWIM's bias is
  +0.3 mm/month vs the ensemble's −6.7 mm/month. The ensemble's monthly dry bias accumulates from
  small daily errors that partially cancel in SWIM.

- **Smaller paired monthly cohort.** Only 33 of 59 sites have sufficient paired monthly data,
  compared to 58 daily. The monthly results are therefore less robust and may not be representative
  of the full network. The loss of 25 sites between daily and monthly evaluation reflects the
  stringent 20-valid-day-per-month requirement interacting with the shorter Volk extraction period.

- **SIMS and DisALEXI narrow the gap.** SWIM's monthly win rate against SIMS and DisALEXI is only
  64%, considerably lower than the 88–91% win rates against SSEBop and geeSEBAL. The strongest
  individual OpenET models approach SWIM's performance at the monthly scale, suggesting diminishing
  returns from inverse modeling when the benchmark satellite product is already well-calibrated for
  croplands.

- **Cropland-only scope.** Example 5 results apply only to croplands. The ensemble calibration
  approach has not been tested on the land cover classes where Example 4 shows SWIM's largest
  advantages (shrublands, evergreen forests) or its most persistent weaknesses (wetlands,
  grasslands).

---

# Study 2 Ablation Results: Spread-Based vs Fixed-SD Weighting

## Experiment Design

- Same 59 cropland flux tower sites as Example 5 (MB_Pch excluded), same container, same
  calibration period (1995–2025), same 6-model ensemble mean ETf target.
- Same 8 parameters per site, PEST++ IES with 200 realizations, 3 iterations, 40 workers.
- Only the PEST observation weighting changes between runs:
  - **E1 (spread)**: `weight = obsval / (member_std + 0.1)` — dates where the 6 models agree
    receive higher weight.
  - **E2 (fixed_sd)**: `weight = obsval / 0.33` — all dates receive magnitude-only weighting
    regardless of inter-model spread.
- Both runs use a common eligibility mask: capture dates with fewer than 2 member ETf values
  receive zero weight in both E1 and E2, so the observation set is identical.
- 20,327 ETf capture-date observations per run (862 per site median), 851 eligible per site
  median after the min-members filter.
- Validated against energy-balance-corrected flux tower ET using Volk 3x3 OpenET daily ET as the
  benchmark (same as canonical Example 5 evaluation).

## Daily ET (58 paired sites)

- E1 (spread) median R² = 0.67 vs E2 (fixed_sd) median R² = 0.59.
- E1 median RMSE = 1.12 mm/day vs E2 1.17 mm/day.
- E1 wins at 59% of sites (35/59).
- Both runs have small bias: E1 median −0.11 mm/day, E2 median +0.03 mm/day.

## Monthly ET (40 paired sites)

- E1 median R² = 0.82 vs E2 median R² = 0.77.
- E1 median RMSE = 22.1 mm/month vs E2 25.7 mm/month.
- E1 win rate drops to 47% (20/43) — essentially a coin flip at the monthly timescale.
- E1 has a small dry bias (−2.8 mm/month); E2 has a small wet bias (+1.2 mm/month).

## Interpretation

Spread-based weighting produces a clear improvement at the daily timescale: +0.08 median R² and
5% lower RMSE. The mechanism is consistent with the Study 2 hypothesis — down-weighting
high-spread (high-disagreement) capture dates directs parameter updates toward dates where the
ensemble signal is most reliable, yielding tighter calibration.

At the monthly timescale the median R² advantage persists (+0.05) but the win rate is 47%,
meaning E1 wins by larger margins at the sites it wins but loses more often at the remainder.
This is consistent with the broader Example 5 finding that monthly aggregation reduces the
marginal value of daily-scale calibration refinements.

## Runtime

Both runs took ~109 minutes (40 workers, 200 realizations). Spread-based weighting adds no
meaningful compute cost.

## Weaknesses and Caveats

- **Monthly win rate is a coin flip.** Despite higher median R², E1 does not win at more sites
  than E2 at the monthly timescale. The spread signal helps some sites substantially but hurts
  others slightly — possibly sites where high-spread dates happen to carry useful information
  that gets down-weighted.

- **Negative-result framing remains viable.** If the manuscript requires a majority win rate at
  both timescales to claim spread weighting "improves" calibration, the monthly result does not
  clear that bar. The honest framing is that spread weighting improves daily skill at the median
  and is neutral at the monthly timescale.

- **Phi convergence needs further inspection.** The phi.meas.csv values suggest phi increased
  from prior to posterior for both runs, which is atypical for IES. This likely reflects the
  per-realization phi structure rather than a convergence failure, but the phi summary should be
  verified against the actual iteration-level aggregation before reporting convergence rates.

- **No spread-stratified evaluation yet.** The most direct mechanism test — evaluating whether
  E1's gains concentrate on dates with high historical ensemble spread — has not been run. This
  is a post-hoc analysis of the existing outputs and does not require re-calibration.
