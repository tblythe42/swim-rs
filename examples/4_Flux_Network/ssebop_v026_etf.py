"""Extract SSEBop ETf using openet-ssebop v0.2.6 (Tcorr FANO, same as NHM asset).

Uses per-scene reduceRegion + getInfo() to avoid projection errors that occur
when clipping or stacking v0.2.6 ETf images (mixed UTM/5km/1km CRS inputs).

Writes one CSV per site-year to local disk, matching the NHM extract format:
  header: site_id, scene1, scene2, ...
  row:    US-ARM, 0.42, 0.87, ...

By default, discovers site+year combos from existing NHM CSVs in ssebop_etf/no_mask/.
Use --sites and --start-yr/--end-yr to override.

Requires the isolated venv at /tmp/ssebop026_venv with openet-ssebop==0.2.6.

Usage:
    /tmp/ssebop026_venv/bin/python ssebop_v026_etf.py
    /tmp/ssebop026_venv/bin/python ssebop_v026_etf.py --sites US-ARM,US-Ne1 --start-yr 2010 --end-yr 2012
"""

import csv
import os
import re
from pathlib import Path

import ee
import geopandas as gpd
import openet.ssebop as ssebop
from tqdm import tqdm

LANDSAT_COLLECTIONS = [
    "LANDSAT/LT05/C02/T1_L2",
    "LANDSAT/LE07/C02/T1_L2",
    "LANDSAT/LC08/C02/T1_L2",
    "LANDSAT/LC09/C02/T1_L2",
]


def parse_scene_name(scene_id):
    """Convert full scene ID to compact name: {sensor}_{pathrow}_{date}."""
    parts = scene_id.split("/")[-1].split("_")
    if len(parts) >= 3:
        return f"{parts[0]}_{parts[1]}_{parts[2]}"
    return scene_id.split("/")[-1]


def extract_etf(scene_id, polygon):
    """Compute v0.2.6 ETf for a single scene and return mean over polygon.

    Returns (scene_name, etf_value) or (scene_name, None) on error.
    """
    name = parse_scene_name(scene_id)
    try:
        img = ssebop.Image.from_landsat_c2_sr(scene_id, et_fraction_type="grass")
        etf = img.et_fraction
        result = etf.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=polygon,
            scale=30,
            maxPixels=1e9,
        ).getInfo()
        val = result.get("et_fraction")
        return name, val
    except Exception as e:
        print(f"    {name}: error — {e}")
        return name, None


def discover_site_years(nhm_dir):
    """Parse NHM CSV filenames to get (site, year) pairs."""
    pattern = re.compile(r"ssebop_etf_(.+)_no_mask_(\d{4})\.csv")
    pairs = []
    for fn in sorted(os.listdir(nhm_dir)):
        m = pattern.match(fn)
        if m:
            pairs.append((m.group(1), int(m.group(2))))
    return pairs


def main():
    import argparse

    parser = argparse.ArgumentParser(description="SSEBop v0.2.6 ETf extract")
    parser.add_argument(
        "--sites", type=str, default=None, help="Comma-separated site IDs (default: all NHM sites)"
    )
    parser.add_argument("--start-yr", type=int, default=None)
    parser.add_argument("--end-yr", type=int, default=None)
    args = parser.parse_args()

    ee.Initialize()

    project_dir = Path(__file__).resolve().parent
    if os.path.isdir("/data/ssd1/swim/4_Flux_Network"):
        data_root = "/data/ssd1/swim/4_Flux_Network/data"
    else:
        data_root = str(project_dir / "data")

    shapefile = os.path.join(data_root, "gis", "flux_fields.shp")
    gdf = gpd.read_file(shapefile, engine="fiona").to_crs(epsg=4326)

    nhm_dir = os.path.join(
        data_root,
        "remote_sensing",
        "landsat",
        "extracts",
        "ssebop_etf",
        "no_mask",
    )
    out_dir = os.path.join(
        data_root,
        "remote_sensing",
        "landsat",
        "extracts",
        "ssebop_v026_etf",
        "no_mask",
    )
    os.makedirs(out_dir, exist_ok=True)

    # Build work list — use NHM CSVs for discovery, but when an explicit
    # year range extends beyond the NHM asset (e.g. 2024-2025), generate
    # site-year pairs directly from the shapefile.
    all_pairs = discover_site_years(nhm_dir)
    if args.sites:
        keep_sites = {s.strip() for s in args.sites.split(",")}
    else:
        keep_sites = None

    if args.start_yr and args.end_yr:
        # Determine sites: either explicit list or all shapefile sites
        nhm_sites = sorted({s for s, _ in all_pairs})
        sites_list = sorted(keep_sites) if keep_sites else nhm_sites
        if not sites_list:
            sites_list = sorted(gdf["site_id"].unique())
        all_pairs = [(s, y) for s in sites_list for y in range(args.start_yr, args.end_yr + 1)]
    else:
        if keep_sites:
            all_pairs = [(s, y) for s, y in all_pairs if s in keep_sites]
        if args.start_yr:
            all_pairs = [(s, y) for s, y in all_pairs if y >= args.start_yr]
        if args.end_yr:
            all_pairs = [(s, y) for s, y in all_pairs if y <= args.end_yr]

    # Skip already-completed
    todo = []
    for site, year in all_pairs:
        out_csv = os.path.join(out_dir, f"ssebop_etf_{site}_no_mask_{year}.csv")
        if not os.path.exists(out_csv):
            todo.append((site, year))

    print(
        f"SSEBop v0.2.6 ETf: {len(todo)} site-years to process "
        f"({len(all_pairs) - len(todo)} already done)"
    )
    print(f"Output: {out_dir}")

    # Cache ee.Geometry per site
    geom_cache = {}

    for i, (site, year) in enumerate(todo):
        if site not in geom_cache:
            row = gdf[gdf["site_id"] == site]
            if row.empty:
                print(f"  {site}: not in shapefile, skipping")
                geom_cache[site] = None
                continue
            geom = row.iloc[0].geometry
            if geom.geom_type not in ("Polygon", "MultiPolygon"):
                geom_cache[site] = None
                continue
            geom_cache[site] = ee.Geometry(geom.__geo_interface__)

        polygon = geom_cache[site]
        if polygon is None:
            continue

        out_csv = os.path.join(out_dir, f"ssebop_etf_{site}_no_mask_{year}.csv")

        coll = ssebop.Collection(
            LANDSAT_COLLECTIONS,
            start_date=f"{year}-01-01",
            end_date=f"{year}-12-31",
            geometry=polygon,
            cloud_cover_max=70,
        )
        scenes = coll.get_image_ids()
        scenes = sorted(set(scenes), key=lambda s: s.split("_")[-1])

        if not scenes:
            print(f"  [{i + 1}/{len(todo)}] {site} {year}: no scenes")
            continue

        print(f"  [{i + 1}/{len(todo)}] {site} {year}: {len(scenes)} scenes")

        names = []
        values = []
        for scene_id in tqdm(scenes, desc=f"  {site} {year}", leave=False):
            name, val = extract_etf(scene_id, polygon)
            names.append(name)
            values.append(val if val is not None else "")

        with open(out_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["site_id"] + names)
            writer.writerow([site] + values)

        n_valid = sum(1 for v in values if v != "")
        print(f"    wrote {os.path.basename(out_csv)} ({n_valid}/{len(names)} valid)")

    print("\nDone.")


if __name__ == "__main__":
    main()
