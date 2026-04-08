# Parameter Transfer: Study 1 → Study 3

Date: 2026-04-07
Scope: Statistics of the Example 4 (Study 1) calibrated parameter set, derivation of LULC-specific defaults, and comparison with Example 5 (Study 2) cropland parameters.
Status: Complete. Provides the empirical basis for LULC defaults and regularization priors.

## Source Calibration: Example 4

- **Sites:** 159 (of 160 in shapefile; 1 dropped during calibration)
- **LULC classes:** 6 (Croplands 59, Grasslands 30, Shrublands 29, Evergreen Forests 18, Mixed Forests 14, Wetland/Riparian 9)
- **Calibration method:** PEST++ IES, 197 realizations, 3 iterations
- **ETf target:** SSEBop NHM (1987–2025)
- **Meteorology:** GridMET
- **Soils:** SSURGO
- **Parameters:** 8 per site (aw, ndvi_k, ndvi_0, mad, ks_alpha, kr_alpha, swe_alpha, swe_beta)

## Between-LULC Separation (ANOVA)

One-way ANOVA on 197-realization median parameters across 6 LULC classes:

| Parameter | F-statistic | p-value | Discrimination |
|---|---:|---|---|
| `mad` | 25.5 | < 0.001 | Strong |
| `aw` | 12.3 | < 0.001 | Strong |
| `ndvi_0` | 9.7 | < 0.001 | Strong |
| `ks_alpha` | 6.4 | < 0.001 | Strong |
| `ndvi_k` | 4.7 | < 0.001 | Strong |
| `kr_alpha` | 1.6 | 0.157 | None |

Five of six soil-vegetation parameters discriminate significantly by LULC. `kr_alpha` does not — it is driven by soil texture and climate, not vegetation type.

## Within-LULC Parameter Statistics

### Croplands (n = 59)

| Parameter | Median | Mean | Std | Min | Max | Q25 | Q75 | Ens. IQR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| aw (mm) | 361 | 320 | 86 | 107 | 400 | 245 | 400 | 47 |
| ndvi_k | 4.85 | 5.22 | 2.23 | 3.00 | 12.79 | 3.63 | 5.69 | 0.80 |
| ndvi_0 | 0.516 | 0.495 | 0.120 | 0.180 | 0.698 | 0.453 | 0.570 | 0.031 |
| mad | 0.125 | 0.212 | 0.140 | 0.100 | 0.546 | 0.107 | 0.314 | 0.018 |
| ks_alpha | 0.390 | 0.458 | 0.261 | 0.012 | 1.000 | 0.291 | 0.577 | 0.340 |
| kr_alpha | 0.104 | 0.169 | 0.193 | 0.014 | 1.000 | 0.068 | 0.185 | 0.043 |
| swe_alpha | 0.337 | 0.351 | 0.063 | 0.271 | 0.528 | 0.305 | 0.374 | 0.461 |
| swe_beta | 1.496 | 1.501 | 0.061 | 1.391 | 1.670 | 1.455 | 1.541 | 0.797 |

Cropland `ndvi_0` and `mad` are the tightest (CV 0.24, 0.66). The bimodal `mad` distribution (low for irrigated, high for dryland) inflates its CV; the median 0.125 reflects the irrigated majority.

### Grasslands (n = 30)

| Parameter | Median | Mean | Std | Min | Max | Q25 | Q75 | Ens. IQR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| aw (mm) | 327 | 303 | 94 | 118 | 400 | 231 | 399 | 36 |
| ndvi_k | 5.32 | 6.20 | 3.89 | 3.00 | 20.00 | 3.47 | 6.52 | 1.03 |
| ndvi_0 | 0.364 | 0.361 | 0.208 | 0.100 | 0.797 | 0.171 | 0.516 | 0.037 |
| mad | 0.351 | 0.354 | 0.048 | 0.300 | 0.469 | 0.309 | 0.379 | 0.066 |
| ks_alpha | 0.363 | 0.416 | 0.273 | 0.021 | 0.973 | 0.194 | 0.581 | 0.268 |
| kr_alpha | 0.121 | 0.211 | 0.261 | 0.011 | 1.000 | 0.032 | 0.288 | 0.075 |

Grassland `mad` is extremely tight (CV=0.13, std=0.048) — the strongest within-LULC constraint in the dataset. `ndvi_0` is wide (CV=0.57), reflecting the diversity from xeric shortgrass to mesic tallgrass.

### Shrublands (n = 29)

| Parameter | Median | Mean | Std | Min | Max | Q25 | Q75 | Ens. IQR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| aw (mm) | 161 | 189 | 72 | 100 | 376 | 138 | 220 | 55 |
| ndvi_k | 7.62 | 7.66 | 2.96 | 3.00 | 17.40 | 5.58 | 9.63 | 4.07 |
| ndvi_0 | 0.267 | 0.300 | 0.156 | 0.100 | 0.633 | 0.174 | 0.411 | 0.048 |
| mad | 0.477 | 0.478 | 0.094 | 0.300 | 0.779 | 0.440 | 0.503 | 0.128 |
| ks_alpha | 0.576 | 0.585 | 0.226 | 0.064 | 1.000 | 0.460 | 0.714 | 0.504 |
| kr_alpha | 0.194 | 0.251 | 0.195 | 0.017 | 0.670 | 0.081 | 0.376 | 0.138 |

Shrublands have the lowest `aw` (161 mm, shallow/sparse roots) and highest `ndvi_k` (7.62, sharp ET threshold). The wide ensemble IQR for `ndvi_k` (4.07) and `ks_alpha` (0.504) indicates these parameters are poorly constrained for arid systems — regularization priors should be correspondingly loose.

### Evergreen Forests (n = 18)

| Parameter | Median | Mean | Std | Min | Max | Q25 | Q75 | Ens. IQR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| aw (mm) | 380 | 336 | 80 | 154 | 400 | 282 | 400 | 28 |
| ndvi_k | 3.34 | 4.26 | 1.95 | 3.00 | 9.97 | 3.00 | 4.67 | 0.38 |
| ndvi_0 | 0.478 | 0.464 | 0.141 | 0.194 | 0.657 | 0.441 | 0.575 | 0.050 |
| mad | 0.371 | 0.423 | 0.138 | 0.300 | 0.800 | 0.315 | 0.496 | 0.051 |
| ks_alpha | 0.577 | 0.652 | 0.354 | 0.028 | 1.000 | 0.432 | 1.000 | 0.078 |
| kr_alpha | 0.070 | 0.110 | 0.115 | 0.010 | 0.469 | 0.027 | 0.166 | 0.037 |

Evergreen forests have very tight `ndvi_k` posteriors (ensemble IQR 0.38, CV 0.46) clustered near the lower bound — reflecting the low, stable NDVI of conifer canopies. `ks_alpha` is high (median 0.577), meaning forests sustain transpiration longer into drought. The tight ensemble IQR for `ks_alpha` (0.078) makes this a well-identified parameter for forest regularization.

### Mixed Forests (n = 14)

| Parameter | Median | Mean | Std | Min | Max | Q25 | Q75 | Ens. IQR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| aw (mm) | 368 | 347 | 67 | 165 | 400 | 333 | 400 | 36 |
| ndvi_k | 5.15 | 5.38 | 1.69 | 3.00 | 9.01 | 4.42 | 6.17 | 0.80 |
| ndvi_0 | 0.565 | 0.541 | 0.119 | 0.286 | 0.710 | 0.499 | 0.619 | 0.030 |
| mad | 0.384 | 0.396 | 0.085 | 0.300 | 0.528 | 0.322 | 0.468 | 0.050 |
| ks_alpha | 0.975 | 0.795 | 0.281 | 0.210 | 1.000 | 0.699 | 1.000 | 0.104 |
| kr_alpha | 0.101 | 0.155 | 0.133 | 0.019 | 0.409 | 0.059 | 0.205 | 0.060 |

Mixed forests have the tightest within-LULC clustering overall: lowest CV for `aw` (0.19), `ndvi_0` (0.22), and `mad` (0.21) of any class. `ks_alpha` converges near 1.0 (linear stress, no early shutdown) — consistent with deep-rooted forest systems.

### Wetland/Riparian (n = 9)

| Parameter | Median | Mean | Std | Min | Max | Q25 | Q75 | Ens. IQR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| aw (mm) | 320 | 265 | 108 | 120 | 400 | 176 | 332 | 35 |
| ndvi_k | 4.11 | 7.87 | 5.99 | 3.00 | 18.17 | 3.00 | 11.81 | 0.69 |
| ndvi_0 | 0.338 | 0.354 | 0.179 | 0.105 | 0.654 | 0.206 | 0.493 | 0.046 |
| mad | 0.343 | 0.366 | 0.146 | 0.100 | 0.565 | 0.302 | 0.468 | 0.046 |
| ks_alpha | 0.264 | 0.324 | 0.285 | 0.047 | 1.000 | 0.139 | 0.347 | 0.170 |
| kr_alpha | 0.072 | 0.123 | 0.142 | 0.015 | 0.430 | 0.035 | 0.118 | 0.051 |

Wetland/Riparian is the least coherent class — `ndvi_k` has CV 0.76 and a bimodal distribution (half at lower bound, half at 10+). These sites lack the groundwater subsidy term that their water balance requires, forcing other parameters to compensate unpredictably. This class should be excluded from regularization priors or given very loose constraints.

## Boundary Hits (Example 4 vs Example 6)

| Parameter | Ex4 lo | Ex4 hi | Ex6 lo | Ex6 hi | Notes |
|---|---:|---:|---:|---:|---|
| aw (100–400) | 1% | 27% | 0% | 35% | Ex6 pushes aw higher to sustain ET against biased targets |
| ndvi_k (3–20) | 17% | 1% | 62% | 2% | Ex6 massively constrained — 3.6× worse than Ex4 |
| ndvi_0 (0.1–0.8) | 2% | 1% | 8% | 0% | Mild |
| mad (0.1–0.8) | 6% | 1% | 0% | 2% | — |
| ks_alpha (0.01–1.0) | 0% | 14% | 0% | 29% | Ex6 doubled; pushing to no-stress to match high ETf |
| kr_alpha (0.01–1.0) | 1% | 2% | 0% | 8% | Mild |

The Ex4 calibration has far fewer boundary hits, confirming that SSEBop provides a less biased calibration target. The Ex6 boundary pile-up is a direct consequence of PT-JPL overestimation.

## Cropland Parameter Comparison: Example 4 vs Example 5

Example 4 calibrated against SSEBop NHM; Example 5 calibrated against the OpenET 6-model ensemble. Both are cropland sites in CONUS.

| Parameter | Ex4 (n=59) Median | Ex4 Std | Ex5 (n=9) Median | Ex5 Std | Δ Median | Consistent? |
|---|---:|---:|---:|---:|---:|---|
| aw (mm) | 361 | 86 | 202 | 86 | -159 | **No** — Ex5 much lower |
| ndvi_k | 4.85 | 2.23 | 8.88 | 1.14 | +4.03 | **No** — Ex5 much steeper |
| ndvi_0 | 0.516 | 0.120 | 0.545 | 0.033 | +0.029 | **Yes** — within 1 Std |
| mad | 0.125 | 0.140 | 0.115 | 0.016 | -0.010 | **Yes** — nearly identical |
| ks_alpha | 0.390 | 0.261 | 0.280 | 0.190 | -0.110 | **Yes** — within 1 Std |
| kr_alpha | 0.104 | 0.193 | 0.334 | 0.137 | +0.230 | **No** — Ex5 3× higher |

### Interpretation

**Consistent parameters (ndvi_0, mad, ks_alpha):** These three are robust to the choice of ETf target and can be confidently transferred across studies. `ndvi_0` (sigmoid midpoint) and `mad` (depletion tolerance) encode crop physiology that is independent of the ET algorithm. These are the strongest candidates for global priors.

**Equifinal trade-off (aw, ndvi_k):** Ex5's lower aw (202 vs 361) pairs with higher ndvi_k (8.88 vs 4.85). These two parameters are negatively correlated in the posterior — a shallower soil profile (low aw) paired with a steeper Kcb curve (high ndvi_k) produces the same seasonal ET trajectory as a deeper profile with a gentler curve. The individual values are less portable than the LULC-relative structure. For regularization, these should use a wider prior or a joint covariance constraint.

**Soil evaporation (kr_alpha):** Not LULC-dependent per ANOVA and not consistent across examples. Should use a single global default (~0.11 from Ex4) with minimal regularization penalty.

## Derivation of LULC Defaults

The `lulc_global_params.json` used for Study 3 was derived as follows:

1. **Start from Ex4 posteriors:** Load the 197-realization × 1,272-parameter ensemble from `4_Flux_Network.3.par.csv`.

2. **Per-site median:** For each site, take the median parameter value across the 197 realizations. This is robust to outlier realizations from early iterations that may not have converged.

3. **Group by LULC:** Assign each site to its MODIS land cover class from the Ex4 shapefile. The 6 Ex4 classes (Croplands, Grasslands, Shrublands, Evergreen Forests, Mixed Forests, Wetland/Riparian) cover the major functional types.

4. **Within-class median:** For each LULC class and parameter, take the median of the per-site medians. This produces one 8-parameter vector per LULC class.

5. **Map to Study 3 MODIS classes:** Study 3 uses the full MODIS classification (11 classes observed). The mapping:

    | Study 3 MODIS class | Study 1 source class |
    |---|---|
    | Cropland (12) | Croplands |
    | CropNatMosaic (14) | Croplands |
    | Grassland (10) | Grasslands |
    | Savanna (9) | Grasslands* |
    | OpenShrub (7) | Shrublands |
    | ENF (1) | Evergreen Forests |
    | EBF (2) | Evergreen Forests* |
    | DBF (4) | Mixed Forests* |
    | MixForest (5) | Mixed Forests |
    | WoodySav (8) | Evergreen Forests* |
    | Urban (13) | Grasslands* |

    Classes marked * use the structurally closest analog. Savanna→Grasslands based on similar `mad` and `ks_alpha`; EBF→Evergreen Forests (same canopy structure); DBF→Mixed Forests (deciduous behavior closer to mixed than evergreen); WoodySav→Evergreen Forests (woody canopy structure).

6. **Assign to sites:** Each Study 3 site receives the parameter vector for its mapped LULC class.

## Ensemble Spread as Regularization Prior Width

The ensemble IQR (interquartile range across 197 realizations at a single site) measures how well the calibration data constrain each parameter. Averaged by LULC class, this provides the natural prior width for Tikhonov regularization:

| LULC | N | aw IQR | ndvi_k IQR | ndvi_0 IQR | mad IQR | ks_α IQR | kr_α IQR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Croplands | 59 | 47 | 0.80 | 0.031 | 0.018 | 0.340 | 0.043 |
| Grasslands | 30 | 36 | 1.03 | 0.037 | 0.066 | 0.268 | 0.075 |
| Evergreen For. | 18 | 28 | 0.38 | 0.050 | 0.051 | 0.078 | 0.037 |
| Mixed Forests | 14 | 36 | 0.80 | 0.030 | 0.050 | 0.104 | 0.060 |
| Shrublands | 29 | 55 | 4.07 | 0.048 | 0.128 | 0.504 | 0.138 |
| Wetland/Rip. | 9 | 35 | 0.69 | 0.046 | 0.046 | 0.170 | 0.051 |

**Interpretation for regularization:**

- **Tight priors** (small IQR → strong regularization): `ndvi_0` and `mad` across all classes; `ndvi_k` and `ks_alpha` for Evergreen Forests. The calibration data strongly identify these parameters for these classes — the regularization should heavily penalize deviations.

- **Loose priors** (large IQR → weak regularization): `ndvi_k` and `ks_alpha` for Shrublands; `ks_alpha` for Croplands and Grasslands. These parameters are poorly constrained — the regularization should allow more site-specific flexibility.

- **Global default** (no LULC structure): `kr_alpha` and `swe_alpha/swe_beta` show no LULC signal. Use a single global prior (kr_alpha ~0.11, swe_alpha ~0.34, swe_beta ~1.50) with uniform regularization weight.

## Files

- `/data/ssd1/swim/4_Flux_Network/results/4_Flux_Network.3.par.csv` — Ex4 ensemble posteriors (197 × 1,272)
- `/data/ssd1/swim/5_Flux_Ensemble/results/5_Flux_Ensemble.3.par.csv` — Ex5 ensemble posteriors (20 × 72)
- `/data/ssd1/swim/6_Flux_International/lulc_global_params.json` — derived LULC defaults (241 sites × 8 params)
- `LULC_PARAMETER_DEFAULTS.md` — earlier analysis with the proposed defaults table
- `MODEL_COMPARISON_241SITE.md` — validation of these defaults on the 241-site network
