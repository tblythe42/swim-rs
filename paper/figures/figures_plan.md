# Figures Plan

Target: 8 main figures, 3-4 supplementary. RSE norm is 6-10 main figures
with dense multi-panel layouts.

---

## Main Figures

### Fig 1. Study Design and Site Map

**Panels:**
(a) Map of 160 Ex4 sites colored by LULC class (croplands, grasslands,
shrublands, evergreen forests, mixed forests, wetland/riparian), with the
60-site Ex5 cropland subset highlighted by marker style.
(b) SWIM modeling chain schematic: meteorology + NDVI → FAO-56 dual Kc
soil water balance → ET, with Landsat ETf calibration loop (PEST++ IES)
shown as a feedback arrow.

**Purpose:** Orient the reader to what the system is, where it was tested,
and how calibration works. Every RSE paper opens with this.

**Data sources:** Shapefile at `/data/ssd1/swim/4_Flux_Network/data/gis/flux_fields.shp`
(160 sites with lc_class), TOML configs for model structure.

---

### Fig 2. Calibration Mechanics

**Panels:**
(a) Phi convergence across PEST++ IES iterations for Ex4 (160 sites) and
Ex5 Run 11 (60 sites). Line plot, x = iteration, y = mean phi.
(b) Prior vs posterior parameter distributions for 2-3 key parameters
(aw, ndvi_k, mad) faceted by land cover class. Violin or ridge plots.

**Purpose:** Show that the inversion converged and learned physically
plausible parameters. Reviewers will want evidence that 8 parameters per
site are identifiable, not just overfitting.

**Data sources:** `4_Flux_Network.phi.meas.csv`, `5_Flux_Ensemble.phi.meas.csv`,
`.3.par.csv` files in results directories, prior distributions from
`pest_builder.py`.

---

### Fig 3. Daily ET Time Series at Representative Sites

**Panels:** 4 subplots, one per site:
(a) High-performing cropland (e.g., US-Ne1 or US-Tw3)
(b) Grassland (e.g., US-ARM)
(c) Evergreen forest (e.g., US-Blo)
(d) Poorly performing wetland (e.g., US-Sne)

Each panel: SWIM ET (line), OpenET ensemble or SSEBop ET (line), flux
tower ET (points), shared y-axis (mm/day), x-axis = date spanning 2-3
years of overlap.

**Purpose:** Readers need to see actual time series, not just summary
statistics. Shows seasonal dynamics, inter-annual variability, and where
SWIM tracks vs misses.

**Data sources:** Forward-run output from `evaluate.py`, flux tower daily
files, OpenET Volk 3x3 extractions.

---

### Fig 4. Daily ET Accuracy Summary

**Panels:**
(a) SWIM ET vs flux tower ET, pooled scatter for the 45-site matched
cropland cohort (Ex5). Color by site or density hexbin. 1:1 line, R²,
RMSE, bias annotated.
(b) OpenET ensemble ET vs flux tower ET, same sites, same format.
(c) Histogram or violin of paired site-level R² deltas (SWIM minus
ensemble) across the 45 sites. Vertical line at zero.

**Purpose:** Headline accuracy figure for the cropland comparison. Panel
(c) shows the distribution of the SWIM advantage/disadvantage at the
site level.

**Data sources:** `evaluation_metrics.csv` from Ex5 results.

---

### Fig 5. Monthly ET Performance by Model (KEY FIGURE)

**Layout:** Dot plot or grouped bar chart. X-axis = model (SWIM, ensemble,
PT-JPL, DisALEXI, SIMS, SSEBop, eeMETRIC, geeSEBAL). Three sub-panels
stacked vertically:
(a) Median R²
(b) Mean RMSE (mm/month)
(c) Mean bias (mm/month)

33-site matched monthly cohort from Ex5 Run 11. Error bars from
bootstrapped 95% CIs.

**Purpose:** The money figure. Shows SWIM competing with 6 RS ET
algorithms and the ensemble on their own validation framework. The bias
panel is where SWIM's advantage is most visible (+1.5 vs -5.9 mm/month
for ensemble).

**Data sources:** `evaluation_monthly_metrics.csv` from Ex5 results.

---

### Fig 6. Stratified Performance by Land Cover (NOVELTY FIGURE)

**Layout:** 6 facets (one per LULC class), each showing box plots of
site-level R² for SWIM vs SSEBop. Monthly R², Ex4 160-site evaluation.

Alternative layout: grouped dot plot with LULC on y-axis, R² on x-axis,
SWIM and SSEBop as paired points per class with n annotated.

**Panels/classes:**
- Croplands (n=51)
- Grasslands (n=29)
- Shrublands (n=28)
- Evergreen Forests (n=18)
- Mixed Forests (n=14)
- Wetland/Riparian (n=9)

**Purpose:** The generalizability figure. Shows where SWIM wins
(evergreen 89%, grasslands 72%) and where it loses (wetland 44%).
Demonstrates that multi-LULC evaluation is not just diluted cropland.

**Data sources:** `evaluation_monthly_metrics.csv` from Ex4 results,
LULC from shapefile.

---

### Fig 7. Site-Level Win Rate Map or Ranked Delta Chart

**Option A — Map:** 160 sites plotted geographically, marker color =
SWIM wins (blue) or SSEBop wins (red) on monthly R², marker size =
magnitude of R² delta. Shows geographic patterns if any.

**Option B — Lollipop chart:** Sites ranked by monthly R² delta
(SWIM - SSEBop), horizontal lollipops colored by LULC class. Vertical
line at zero. Compact way to show the full distribution.

**Purpose:** Complements Fig 6 by showing the site-level detail.
Reviewers can see that the win rate is not driven by a few outliers.

**Data sources:** Same as Fig 6 plus site coordinates from shapefile.

---

### Fig 8. Seasonal Cumulative ET and Bias Accumulation

**Panels:**
(a) Cumulative ET (mm) over a representative growing season at 3-4
sites, lines for SWIM, ensemble, and flux tower. Shows how daily bias
compounds.
(b) Distribution of seasonal bias (mm/season) across the 33-site
monthly cohort for SWIM vs ensemble vs individual models. Box or violin.

**Purpose:** Translates daily bias statistics into the units water
managers use (mm/season, acre-feet/field). Makes the operational
relevance argument concrete. SWIM's +9 mm/season vs ensemble's
-35 mm/season is a 44 mm difference in consumptive use reporting.

**Data sources:** Daily ET time series from `evaluate.py` output,
growing season windows defined per site.

**Note:** If the controlled weighting experiment (TODO_EXPERIMENTS.md)
is completed before submission, this figure could be replaced by the
ensemble-derived vs standard weighting comparison. Decide based on
which result is stronger.

---

## Supplementary Figures

### Fig S1. ETf Fit at Landsat Capture Dates

Scatter of SWIM-predicted ETf vs observed Landsat ETf at capture dates
for a subset of sites. Shows calibration quality (how well the model
reproduces the signal it was trained on), not validation.

**Data sources:** `evaluation_etf_metrics.csv`.

---

### Fig S2. Parameter Identifiability

(a) Heatmap of posterior parameter CV (coefficient of variation) by
parameter and LULC class. Low CV = well-constrained, high CV =
prior-dominated.
(b) Parameter correlation matrix from the posterior ensemble.

**Purpose:** Supports the claim that 8 parameters per site are
identifiable and not overfitting.

**Data sources:** `.3.par.csv` posterior ensembles.

---

### Fig S3. Phi Decomposition by Observation Type

Stacked bar or area chart showing contribution of ETf vs SWE observations
to total phi across iterations. Shows that ETf dominates the objective
function.

**Data sources:** PEST++ diagnostics from `build_pest`.

---

### Fig S4. Ensemble vs Single-Model Target (Confounded)

Paired comparison of Ex4 (SSEBop target) vs Ex5 (ensemble target) on
60 matched cropland sites, with confound caveats in caption. Presented
as supplementary until the controlled experiment is completed.

(a) R² delta distribution (Ex5 - Ex4)
(b) Site-level scatter

**Data sources:** `evaluation_metrics.csv` from Ex4 and Ex5.

---

## Production Notes

- All figures should use consistent color schemes: one palette for LULC
  classes, one for models (SWIM vs OpenET members).
- RSE requires figures at 300 dpi minimum, vector preferred for line art.
- Multi-panel figures should use (a), (b), (c) labels in top-left of each
  panel.
- Every figure caption must state n (sites), time period, and data source.
- Bootstrap CIs (95%) on all summary statistics where sample size permits.
