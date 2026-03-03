# ERA5-Land Meteorology and Bias Correction

## Overview

SWIM-RS uses ERA5-Land reanalysis data (0.1 degree, ~9 km) as its meteorological forcing for
international and multi-site applications where station-based gridded products (e.g., GridMET) are
unavailable. ERA5-Land provides global, gap-free daily coverage from 1950 to near-present, but it
carries known regional biases in solar radiation, wind speed, and humidity that propagate directly into
reference evapotranspiration (ETo). We correct these biases using ground observations from NOAA
Integrated Surface Database (ISD) stations globally, supplemented with MODIS MCD18A1 satellite-derived
surface downwelling shortwave radiation (DSR) for the solar radiation component.

This document describes the full pipeline: ERA5-Land variable extraction, unit conversions, ETo
computation, station-based quality control, bias-correction factor derivation, and application. The
published `correction_factors.json` file allows users to reproduce corrected ETo without access to the
raw station observations.

## ERA5-Land Variables and Unit Conversions

We download six daily ERA5-Land fields and derive the meteorological inputs needed for the
ASCE Standardized Reference Evapotranspiration Equation (ASCE, 2005):

| ERA5-Land Variable | Raw Unit | Conversion | Output Variable | Output Unit |
|---|---|---|---|---|
| 2 m temperature (daily max) | K | -273.15 | tmax | deg C |
| 2 m temperature (daily min) | K | -273.15 | tmin | deg C |
| Surface solar radiation downwards (daily sum) | J m-2 d-1 | / 1e6 | rsds | MJ m-2 d-1 |
| 10 m u-component of wind | m s-1 | sqrt(u^2 + v^2), then 10 m to 2 m | u2 | m s-1 |
| 10 m v-component of wind | m s-1 | (same as above) | u2 | m s-1 |
| 2 m dewpoint temperature | K | Tetens formula | ea | kPa |

Derived variables:

- **tmean** = (tmax + tmin) / 2
- **ea** (actual vapor pressure) from dewpoint via the Tetens formula:
  ea = 0.6108 * exp(17.27 * T_dew / (T_dew + 237.3))
- **vpd** (vapor pressure deficit) = (e_s(tmax) + e_s(tmin)) / 2 - ea
- **Wind height adjustment** from 10 m to 2 m: u2 = u10 * 4.87 / ln(67.8 * 10 - 5.42)

## Reference Evapotranspiration (ETo)

We compute ASCE Standardized Reference ET (short reference, grass) using the
[refet](https://github.com/DRI-WSWUP/RefET) Python package:

```python
refet.Daily(
    tmin=tmin,       # deg C
    tmax=tmax,       # deg C
    rs=rsds,         # MJ m-2 d-1
    uz=u2,           # m s-1
    zw=2.0,          # wind measurement height (m)
    elev=elev,       # station elevation (m)
    lat=lat,         # latitude (degrees)
    doy=doy,         # day of year
    ea=ea,           # actual vapor pressure (kPa)
).eto()
```

This is the Penman-Monteith equation as standardized by ASCE (2005), identical to the formulation used
by GridMET, NLDAS-2, and the OpenET consortium. ERA5-Land ETo is computed at each site's nearest grid
cell using the grid-cell elevation for the pressure term.

## Bias Correction Using ISD Station Observations and MODIS DSR

### Motivation

ERA5-Land's global reanalysis model introduces systematic biases that vary by region and season. The
most consequential for ETo are:

- **Solar radiation (rsds):** ERA5-Land tends to overestimate clear-sky solar radiation by 5-15%
  relative to ground pyranometers, particularly in the western US.
- **Wind speed (u2):** Reanalysis wind is smoothed over the grid cell and often underrepresents
  sheltered agricultural settings, while overrepresenting exposed ridgelines.
- **Humidity (ea/vpd):** Dewpoint-derived vapor pressure can carry biases from the land surface model,
  especially in irrigated areas where the surface is wetter than the reanalysis assumes.
- **Temperature (tmean):** Generally ERA5-Land's strongest variable, but elevation mismatches between
  the 9 km grid and the actual site can introduce 1-2 deg C offsets.

These biases compound nonlinearly through the Penman-Monteith equation. A 10% high bias in rsds plus
a 15% low bias in VPD can produce a 20%+ error in ETo. Correcting at the variable level before ETo
computation is more principled than correcting ETo directly, but we also compute and apply an ETo ratio
as a pragmatic summary correction.

### Data Sources

**NOAA Integrated Surface Database (ISD):** ISD provides global weather observations from ~28,000
stations, including daily maximum and minimum temperature, dewpoint, and wind speed. Observations have
upstream quality control flags; we retain only values with quality codes 1 (passed all checks) or 5
(passed with corrections). After filtering for stations with >365 days of all four variables and valid
elevation metadata, approximately 22,000 stations are available worldwide.

ISD does not include pyranometer-based solar radiation measurements. We fill this gap with satellite
observations.

**MODIS MCD18A1 (Surface Downwelling Shortwave Radiation):** The MCD18A1 product provides daily
surface DSR at 1 km resolution, derived from MODIS Terra and Aqua observations using a look-up table
approach (Wang et al., 2020). We extract DSR at each ISD station location via Google Earth Engine,
summing the 8 three-hourly bands and converting from W/m² to MJ/m²/d. Temporal coverage is
2000-03-03 to present, limiting the overlap period to 2000-2024. Typical clear-sky mid-latitude
values are 20-30 MJ/m²/d.

### Station Selection

We select ground truth stations from NOAA ISD with the following criteria:

1. **Observation count filter:** Stations must have >365 days of valid observations for each of:
   tmax, tmin, dewpoint, and wind speed. This ensures sufficient temporal coverage for computing
   robust monthly statistics.
2. **Elevation metadata:** Stations must have valid elevation (required for the PM-ETo pressure term
   and clear-sky radiation computation).
3. **Land cover filter (optional):** Stations can be filtered to cropland per FROM-GLC10 (10 m land
   cover, 200 m zonal mode) to exclude urban, forested, or other non-agricultural surfaces.
4. **Proximity:** For each flux site, we select the 20 nearest qualifying stations by geodesic
   distance.

This process yields stations serving all 64 flux sites globally, including the 11 sites in Europe,
Australia, and Puerto Rico that had no coverage under the previous MADIS-only approach.

### Station Data Quality Control

Raw ISD station data and MODIS DSR are processed through five QAQC steps using the
[agweather-qaqc](https://github.com/WSWUP/agweather-qaqc) package (Dunkerly, 2024), which implements
the quality control procedures recommended by Allen et al. (1998) and the ASCE Manual of Practice:

**Variable preparation:**
- Temperature (tmax, tmin): used directly from ISD (deg C)
- Actual vapor pressure (ea): derived from ISD dewpoint via the Tetens formula
- Wind speed (u2): ISD 10 m wind converted to 2 m using the logarithmic wind profile
- Solar radiation (rsds): from MODIS MCD18A1 daily DSR (MJ/m²/d, converted to W/m² for QAQC)

ISD and MODIS observations are aligned on common dates; stations with <365 common days are excluded.

**Step 1 -- Physical bounds.** Replace values outside physically realistic limits with NaN:

| Variable | Lower Bound | Upper Bound |
|---|---|---|
| Temperature (tmax, tmin) | -50 deg C | 60 deg C |
| Vapor pressure (ea) | 0 kPa | 8 kPa |
| Wind speed (u2) | 0.1 m s-1 | 35 m s-1 |
| Solar radiation (rsds) | 5 W m-2 | 700 W m-2 |

**Step 2 -- Isolated observation removal.** Any observation flanked by NaN on both sides is set to NaN.
Isolated valid points amid missing data are unreliable because they cannot be verified against
neighboring values and are often associated with intermittent sensor connections.

**Step 3 -- Monthly modified z-score outlier detection.** For each variable and calendar month, we
compute the modified z-score (Iglewicz and Hoaglin, 1993):

    z_modified = 0.6745 * (x - median) / MAD

where MAD is the median absolute deviation. Values with |z_modified| > 3.5 are flagged as outliers and
set to NaN. The modified z-score is more robust than the standard z-score because it uses the median
rather than the mean, making it resistant to the very outliers it is trying to detect. We apply this
per calendar month (requiring at least 10 valid observations) to preserve seasonal cycles -- a
legitimate July maximum should not be flagged as an outlier relative to the annual distribution.

**Step 4 -- Solar radiation period-ratio drift correction.** Even satellite-derived rsds can have
systematic biases that vary over time. We detect and correct this using the period-ratio method:

1. Compute theoretical clear-sky radiation Rso from extraterrestrial radiation Ra and station elevation
   using the simplified ASCE formula: Rso = (0.75 + 2e-5 * elev) * Ra.
2. Divide the record into 60-day periods. Within each period, take the 6 largest Rs/Rso ratios and
   compute a correction factor = mean(Rso) / mean(Rs) from those points.
3. Screen for suspect values: if removing any single ratio changes the correction factor by more than
   2%, that ratio likely represents a spike rather than a clear-sky day. Replace the suspect Rs value
   with 1.05 * Rso.
4. Apply the period correction factor to all days in each period, but only when the factor falls
   between 0.50 and 1.50. Factors outside this range indicate fundamentally unreliable data, and those
   periods are set to NaN.

**Step 5 -- Recompute ETo.** After cleaning all input variables, we recompute ASCE PM-ETo from the
corrected tmax, tmin, rsds, ea, and u2 using the same refet formulation as the ERA5 extraction. This
ensures the station ETo used for bias ratios is physically consistent with the corrected inputs.

### Correction Factor Computation

For each station that passes QAQC, we pair its cleaned daily observations with the ERA5-Land
extraction at the same location on matching dates. We then compute long-term monthly statistics:

**Multiplicative ratios** for ETo, rsds, u2, and VPD:

    ratio(month) = mean(obs[month]) / mean(ERA5[month])

where the means are taken over all years with at least 10 valid paired days in that month. Ratios are
clamped to [0.5, 1.5] to prevent extreme corrections from stations with residual data quality issues.

**Additive deltas** for tmean:

    delta(month) = mean(obs[month]) - mean(ERA5[month])

Deltas are clamped to [-10, +10] deg C.

### Spatial Interpolation to Flux Sites

Each flux site's correction factors are computed by inverse-distance-weighted (IDW) interpolation from
its nearest qualifying stations that survived QAQC:

    correction(site, month) = sum(w_i * correction_i) / sum(w_i)

where w_i = 1 / d_i^2 and d_i is the geodesic distance (km) from the station to the flux site, with a
minimum distance floor of 0.1 km.

All 64 sites receive real corrections from nearby ISD stations (no identity fallback needed).

## Correction Factors File Format

The file `correction_factors.json` contains the complete set of per-site, per-month correction factors.
Structure:

```json
{
  "CA-ER1": {
    "eto":   {"1": 0.6521, "2": 0.6708, ..., "12": 0.6995},
    "rsds":  {"1": 0.9491, "2": 0.9648, ..., "12": 0.8655},
    "u2":    {"1": 1.3357, "2": 1.3150, ..., "12": 1.3266},
    "vpd":   {"1": 0.5715, "2": 0.6136, ..., "12": 0.5787},
    "tmean": {"1": -0.234, "2": -0.058, ..., "12": -0.488}
  },
  ...
}
```

Keys are month numbers (1-12) as strings. The correction is applied as:

- **eto, rsds, u2, vpd:** `corrected = ERA5_value * ratio`
- **tmean:** `corrected = ERA5_value + delta`

## Reproducing Corrected ERA5-Land ETo

Users can reproduce the corrected meteorological forcing in two ways:

### Option A: Apply Published Correction Factors (recommended)

If you already have ERA5-Land ETo for your sites, apply the monthly ratios from
`correction_factors.json`:

```python
import json
import pandas as pd

with open("correction_factors.json") as f:
    corrections = json.load(f)

# For a given site and date
site = "US-Tw1"
month = "7"  # July
eto_ratio = corrections[site]["eto"][month]  # e.g. 1.096
eto_corrected = eto_raw * eto_ratio
```

The script `apply_corrections.py` automates this for all sites and months, reading ERA5 monthly CSVs
and writing corrected CSVs with `eto_corr` columns.

### Option B: Full Reproduction from ERA5-Land NetCDF

1. **Download ERA5-Land daily NetCDF** for the six variables listed above from the
   [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/). The CDS API provides
   programmatic access.

2. **Extract at site locations** using nearest-neighbor sampling from the NetCDF grid. The script
   `extract_era5_at_stations.py` demonstrates this with xarray, applying all unit conversions and
   computing PM-ETo with refet.

3. **Apply correction factors** from `correction_factors.json` using `apply_corrections.py`.

## Pipeline Execution Sequence

1. `select_stations.py --skip-lc` — Select 20 nearest ISD stations per flux site
2. `extract_era5_at_stations.py` — Extract ERA5-Land at ISD station locations
3. `extract_modis_dsr.py --export` — Submit EE tasks for MODIS DSR at stations
4. `extract_modis_dsr.py --process` — Process downloaded CSVs into per-station files
5. `qaqc_stations.py` — QAQC ISD + MODIS data and recompute PM-ETo
6. `calc_corrections.py` — Compute monthly ratios and IDW interpolation
7. `apply_corrections.py --ingest` — Apply corrections and ingest into container

## References

- Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). Crop evapotranspiration: Guidelines for
  computing crop water requirements. FAO Irrigation and Drainage Paper 56.
- ASCE-EWRI (2005). The ASCE Standardized Reference Evapotranspiration Equation. ASCE.
- Dunkerly, C. (2024). agweather-qaqc: A Python package for quality assurance and quality control of
  daily agricultural weather data. https://github.com/WSWUP/agweather-qaqc
- Iglewicz, B., Hoaglin, D.C. (1993). Volume 16: How to Detect and Handle Outliers. The ASQC Basic
  References in Quality Control: Statistical Techniques.
- Munoz Sabater, J. (2019). ERA5-Land hourly data from 1950 to present. Copernicus Climate Change
  Service (C3S) Climate Data Store (CDS). doi:10.24381/cds.e2161bac
- Wang, D., Liang, S., Zhang, Y., Gao, X., Brown, M.G.L., Jia, A. (2020). A New Set of MODIS Land
  Surface Temperature and Emissivity Products (MCD18A1/A2). Remote Sensing, 12(22), 3783.
