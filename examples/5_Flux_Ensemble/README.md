# Example 5: Flux Ensemble Calibration

Daily ET calibration for 59 US cropland flux tower sites using PEST++ IES against a 6-model OpenET Landsat ETf ensemble.

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
python data_extract.py
```

**2. Sync EE exports to local storage**
```bash
gsutil -m rsync -r gs://{bucket}/5_Flux_Ensemble data/remote_sensing/
```

**3. Build container**
```bash
python container_prep.py --overwrite
```

**4. Calibrate**
```bash
python calibrate.py
```

**5. Evaluate**
```bash
# Daily ET vs flux tower
python evaluate.py

# ETf comparison at Landsat capture dates
python evaluate.py --etf

# Monthly ET totals vs flux and Volk 3x3
python evaluate.py --monthly
```

## Results (Run 8)

| Metric | Daily | Monthly |
|--------|-------|---------|
| Mean bias (mm/d) | -0.001 | — |
| R² (median) | 0.604 | 0.792 |

SWIM is the least biased model compared to the 6 OpenET models and their ensemble.

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
| `params.csv` | Sample per-site parameter file (regenerated at runtime) |
