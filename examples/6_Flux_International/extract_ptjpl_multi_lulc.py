"""
Extract PT-JPL ETf for the 241-site multi-LULC international flux network.

Uses the same ERA5LAND-based openet-ptjpl approach as the existing Example 6
extraction (data_extract.py --etf), applied to the expanded 23MAR2026 shapefile
which covers cropland, forest, grassland, and shrubland sites.

Wetland sites (MODIS=11) are excluded from the shapefile.

Output:
    gs://wudr/7_Flux_Multi_LULC/remote_sensing/landsat/extracts/ptjpl_etf/no_mask/

Requires openet-ptjpl >= 0.5.0 (era5land-updates branch):
    uv pip install -e /home/dgketchum/code/openet-ptjpl

Usage:
    uv run python extract_ptjpl_multi_lulc.py
    uv run python extract_ptjpl_multi_lulc.py --sites US-NR1,AU-How,DE-Hai
    uv run python extract_ptjpl_multi_lulc.py --overwrite
"""

import argparse
import os
import sys
from pathlib import Path

# Make the local etf/ package (ERA5LAND version) importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

SHAPEFILE = "/nas/climate/flux_stations/stations/flux_intl_150m_23MAR2026.shp"
BUCKET = "wudr"
FILE_PREFIX = "6_Flux_International"
FEATURE_ID = "sid"
START_YR = 1995
END_YR = 2025
BATCH_SIZE = 15

# Local check dir — existing 64-site CSVs live here; new sites will be skipped only once extracted
CHECK_DIR = (
    "/data/ssd1/swim/6_Flux_International/data/remote_sensing/landsat/extracts/ptjpl_etf/no_mask"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", type=str, default=None, help="Comma-separated site IDs")
    parser.add_argument("--overwrite", action="store_true", help="Re-export even if files exist")
    parser.add_argument("--project", type=str, default="ee-dgketchum", help="EE project ID")
    args = parser.parse_args()

    from swimrs.data_extraction.ee.ee_utils import is_authorized

    is_authorized(project=args.project)

    from etf import export_ptjpl_zonal_stats

    sites = args.sites.split(",") if args.sites else None
    chk_dir = None if args.overwrite else CHECK_DIR

    if chk_dir and not os.path.isdir(chk_dir):
        print(f"  check_dir {chk_dir} does not exist — running without skip check")
        chk_dir = None

    print(f"\n{'=' * 60}")
    print("Extracting PT-JPL ETf (ERA5LAND) — multi-LULC international")
    print(f"  shapefile : {SHAPEFILE}")
    print(f"  years     : {START_YR}–{END_YR}")
    print(f"  sites     : {sites or 'all'}")
    print(f"  check_dir : {chk_dir or 'none (overwrite)'}")
    print(f"{'=' * 60}\n")

    export_ptjpl_zonal_stats(
        shapefile=SHAPEFILE,
        bucket=BUCKET,
        feature_id=FEATURE_ID,
        select=sites,
        start_yr=START_YR,
        end_yr=END_YR,
        check_dir=chk_dir,
        buffer=None,
        batch_size=BATCH_SIZE,
        file_prefix=FILE_PREFIX,
    )


if __name__ == "__main__":
    main()
