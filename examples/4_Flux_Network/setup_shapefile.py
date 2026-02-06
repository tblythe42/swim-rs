#!/usr/bin/env python
"""
Setup Flux Fields Shapefile for Example 4 (Flux Network)
=========================================================

This script creates the flux stations shapefile for the full network
(~160 stations) by combining shipped footprints and metadata.

Usage
-----
    python setup_shapefile.py

Output path is read from 4_Flux_Network.toml (fields_shapefile setting).
"""

import argparse
import os
import sys

# Add project root to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))
sys.path.insert(0, ROOT_DIR)

from swimrs.swim.config import ProjectConfig
from swimrs.utils.flux_stations import create_master_shapefile

# Shipped data paths (relative to repo root)
FOOTPRINTS_SHP = os.path.join(ROOT_DIR, "examples", "data", "flux_footprints_3p_clean.shp")
METADATA_CSV = os.path.join(ROOT_DIR, "examples", "data", "station_metadata.csv")


def _get_output_path():
    """Get output shapefile path from TOML config."""
    toml_path = os.path.join(SCRIPT_DIR, "4_Flux_Network.toml")
    cfg = ProjectConfig()
    if os.path.isdir("/data/ssd1/swim"):
        cfg.read_config(toml_path)
    else:
        cfg.read_config(toml_path, project_root_override=os.path.join(SCRIPT_DIR, ".."))
    return cfg.fields_shapefile


def main():
    parser = argparse.ArgumentParser(
        description="Create flux stations shapefile for Example 4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing shapefile")
    args = parser.parse_args()

    # Verify shipped data exists
    if not os.path.exists(FOOTPRINTS_SHP):
        print(f"Error: Footprints shapefile not found: {FOOTPRINTS_SHP}")
        sys.exit(1)
    if not os.path.exists(METADATA_CSV):
        print(f"Error: Metadata CSV not found: {METADATA_CSV}")
        sys.exit(1)

    # Get output path from TOML config
    output_shapefile = _get_output_path()
    output_gis_dir = os.path.dirname(output_shapefile)

    # Create output directory if needed
    os.makedirs(output_gis_dir, exist_ok=True)

    print("\nCreating flux stations shapefile...")
    print(f"  Footprints: {FOOTPRINTS_SHP}")
    print(f"  Metadata:   {METADATA_CSV}")
    print(f"  Output:     {output_shapefile}")

    gdf = create_master_shapefile(
        FOOTPRINTS_SHP, METADATA_CSV, output_shapefile, overwrite=args.overwrite
    )

    print(f"\nDone! Created shapefile with {len(gdf)} stations: {output_shapefile}")


if __name__ == "__main__":
    main()
