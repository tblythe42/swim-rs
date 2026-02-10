"""Copy OpenET ETf images to user-owned EE ImageCollections.

Reads from an OpenET v2.1 source collection, applies per-model band/scaling to
produce uniform ETf (single ``etf`` band, float, 0-2 range), clips to 4km buffers
around all sites, and exports to
``projects/ee-dgketchum/assets/openet_etf/v2_1/{model}``.

This creates a cached copy so that downstream extraction does not depend on
continued access to the official OpenET asset paths.

Usage:
    python copy_openet_assets.py --shapefile <path> --model ssebop \\
        [--source <collection>] [--start-yr 2016] [--end-yr 2024] \\
        [--sites SITE1,SITE2] [--buffer 4000]
"""

import ee
import geopandas as gpd
from pyproj import CRS
from shapely.ops import unary_union
from tqdm import tqdm

# OpenET v2.1 source collections
# NOTE: ptjpl and disalexi are not yet available at v2.1 — access pending
OPENET_SOURCES = {
    "ssebop": "projects/openet/assets/ssebop/conus/gridmet/landsat/v2_1",
    "sims": "projects/openet/assets/sims/conus/gridmet/landsat/v2_1",
    "geesebal": "projects/openet/assets/geesebal/conus/gridmet/landsat/v2_1",
    "eemetric": "projects/openet/assets/eemetric/conus/gridmet/landsat/v2_1",
    "ensemble": "projects/openet/assets/ensemble/conus/gridmet/landsat/v2_1",
}

DEST_ROOT = "projects/ee-dgketchum/assets/openet_etf/v2_1"

# Reference ET for converting ET -> ETf (geesebal)
REFET_COLLECTION = "projects/openet/assets/reference_et/conus/gridmet/daily/v1"

# Models where the band is already ETf (et_fraction / 10000)
DIRECT_ETF_MODELS = {"ssebop", "sims", "eemetric"}

# Models where the band is ET (et / 1000) and must be divided by ETo
ET_BAND_MODELS = {"geesebal"}

# Ensemble model: et_ensemble_mad / 10000
ENSEMBLE_MODELS = {"ensemble"}


def _build_union_geometry(shapefile, feature_id, buffer_m=4000, select=None):
    """Load shapefile, buffer each site by buffer_m, return dissolved union in EPSG:4326.

    Parameters
    ----------
    shapefile : str
        Path to polygon shapefile.
    feature_id : str
        Column name for feature identifier.
    buffer_m : float
        Buffer distance in meters around each site geometry.
    select : list[str], optional
        Subset of feature IDs to process.

    Returns
    -------
    ee.Geometry
        Union of all buffered site geometries in EPSG:4326.
    """
    gdf = gpd.read_file(shapefile)
    gdf = gdf.set_index(feature_id)

    if select is not None:
        gdf = gdf[gdf.index.isin(select)]

    # Project to a meter-based CRS for buffering
    src_crs = gdf.crs
    if src_crs is None or src_crs.is_geographic:
        # Use Conus Albers for buffering
        proj_crs = CRS.from_epsg(5070)
        gdf_proj = gdf.to_crs(proj_crs)
    else:
        gdf_proj = gdf

    buffered = gdf_proj.buffer(buffer_m)
    union_geom = unary_union(buffered)

    # Back to 4326 for EE
    gdf_union = gpd.GeoDataFrame(geometry=[union_geom], crs=gdf_proj.crs)
    gdf_union = gdf_union.to_crs(epsg=4326)
    union_4326 = gdf_union.geometry.iloc[0]

    return ee.Geometry(union_4326.__geo_interface__)


def _normalize_etf(model, image, geometry):
    """Apply per-model band selection and scaling to produce uniform ETf.

    Parameters
    ----------
    model : str
        Model name.
    image : ee.Image
        Raw image from the source collection.
    geometry : ee.Geometry
        Clip geometry (for reference ET lookup).

    Returns
    -------
    ee.Image
        Single-band ``etf`` image, float, clamped to 0-2.
    """
    if model in DIRECT_ETF_MODELS:
        return image.select("et_fraction").divide(10000).clamp(0, 2).rename("etf")

    if model in ENSEMBLE_MODELS:
        return image.select("et_ensemble_mad").divide(10000).clamp(0, 2).rename("etf")

    if model in ET_BAND_MODELS:
        et_img = image.select("et").divide(1000)
        scene_date = image.date()
        date_str = scene_date.format("YYYYMMdd")
        eto_img = (
            ee.Image(ee.String(REFET_COLLECTION + "/").cat(date_str)).select("eto").divide(1000)
        )
        return et_img.divide(eto_img).clamp(0, 2).rename("etf")

    raise ValueError(f"Unknown model: {model}")


def _ensure_asset_exists(asset_id, asset_type):
    """Create an EE asset (folder or ImageCollection) if it doesn't exist.

    Parameters
    ----------
    asset_id : str
        Full asset path.
    asset_type : str
        One of 'FOLDER' or 'IMAGE_COLLECTION'.
    """
    try:
        ee.data.getAsset(asset_id)
    except ee.ee_exception.EEException:
        print(f"Creating {asset_type}: {asset_id}")
        ee.data.createAsset({"type": asset_type}, asset_id)


def _list_existing_images(collection_path):
    """Return set of image IDs already in the destination collection."""
    try:
        assets = ee.data.listAssets({"parent": collection_path})
        return {a["id"].split("/")[-1] for a in assets.get("assets", [])}
    except ee.ee_exception.EEException:
        return set()


def copy_openet_to_assets(
    shapefile,
    model,
    source_collection=None,
    dest_collection=None,
    feature_id="site_id",
    buffer_m=4000,
    start_yr=2016,
    end_yr=2024,
    select=None,
):
    """Copy OpenET images to a user-owned EE ImageCollection.

    Each image is normalized to a single ``etf`` band (float, 0-2 range),
    clipped to the union of 4km-buffered site geometries, and exported
    to the destination collection via ``Export.image.toAsset()``.

    Parameters
    ----------
    shapefile : str
        Path to polygon shapefile with site geometries.
    model : str
        Model name: 'ssebop', 'sims', 'geesebal', 'eemetric', or 'ensemble'.
    source_collection : str, optional
        Override source EE ImageCollection path. Defaults to OPENET_SOURCES[model].
    dest_collection : str, optional
        Override destination EE ImageCollection path.
        Defaults to ``{DEST_ROOT}/{model}``.
    feature_id : str
        Column name for feature identifier.
    buffer_m : float
        Buffer distance in meters around each site.
    start_yr, end_yr : int
        Inclusive year range.
    select : list[str], optional
        Subset of feature IDs to process.
    """
    if model not in OPENET_SOURCES and source_collection is None:
        raise ValueError(f"Unknown model: {model}. Provide --source or use: {list(OPENET_SOURCES)}")

    src_path = source_collection or OPENET_SOURCES[model]
    dst_path = dest_collection or f"{DEST_ROOT}/{model}"

    print(f"Source: {src_path}")
    print(f"Destination: {dst_path}")

    # Build union geometry from buffered sites
    union_geom = _build_union_geometry(shapefile, feature_id, buffer_m, select)
    print("Built union geometry from buffered sites")

    # Ensure destination folder hierarchy and collection exist
    _ensure_asset_exists("projects/ee-dgketchum/assets/openet_etf", "FOLDER")
    _ensure_asset_exists(DEST_ROOT, "FOLDER")
    _ensure_asset_exists(dst_path, "IMAGE_COLLECTION")

    # Check what's already copied
    existing = _list_existing_images(dst_path)
    if existing:
        print(f"Found {len(existing)} existing images in destination, will skip")

    submitted = 0

    for year in tqdm(range(start_yr, end_yr + 1), desc=f"Copy {model}"):
        # Discover scenes for this year
        coll = (
            ee.ImageCollection(src_path)
            .filterDate(f"{year}-01-01", f"{year}-12-31")
            .filterBounds(union_geom)
        )
        scene_hist = coll.aggregate_histogram("system:index").getInfo()

        if not scene_hist:
            continue

        scene_ids = sorted(scene_hist.keys(), key=lambda s: s.split("_")[-1])

        for img_id in scene_ids:
            if img_id in existing:
                continue

            src_image = ee.Image(f"{src_path}/{img_id}")
            etf_image = _normalize_etf(model, src_image, union_geom)

            # Clip to union geometry
            etf_clipped = etf_image.clip(union_geom)

            # Copy key properties for provenance
            etf_out = etf_clipped.copyProperties(
                src_image,
                [
                    "system:time_start",
                    "system:index",
                    "SPACECRAFT_ID",
                ],
            ).set("source_collection", src_path)

            dest_id = f"{dst_path}/{img_id}"
            desc = f"copy_{model}_{img_id}".replace("/", "_")[:100]

            task = ee.batch.Export.image.toAsset(
                image=etf_out,
                description=desc,
                assetId=dest_id,
                region=union_geom,
                scale=30,
                crs="EPSG:5070",
                maxPixels=1e13,
            )
            task.start()
            submitted += 1

    print(f"Submitted {submitted} export tasks for {model}")


if __name__ == "__main__":
    import argparse

    from swimrs.data_extraction.ee.ee_utils import is_authorized

    parser = argparse.ArgumentParser(description="Copy OpenET images to user-owned EE assets")
    parser.add_argument("--shapefile", required=True, help="Path to polygon shapefile")
    parser.add_argument(
        "--model",
        required=True,
        choices=list(OPENET_SOURCES),
        help="OpenET model name",
    )
    parser.add_argument("--source", type=str, default=None, help="Override source collection path")
    parser.add_argument(
        "--dest", type=str, default=None, help="Override destination collection path"
    )
    parser.add_argument("--sites", type=str, default=None, help="Comma-separated site IDs")
    parser.add_argument("--start-yr", type=int, default=2016)
    parser.add_argument("--end-yr", type=int, default=2024)
    parser.add_argument("--feature-id", type=str, default="site_id")
    parser.add_argument("--buffer", type=int, default=4000, help="Buffer distance in meters")
    args = parser.parse_args()

    is_authorized()

    sites = [s.strip() for s in args.sites.split(",")] if args.sites else None

    copy_openet_to_assets(
        shapefile=args.shapefile,
        model=args.model,
        source_collection=args.source,
        dest_collection=args.dest,
        feature_id=args.feature_id,
        buffer_m=args.buffer,
        start_yr=args.start_yr,
        end_yr=args.end_yr,
        select=sites,
    )
