"""Extract ETf from pre-computed OpenET EE asset collections.

Reads from the official OpenET image collections on Earth Engine rather than
running the FOSS packages on-the-fly.  This is much faster because the ETf
images are already computed — we just need to do zonal stats.

Supported models and their EE assets / band logic:

- **ssebop**: ``projects/openet/assets/ssebop/conus/gridmet/landsat/c02``
  — ``et_fraction`` / 10000
- **sims**: ``projects/openet/assets/sims/conus/gridmet/landsat/c02``
  — ``et_fraction`` / 10000
- **ptjpl**: ``projects/openet/assets/ptjpl/conus/gridmet/landsat/c02``
  — ``et`` / 1000 / ETo  (ET band, convert to ETf)
- **geesebal**: ``projects/openet/assets/geesebal/conus/gridmet/landsat/c02``
  — ``et`` / 1000 / ETo  (ET band, convert to ETf)
- **ensemble**: ``projects/openet/assets/ensemble/conus/gridmet/landsat/c02``
  — ``et_ensemble_mad`` / 10000
- **ssebop_nhm**: ``projects/usgs-gee-nhm-ssebop/assets/ssebop/landsat/c02``
  — ``et_fraction`` / 10000

Usage:
    python etf_asset_extract.py --shapefile <path> --model ptjpl \\
        [--mask no_mask] [--sites SITE1,SITE2] [--bucket BUCKET]
"""

import os

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

# EE asset paths for pre-computed OpenET collections
ASSET_PATHS = {
    "ssebop": "projects/openet/assets/ssebop/conus/gridmet/landsat/c02",
    "sims": "projects/openet/assets/sims/conus/gridmet/landsat/c02",
    "ptjpl": "projects/openet/assets/ptjpl/conus/gridmet/landsat/c02",
    "geesebal": "projects/openet/assets/geesebal/conus/gridmet/landsat/c02",
    "ensemble": "projects/openet/assets/ensemble/conus/gridmet/landsat/c02",
    "ssebop_nhm": "projects/usgs-gee-nhm-ssebop/assets/ssebop/landsat/c02",
}

# Reference ET for converting ET -> ETf (ptjpl, geesebal)
REFET_COLLECTION = "projects/openet/assets/reference_et/conus/gridmet/daily/v1"

# Models where the band is already ETf (et_fraction / 10000)
DIRECT_ETF_MODELS = {"ssebop", "sims", "ssebop_nhm"}

# Models where the band is ET (et / 1000) and must be divided by ETo
ET_BAND_MODELS = {"ptjpl", "geesebal"}

# Ensemble uses a different band name
ENSEMBLE_MODELS = {"ensemble"}


def _get_etf_image(model, img_id, polygon):
    """Compute an ETf ee.Image from a pre-computed OpenET asset scene.

    Parameters
    ----------
    model : str
        Model name (key into ASSET_PATHS).
    img_id : str
        Scene system:index within the collection.
    polygon : ee.Geometry
        Geometry for clipping reference ET (used only for ET-band models).

    Returns
    -------
    ee.Image
        Single-band ETf image.
    """
    asset_path = ASSET_PATHS[model]
    full_id = f"{asset_path}/{img_id}"

    if model in DIRECT_ETF_MODELS:
        return ee.Image(full_id).select("et_fraction").divide(10000)

    if model in ENSEMBLE_MODELS:
        return ee.Image(full_id).select("et_ensemble_mad").divide(10000)

    if model in ET_BAND_MODELS:
        et_img = ee.Image(full_id).select("et").divide(1000)

        # Get the scene date for reference ET lookup
        scene_date = ee.Image(full_id).date()
        date_str = scene_date.format("YYYYMMdd")
        eto_img = (
            ee.Image(ee.String(REFET_COLLECTION + "/").cat(date_str)).select("eto").divide(1000)
        )

        return et_img.divide(eto_img).clamp(0, 2)

    raise ValueError(f"Unknown model: {model}")


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
        Model name: 'ssebop', 'ptjpl', 'sims', 'geesebal', 'ensemble',
        or 'ssebop_nhm'.
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
