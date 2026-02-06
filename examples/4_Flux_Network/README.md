# 4_Flux_Network: SWIM with USGS SSEBop NHM

Field-scale SWIM runs across ~245 CONUS flux stations (all land cover types), using SSEBop NHM as the sole ETf calibration target. Date range: 1987-2024.

## Data sources

- **ETf**: USGS SSEBop NHM (`projects/usgs-gee-nhm-ssebop/assets/ssebop/landsat/c02`)
- **NDVI**: Landsat + Sentinel (fused)
- **Meteorology**: GridMET (ETo, ETr, prcp, tmin, tmax, srad, u2, ea, bias-corrected)
- **Snow**: SNODAS SWE
- **Soils/properties**: SSURGO, CDL, LANID irrigation masks

## Setup

Data lives at `/data/ssd1/swim/4_Flux_Network/data/` (with symlinks to ssd2 for flux files).

```bash
# Install dependencies
uv sync --all-extras
```

## Workflow

### Step 1: Setup shapefile
```bash
python setup_shapefile.py
```
Creates `data/gis/flux_fields.shp` from canonical repo data (all land cover types, no filter).

### Step 2: Extract data (if not already present)
```bash
python data_extract.py --extract nhm     # SSEBop NHM ETf only
python data_extract.py --extract ndvi    # NDVI only
python data_extract.py --extract all     # everything
```

### Step 3: Build container
```bash
python container_prep.py --overwrite
python container_prep.py --overwrite --sites US-ARM,US-Ne1  # subset
```

### Step 4: Run single site
```bash
python run.py --site US-ARM
```

### Step 5: Calibrate with PEST++
```bash
python calibrate.py
```

### Step 6: Evaluate
```bash
python evaluate.py --sites US-ARM
python evaluate.py                   # all sites
python evaluate.py --etf             # ETf comparison at capture dates
```

## Quick test (single site end-to-end)
```bash
python setup_shapefile.py
python container_prep.py --overwrite --sites US-ARM
python run.py --site US-ARM
```
