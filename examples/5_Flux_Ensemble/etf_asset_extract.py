"""Extract ETf from official OpenET v2.1 source collections.

Reads directly from the public OpenET v2.1 EE ImageCollections, applies
per-model band selection and normalization to produce ETf (0-2 range),
then exports per-field zonal means as CSVs.

Band/scaling by model:
- ssebop, sims, eemetric: ``et_fraction / 10000``
- geesebal, disalexi, ptjpl: ``et / 1000 / ETo``  (GridMET daily ETo)
- ensemble: ``et_ensemble_mad / 1000 / ETo``  (GridMET daily ETo)

Usage:
    python etf_asset_extract.py --shapefile <path> --model ssebop \\
        [--mask irr] [--sites SITE1,SITE2] [--bucket BUCKET]
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

# Official OpenET v2.1 source collections
OPENET_V21 = {
    "ssebop": "projects/openet/assets/ssebop/conus/gridmet/landsat/v2_1",
    "sims": "projects/openet/assets/sims/conus/gridmet/landsat/v2_1",
    "geesebal": "projects/openet/assets/geesebal/conus/gridmet/landsat/v2_1",
    "eemetric": "projects/openet/assets/eemetric/conus/gridmet/landsat/v2_1",
    "ensemble": "projects/openet/assets/ensemble/conus/gridmet/landsat/v2_1",
    "ptjpl": "projects/openet/assets/ptjpl/conus/nldas2/landsat/v2_1",
    "disalexi": "projects/openet/assets/disalexi/conus/cfsr/landsat/v2_1",
}

# Models that store raw ET (mm) and need division by reference ET
_ET_MODELS = {"geesebal", "ptjpl", "disalexi", "ensemble"}

# Band name for ET models (default "et"; ensemble uses a different band)
_ET_BAND_NAME = {"ensemble": "et_ensemble_mad"}

# GridMET reference ET for normalizing ET→ETf
_GRIDMET = "IDAHO_EPSCOR/GRIDMET"
_ETO_BAND = "eto"


def _normalize_etf(model, img_id):
    """Load an image from a v2.1 source collection and normalize to ETf.

    Returns a single-band ee.Image named ``etf`` in the 0-2 range.
    """
    src_path = OPENET_V21[model]
    src_image = ee.Image(f"{src_path}/{img_id}")

    if model in _ET_MODELS:
        # et band is in mm × 1000 (integer); divide by 1000 then by daily ETo
        band = _ET_BAND_NAME.get(model, "et")
        et_mm = src_image.select(band).divide(1000)
        # Get the image date for matching GridMET ETo
        date = src_image.date()
        eto = (
            ee.ImageCollection(_GRIDMET)
            .filterDate(date, date.advance(1, "day"))
            .first()
            .select(_ETO_BAND)
        )
        return et_mm.divide(eto).rename("etf")

    # ssebop, sims, eemetric: et_fraction is integer × 10000
    return src_image.select("et_fraction").divide(10000).rename("etf")


def extract_etf_v21(
    shapefile,
    bucket,
    feature_id,
    model,
    mask_type="irr",
    start_yr=2016,
    end_yr=2024,
    check_dir=None,
    state_col="state",
    select=None,
    file_prefix="5_Flux_Ensemble",
    dest="bucket",
):
    """Export per-field ETf zonal stats from OpenET v2.1 source collections.

    Parameters
    ----------
    shapefile : str
        Path to polygon shapefile with feature IDs.
    bucket : str
        GCS bucket name.
    feature_id : str
        Column name for feature identifier.
    model : str
        Model name (key into OPENET_V21).
    mask_type : str
        Irrigation masking: 'irr', 'inv_irr', or 'no_mask'.
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
    if model not in OPENET_V21:
        raise ValueError(f"Unknown model: {model}. Available: {list(OPENET_V21)}")

    if dest == "bucket" and not bucket:
        raise ValueError("bucket is required when dest='bucket'")

    src_path = OPENET_V21[model]
    df = load_shapefile(shapefile, feature_id)

    if select is not None:
        df = df[df.index.isin(select)]

    print(f"OpenET v2.1 ETf ({model}): {len(df)} fields, mask={mask_type}, {start_yr}-{end_yr}")
    print(f"Source: {src_path}")

    if mask_type != "no_mask":
        irr_coll, irr_min_yr_mask, lanid, east_fc = setup_irrigation_masks()

    skipped, exported = 0, 0

    for fid, row in tqdm(df.iterrows(), desc=f"{model} v2.1 ETf", total=len(df)):
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
                ee.ImageCollection(src_path)
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
                    etf_img = _normalize_etf(model, img_id).rename(_name)
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

    print(f"OpenET v2.1 ETf ({model}): exported {exported}, skipped {skipped}")


if __name__ == "__main__":
    import argparse

    from swimrs.data_extraction.ee.ee_utils import is_authorized

    parser = argparse.ArgumentParser(description="Extract ETf from OpenET v2.1 collections")
    parser.add_argument("--shapefile", required=True, help="Path to polygon shapefile")
    parser.add_argument(
        "--model",
        required=True,
        choices=list(OPENET_V21),
        help="OpenET model name",
    )
    parser.add_argument(
        "--mask",
        choices=["irr", "inv_irr", "no_mask"],
        default="irr",
        help="Mask type (default: irr)",
    )
    parser.add_argument("--sites", type=str, default=None, help="Comma-separated site IDs")
    parser.add_argument("--start-yr", type=int, default=2016)
    parser.add_argument("--end-yr", type=int, default=2024)
    parser.add_argument("--feature-id", type=str, default="site_id")
    parser.add_argument("--state-col", type=str, default="state")
    parser.add_argument("--bucket", type=str, default="wudr")
    parser.add_argument("--dest", choices=["drive", "bucket"], default="bucket")
    parser.add_argument("--file-prefix", type=str, default="5_Flux_Ensemble")
    parser.add_argument("--check-dir", type=str, default=None, help="Skip if CSV exists here")
    parser.add_argument("--debug", action="store_true", help="Process first site only")
    args = parser.parse_args()

    is_authorized()

    sites = [s.strip() for s in args.sites.split(",")] if args.sites else None

    if args.debug and sites:
        sites = sites[:1]
        print(f"DEBUG: processing only {sites}")

    extract_etf_v21(
        shapefile=args.shapefile,
        bucket=args.bucket,
        feature_id=args.feature_id,
        model=args.model,
        mask_type=args.mask,
        start_yr=args.start_yr,
        end_yr=args.end_yr,
        check_dir=args.check_dir,
        state_col=args.state_col,
        select=sites,
        file_prefix=args.file_prefix,
        dest=args.dest,
    )
