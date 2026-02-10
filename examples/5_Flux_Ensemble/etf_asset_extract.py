"""Extract ETf from pre-computed OpenET v2.1 EE asset collections.

Reads from user-owned cached EE ImageCollections that contain pre-normalized
ETf (single ``etf`` band, float, 0-2 range).  These cached copies are created
by ``copy_openet_assets.py`` and live under
``projects/ee-dgketchum/assets/openet_etf/v2_1/{model}``.

Usage:
    python etf_asset_extract.py --shapefile <path> --model ssebop \\
        [--mask no_mask] [--sites SITE1,SITE2] [--bucket BUCKET]
"""

import os
import warnings

import ee
from tqdm import tqdm

from swimrs.data_extraction.ee.common import (
    build_feature_collection,
    export_table,
    get_irrigation_mask,
    load_shapefile,
    parse_scene_name,
    setup_irrigation_masks,
)

# Cached user-owned EE asset collections (created by copy_openet_assets.py).
# These contain pre-normalized ETf: single "etf" band, float, 0-2 range.
CACHED_ROOT = "projects/ee-dgketchum/assets/openet_etf/v2_1"

ASSET_PATHS = {
    "ssebop": f"{CACHED_ROOT}/ssebop",
    "sims": f"{CACHED_ROOT}/sims",
    "geesebal": f"{CACHED_ROOT}/geesebal",
    "eemetric": f"{CACHED_ROOT}/eemetric",
    "ensemble": f"{CACHED_ROOT}/ensemble",
}

# Models not yet available at v2.1 — access pending
_PENDING_MODELS = {"ptjpl", "disalexi"}


def _get_etf_image(model, img_id, polygon):
    """Load an ETf ee.Image from a cached asset scene.

    All cached models have a single ``etf`` band in 0-2 range.

    Parameters
    ----------
    model : str
        Model name (key into ASSET_PATHS).
    img_id : str
        Scene system:index within the collection.
    polygon : ee.Geometry
        Geometry (unused, kept for API compatibility).

    Returns
    -------
    ee.Image
        Single-band ETf image.
    """
    asset_path = ASSET_PATHS[model]
    full_id = f"{asset_path}/{img_id}"
    return ee.Image(full_id).select("etf")


def extract_etf_assets(
    shapefile,
    bucket,
    feature_id,
    model,
    mask_type="no_mask",
    start_yr=2016,
    end_yr=2024,
    check_dir=None,
    state_col="state",
    select=None,
    file_prefix="swim",
    dest="bucket",
):
    """Export per-field ETf zonal statistics from OpenET EE asset collections.

    Iterates features row-by-row from a local shapefile, discovers scenes
    from the pre-computed OpenET asset collection, applies optional irrigation
    masking, and exports mean ETf via ``reduceRegions`` at 30 m.

    Parameters
    ----------
    shapefile : str
        Path to polygon shapefile with feature IDs.
    bucket : str
        GCS bucket name.
    feature_id : str
        Column name for feature identifier.
    model : str
        Model name: 'ssebop', 'sims', 'geesebal', 'eemetric', or 'ensemble'.
    mask_type : str
        Irrigation masking: 'no_mask', 'irr', or 'inv_irr'.
    start_yr, end_yr : int
        Inclusive year range.
    check_dir : str, optional
        Skip exports if CSV already exists at ``<check_dir>/<desc>.csv``.
    state_col : str
        Column with state abbreviation for mask source selection.
    select : list[str], optional
        Subset of feature IDs to process.
    file_prefix : str
        Bucket path prefix.
    dest : str
        Export destination: 'drive' or 'bucket'.
    """
    if model in _PENDING_MODELS:
        warnings.warn(
            f"Model '{model}' is not yet available at v2.1 — access pending. "
            f"Available models: {sorted(ASSET_PATHS)}",
            UserWarning,
        )
        return

    if model not in ASSET_PATHS:
        raise ValueError(f"Unknown model: {model}. Available: {list(ASSET_PATHS)}")

    if dest == "bucket" and not bucket:
        raise ValueError("bucket is required when dest='bucket'")

    asset_path = ASSET_PATHS[model]
    df = load_shapefile(shapefile, feature_id)

    if select is not None:
        df = df[df.index.isin(select)]

    print(f"OpenET asset ETf ({model}): {len(df)} fields, mask={mask_type}, {start_yr}-{end_yr}")

    if mask_type != "no_mask":
        irr_coll, irr_min_yr_mask, lanid, east_fc = setup_irrigation_masks()

    skipped, exported = 0, 0

    for fid, row in tqdm(df.iterrows(), desc=f"{model} asset ETf", total=len(df)):
        if row["geometry"].geom_type not in ("Polygon", "MultiPolygon"):
            continue

        polygon = ee.Geometry(row.geometry.__geo_interface__)

        for year in range(start_yr, end_yr + 1):
            if mask_type in ("irr", "inv_irr"):
                state = row.get(state_col, None) if state_col in row.index else None
                irr, irr_mask = get_irrigation_mask(
                    year, state, irr_coll, irr_min_yr_mask, lanid, east_fc
                )
            else:
                irr, irr_mask = None, None

            # Discover scenes for this field-year
            etf_coll = (
                ee.ImageCollection(asset_path)
                .filterDate(f"{year}-01-01", f"{year}-12-31")
                .filterBounds(polygon)
            )
            etf_scenes = etf_coll.aggregate_histogram("system:index").getInfo()

            if not etf_scenes:
                continue

            scene_ids = sorted(etf_scenes.keys(), key=lambda s: s.split("_")[-1])

            desc = f"{model}_etf_{fid}_{mask_type}_{year}"

            if check_dir:
                check_path = os.path.join(check_dir, f"{desc}.csv")
                if os.path.exists(check_path):
                    skipped += 1
                    continue

            fn_prefix = (
                f"{file_prefix}/remote_sensing/landsat/extracts"
                f"/openet/{model}_etf/{mask_type}/{desc}"
            )

            first, bands = True, None
            selectors = [feature_id]

            for img_id in scene_ids:
                _name = parse_scene_name(img_id)
                selectors.append(_name)

                try:
                    etf_img = _get_etf_image(model, img_id, polygon).rename(_name)
                except Exception as e:
                    print(f"{_name} error: {e}")
                    continue

                if mask_type == "irr":
                    etf_img = etf_img.clip(polygon).mask(irr_mask)
                elif mask_type == "inv_irr":
                    etf_img = etf_img.clip(polygon).mask(irr.gt(0))
                else:
                    etf_img = etf_img.clip(polygon)

                if first:
                    bands = etf_img
                    first = False
                else:
                    bands = bands.addBands([etf_img])

            if bands is None:
                continue

            fc = build_feature_collection(polygon, fid, feature_id)
            data = bands.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=30)

            export_table(
                data=data,
                desc=desc,
                selectors=selectors,
                dest=dest,
                bucket=bucket,
                fn_prefix=fn_prefix,
            )
            exported += 1

    print(f"OpenET asset ETf ({model}): exported {exported}, skipped {skipped}")


if __name__ == "__main__":
    import argparse

    from swimrs.data_extraction.ee.ee_utils import is_authorized

    parser = argparse.ArgumentParser(description="Extract ETf from OpenET EE assets")
    parser.add_argument("--shapefile", required=True, help="Path to polygon shapefile")
    parser.add_argument(
        "--model",
        required=True,
        choices=list(ASSET_PATHS),
        help="OpenET model name",
    )
    parser.add_argument(
        "--mask",
        choices=["irr", "inv_irr", "no_mask"],
        default="no_mask",
        help="Mask type (default: no_mask)",
    )
    parser.add_argument("--sites", type=str, default=None, help="Comma-separated site IDs")
    parser.add_argument("--start-yr", type=int, default=2016)
    parser.add_argument("--end-yr", type=int, default=2024)
    parser.add_argument("--feature-id", type=str, default="site_id")
    parser.add_argument("--state-col", type=str, default="state")
    parser.add_argument("--bucket", type=str, default=None)
    parser.add_argument("--dest", choices=["drive", "bucket"], default="bucket")
    parser.add_argument("--file-prefix", type=str, default="swim")
    parser.add_argument("--debug", action="store_true", help="Process first site only")
    args = parser.parse_args()

    is_authorized()

    sites = [s.strip() for s in args.sites.split(",")] if args.sites else None

    if args.debug and sites:
        sites = sites[:1]
        print(f"DEBUG: processing only {sites}")

    extract_etf_assets(
        shapefile=args.shapefile,
        bucket=args.bucket,
        feature_id=args.feature_id,
        model=args.model,
        mask_type=args.mask,
        start_yr=args.start_yr,
        end_yr=args.end_yr,
        state_col=args.state_col,
        select=sites,
        file_prefix=args.file_prefix,
        dest=args.dest,
    )
