"""Extract ERA5-Land variables at non-CONUS ISD stations via Earth Engine.

For stations outside the local NetCDF domain (lat 22.2–60.4°N, lon -129.6 to
-63.0°W), uses EE's ECMWF/ERA5_LAND/DAILY_AGGR collection to extract daily
meteorology and compute PM-ETo. Output CSVs go to the same era5_extractions/
directory used by extract_era5_at_stations.py.

Two-phase workflow:
  1. python extract_era5_ee.py --export   # Submit EE batch export tasks (one per year)
  2. python extract_era5_ee.py --process  # Process downloaded GCS CSVs into per-station files

Usage:
    python extract_era5_ee.py --export
    python extract_era5_ee.py --process
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import refet

SELECTED = Path(__file__).parent / "selected_stations.json"
ISD_STATIONS = "/nas/climate/isd/indices/stations.parquet"
OUT_DIR = Path(__file__).parent / "era5_extractions"
GCS_DIR = Path(__file__).parent / "era5_ee_gcs"

GCS_BUCKET = "wudr"
GCS_PREFIX = "isd_era5_land"

YEAR_START = 2000
YEAR_END = 2024

# NetCDF grid domain (CONUS only) — must match extract_era5_at_stations.py
NC_LAT_MIN = 22.2
NC_LAT_MAX = 60.4
NC_LON_MIN = -129.6
NC_LON_MAX = -63.0

# ERA5-Land daily aggregated bands to extract
EE_BANDS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "dewpoint_temperature_2m",
    "surface_solar_radiation_downwards_sum",
    "u_component_of_wind_10m",
    "v_component_of_wind_10m",
]

# 10m -> 2m wind conversion factor: 4.87 / ln(67.8*10 - 5.42)
WIND_10M_TO_2M = 4.87 / np.log(67.8 * 10 - 5.42)


def get_unique_stations():
    """Get deduplicated station IDs from selected_stations.json."""
    with open(SELECTED) as f:
        selected = json.load(f)
    stations = set()
    for site_data in selected.values():
        stations.update(site_data["stations"])
    return sorted(stations)


def get_station_meta(station_ids):
    """Get lat/lon/elev for station IDs from ISD stations parquet."""
    stations = pd.read_parquet(ISD_STATIONS)
    stations = stations.set_index("station_id")
    return stations.loc[stations.index.isin(station_ids), ["lat", "lon", "elev_m"]]


def filter_out_of_domain(station_ids, meta):
    """Return station IDs outside the CONUS NC grid domain."""
    out = []
    for sid in station_ids:
        if sid not in meta.index:
            continue
        lat = meta.loc[sid, "lat"]
        lon = meta.loc[sid, "lon"]
        if not (NC_LAT_MIN <= lat <= NC_LAT_MAX and NC_LON_MIN <= lon <= NC_LON_MAX):
            out.append(sid)
    return out


def saturation_vp(t_c):
    """Tetens formula: temperature [C] -> saturation vapor pressure [kPa]."""
    return 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))


def export_yearly_tasks(station_ids, meta):
    """Submit one EE export task per year (2000-2024)."""
    import ee

    ee.Initialize()

    features = []
    for sid in station_ids:
        lat = float(meta.loc[sid, "lat"])
        lon = float(meta.loc[sid, "lon"])
        pt = ee.Geometry.Point([lon, lat])
        features.append(ee.Feature(pt, {"station_id": sid}))

    fc = ee.FeatureCollection(features)
    print(f"  {len(features)} station points in FeatureCollection")

    era5 = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")

    for year in range(YEAR_START, YEAR_END + 1):
        start = f"{year}-01-01"
        end = f"{year + 1}-01-01"

        yearly = era5.filterDate(start, end).select(EE_BANDS)

        def extract_at_stations(image):
            date_str = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd")
            reduced = image.reduceRegions(
                collection=fc,
                reducer=ee.Reducer.first(),
                scale=11132,
            )
            return reduced.map(lambda f: f.set("date", date_str).setGeometry(None))

        results = yearly.map(extract_at_stations).flatten()

        desc = f"{GCS_PREFIX}_{year}"
        selectors = ["station_id", "date"] + EE_BANDS
        task = ee.batch.Export.table.toCloudStorage(
            collection=results,
            description=desc,
            bucket=GCS_BUCKET,
            fileNamePrefix=desc,
            fileFormat="CSV",
            selectors=selectors,
        )
        task.start()
        status = task.status()
        print(f"    {year}: {desc} ({status['id'][:8]}...)")

    print("\n  Monitor: https://code.earthengine.google.com/tasks")
    print(f"  Output: gs://{GCS_BUCKET}/{GCS_PREFIX}_*.csv")
    print("\n  When complete, download:")
    print(f"    mkdir -p {GCS_DIR}")
    print(f"    gsutil -m cp 'gs://{GCS_BUCKET}/{GCS_PREFIX}_*.csv' {GCS_DIR}/")
    print(f"    python {__file__} --process")


def process_gcs_csvs(meta):
    """Read yearly GCS CSVs, apply unit conversions, compute ETo, write per-station CSVs."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(GCS_DIR.glob(f"{GCS_PREFIX}_*.csv"))
    if not csv_files:
        print(f"  No CSVs found in {GCS_DIR}")
        print(f"  Download first: gsutil -m cp 'gs://{GCS_BUCKET}/{GCS_PREFIX}_*.csv' {GCS_DIR}/")
        return

    print(f"  Reading {len(csv_files)} yearly CSVs...")
    frames = []
    for f in csv_files:
        df = pd.read_csv(f)
        frames.append(df)
        print(f"    {f.name}: {len(df)} rows, cols={list(df.columns)[:4]}...")

    all_data = pd.concat(frames, ignore_index=True)
    all_data["date"] = pd.to_datetime(all_data["date"])

    # EE reduceRegions with Reducer.first() on multi-band images produces columns
    # named after the bands directly
    col_map = {}
    for band in EE_BANDS:
        if band in all_data.columns:
            col_map[band] = band
        else:
            # Try "first" naming convention
            for col in all_data.columns:
                if band.startswith(col.replace("first", "").strip("_")):
                    col_map[band] = col
                    break

    # If direct band names are present, use them; otherwise detect the pattern
    if all(b in all_data.columns for b in EE_BANDS):
        pass  # columns already named by band
    else:
        print(f"  WARNING: Expected band-name columns not found. Columns: {list(all_data.columns)}")
        print("  Attempting to proceed with available columns...")

    # Drop rows missing any required variable
    all_data = all_data.dropna(subset=[c for c in EE_BANDS if c in all_data.columns])

    # Unit conversions (same as NC pipeline)
    all_data["tmax"] = all_data["temperature_2m_max"] - 273.15
    all_data["tmin"] = all_data["temperature_2m_min"] - 273.15
    all_data["tdew"] = all_data["dewpoint_temperature_2m"] - 273.15
    all_data["rsds"] = all_data["surface_solar_radiation_downwards_sum"] / 1e6
    u10 = all_data["u_component_of_wind_10m"]
    v10 = all_data["v_component_of_wind_10m"]
    all_data["u2"] = np.sqrt(u10**2 + v10**2) * WIND_10M_TO_2M
    all_data["ea"] = saturation_vp(all_data["tdew"].values)
    all_data["vpd"] = (
        saturation_vp(all_data["tmax"].values) + saturation_vp(all_data["tmin"].values)
    ) / 2 - all_data["ea"]
    all_data["tmean"] = (all_data["tmax"] + all_data["tmin"]) / 2

    all_data = all_data.sort_values(["station_id", "date"])

    # Compute PM-ETo per station
    print("  Computing PM-ETo...")
    out_vars = ["tmax", "tmin", "tmean", "rsds", "ea", "vpd", "u2", "eto"]
    n_written = 0

    for sid, group in all_data.groupby("station_id"):
        if sid not in meta.index:
            continue
        lat = float(meta.loc[sid, "lat"])
        elev = float(meta.loc[sid, "elev_m"])
        group = group.set_index("date").sort_index()
        doy = group.index.dayofyear.values

        eto_vals = refet.Daily(
            tmin=group["tmin"].values,
            tmax=group["tmax"].values,
            rs=group["rsds"].values,
            uz=group["u2"].values,
            zw=2.0,
            elev=elev,
            lat=lat,
            doy=doy,
            ea=group["ea"].values,
        ).eto()

        group["eto"] = eto_vals
        out = group[out_vars].copy()
        out.index.name = "date"
        out.to_csv(OUT_DIR / f"{sid}.csv")
        n_written += 1

    print(f"  Wrote {n_written} per-station CSVs to {OUT_DIR}")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--export", action="store_true", help="Submit EE batch export tasks")
    group.add_argument("--process", action="store_true", help="Process downloaded GCS CSVs")
    args = parser.parse_args()

    print("Loading selected stations...")
    station_ids = get_unique_stations()
    print(f"  {len(station_ids)} unique stations")

    meta = get_station_meta(station_ids)
    station_ids = [s for s in station_ids if s in meta.index]
    print(f"  {len(station_ids)} with metadata")

    # Filter to out-of-domain only
    station_ids = filter_out_of_domain(station_ids, meta)
    print(f"  {len(station_ids)} outside CONUS NC domain")

    if not station_ids:
        print("  No out-of-domain stations — nothing to do")
        return

    if args.export:
        print(f"Submitting EE export tasks ({YEAR_START}-{YEAR_END})...")
        export_yearly_tasks(station_ids, meta)

    elif args.process:
        print("Processing GCS CSVs into per-station files...")
        process_gcs_csvs(meta)


if __name__ == "__main__":
    main()
