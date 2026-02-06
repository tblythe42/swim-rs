"""
Convert ECOSTRESS daily ET to ET fraction (ETf) using ERA5-Land ETo.

ECOSTRESS provides daily ET in mm/day from zonal statistics over flux tower buffers.
This script divides by ERA5-Land daily reference ET (ETo) to produce ETf = ET / ETo,
matching the same quantity that Landsat PT-JPL provides.

Output CSVs follow the same naming and column convention as Landsat ETf extracts
so they can be ingested by container.ingest.etf(instrument="ecostress").

Usage:
    python ecostress_etf_convert.py [--min-count 5] [--min-eto 0.5]
"""

import json
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


def load_ecostress_extract(json_path: str) -> dict[str, dict[str, dict]]:
    """Load ECOSTRESS zonal statistics JSON.

    Returns dict: {site_id: {date_str: {mean, min, max, count, std}}}
    """
    with open(json_path) as f:
        return json.load(f)


def load_era5_eto(era5_dir: str, sites: list[str]) -> pd.DataFrame:
    """Load ERA5-Land daily ETo for the given sites.

    Parses monthly CSVs with columns like eto_YYYYMMDD.

    Returns DataFrame with DatetimeIndex and site columns.
    """
    csv_files = sorted(Path(era5_dir).glob("era5_vars_*.csv"))
    all_series = {site: {} for site in sites}
    sites_set = set(sites)

    for csv_file in csv_files:
        df = pd.read_csv(csv_file)

        # Identify UID column
        uid_col = None
        for col in ["sid", "SID", "FID", "fid", "site_id"]:
            if col in df.columns:
                uid_col = col
                break
        if uid_col is None:
            continue

        df[uid_col] = df[uid_col].astype(str)
        df = df[df[uid_col].isin(sites_set)]
        if df.empty:
            continue

        # Extract eto columns
        eto_cols = [c for c in df.columns if c.startswith("eto_")]
        for _, row in df.iterrows():
            site = str(row[uid_col])
            for col in eto_cols:
                date_str = col.split("_", 1)[1]
                if len(date_str) == 8 and date_str.isdigit():
                    val = row[col]
                    if pd.notna(val):
                        all_series[site][date_str] = float(val)

    # Build DataFrame
    result_series = []
    for site in sites:
        if all_series[site]:
            dates = [pd.to_datetime(d) for d in all_series[site].keys()]
            values = list(all_series[site].values())
            s = pd.Series(values, index=dates, name=site)
            result_series.append(s)

    if not result_series:
        return pd.DataFrame()

    return pd.concat(result_series, axis=1).sort_index()


def convert_et_to_etf(
    ecostress_data: dict,
    eto_df: pd.DataFrame,
    sites: list[str],
    min_count: int = 5,
    min_eto: float = 0.5,
    max_etf: float = 2.0,
) -> dict[str, pd.Series]:
    """Convert ECOSTRESS daily ET to ETf by dividing by ERA5-Land ETo.

    Args:
        ecostress_data: Raw ECOSTRESS extract {site: {date: stats}}
        eto_df: ERA5-Land ETo DataFrame (dates x sites)
        sites: List of site IDs to process
        min_count: Minimum pixel count for a valid ECOSTRESS observation
        min_eto: Minimum ETo (mm/day) to avoid division by near-zero
        max_etf: Maximum allowed ETf value (clip outliers)

    Returns:
        Dict of {site_id: pd.Series} with ETf values indexed by date
    """
    etf_results = {}

    for site in sites:
        if site not in ecostress_data:
            continue
        if site not in eto_df.columns:
            continue

        site_eto = eto_df[site]
        site_et_data = ecostress_data[site]

        dates = []
        etf_values = []

        for date_str, stats in site_et_data.items():
            # Filter by pixel count
            if stats.get("count", 0) < min_count:
                continue

            et_mean = stats.get("mean")
            if et_mean is None or np.isnan(et_mean) or et_mean < 0:
                continue

            # Look up ETo for this date
            dt = pd.to_datetime(date_str)
            if dt not in site_eto.index:
                continue

            eto = site_eto.loc[dt]
            if pd.isna(eto) or eto < min_eto:
                continue

            etf = et_mean / eto
            if etf > max_etf:
                continue

            dates.append(dt)
            etf_values.append(etf)

        if dates:
            etf_results[site] = pd.Series(etf_values, index=dates, name=site).sort_index()

    return etf_results


def write_etf_csvs(
    etf_results: dict[str, pd.Series],
    output_dir: str,
    uid_column: str = "sid",
):
    """Write per-year ETf CSVs in the Earth Engine export format.

    Each CSV has one row per site, with columns named ETF_YYYYMMDD.
    Files are named etf_{site}_{mask}_{year}.csv to match the
    ingestor's mask-filtering logic.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Group by year across all sites
    year_site_data = {}
    for site, series in etf_results.items():
        for year in series.index.year.unique():
            year = int(year)
            if year not in year_site_data:
                year_site_data[year] = {}
            mask = series.index.year == year
            year_site_data[year][site] = series[mask]

    files_written = 0
    for year, site_data in sorted(year_site_data.items()):
        for site, series in site_data.items():
            if series.empty:
                continue

            # Build row: uid_column value followed by ETf values at each date
            col_names = [uid_column]
            values = [site]

            for dt, val in series.items():
                col_name = f"ETF_{dt.strftime('%Y%m%d')}"
                col_names.append(col_name)
                values.append(val)

            df = pd.DataFrame([values], columns=col_names)

            fname = f"etf_{site}_no_mask_{year}.csv"
            df.to_csv(os.path.join(output_dir, fname), index=False)
            files_written += 1

    return files_written


def main(
    ecostress_json: str = None,
    era5_dir: str = None,
    shapefile: str = None,
    output_dir: str = None,
    uid_column: str = "sid",
    min_count: int = 5,
    min_eto: float = 0.5,
):
    """Run the full ECOSTRESS ET → ETf conversion pipeline."""
    # Default paths from project layout
    project_data = "/data/ssd1/swim/6_Flux_International/data"

    if ecostress_json is None:
        ecostress_json = os.path.join(
            project_data, "remote_sensing/ecostress/ecostress_extract_31DEC2025.json"
        )
    if era5_dir is None:
        era5_dir = os.path.join(project_data, "meteorology/era5_land")
    if shapefile is None:
        shapefile = os.path.join(project_data, "gis/flux_intl_buffers_150m_06JAN2026.shp")
    if output_dir is None:
        output_dir = os.path.join(project_data, "remote_sensing/ecostress/extracts/etf/no_mask")

    # Load site list from shapefile
    gdf = gpd.read_file(shapefile)
    sites = sorted(gdf[uid_column].astype(str).unique().tolist())
    print(f"Sites from shapefile: {len(sites)}")

    # Load ECOSTRESS extract
    print(f"Loading ECOSTRESS extract: {ecostress_json}")
    eco_data = load_ecostress_extract(ecostress_json)
    eco_sites = [s for s in sites if s in eco_data]
    print(f"  Sites with ECOSTRESS data: {len(eco_sites)}/{len(sites)}")

    total_obs = sum(len(eco_data[s]) for s in eco_sites)
    print(f"  Total ECOSTRESS observations: {total_obs}")

    # Load ERA5-Land ETo
    print(f"Loading ERA5-Land ETo from: {era5_dir}")
    eto_df = load_era5_eto(era5_dir, sites)
    print(f"  ETo loaded: {len(eto_df)} days, {len(eto_df.columns)} sites")

    # Convert ET → ETf
    print("Converting ET to ETf...")
    etf_results = convert_et_to_etf(
        eco_data, eto_df, eco_sites, min_count=min_count, min_eto=min_eto
    )
    print(f"  Sites with valid ETf: {len(etf_results)}/{len(eco_sites)}")

    total_etf_obs = sum(len(s) for s in etf_results.values())
    print(f"  Total ETf observations: {total_etf_obs}")

    # Spot-check ETf values
    if etf_results:
        all_etf = pd.concat(etf_results.values())
        print(f"  ETf range: [{all_etf.min():.3f}, {all_etf.max():.3f}]")
        print(f"  ETf median: {all_etf.median():.3f}")
        print(f"  ETf mean: {all_etf.mean():.3f}")

    # Write CSVs
    print(f"Writing ETf CSVs to: {output_dir}")
    n_files = write_etf_csvs(etf_results, output_dir, uid_column=uid_column)
    print(f"  Wrote {n_files} CSV files")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert ECOSTRESS daily ET to ETf")
    parser.add_argument("--ecostress-json", type=str, default=None)
    parser.add_argument("--era5-dir", type=str, default=None)
    parser.add_argument("--shapefile", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--min-count", type=int, default=5)
    parser.add_argument("--min-eto", type=float, default=0.5)
    args = parser.parse_args()

    main(
        ecostress_json=args.ecostress_json,
        era5_dir=args.era5_dir,
        shapefile=args.shapefile,
        output_dir=args.output_dir,
        min_count=args.min_count,
        min_eto=args.min_eto,
    )
