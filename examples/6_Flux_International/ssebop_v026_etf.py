# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "openet-ssebop==0.2.6",
#   "earthengine-api",
#   "geopandas",
#   "fiona",
#   "tqdm",
# ]
# ///
"""Extract SSEBop ETf using openet-ssebop v0.2.6 for international sites.

For international use, the default CONUS-only dT (Daymet) and land cover
(NALCMS) assets must be replaced with global equivalents. Build a global dT
climatology via the ssebop_v026_tmax_climo → dt_daily → dt_climo pipeline,
then pass the asset ID via --dt-source.

Per-scene reduceRegion + getInfo() avoids projection errors from mixed CRS.
Writes one CSV per site-year to local disk.

Prerequisites for international sites:
    1. Build Tmax climatology (ssebop_v026_tmax_climo.py)
    2. Build daily dT (ssebop_v026_dt_daily.py)
    3. Build dT DOY climatology (ssebop_v026_dt_climo.py)
    4. Pass the dT climo asset via --dt-source

Usage:
    uv run ssebop_v026_etf.py --dt-source <custom_dt_climo> --sites US-ARM,DE-Kli
    uv run ssebop_v026_etf.py --start-yr 2020 --end-yr 2022
"""

import csv
import importlib.util
import os
from pathlib import Path


def _apply_patches():
    """Patch openet-ssebop==0.2.6 in-place (idempotent).

    Must be called before `import openet.ssebop`.
    """
    spec = importlib.util.find_spec("openet.ssebop")
    if spec is None:
        raise ImportError("openet-ssebop not found — run via: uv run ssebop_v026_etf.py")
    pkg_dir = os.path.dirname(spec.origin)

    # Patch 1: image.py — select band 0 for projection() call.
    image_py = os.path.join(pkg_dir, "image.py")
    with open(image_py) as f:
        src = f.read()
    if "image.projection().crs()" in src:
        src = src.replace(
            "image.projection().crs()",
            "image.select([0]).projection().crs()",
        )
        src = src.replace(
            "ee.Algorithms.Describe(image.projection())",
            "ee.Algorithms.Describe(image.select([0]).projection())",
        )
        with open(image_py, "w") as f:
            f.write(src)
        print("[patch] image.py: projection fix applied")

    # Patch 2: model.py — remove .clamp(0, 1.0) so ETf > 1.0 is preserved.
    model_py = os.path.join(pkg_dir, "model.py")
    with open(model_py) as f:
        src = f.read()
    if ".clamp(0, 1.0).rename(['et_fraction'])" in src:
        src = src.replace(
            ".clamp(0, 1.0).rename(['et_fraction'])",
            ".max(0).rename(['et_fraction'])",
        )
        with open(model_py, "w") as f:
            f.write(src)
        print("[patch] model.py: clamp removed")


_apply_patches()

import ee  # noqa: E402
import geopandas as gpd  # noqa: E402
import openet.ssebop as ssebop  # noqa: E402
from tqdm import tqdm  # noqa: E402

LANDSAT_COLLECTIONS = [
    "LANDSAT/LT05/C02/T1_L2",
    "LANDSAT/LE07/C02/T1_L2",
    "LANDSAT/LC08/C02/T1_L2",
    "LANDSAT/LC09/C02/T1_L2",
]

# Default asset IDs — MUST be overridden for international use.
# The Daymet dT and NALCMS land cover are CONUS-only.
# Build global equivalents with ssebop_v026_tmax_climo.py + ssebop_v026_dt_daily.py
# + ssebop_v026_dt_climo.py, then pass --dt-source and --lc-source.
DEFAULT_DT_SOURCE = "projects/earthengine-legacy/assets/projects/usgs-ssebop/dt/daymet_median_v7"
DEFAULT_LC_SOURCE = "USGS/NLCD_RELEASES/2020_REL/NALCMS"


def parse_scene_name(scene_id):
    """Convert full scene ID to compact name: {sensor}_{pathrow}_{date}."""
    parts = scene_id.split("/")[-1].split("_")
    if len(parts) >= 3:
        return f"{parts[0]}_{parts[1]}_{parts[2]}"
    return scene_id.split("/")[-1]


def extract_etf(scene_id, polygon, dt_source, lc_source, et_fraction_type):
    """Compute v0.2.6 ETf for a single scene and return mean over polygon."""
    name = parse_scene_name(scene_id)
    try:
        img = ssebop.Image.from_landsat_c2_sr(
            scene_id,
            dt_source=dt_source,
            tcold_source="FANO",
            et_fraction_type=et_fraction_type,
            lc_source=lc_source,
        )
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


def main():
    import argparse

    parser = argparse.ArgumentParser(description="SSEBop v0.2.6 ETf international extract")
    parser.add_argument("--sites", type=str, default=None, help="Comma-separated site IDs")
    parser.add_argument("--start-yr", type=int, default=2000)
    parser.add_argument("--end-yr", type=int, default=2025)
    parser.add_argument(
        "--dt-source",
        type=str,
        default=DEFAULT_DT_SOURCE,
        help="EE ImageCollection ID for dT climatology",
    )
    parser.add_argument(
        "--lc-source",
        type=str,
        default=DEFAULT_LC_SOURCE,
        help="EE land cover asset for FANO ag mask",
    )
    parser.add_argument(
        "--et-fraction-type", type=str, default="alfalfa", choices=["alfalfa", "grass"]
    )
    parser.add_argument("--project", type=str, default="ee-dgketchum")
    args = parser.parse_args()

    ee.Initialize(project=args.project)

    # Paths
    if os.path.isdir("/data/ssd1/swim/6_Flux_International"):
        data_root = "/data/ssd1/swim/6_Flux_International/data"
    else:
        data_root = str(Path(__file__).resolve().parent / "data")

    shapefile = os.path.join(data_root, "gis", "flux_intl_150m_23MAR2026.shp")
    gdf = gpd.read_file(shapefile, engine="fiona").to_crs(epsg=4326)

    out_dir = os.path.join(
        data_root, "remote_sensing", "landsat", "extracts", "ssebop_v026_etf", "no_mask"
    )
    os.makedirs(out_dir, exist_ok=True)

    # Site selection
    if args.sites:
        sites = [s.strip() for s in args.sites.split(",")]
    else:
        sites = sorted(gdf["sid"].unique())

    years = list(range(args.start_yr, args.end_yr + 1))

    # Build work list, skip existing
    todo = []
    for site in sites:
        for year in years:
            out_csv = os.path.join(out_dir, f"ssebop_etf_{site}_no_mask_{year}.csv")
            if not os.path.exists(out_csv):
                todo.append((site, year))

    print("SSEBop v0.2.6 ETf (international)")
    print(f"  Sites: {len(sites)}, Years: {args.start_yr}-{args.end_yr}")
    print(f"  Todo: {len(todo)} site-years (skipping existing)")
    print(f"  dt_source: {args.dt_source}")
    print(f"  lc_source: {args.lc_source}")
    print(f"  et_fraction_type: {args.et_fraction_type}")
    print(f"  Output: {out_dir}")

    # Build geometry cache
    geom_cache = {}
    for site in sites:
        row = gdf[gdf["sid"] == site]
        if row.empty:
            continue
        geom = row.iloc[0].geometry
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        geom_cache[site] = ee.Geometry(geom.__geo_interface__)

    for i, (site, year) in enumerate(todo):
        polygon = geom_cache.get(site)
        if polygon is None:
            continue

        out_csv = os.path.join(out_dir, f"ssebop_etf_{site}_no_mask_{year}.csv")

        # Get scene list for this site-year
        coll = ssebop.Collection(
            LANDSAT_COLLECTIONS,
            start_date=f"{year}-01-01",
            end_date=f"{year}-12-31",
            geometry=polygon,
            cloud_cover_max=70,
        )
        scenes = sorted(set(coll.get_image_ids()), key=lambda s: s.split("_")[-1])
        if not scenes:
            print(f"  [{i + 1}/{len(todo)}] {site} {year}: no scenes")
            continue

        print(f"  [{i + 1}/{len(todo)}] {site} {year}: {len(scenes)} scenes")
        names, values = [], []
        for sid in tqdm(scenes, desc=f"  {site} {year}", leave=False):
            name, val = extract_etf(
                sid, polygon, args.dt_source, args.lc_source, args.et_fraction_type
            )
            names.append(name)
            values.append(val if val is not None else "")

        with open(out_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sid"] + names)
            w.writerow([site] + values)

        n_valid = sum(1 for v in values if v != "" and v is not None)
        print(f"    wrote {os.path.basename(out_csv)} ({n_valid}/{len(names)} valid)")

    print("Done.")


if __name__ == "__main__":
    main()
