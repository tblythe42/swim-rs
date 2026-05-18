# SWIM-RS Validation Policy

**Status date:** April 3, 2026

This document defines the canonical validation framework for all SWIM-RS
examples. It supersedes per-example validation policies in
`4_Flux_Network/notes/VALIDATION_POLICY.md`,
`5_Flux_Ensemble/VALIDATION_POLICY.md`, and
`5_Flux_Ensemble/notes/VALIDATION_POLICY.md`, which are retained as
historical context only.

---

## Common Framework

These rules apply to Examples 2, 3, 4, 5, and 6.

### Publication Data Horizon

For publication-track Examples 4, 5, and 6, the default container data
horizon is **through 2025-12-31** for NDVI and ETf.

- This is the default publication policy for Ex4, Ex5, and Ex6.
- A shorter or otherwise different analysis window is allowed only when it is
  explicitly declared in the experiment TOML and the companion experiment
  plan.
- For ablation studies, the controlling experiment-plan document is
  `examples/ablation_plan.md`.

In other words:

- **Container policy:** carry NDVI and ETf through `2025-12-31`.
- **Experiment policy:** a run may use a narrower period, but that narrower
  period must be intentional and documented.

### Flux Data Role

Flux tower ET is used **exclusively for validation**. No flux data may enter
calibration targets, parameter estimation, or model inputs. Calibration
targets are satellite-derived ETf (and optionally SWE from SNODAS). The
suggested manuscript framing is: "We evaluate SWIM as a field-specific
inverse model calibrated to satellite ETf constraints, with independent flux
data used exclusively for validation."

### Site Minimum Data Requirements

A site is included in the validation cohort only if its flux record meets
**all** of the following thresholds:

1. **At least 90 valid daily flux observations** (ET or ET_corr finite).
2. **At least 3 qualifying months**, where a qualifying month has at least
   20 valid daily flux observations.

Sites that fail either criterion are excluded from all headline tables and
figures. They may appear in diagnostic or supplementary outputs if labeled
as below-threshold.

### Paired Comparison Methodology

All headline model-vs-model comparisons use **paired evaluation**:

- **Daily:** SWIM and the reference model (SSEBop, OpenET ensemble, or
  per-model ET) are scored on the **exact same valid days** within each
  site. A day is valid only if flux ET, SWIM ET, and reference ET are all
  finite.
- **Monthly:** SWIM and the reference model are scored on the **exact same
  valid months** within each site. A month is valid only if it contains at
  least 20 valid daily flux observations and both SWIM and reference
  monthly means are finite.

Unpaired or "independent" summaries (where SWIM and the reference are scored
on different day/month sets) are diagnostic only and must not be cited as
headline benchmarks.

### Aggregation and Reporting

- **Aggregate only** across sites with finite metrics for both SWIM and the
  reference model in the paired output.
- **Report with every table or figure:** site count (n), time period,
  evaluation date, and data source.
- **Median over mean** for R2: the mean R2 is dominated by a few
  catastrophic sites with extremely negative values. Report both, but use
  the median as the primary summary statistic for heterogeneous cohorts.
- **Land cover stratification** (where applicable): report per-class and
  all-site aggregates side by side so that weak classes are visible rather
  than hidden in the average.

### Metrics

Standard metrics for all examples:

| Metric | Daily units | Monthly units |
|--------|-------------|---------------|
| R2 (coefficient of determination) | dimensionless | dimensionless |
| RMSE | mm/day | mm/month |
| Bias (mean error, model - observed) | mm/day | mm/month |
| Pearson r | dimensionless | dimensionless |

Win rate (fraction of sites where SWIM R2 > reference R2) is reported for
multi-site examples (4, 5, 6).

### Site Exclusion List

The following sites are excluded from all examples in which they appear,
due to known data quality issues:

- `MB_Pch`

Additional per-example exclusions may be defined in the example-specific
sections below. Any exclusion must state the reason.

### Parameter Files

Always specify the parameter file and container path explicitly in
evaluation commands. Never rely on automatic discovery of `.par.csv` files
in results directories, because multiple iteration files may coexist.

### Deprecated Outputs

Any evaluation outputs generated before March 31, 2026 predate the
paired-comparison policy and site minimum data requirements. They are
retained as historical context only and must not be cited as current
benchmarks.

---

## Example 2: Fort Peck

### Scope

Single-site tutorial. One unirrigated grassland flux tower (US-FPe) in
eastern Montana.

### Configuration

| Setting | Value |
|---------|-------|
| Sites | 1 (US-FPe) |
| Period | 1987-01-01 to 2022-12-31 |
| Calibration target | PT-JPL Landsat ETf (single model) |
| Meteorology | GridMET |
| Soils | SSURGO |
| mask_mode | irrigation |
| runoff_process | cn |
| PEST++ IES | 200 realizations, 3 iterations |

### Validation Reference

SWIM ET is compared against:
- **PT-JPL ET** (interpolated ETf x ETo from Landsat capture dates)
- **Flux tower ET** (energy-balance-corrected `ET_corr` from US-FPe)

Flux data source: `data/US-FPe_daily_data.csv` (Volk et al.).

### Nuances

- **Single site**: win rates and aggregate statistics are not applicable.
  Report site-level R2, RMSE, and bias only.
- **Two comparison modes**: (a) Landsat capture dates only (sparse), where
  both SWIM and PT-JPL have values; (b) full time series, where PT-JPL is
  linearly interpolated between capture dates and SWIM provides daily
  output. Both modes must report n (number of comparison days).
- **Calibration improvement**: the primary narrative is uncalibrated vs
  calibrated SWIM performance, not SWIM vs PT-JPL head-to-head.
- **mask_mode = irrigation**: unlike Examples 4 and 5, this example uses
  irrigation masking because it predates the no_mask policy. This is
  acceptable for a single-site grassland tutorial where the distinction has
  minimal impact.
- **Minimum data threshold**: US-FPe has a multi-decade flux record and
  easily exceeds the 90-day / 3-month minimum.

### Evaluation Workflow

Evaluation is performed in notebook `03_calibrated_model.ipynb`. There is
no standalone `evaluate.py` script for this example.

---

## Example 3: Crane

### Scope

Single-site tutorial. One irrigated alfalfa flux tower (S2) near Crane,
Oregon.

### Configuration

| Setting | Value |
|---------|-------|
| Sites | 1 (S2) |
| Period | 1987-01-01 to 2022-12-31 |
| Calibration target | Ensemble mean of 4 OpenET models |
| Ensemble members | PT-JPL, SIMS, SSEBop, geeSEBAL |
| Meteorology | GridMET |
| Soils | SSURGO |
| mask_mode | irrigation |
| runoff_process | cn |
| PEST++ IES | 20 realizations, 3 iterations |

### Validation Reference

SWIM ET is compared against:
- **OpenET ensemble ET** (mean of 4 models, interpolated ETf x ETo)
- **Flux tower ET** (energy-balance-corrected `ET_corr` from S2)

Flux data source: `data/S2_daily_data.csv`.

### Nuances

- **Single site**: same as Example 2 -- report site-level metrics only, no
  win rates.
- **Two comparison modes**: (a) Landsat capture dates only; (b) full time
  series with interpolated OpenET. Both modes must report n.
- **Reduced ensemble**: uses 4 of 6 OpenET models (no eeMETRIC or
  DisALEXI), unlike Example 5 which uses all 6. This is a tutorial
  limitation, not a methodological choice.
- **Low realization count**: 20 realizations (vs 200 in Examples 4/5) for
  tutorial speed. Uncertainty estimates from this run are illustrative only.
- **mask_mode = irrigation**: same caveat as Example 2. Acceptable for a
  single irrigated site where the mask correctly identifies irrigation
  status.
- **Calibration improvement**: primary narrative is uncalibrated vs
  calibrated, same as Example 2.
- **Minimum data threshold**: S2 has sufficient flux coverage to exceed the
  90-day / 3-month minimum, but the evaluation period (overlapping with
  Landsat captures 2003-2007) is shorter than Example 2.

### Evaluation Workflow

Evaluation is performed in notebook `03_calibrated_model.ipynb`. There is
no standalone `evaluate.py` script for this example.

---

## Example 4: Flux Network

### Scope

Multi-site CONUS evaluation. 160 US flux tower sites across 6 land cover
classes, calibrated against SSEBop ETf.

### Configuration

| Setting | Value |
|---------|-------|
| Sites | 160 (6 LULC classes) |
| Period | 1987-01-01 to 2025-12-31 (publication default) |
| Calibration target | SSEBop NHM ETf (no_mask) |
| Parameters | 8 per site: aw, ndvi_k, ndvi_0, mad, kr_alpha, ks_alpha, swe_alpha, swe_beta |
| PEST++ IES | 200 realizations, 3 iterations |
| Meteorology | GridMET (with static TIF-based ETo correction) |
| Snow | SNODAS |
| Soils | SSURGO |
| mask_mode | none |
| runoff_process | cn |
| refet_type | eto |

### ETf Masking: no_mask Only

Both calibration and validation use **no_mask** (full footprint) SSEBop ETf
exclusively. The TOML sets `mask_mode = "none"`, and the evaluator loads
ETf from `remote_sensing/etf/landsat/ssebop/no_mask`. The irr/inv_irr
mask-switched paths are retained in the container for diagnostic use but
are not part of the canonical pipeline.

### Publication Window Rule

For publication-track Example 4 containers, NDVI and SSEBop NHM ETf should
be carried through `2025-12-31`. If a specific experiment uses a shorter
window, that shorter window must be declared in the Example 4 TOML and in
the governing experiment plan or `examples/ablation_plan.md`.

### Canonical Cohorts

- **Container:** 160 flux sites.
- **Excluded:** `MB_Pch`.
- **Evaluation candidate cohort:** 159 sites after exclusion and site
  minimum data filter (90 days, 3 qualifying months).
- **Daily paired cohort:** sites with finite SWIM and SSEBop metrics on
  identical valid days.
- **Monthly paired cohort:** sites with finite SWIM and SSEBop metrics on
  identical valid months (20 days/month minimum).

### Validation Reference

- **Headline benchmark:** SSEBop NHM no_mask ET (interpolated ETf x ETo
  from container-stored Landsat SSEBop ETf at full footprint).
- **Flux tower ET:** energy-balance-corrected daily ET from 160
  AmeriFlux/FLUXNET stations.

### Land Cover Stratification

| Class | MODIS LC codes | n sites (approx) |
|-------|----------------|-------------------|
| Croplands | 12, 14 | 74 |
| Grasslands | 10 | 22 |
| Shrublands | 6, 7, 8, 9 | 37 |
| Evergreen Forests | 1, 2, 4, 5 | 27 |
| Mixed Forests | 11 | 4 |
| Wetland/Riparian | 13, 16, 17 | 13 |

Report per-class and all-site aggregates side by side.

### Known Limitations

- **Wetland/Riparian:** SWIM's precipitation-driven soil water balance
  cannot reproduce ET driven by shallow groundwater subsidy. These sites
  consistently show negative median R2 and are SWIM's primary weakness.
- **Heavy tails:** mean R2 is strongly negative for both models due to a
  handful of catastrophic sites. Median R2 is the informative aggregate.

### Current Canonical Snapshot (May 17, 2026)

#### Daily ET vs Flux Tower (159 paired sites)

| Model | R2 mean | R2 median | RMSE mean | RMSE median | Bias mean | Bias median |
|-------|---------|-----------|-----------|-------------|-----------|-------------|
| SWIM | -0.299 | 0.467 | 1.151 | 1.009 | -0.026 | 0.017 |
| SSEBop | -0.689 | 0.415 | 1.141 | 1.091 | -0.022 | -0.036 |

SWIM daily win rate: 95/159 = 60%

#### Monthly ET vs Flux Tower (143 paired sites)

| Model | R2 mean | R2 median | RMSE mean (mm/mo) | RMSE median (mm/mo) | Bias mean (mm/mo) | Bias median (mm/mo) |
|-------|---------|-----------|--------------------|--------------------|--------------------|--------------------|
| SWIM | 0.266 | 0.562 | 27.451 | 20.861 | -1.347 | 0.339 |
| SSEBop | -0.303 | 0.515 | 27.604 | 25.004 | -0.712 | -0.823 |

SWIM monthly win rate: 95/143 = 66%

### Diagnostic-Only Comparisons

- Pre-March 31, 2026 outputs (pre-paired-comparison, different masking).
- ACCURACY.md baseline and change-log entries.
- Runs relying on automatic `par.csv` discovery.
- ETf-only comparisons (`--etf` flag).
- Mask-switched (irr/inv_irr) variants.

### Canonical Commands

```bash
uv run python /home/dgketchum/code/swim-rs/examples/4_Flux_Network/evaluate.py \
  --par-csv /data/ssd1/swim/4_Flux_Network/results/4_Flux_Network.3.par.csv \
  --container /data/ssd1/swim/4_Flux_Network/data/4_Flux_Network.swim

uv run python /home/dgketchum/code/swim-rs/examples/4_Flux_Network/evaluate.py \
  --par-csv /data/ssd1/swim/4_Flux_Network/results/4_Flux_Network.3.par.csv \
  --container /data/ssd1/swim/4_Flux_Network/data/4_Flux_Network.swim \
  --monthly
```

### Data Paths

| Resource | Path |
|----------|------|
| Parameter file | `/data/ssd1/swim/4_Flux_Network/results/4_Flux_Network.3.par.csv` |
| Container | `/data/ssd1/swim/4_Flux_Network/data/4_Flux_Network.swim` |
| Evaluation script | `examples/4_Flux_Network/evaluate.py` |
| Shapefile | `/data/ssd1/swim/4_Flux_Network/data/gis/flux_fields.shp` |

---

## Example 5: Flux Ensemble

### Scope

Multi-site CONUS cropland evaluation. 60 cropland flux tower sites
calibrated against the 6-model OpenET ensemble mean.

### Configuration

| Setting | Value |
|---------|-------|
| Sites | 60 cropland flux sites |
| Period | 1995-01-01 to 2025-12-31 |
| Calibration target | Ensemble mean of 6 OpenET Landsat models |
| Ensemble members | SSEBop, PT-JPL, SIMS, geeSEBAL, eeMETRIC, DisALEXI |
| ETf observation period | 2016-2025 |
| Parameters | 8 per site (same as Example 4) |
| PEST++ IES | 200 realizations, 3 iterations, 40 workers |
| Runtime | ~109 min |
| Meteorology | GridMET |
| Snow | SNODAS (2004+) |
| Soils | SSURGO |
| mask_mode | none |
| kc_max floor | 1.35 |
| max_irr_rate | 100 mm/day |
| runoff_process | cn |
| refet_type | eto |

### ETf Masking: no_mask Only

Same as Example 4. Both calibration and validation use full-footprint ETf
from `remote_sensing/etf/landsat/{model}/no_mask`.

### Publication Window Rule

For publication-track Example 5 containers, NDVI and all ensemble-member ETf
inputs should be carried through `2025-12-31`. If a specific experiment uses
a shorter window, that shorter window must be declared in the Example 5 TOML
and in the governing experiment plan or `examples/ablation_plan.md`.

### Canonical Cohorts

- **Calibration configuration:** 60 cropland flux sites (Run 11).
- **Excluded:** `MB_Pch`.
- **Evaluation candidate cohort:** 59 sites after exclusion and site
  minimum data filter (90 days, 3 qualifying months).
- **Daily paired cohort:** sites with finite SWIM and Volk ensemble metrics
  on identical valid days.
- **Monthly paired cohort:** sites with finite SWIM and Volk ensemble
  metrics on identical valid months (20 days/month minimum).

### Validation Reference

- **Headline benchmark:** Volk et al. 3x3 OpenET ensemble ET.
- **Per-model benchmarks:** SSEBop, PT-JPL, SIMS, geeSEBAL, eeMETRIC,
  DisALEXI (each scored on its own paired day/month set with SWIM).
- **Flux tower ET:** energy-balance-corrected daily ET from the 60
  cropland stations.

### Ensemble-Derived Weighting

Run 11 uses ensemble-derived observation weights:
`weight = obsval / (std + 0.1)` where `std` is per-timestep standard
deviation across the 6 ensemble member ETf values. Observations where
models agree strongly receive higher weight. A controlled experiment
comparing this to standard fixed-denominator weighting is planned
(see `examples/ablation_plan.md`).

### Current Canonical Snapshot (March 31, 2026)

#### Daily ET vs Flux Tower (58 paired sites)

| Model | R2 mean | R2 median | RMSE mean | RMSE median | Bias mean | Bias median |
|-------|---------|-----------|-----------|-------------|-----------|-------------|
| SWIM | 0.392 | 0.652 | 1.277 | 1.141 | -0.151 | -0.010 |
| Ensemble | 0.323 | 0.567 | 1.382 | 1.189 | -0.099 | -0.094 |

SWIM daily win rate: 41/58 = 71%

#### Monthly ET vs Flux Tower (33 paired sites)

| Model | R2 mean | R2 median | RMSE mean (mm/mo) | RMSE median (mm/mo) | Bias mean (mm/mo) | Bias median (mm/mo) |
|-------|---------|-----------|--------------------|--------------------|--------------------|--------------------|
| SWIM | 0.814 | 0.845 | 21.451 | 21.474 | -0.774 | 0.326 |
| Ensemble | 0.799 | 0.859 | 21.224 | 19.591 | -5.877 | -6.697 |

SWIM monthly win rate: 17/33 = 52%

### Diagnostic-Only Comparisons

- Pre-March 31, 2026 summaries (pre-paired-comparison).
- SWIM-vs-flux "independent" summaries from experimental branches.
- Runs relying on automatic `par.csv` discovery in
  `/data/ssd1/swim/5_Flux_Ensemble/results/`.
- Per-model comparisons without an explicitly matched SWIM denominator.

### Canonical Commands

```bash
uv run python /home/dgketchum/code/swim-rs/examples/5_Flux_Ensemble/evaluate.py \
  --par-csv /data/ssd1/swim/5_Flux_Ensemble/results/run11_full_period/5_Flux_Ensemble.3.par.csv \
  --container /data/ssd1/swim/5_Flux_Ensemble/data/5_Flux_Ensemble.swim \
  --openet-source volk

uv run python /home/dgketchum/code/swim-rs/examples/5_Flux_Ensemble/evaluate.py \
  --par-csv /data/ssd1/swim/5_Flux_Ensemble/results/run11_full_period/5_Flux_Ensemble.3.par.csv \
  --container /data/ssd1/swim/5_Flux_Ensemble/data/5_Flux_Ensemble.swim \
  --monthly
```

### Data Paths

| Resource | Path |
|----------|------|
| Parameter file | `/data/ssd1/swim/5_Flux_Ensemble/results/run11_full_period/5_Flux_Ensemble.3.par.csv` |
| Container | `/data/ssd1/swim/5_Flux_Ensemble/data/5_Flux_Ensemble.swim` |
| Evaluation script | `examples/5_Flux_Ensemble/evaluate.py` |
| Validation policy (historical) | `examples/5_Flux_Ensemble/VALIDATION_POLICY.md` |
| Run 11 reference | `examples/5_Flux_Ensemble/RUN11_REFERENCE.md` |

---

## Example 6: Flux International

### Scope

Multi-site international cropland evaluation. 75 flux tower sites spanning
the Americas, Europe, and Oceania, calibrated against a Landsat SSEBop +
PT-JPL ensemble mean ETf. ERA5-Land meteorology, HWSD soils, no ECOSTRESS.

### Configuration

| Setting | Value |
|---------|-------|
| Sites | 75 international cropland flux sites |
| Period | 2013-01-01 to 2025-12-31 |
| Calibration target | Landsat ensemble mean (SSEBop + PT-JPL) ETf |
| PEST++ IES | 200 realizations, 3 iterations, 20 workers, 2 batches |
| Meteorology | ERA5-Land |
| Soils | HWSD |
| Shapefile | `flux_crop_pub_75_150m.shp` |
| mask_mode | none |
| runoff_process | cn |
| refet_type | eto |
| TOML | `6_Flux_International_LSEnsemble_POR.toml` |

### ETf and NDVI Masking: no_mask Only

Example 6 uses `mask_mode = "none"` and the international workflow ingests
NDVI and ETf under `no_mask` only. There is no canonical irrigation-mask
switching workflow for Ex6 publication runs.

### Publication Window Rule

For publication-track Example 6 containers, NDVI and ETf should be carried
through `2025-12-31`.

- This applies to Landsat NDVI, Sentinel NDVI, Landsat ETf, and ECOSTRESS
  ETf where those products are part of the container.
- A shorter or otherwise different period is allowed only when it is
  explicitly declared in the experiment TOML and the companion experiment
  plan.

### Validation Reference

- **Headline benchmark:** SWIM ET vs flux tower ET (energy-balance-corrected
  ET_corr from multi-network QAQC archive: AmeriFlux, FLUXNET, ICOS, OzFlux).
- **RS diagnostic benchmark:** native Landsat ETf (ensemble, SSEBop, PT-JPL
  individually), linearly interpolated to daily, multiplied by ERA5-Land ETo.
  Both SWIM and RS ETa are scored against flux on identical paired days.
- Calibration parameters are loaded from the container (ingested by
  batch_runner); no external `.par.csv` is required.

### Known Limitations

- **No OpenET reference:** international sites lack OpenET coverage, so
  the SWIM-vs-OpenET head-to-head is not applicable.
- **ERA5 bias correction:** ETo from ERA5-Land is systematically biased
  relative to station observations. A correction pipeline
  (`examples/6_Flux_International/met/`) applies monthly multiplicative
  factors derived from ag-met station comparisons. Coverage is incomplete
  for some arid and European sites.
- **Multi-network flux data:** QAQC archive spans four networks with
  varying data quality conventions.
- **Site minimum data threshold** applies as in the common framework
  (90 days, 3 qualifying months). 4 of 75 container sites lack post-2013
  flux data and are excluded from validation automatically.

### Current Canonical Snapshot (May 17, 2026)

Evaluation mode: `evaluate.py --config 6_Flux_International_LSEnsemble_POR.toml`
(daily, paired SWIM vs RS ensemble ETa vs flux).

#### Daily ET vs Flux Tower (71 paired sites)

| Model | R2 mean | R2 median | KGE mean | KGE median | RMSE median | Bias median |
|-------|---------|-----------|----------|------------|-------------|-------------|
| SWIM | 0.268 | 0.618 | 0.577 | 0.696 | 0.933 | -0.043 |
| RS Ensemble | 0.455 | 0.650 | 0.633 | 0.703 | 0.915 | -0.067 |

SWIM R2 win rate vs RS Ensemble: 29/71 = 41%
SWIM KGE win rate vs RS Ensemble: 29/71 = 41%

#### Daily ET vs Flux Tower — per-model RS benchmarks

| RS Model | n sites | SWIM R2 med | RS R2 med | SWIM R2 win | SWIM KGE win |
|----------|---------|-------------|-----------|-------------|--------------|
| LS SSEBop | 64 | 0.626 | 0.557 | 64% | 66% |
| LS PT-JPL | 71 | 0.618 | 0.618 | 49% | 45% |
| LS Ensemble | 71 | 0.618 | 0.650 | 41% | 41% |

#### Monthly ET vs Flux Tower (54 paired sites)

| Model | R2 mean | R2 median | KGE mean | KGE median | RMSE median (mm/mo) | Bias median (mm/mo) |
|-------|---------|-----------|----------|------------|---------------------|---------------------|
| SWIM | -0.121 | 0.652 | 0.507 | 0.647 | 21.772 | 2.479 |
| RS Ensemble | 0.180 | 0.679 | 0.558 | 0.669 | 21.943 | 3.369 |

### Canonical Commands

```bash
uv run python /home/dgketchum/code/swim-rs/examples/6_Flux_International/evaluate.py \
  --config /home/dgketchum/code/swim-rs/examples/6_Flux_International/6_Flux_International_LSEnsemble_POR.toml

uv run python /home/dgketchum/code/swim-rs/examples/6_Flux_International/evaluate.py \
  --config /home/dgketchum/code/swim-rs/examples/6_Flux_International/6_Flux_International_LSEnsemble_POR.toml \
  --monthly
```

### Data Paths

| Resource | Path |
|----------|------|
| Container | `/data/ssd1/swim/6_Flux_International/data/6_Flux_International_ls_ensemble_por.swim` |
| Evaluation script | `examples/6_Flux_International/evaluate.py` |
| TOML | `examples/6_Flux_International/6_Flux_International_LSEnsemble_POR.toml` |
| Results | `/data/ssd1/swim/6_Flux_International/results/6_Flux_International_LSEnsemble_POR/` |
| Detailed notes | `examples/6_Flux_International/notes/LS_ENSEMBLE_POR_RESULTS.md` |
