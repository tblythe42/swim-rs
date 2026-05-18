# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "earthengine-api",
#   "geopandas",
#   "fiona",
# ]
# ///
"""Build WRS-2 union geometry for SSEBop v0.2.6 international climatology exports.

Discovers Landsat WRS-2 path/rows that intersect the Example 6 flux sites
by spatial intersection with a local WRS-2 descending shapefile, unions their
footprints, and writes the result as a local GeoJSON and a path/row manifest.
The union geometry is used as the export region for the tmax and dt climatology
builders.

Usage:
    uv run ssebop_v026_wrs2_union.py
    uv run ssebop_v026_wrs2_union.py --sites US-ARM,DE-Kli,AU-Tum
    uv run ssebop_v026_wrs2_union.py --wrs2-shp /path/to/WRS2_descending.shp
"""

import argparse
import json
import os

import geopandas as gpd

DEFAULT_WRS2_SHP = "/nas/boundaries/wrs2_descending/WRS2_descending_0/WRS2_descending.shp"


def discover_pathrows_local(sites_gdf, wrs2_gdf):
    """Find WRS-2 path/rows that intersect any site polygon via spatial join.

    Returns (set of (path, row) tuples, GeoDataFrame of matched WRS-2 footprints).
    """
    # Ensure both are in the same CRS
    if sites_gdf.crs != wrs2_gdf.crs:
        sites_gdf = sites_gdf.to_crs(wrs2_gdf.crs)

    # Spatial join: which WRS-2 footprints intersect any site?
    joined = gpd.sjoin(wrs2_gdf, sites_gdf, how="inner", predicate="intersects")

    # Unique path/rows
    pathrows = set()
    matched_indices = set()
    for idx, row in joined.iterrows():
        pr = (int(row["PATH"]), int(row["ROW"]))
        pathrows.add(pr)
        matched_indices.add(idx)

    matched_gdf = wrs2_gdf.loc[list(matched_indices)].drop_duplicates(subset=["PATH", "ROW"])
    return pathrows, matched_gdf


def main():
    parser = argparse.ArgumentParser(description="Build WRS-2 union for SSEBop climatology")
    parser.add_argument("--sites", type=str, default=None, help="Comma-separated site IDs")
    parser.add_argument(
        "--wrs2-shp",
        default=DEFAULT_WRS2_SHP,
        help="Path to WRS-2 descending footprint shapefile",
    )
    parser.add_argument("--project", default="ee-dgketchum", help="EE project ID (for EE union)")
    args = parser.parse_args()

    # Load sites
    if os.path.isdir("/data/ssd1/swim/6_Flux_International"):
        data_root = "/data/ssd1/swim/6_Flux_International/data"
    else:
        data_root = os.path.join(os.path.dirname(__file__), "data")

    shapefile = os.path.join(data_root, "gis", "flux_intl_150m_23MAR2026.shp")
    gdf = gpd.read_file(shapefile, engine="fiona")

    if args.sites:
        sites = [s.strip() for s in args.sites.split(",")]
        gdf = gdf[gdf["sid"].isin(sites)]

    print(f"Sites: {len(gdf)}")

    # Load WRS-2 footprints
    if not os.path.exists(args.wrs2_shp):
        raise FileNotFoundError(f"WRS-2 shapefile not found: {args.wrs2_shp}")

    print(f"Loading WRS-2 footprints: {args.wrs2_shp}")
    wrs2 = gpd.read_file(args.wrs2_shp, engine="fiona")
    print(f"  WRS-2 features: {len(wrs2)}")

    # Discover intersecting path/rows via spatial join
    print("Finding intersecting WRS-2 footprints...")
    pathrows, matched_gdf = discover_pathrows_local(gdf, wrs2)
    print(f"  Unique path/rows: {len(pathrows)}")
    print(f"  Matched footprints: {len(matched_gdf)}")

    if not pathrows:
        print("ERROR: No path/rows found. Check site locations and WRS-2 shapefile.")
        return

    # Build union geometry locally
    print("Building WRS-2 union geometry...")
    union_geom = matched_gdf.geometry.unary_union
    union_gdf = gpd.GeoDataFrame(geometry=[union_geom], crs=matched_gdf.crs)
    # Convert to WGS84 for GeoJSON
    union_gdf_4326 = union_gdf.to_crs(epsg=4326)
    union_geojson = union_gdf_4326.geometry.iloc[0].__geo_interface__

    # Write outputs
    out_dir = os.path.join(data_root, "gis")
    os.makedirs(out_dir, exist_ok=True)

    # Path/row manifest
    manifest = {
        "sites": sorted(gdf["sid"].tolist()),
        "n_sites": len(gdf),
        "wrs2_source": args.wrs2_shp,
        "pathrows": sorted([f"{p:03d}{r:03d}" for p, r in pathrows]),
        "n_pathrows": len(pathrows),
        "n_footprints": len(matched_gdf),
    }
    manifest_path = os.path.join(out_dir, "wrs2_pathrow_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Wrote manifest: {manifest_path}")

    # Union geometry GeoJSON
    geojson_path = os.path.join(out_dir, "wrs2_union.geojson")
    geojson_fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": union_geojson, "properties": manifest}],
    }
    with open(geojson_path, "w") as f:
        json.dump(geojson_fc, f)
    print(f"  Wrote union geometry: {geojson_path}")

    # Also write matched footprints for inspection
    matched_path = os.path.join(out_dir, "wrs2_matched_footprints.shp")
    matched_gdf.to_file(matched_path, engine="fiona")
    print(f"  Wrote matched footprints: {matched_path}")

    # Summary
    print("\n=== WRS-2 Union Summary ===")
    print(f"  Sites: {len(gdf)}")
    print(f"  Path/rows: {len(pathrows)}")
    print(f"  Footprints: {len(matched_gdf)}")
    print("  Use wrs2_union.geojson as --region for tmax and dt builders")


if __name__ == "__main__":
    main()
