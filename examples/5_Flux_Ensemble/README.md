# Example 5: Flux Ensemble Calibration

Daily ET calibration for 60 US cropland flux tower sites using PEST++ IES
against a 6-model OpenET Landsat ETf ensemble. For validation reporting,
`MB_Pch` is excluded, leaving a 59-site evaluation candidate cohort.

## Approach

SWIM is calibrated via PEST++ IES (iterative ensemble smoother) against unmasked Landsat ETf from 6 OpenET models: SSEBop, PT-JPL, SIMS, geeSEBAL, eeMETRIC, and DisALEXI. Each site has 8 calibration parameters (aw, ndvi_k, ndvi_0, mad, kr_alpha, ks_alpha, swe_alpha, swe_beta) with 200 ensemble realizations over 3 iterations. Calibrated ET is evaluated against energy-balance-corrected flux tower ET and Volk et al. (2024) 3x3 OpenET field-scale extractions.

## Data Sources

| Source | Description |
|--------|-------------|
| Landsat NDVI (no_mask) | Unmasked vegetation index from EE |
| Landsat ETf (no_mask, 6 models) | Pre-computed OpenET v2.1 EE asset collections |
| GridMET | Daily meteorology (ETo, precip, temp, humidity, wind, solar) |
| SNODAS | Daily SWE from NOAA |
| SSURGO | Soil properties (AWC, texture, depth) |
| CDL / LANID | Crop type and irrigation status |

## Workflow

**1. Extract remote sensing data**
```bash
uv run python /home/dgketchum/code/swim-rs/examples/5_Flux_Ensemble/data_extract.py
```

**2. Sync EE exports to local storage**
```bash
gsutil -m rsync -r gs://{bucket}/5_Flux_Ensemble data/remote_sensing/
```

**3. Build container**
```bash
uv run python /home/dgketchum/code/swim-rs/examples/5_Flux_Ensemble/container_prep.py --overwrite
```

**4. Calibrate**
```bash
uv run python /home/dgketchum/code/swim-rs/examples/5_Flux_Ensemble/calibrate.py
```

**5. Evaluate**
```bash
# Canonical daily paired benchmark
uv run python /home/dgketchum/code/swim-rs/examples/5_Flux_Ensemble/evaluate.py --par-csv /data/ssd1/swim/5_Flux_Ensemble/results/run11_full_period/5_Flux_Ensemble.3.par.csv --container /data/ssd1/swim/5_Flux_Ensemble/data/5_Flux_Ensemble.swim --openet-source volk

# Canonical monthly paired benchmark
uv run python /home/dgketchum/code/swim-rs/examples/5_Flux_Ensemble/evaluate.py --par-csv /data/ssd1/swim/5_Flux_Ensemble/results/run11_full_period/5_Flux_Ensemble.3.par.csv --container /data/ssd1/swim/5_Flux_Ensemble/data/5_Flux_Ensemble.swim --monthly

# ETf comparison at Landsat capture dates
uv run python /home/dgketchum/code/swim-rs/examples/5_Flux_Ensemble/evaluate.py --par-csv /data/ssd1/swim/5_Flux_Ensemble/results/run11_full_period/5_Flux_Ensemble.3.par.csv --container /data/ssd1/swim/5_Flux_Ensemble/data/5_Flux_Ensemble.swim --etf
```

## Validation Policy

Example 5 now uses one canonical validation policy documented in
`VALIDATION_POLICY.md`.

- Headline ET benchmark: paired SWIM vs Volk 3x3 OpenET ensemble.
- Calibration configuration: 60 sites.
- Excluded from validation outputs: `MB_Pch`.
- Evaluation candidate cohort: 59 sites.
- Current paired cohorts from the March 31, 2026 rerun:
  - Daily headline benchmark: 58 sites.
  - Monthly headline benchmark: 33 sites.

Current canonical paired snapshot:

| Benchmark | SWIM R² mean | Ensemble R² mean | SWIM bias mean | Ensemble bias mean |
|-----------|--------------|------------------|----------------|--------------------|
| Daily | 0.392 | 0.323 | -0.151 mm/day | -0.099 mm/day |
| Monthly | 0.814 | 0.799 | -0.774 mm/month | -5.877 mm/month |

## Files

| File | Description |
|------|-------------|
| `5_Flux_Ensemble.toml` | Project configuration |
| `setup_shapefile.py` | Build flux site shapefile from master station list |
| `data_extract.py` | Extract NDVI, ETf, met, snow, and properties from EE/GridMET |
| `etf_asset_extract.py` | Extract ETf from pre-computed OpenET EE asset collections |
| `copy_openet_assets.py` | Copy OpenET EE assets to project asset folder |
| `container_prep.py` | Build `.swim` container (ingest + compute + export) |
| `calibrate.py` | Run PEST++ IES calibration sequence |
| `evaluate.py` | Evaluate calibrated model against flux and OpenET |
| `VALIDATION_POLICY.md` | Canonical comparison policy and current benchmark snapshot |
| `RUN11_REFERENCE.md` | Tracked Run 11 reference and paired benchmark summary |
| `params.csv` | Sample per-site parameter file (regenerated at runtime) |
