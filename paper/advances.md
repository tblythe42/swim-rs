# Key Advances for RSE Submission

What this paper demonstrates that the literature does not yet contain,
and what we need to execute cleanly to make each claim stick.

---

## 1. Ensemble inverse calibration of a soil water model against satellite ETf at scale

Prior work inverts one parameter at one site (Campos 2016). We invert 8
parameters per site at 160 sites using PEST++ IES with 200-member ensembles.
This is the first application of formal ensemble parameter estimation to the
NDVI-Kc / ETf-driven soil water balance at continental scale.

**What we need to show:**
- Phi convergence across iterations (already have for Ex4 and Ex5)
- Parameter identifiability: not all 8 parameters are well-constrained
  everywhere. Report which parameters are learned vs prior-dominated, and
  how that varies by land cover.
- That the calibrated parameters are physically plausible (distributions vs
  literature soil/vegetation values).

---

## 2. A process model that competes with energy-balance RS ET algorithms

SWIM is not an ET algorithm — it is a soil water balance model that produces
ET as an output. Yet on the 45-site matched cropland cohort, SWIM daily R²
(0.654) exceeds every individual OpenET model except the 6-model ensemble
(0.708). At the monthly scale, SWIM R² (0.808) exceeds even the ensemble
(0.799). No process-based soil water model has been benchmarked head-to-head
against the full OpenET suite at this scale.

**What we need to show:**
- The comparison is fair: same flux tower validation data, same time periods,
  same extraction footprints (Volk 3x3).
- SWIM is the least biased model (+0.1 mm/day daily, +1.5 mm/month monthly)
  — this matters for cumulative water budgets.
- Explicitly report where SWIM loses (vs ensemble daily R², vs SIMS on some
  sites) so reviewers trust the comparison.

---

## 3. Multi-LULC generalizability beyond croplands

OpenET was designed for and validated primarily on croplands (Volk 2024 shows
degraded accuracy on shrublands and forests). SWIM is calibrated and evaluated
across 6 land cover classes (croplands, grasslands, shrublands, evergreen
forests, mixed forests, wetland/riparian) at 160 sites. SWIM wins 65% of
sites daily and 70% monthly against SSEBop across all land covers.

**What we need to show:**
- Stratified performance tables by land cover (already computed).
- Honest treatment of where SWIM fails: wetland/riparian (missing groundwater
  subsidy) and shrublands (both models poor).
- That the multi-LULC result is not just a diluted cropland signal — the
  non-cropland classes individually show SWIM advantages (evergreen forests
  89% win rate, grasslands 70%).

---

## 4. The value of calibration target architecture (single-model vs ensemble)

Example 4 calibrates against SSEBop alone. Example 5 calibrates against a
6-model ensemble mean with inter-model-spread weighting. The paired comparison
on the same 60 cropland sites shows the ensemble target marginally improves
monthly R² (+0.037) but the effect is small relative to the confounds. The
controlled experiment (TODO_EXPERIMENTS.md) will isolate the weighting effect.

**What we need to show:**
- The controlled experiment (ensemble mean target with vs without spread-derived
  weights) to cleanly attribute value to uncertainty-informed weighting.
- If the effect is small, that is still a publishable finding: it means the
  ensemble mean target itself is the source of value, not the uncertainty
  weighting. Either outcome is informative.

---

## 5. Temporal generalization: calibration window vs prediction period

SWIM in Example 5 is calibrated against ETf observations from 2016-2025 but
runs the full water balance from 1995-2025. The parameters learned from 9
years of Landsat ETf generalize to reproduce soil water dynamics over a 31-year
period validated against flux towers with observations spanning the full record.

**What we need to show:**
- That flux-validated performance is stable across time (pre-2016 vs post-2016
  subsets, if sufficient flux data exists in both windows).
- That this temporal generalization is a practical advantage: a short Landsat
  ETf calibration window produces a model usable for long-term water budget
  reconstruction.

---

## 6. Bias advantage for cumulative water budgets

Every OpenET model underestimates ET (negative bias). SWIM is the only model
with near-zero or slightly positive bias (+0.1 mm/day daily, +1.5 mm/month
monthly). Over a growing season, OpenET ensemble bias of -5.9 mm/month
accumulates to ~35 mm of underestimated consumptive use. SWIM's +1.5 mm/month
accumulates to ~9 mm. For water rights administration and irrigation accounting,
this bias difference is operationally significant.

**What we need to show:**
- Seasonal/annual cumulative ET comparisons (not just daily/monthly statistics).
- That the bias advantage is consistent across sites, not driven by a few
  outliers.
- Frame this in terms of what water managers care about: acre-feet per field
  per season, error in consumptive use reporting.

---

## 7. Computational cost transparency

SWIM calibration for 60 sites (200 realizations, 3 iterations) completes in
109 minutes on 40 cores. This is negligible compared to the cost of running
6 energy balance models on Landsat imagery via Google Earth Engine. A reviewer
will ask whether the calibration overhead undermines the operational value.

**What we need to show:**
- Wall-clock time and CPU-hours for each experiment.
- Comparison to the implicit cost of generating the OpenET ensemble (which
  requires running 6 models on every Landsat scene over the full archive).
- That recalibration is infrequent: once parameters are estimated, SWIM runs
  as a forward model with new meteorology and NDVI inputs, no re-inversion
  needed.

---

## What could sink the paper

- **Unfair comparison.** If reviewers perceive that SWIM is evaluated on
  different data or time windows than OpenET, the head-to-head loses
  credibility. The Volk 3x3 extraction must be identical.
- **Overstating cropland results for a "generalizable" model.** The multi-LULC
  story is strong but the non-cropland sample sizes are small (9-29 sites per
  class). Acknowledge statistical limitations.
- **Ignoring where SWIM fails.** Wetland/riparian is a clear structural
  limitation (no groundwater). If we bury it, reviewers will find it. Lead
  with it as a known boundary condition.
- **No controlled experiment for ensemble vs single-model targets.** The
  existing Ex4 vs Ex5 comparison is confounded. The TODO experiment must be
  run before submission or the claim must be dropped.
