"""Extract SSEBop ETf using openet-ssebop v0.2.6 via batch EE export tasks.

Computes v0.2.6 ETf on-the-fly from Landsat C02 SR (Tcorr FANO, same as
NHM asset) and exports per-site-year CSVs to a GCS bucket, matching the
NHM extract format.

Requires the isolated venv at /tmp/ssebop026_venv with openet-ssebop==0.2.6.

Usage:
    /tmp/ssebop026_venv/bin/python ssebop_v026_etf.py --start-yr 2024 --end-yr 2025
    /tmp/ssebop026_venv/bin/python ssebop_v026_etf.py --sites US-ARM,US-Ne1 --start-yr 2024 --end-yr 2025
"""

import os
import re
import time
from pathlib import Path

import ee
import geopandas as gpd
import openet.ssebop as ssebop

LANDSAT_COLLECTIONS = [
    "LANDSAT/LT05/C02/T1_L2",
    "LANDSAT/LE07/C02/T1_L2",
    "LANDSAT/LC08/C02/T1_L2",
    "LANDSAT/LC09/C02/T1_L2",
]

BUCKET = "wudr"
FEATURE_ID = "site_id"


def parse_scene_name(scene_id):
    """Convert full scene ID to compact lowercase name: {sensor}_{pathrow}_{date}."""
    parts = scene_id.split("/")[-1].split("_")
    if len(parts) >= 3:
        return f"{parts[0]}_{parts[1]}_{parts[2]}".lower()
    return scene_id.split("/")[-1].lower()


def discover_site_years(nhm_dir):
    """Parse NHM CSV filenames to get (site, year) pairs."""
    pattern = re.compile(r"ssebop_etf_(.+)_no_mask_(\d{4})\.csv")
    pairs = []
    for fn in sorted(os.listdir(nhm_dir)):
        m = pattern.match(fn)
        if m:
            pairs.append((m.group(1), int(m.group(2))))
    return pairs


def export_table(data, desc, selectors, bucket, fn_prefix):
    """Export a FeatureCollection to GCS as CSV."""
    task = ee.batch.Export.table.toCloudStorage(
        data,
        description=desc,
        bucket=bucket,
        fileNamePrefix=fn_prefix,
        fileFormat="CSV",
        selectors=selectors,
    )
    try:
        task.start()
        print(desc, flush=True)
        return True
    except ee.ee_exception.EEException as e:
        msg = str(e)
        if "many tasks already in the queue" in msg:
            print(f"Task queue full. Waiting 10 minutes to retry {desc}...")
            time.sleep(600)
            task.start()
            print(desc, flush=True)
            return True
        raise


def main():
    import argparse

    parser = argparse.ArgumentParser(description="SSEBop v0.2.6 ETf batch export")
    parser.add_argument(
        "--sites",
        type=str,
        default=None,
        help="Comma-separated site IDs (default: all)",
    )
    parser.add_argument("--start-yr", type=int, default=2024)
    parser.add_argument("--end-yr", type=int, default=2025)
    args = parser.parse_args()

    ee.Initialize()

    project_dir = Path(__file__).resolve().parent
    if os.path.isdir("/data/ssd1/swim/4_Flux_Network"):
        data_root = "/data/ssd1/swim/4_Flux_Network/data"
    else:
        data_root = str(project_dir / "data")

    shapefile = os.path.join(data_root, "gis", "flux_fields.shp")
    gdf = gpd.read_file(shapefile, engine="fiona").to_crs(epsg=4326)

    # Local check directory — skip if CSV already synced from bucket
    check_dir = os.path.join(
        data_root,
        "remote_sensing",
        "landsat",
        "extracts",
        "ssebop_v026_etf",
        "no_mask",
    )
    os.makedirs(check_dir, exist_ok=True)

    # Build site list
    nhm_dir = os.path.join(
        data_root,
        "remote_sensing",
        "landsat",
        "extracts",
        "ssebop_etf",
        "no_mask",
    )
    all_nhm_pairs = discover_site_years(nhm_dir)
    nhm_sites = sorted({s for s, _ in all_nhm_pairs})

    if args.sites:
        sites = [s.strip() for s in args.sites.split(",")]
    else:
        sites = nhm_sites if nhm_sites else sorted(gdf[FEATURE_ID].unique())

    print(f"SSEBop v0.2.6 ETf: {len(sites)} sites, {args.start_yr}-{args.end_yr}")
    print(f"Bucket: gs://{BUCKET}")

    exported, skipped = 0, 0

    for fid in sites:
        row = gdf[gdf[FEATURE_ID] == fid]
        if row.empty:
            continue
        geom = row.iloc[0].geometry
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        polygon = ee.Geometry(geom.__geo_interface__)

        for year in range(args.start_yr, args.end_yr + 1):
            desc = f"ssebop_etf_{fid}_no_mask_{year}"

            # Skip if already exported locally
            if os.path.exists(os.path.join(check_dir, f"{desc}.csv")):
                skipped += 1
                continue

            # Discover scenes
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
                continue

            # Stack all scene ETf bands into one image
            selectors = [FEATURE_ID]
            bands = None

            for scene_id in scenes:
                name = parse_scene_name(scene_id)
                selectors.append(name)

                try:
                    img = ssebop.Image.from_landsat_c2_sr(
                        scene_id,
                    )
                    etf_img = img.et_fraction.rename(name).clip(polygon)
                except Exception as e:
                    print(f"  {fid} {year} {name}: skip ({e})")
                    continue

                if bands is None:
                    bands = etf_img
                else:
                    bands = bands.addBands([etf_img])

            if bands is None:
                continue

            fc = ee.FeatureCollection(ee.Feature(polygon, {FEATURE_ID: fid}))
            data = bands.reduceRegions(
                collection=fc,
                reducer=ee.Reducer.mean(),
                scale=30,
            )

            fn_prefix = (
                f"4_Flux_Network/remote_sensing/landsat/extracts/ssebop_v026_etf/no_mask/{desc}"
            )
            export_table(data, desc, selectors, BUCKET, fn_prefix)
            exported += 1

    print(f"\nExported {exported}, skipped {skipped} existing")
    print(
        "Sync with: gsutil -m rsync gs://wudr/4_Flux_Network/remote_sensing/"
        "landsat/extracts/ssebop_v026_etf/no_mask/ " + check_dir
    )


if __name__ == "__main__":
    main()
