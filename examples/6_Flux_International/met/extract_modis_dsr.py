"""Extract MODIS MCD18A1 daily surface downwelling shortwave radiation at ISD stations.

Uses Google Earth Engine to extract daily DSR (MJ/m²/d) from MCD18A1 at
selected ISD station locations. The 8 three-hourly GMT bands are summed
and converted from W/m² to MJ/m²/d.

Two-phase workflow:
  1. python extract_modis_dsr.py --export   # Submit EE batch export tasks (one per year)
  2. python extract_modis_dsr.py --process  # Download CSVs from GCS and split per station

Usage:
    python extract_modis_dsr.py --export
    python extract_modis_dsr.py --process
"""

import argparse
import json
from pathlib import Path

import pandas as pd

SELECTED = Path(__file__).parent / "selected_stations.json"
ISD_STATIONS = "/nas/climate/isd/indices/stations.parquet"
OUT_DIR = Path(__file__).parent / "modis_dsr"
GCS_DIR = Path(__file__).parent / "modis_dsr_gcs"

GCS_BUCKET = "wudr"
GCS_PREFIX = "isd_modis_dsr"

YEAR_START = 2000
YEAR_END = 2024

# 8 three-hourly DSR bands in W/m²; sum * 0.0108 -> MJ/m²/d
# 3 hours = 10800 seconds; W/m² * 10800 s = J/m²; / 1e6 = MJ/m²
# So factor = 10800 / 1e6 = 0.0108
WM2_3HR_TO_MJM2D = 0.0108

DSR_BANDS = [
    "GMT_0000_DSR",
    "GMT_0300_DSR",
    "GMT_0600_DSR",
    "GMT_0900_DSR",
    "GMT_1200_DSR",
    "GMT_1500_DSR",
    "GMT_1800_DSR",
    "GMT_2100_DSR",
]


def get_unique_stations():
    """Get deduplicated station IDs from selected_stations.json."""
    with open(SELECTED) as f:
        selected = json.load(f)
    stations = set()
    for site_data in selected.values():
        stations.update(site_data["stations"])
    return sorted(stations)


def get_station_coords(station_ids):
    """Get lat/lon for station IDs from ISD stations parquet."""
    stations = pd.read_parquet(ISD_STATIONS)
    stations = stations.set_index("station_id")
    return stations.loc[stations.index.isin(station_ids), ["lat", "lon"]]


def export_yearly_tasks(station_ids, coords):
    """Submit one EE export task per year (2000-2024)."""
    import ee

    ee.Initialize()

    # Build EE FeatureCollection of station points
    features = []
    for sid in station_ids:
        if sid not in coords.index:
            continue
        lat = float(coords.loc[sid, "lat"])
        lon = float(coords.loc[sid, "lon"])
        pt = ee.Geometry.Point([lon, lat])
        features.append(ee.Feature(pt, {"station_id": sid}))

    fc = ee.FeatureCollection(features)
    print(f"  {len(features)} station points in FeatureCollection")

    mcd18a1 = ee.ImageCollection("MODIS/062/MCD18A1")

    for year in range(YEAR_START, YEAR_END + 1):
        start = f"{year}-01-01"
        end = f"{year + 1}-01-01"

        yearly = mcd18a1.filterDate(start, end)

        def sum_dsr(image):
            daily_rsds = image.select(DSR_BANDS).reduce(ee.Reducer.sum()).multiply(WM2_3HR_TO_MJM2D)
            return daily_rsds.rename("rsds").set(
                "system:time_start", image.get("system:time_start")
            )

        daily_rsds = yearly.map(sum_dsr)

        def extract_at_stations(image):
            date_str = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd")
            reduced = image.reduceRegions(
                collection=fc,
                reducer=ee.Reducer.first().setOutputs(["rsds"]),
                scale=1000,
            )
            return reduced.map(lambda f: f.set("date", date_str).setGeometry(None))

        results = daily_rsds.map(extract_at_stations).flatten()

        desc = f"{GCS_PREFIX}_{year}"
        task = ee.batch.Export.table.toCloudStorage(
            collection=results,
            description=desc,
            bucket=GCS_BUCKET,
            fileNamePrefix=desc,
            fileFormat="CSV",
            selectors=["station_id", "date", "rsds"],
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


def process_gcs_csvs():
    """Download yearly CSVs from GCS dir and split into per-station files."""
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
        if "station_id" in df.columns and "date" in df.columns and "rsds" in df.columns:
            frames.append(df[["station_id", "date", "rsds"]])
            print(f"    {f.name}: {len(df)} rows")
        else:
            print(f"    {f.name}: unexpected columns {list(df.columns)}, skipping")

    if not frames:
        print("  No valid data found")
        return

    all_data = pd.concat(frames, ignore_index=True)
    all_data["date"] = pd.to_datetime(all_data["date"])
    all_data = all_data.sort_values(["station_id", "date"])

    # Drop rows where rsds is null (no MODIS data for that day/location)
    all_data = all_data.dropna(subset=["rsds"])

    n_stations = all_data["station_id"].nunique()
    print(f"  {len(all_data)} total observations across {n_stations} stations")

    # Write per-station CSVs
    for sid, group in all_data.groupby("station_id"):
        out = group[["date", "rsds"]].copy()
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
        out.to_csv(OUT_DIR / f"{sid}.csv", index=False)

    print(f"  Wrote {n_stations} per-station CSVs to {OUT_DIR}")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--export", action="store_true", help="Submit EE batch export tasks")
    group.add_argument("--process", action="store_true", help="Process downloaded GCS CSVs")
    args = parser.parse_args()

    if args.export:
        print("Loading selected stations...")
        station_ids = get_unique_stations()
        print(f"  {len(station_ids)} unique stations")

        coords = get_station_coords(station_ids)
        station_ids = [s for s in station_ids if s in coords.index]
        print(f"  {len(station_ids)} with coordinates")

        print(f"Submitting EE export tasks ({YEAR_START}-{YEAR_END})...")
        export_yearly_tasks(station_ids, coords)

    elif args.process:
        print("Processing GCS CSVs into per-station files...")
        process_gcs_csvs()


if __name__ == "__main__":
    main()
