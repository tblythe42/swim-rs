# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "earthengine-api",
#   "geopandas",
#   "fiona",
# ]
# ///
"""Build WRS-2 union geometry for SSEBop v0.2.6 international climatology exports.

Discovers Landsat WRS-2 path/rows that intersect the Example 6 flux sites,
unions their footprints, and writes the result as a local GeoJSON and a
path/row manifest. The union geometry is used as the export region for the
tmax and dt climatology builders.

Usage:
    uv run ssebop_v026_wrs2_union.py
    uv run ssebop_v026_wrs2_union.py --sites US-ARM,DE-Kli,AU-Tum
"""

import argparse
import json
import os

import ee
import geopandas as gpd

WRS2_COLLECTION = "projects/google/wrs2_descending"

LANDSAT_COLLECTIONS = [
    "LANDSAT/LT05/C02/T1_L2",
    "LANDSAT/LE07/C02/T1_L2",
    "LANDSAT/LC08/C02/T1_L2",
    "LANDSAT/LC09/C02/T1_L2",
]


def discover_pathrows(site_geom, start_year=2013, end_year=2023, project="ee-dgketchum"):
    """Find unique Landsat WRS-2 path/rows intersecting a geometry.

    Uses a representative date span (default 2013-2023) to capture L7, L8, L9
    scene coverage. Returns set of (path, row) tuples.
    """
    pathrows = set()
    for coll_id in LANDSAT_COLLECTIONS:
        try:
            coll = (
                ee.ImageCollection(coll_id)
                .filterBounds(site_geom)
                .filterDate(f"{start_year}-01-01", f"{end_year}-12-31")
                .limit(5000)
            )
            ids = coll.aggregate_array("system:index").getInfo()
            for sid in ids:
                parts = sid.split("_")
                if len(parts) >= 3:
                    pathrow = parts[1]  # e.g., "044033"
                    if len(pathrow) == 6:
                        path = int(pathrow[:3])
                        row = int(pathrow[3:])
                        pathrows.add((path, row))
        except Exception as e:
            print(f"  Warning: {coll_id}: {e}")
    return pathrows


def build_wrs2_union(pathrows, project="ee-dgketchum"):
    """Build union geometry from WRS-2 footprints for given path/rows.

    Returns (ee.Geometry, GeoJSON dict).
    """
    wrs2 = ee.FeatureCollection(WRS2_COLLECTION)

    # Build filter for all path/rows
    filters = []
    for path, row in pathrows:
        filters.append(ee.Filter.And(ee.Filter.eq("PATH", path), ee.Filter.eq("ROW", row)))

    if not filters:
        raise ValueError("No path/rows to union")

    combined_filter = filters[0]
    for f in filters[1:]:
        combined_filter = ee.Filter.Or(combined_filter, f)

    selected = wrs2.filter(combined_filter)
    n_selected = selected.size().getInfo()
    print(f"  WRS-2 footprints matched: {n_selected} (from {len(pathrows)} path/rows)")

    union_geom = selected.geometry().dissolve(maxError=100)
    geojson = union_geom.getInfo()

    return union_geom, geojson, n_selected


def main():
    parser = argparse.ArgumentParser(description="Build WRS-2 union for SSEBop climatology")
    parser.add_argument("--sites", type=str, default=None, help="Comma-separated site IDs")
    parser.add_argument("--project", default="ee-dgketchum", help="EE project ID")
    parser.add_argument("--start-year", type=int, default=2013, help="Scene discovery start year")
    parser.add_argument("--end-year", type=int, default=2023, help="Scene discovery end year")
    args = parser.parse_args()

    ee.Initialize(project=args.project)

    # Load sites
    if os.path.isdir("/data/ssd1/swim/6_Flux_International"):
        data_root = "/data/ssd1/swim/6_Flux_International/data"
    else:
        data_root = os.path.join(os.path.dirname(__file__), "data")

    shapefile = os.path.join(data_root, "gis", "flux_intl_150m_23MAR2026.shp")
    gdf = gpd.read_file(shapefile, engine="fiona").to_crs(epsg=4326)

    if args.sites:
        sites = [s.strip() for s in args.sites.split(",")]
        gdf = gdf[gdf["sid"].isin(sites)]
    else:
        sites = sorted(gdf["sid"].tolist())

    print(f"Sites: {len(gdf)}")

    # Dissolve site polygons into union for scene discovery
    site_union = gdf.geometry.unary_union
    site_geom_ee = ee.Geometry(site_union.__geo_interface__)

    # Discover path/rows
    print(f"Discovering Landsat scenes ({args.start_year}-{args.end_year})...")
    pathrows = discover_pathrows(
        site_geom_ee, start_year=args.start_year, end_year=args.end_year, project=args.project
    )
    print(f"  Unique path/rows: {len(pathrows)}")

    if not pathrows:
        print("ERROR: No path/rows found. Check site locations and date range.")
        return

    # Build WRS-2 union
    print("Building WRS-2 union geometry...")
    union_geom_ee, union_geojson, n_matched = build_wrs2_union(pathrows, project=args.project)

    # Write outputs
    out_dir = os.path.join(data_root, "gis")
    os.makedirs(out_dir, exist_ok=True)

    # Path/row manifest
    manifest = {
        "sites": sorted(gdf["sid"].tolist()),
        "n_sites": len(gdf),
        "discovery_years": f"{args.start_year}-{args.end_year}",
        "pathrows": sorted([f"{p:03d}{r:03d}" for p, r in pathrows]),
        "n_pathrows": len(pathrows),
        "n_wrs2_matched": n_matched,
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

    # Summary
    print("\n=== WRS-2 Union Summary ===")
    print(f"  Sites: {len(gdf)}")
    print(f"  Path/rows: {len(pathrows)}")
    print(f"  WRS-2 footprints: {n_matched}")
    print("  Use this geometry as --region for tmax and dt builders")


if __name__ == "__main__":
    main()
