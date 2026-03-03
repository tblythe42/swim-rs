"""Select 20 nearest ISD stations per flux site for ERA5-Land bias correction.

For each flux site, find 20 nearest NOAA ISD stations that:
  - Have >365 days of tmax, tmin, dewpoint, and wind speed data
  - Have valid elevation metadata
  - Are on cropland per FROM-GLC10 (200m zonal mode) [optional]

Two-phase workflow:
  1. python select_stations.py --export-lc     # Submit EE export task
  2. python select_stations.py --glc10-csv <path>  # Use exported CSV to filter + select

Or skip land cover:
  python select_stations.py --skip-lc
"""

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod

FLUX_SHP = "/data/ssd1/swim/6_Flux_International/data/gis/flux_intl_buffers_150m_06JAN2026.shp"
ISD_STATIONS = "/nas/climate/isd/indices/stations.parquet"
ISD_COVERAGE = "/nas/climate/isd/indices/daily_coverage.shp"
OUT_DIR = Path(__file__).parent
OUT_FILE = OUT_DIR / "selected_stations.json"

# FROM-GLC10 cropland class
GLC10_CROPLAND = 10
GCS_BUCKET = "wudr"
N_NEIGHBORS = 20

MIN_OBS_DAYS = 365


def load_flux_sites():
    """Load all flux sites (global)."""
    return gpd.read_file(FLUX_SHP, engine="fiona")


def filter_isd_stations():
    """Filter ISD stations to those with sufficient coverage and valid elevation."""
    coverage = gpd.read_file(ISD_COVERAGE, engine="fiona")
    stations = pd.read_parquet(ISD_STATIONS)

    print(f"    {len(coverage)} stations in coverage shapefile")
    print(f"    {len(stations)} stations in metadata parquet")

    mask = (
        (coverage["n_tmax_c"] > MIN_OBS_DAYS)
        & (coverage["n_tmin_c"] > MIN_OBS_DAYS)
        & (coverage["n_dewpoint"] > MIN_OBS_DAYS)
        & (coverage["n_wind_spe"] > MIN_OBS_DAYS)
    )
    coverage = coverage[mask].copy()
    print(f"    {len(coverage)} pass observation count filters (>{MIN_OBS_DAYS} days each var)")

    merged = coverage.merge(
        stations[["station_id", "lat", "lon", "elev_m"]],
        on="station_id",
        how="inner",
    )
    merged = merged[merged["elev_m"].notna()].copy()
    print(f"    {len(merged)} with valid elevation after metadata merge")

    return merged


def export_glc10_task(stations_gdf, bucket=GCS_BUCKET, buffer_m=200, batch_size=2500):
    """Submit batched EE export tasks: GLC10 200m zonal mode at candidate stations.

    Parameters
    ----------
    stations_gdf : GeoDataFrame
        Must have 'station_id', 'lat', 'lon' columns.
    bucket : str
        GCS bucket for export.
    buffer_m : int
        Buffer radius (m) for zonal mode (default 200).
    batch_size : int
        Max stations per EE task (default 2500).
    """
    import ee

    ee.Initialize()

    glc10 = ee.ImageCollection("projects/sat-io/open-datasets/FROM-GLC10").mosaic()

    n = len(stations_gdf)
    n_batches = (n + batch_size - 1) // batch_size
    print(f"  {n} stations -> {n_batches} export tasks ({batch_size}/batch)")

    sids = stations_gdf["station_id"].values
    lats = stations_gdf["lat"].values
    lons = stations_gdf["lon"].values

    for b in range(n_batches):
        start = b * batch_size
        end = min(start + batch_size, n)

        features = []
        for i in range(start, end):
            pt = ee.Geometry.Point([float(lons[i]), float(lats[i])])
            feat = ee.Feature(pt, {"station_id": sids[i]})
            features.append(feat)

        fc = ee.FeatureCollection(features)
        fc_buffered = fc.map(lambda f: f.setGeometry(f.geometry().buffer(buffer_m)))
        result = glc10.reduceRegions(
            collection=fc_buffered,
            reducer=ee.Reducer.mode(),
            scale=30,
        )
        result_flat = result.map(lambda f: f.setGeometry(None))

        desc = f"isd_glc10_cropland_{b:02d}"
        task = ee.batch.Export.table.toCloudStorage(
            collection=result_flat,
            description=desc,
            bucket=bucket,
            fileNamePrefix=desc,
            fileFormat="CSV",
        )
        task.start()

        status = task.status()
        print(
            f"    batch {b + 1}/{n_batches}: {end - start} stations -> {desc} ({status['id'][:8]}...)"
        )

    print("\n  Monitor: https://code.earthengine.google.com/tasks")
    print(f"  Output: gs://{bucket}/isd_glc10_cropland_*.csv")
    print("\n  When all tasks complete, download and merge:")
    print(f"    gsutil cp 'gs://{bucket}/isd_glc10_cropland_*.csv' {OUT_DIR}/")
    cat_cmd = f"head -1 {OUT_DIR}/isd_glc10_cropland_00.csv > {OUT_DIR}/isd_glc10_cropland.csv"
    cat_cmd += (
        f" && tail -n +2 -q {OUT_DIR}/isd_glc10_cropland_*.csv >> {OUT_DIR}/isd_glc10_cropland.csv"
    )
    print(f"    {cat_cmd}")
    print(f"    python {__file__} --glc10-csv {OUT_DIR}/isd_glc10_cropland.csv")


def load_glc10_cropland_sids(csv_path):
    """Read exported GLC10 CSV, return set of station_ids on cropland."""
    df = pd.read_csv(csv_path)
    df["mode"] = pd.to_numeric(df["mode"], errors="coerce")
    has_lc = df["mode"].notna()
    # EE mode reducer returns float with precision noise; round to int
    cropland = df[has_lc & (df["mode"].round() == GLC10_CROPLAND)]
    n_nodata = (~has_lc).sum()
    print(
        f"    {len(df)} stations in CSV, {n_nodata} with no GLC10 data, {len(cropland)} on cropland"
    )
    return set(cropland["station_id"])


def find_nearest(flux_sites, stations, n=N_NEIGHBORS):
    """For each flux site, find n nearest qualifying stations by geodesic distance."""
    geod = Geod(ellps="WGS84")
    result = {}

    s_lons = stations["lon"].values
    s_lats = stations["lat"].values
    s_sids = stations["station_id"].values

    for _, site in flux_sites.iterrows():
        _, _, dists = geod.inv(
            np.full(len(s_lons), site["lon"]),
            np.full(len(s_lats), site["lat"]),
            s_lons,
            s_lats,
        )
        dists_km = np.abs(dists) / 1000.0
        idx = np.argsort(dists_km)[:n]
        result[site["sid"]] = {
            "stations": s_sids[idx].tolist(),
            "distances_km": [round(dists_km[i], 2) for i in idx],
        }

    return result


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--export-lc", action="store_true", help="Submit EE export task for GLC10 zonal mode"
    )
    group.add_argument("--glc10-csv", type=str, help="Path to exported GLC10 CSV from EE")
    group.add_argument("--skip-lc", action="store_true", help="Skip land cover check entirely")
    args = parser.parse_args()

    print("Loading flux sites...")
    flux_sites = load_flux_sites()
    print(f"  {len(flux_sites)} sites")

    print("Filtering ISD stations...")
    stations = filter_isd_stations()
    print(f"  {len(stations)} ISD stations pass filters")

    # --- Phase 1: export only ---
    if args.export_lc:
        print("\nSubmitting EE export task for GLC10 land cover...")
        export_glc10_task(stations)
        sys.exit(0)

    # --- Phase 2 or skip: filter + select ---
    if args.glc10_csv:
        print(f"\nFiltering to GLC10 cropland from {args.glc10_csv}...")
        cropland_sids = load_glc10_cropland_sids(args.glc10_csv)
        stations = stations[stations["station_id"].isin(cropland_sids)].copy()
        print(f"  {len(stations)} stations after cropland filter")
    elif not args.skip_lc:
        print("ERROR: specify --export-lc, --glc10-csv <path>, or --skip-lc")
        sys.exit(1)

    print(f"\nFinding {N_NEIGHBORS} nearest stations per flux site...")
    selected = find_nearest(flux_sites, stations)

    for sid, data in sorted(selected.items()):
        dists = data["distances_km"]
        nearest = f"{dists[0]:.0f}" if dists else "N/A"
        farthest = f"{dists[-1]:.0f}" if dists else "N/A"
        print(f"    {sid}: nearest={nearest} km, farthest={farthest} km")

    print(f"\nWriting {OUT_FILE}")
    with open(OUT_FILE, "w") as f:
        json.dump(selected, f, indent=2)

    n_with = sum(1 for v in selected.values() if v["stations"])
    print(f"  {n_with} sites with stations, {len(selected) - n_with} without")


if __name__ == "__main__":
    main()
