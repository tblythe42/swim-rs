# NDVI extraction for the Montana SID 1991-2023 using swimrs EE modules.
# Outputs raw per-county DataFrames as CSV (no netCDF post-processing).

import os
import sys
import time

import ee
import geopandas as gpd
import pandas as pd

from swimrs.data_extraction.ee.common import export_table, shapefile_to_feature_collection
from swimrs.data_extraction.ee.ee_utils import is_authorized, landsat_masked

WAIT_MINUTES = 10
MAX_RETRIES = 6

IRR = "projects/ee-dgketchum/assets/IrrMapper/IrrMapperComp"
FEATURE_ID = "FID"
SHAPEFILE = (
    "/nas/Montana/statewide_irrigation_dataset/statewide_irrigation_dataset_15FEB2024_aea.shp"
)


def extract_ndvi(
    feature_coll,
    mask_type="irr",
    start_yr=2004,
    end_yr=2024,
    feature_id="FID",
    dest="local",
    bucket="wudr",
    file_prefix="sid",
):
    """Extract mean NDVI per field using harmonized Landsat.

    Uses SBAF-adjusted NIR_H/RED_H for consistent cross-sensor NDVI.

    When dest="local", uses ee.data.computeFeatures for synchronous return
    and returns a concatenated DataFrame.

    When dest="bucket", starts one ee.batch export task per year to GCS
    and returns None.
    """
    irr_coll = ee.ImageCollection(IRR)
    remap = irr_coll.filterDate("1987-01-01", "2024-12-31").select("classification")
    irr_min_yr_mask = remap.map(lambda img: img.lt(1)).sum().gte(5)

    dfs = []

    for year in range(start_yr, end_yr + 1):
        irr = (
            irr_coll.filterDate(f"{year}-01-01", f"{year}-12-31").select("classification").mosaic()
        )
        irr_mask = irr_min_yr_mask.updateMask(irr.lt(1))

        coll = landsat_masked(year, feature_coll, harmonize=True).map(
            lambda x: x.normalizedDifference(["NIR_H", "RED_H"])
        )

        for attempt in range(MAX_RETRIES):
            try:
                scenes = coll.aggregate_histogram("system:index").getInfo()
                break
            except ee.ee_exception.EEException as exc:
                if attempt == MAX_RETRIES - 1:
                    raise
                print(f"  getInfo failed ({exc}), retrying in {WAIT_MINUTES} min...")
                time.sleep(WAIT_MINUTES * 60)

        band_names = sorted(scenes.keys())
        print(f"  {year}: {len(band_names)} scenes")
        bands = coll.toBands().rename(band_names)

        if mask_type == "irr":
            bands = bands.mask(irr_mask)
        elif mask_type == "inv_irr":
            bands = bands.mask(irr.gt(0))

        data = bands.reduceRegions(
            collection=feature_coll,
            reducer=ee.Reducer.mean(),
            scale=30,
            tileScale=8,
        )

        if dest == "local":
            data_df = ee.data.computeFeatures(
                {"expression": data, "fileFormat": "PANDAS_DATAFRAME"}
            )
            data_df.index = data_df[feature_id]
            data_df.drop(columns=["geo"], inplace=True, errors="ignore")
            dfs.append(data_df)
        elif dest == "bucket":
            desc = f"ndvi_{mask_type}_{year}"
            selectors = [feature_id] + band_names
            for attempt in range(MAX_RETRIES):
                try:
                    export_table(
                        data,
                        desc=desc,
                        selectors=selectors,
                        dest="bucket",
                        bucket=bucket,
                        fn_prefix=f"{file_prefix}/ndvi/{mask_type}/{desc}",
                    )
                    break
                except ee.ee_exception.EEException as exc:
                    if attempt == MAX_RETRIES - 1:
                        raise
                    print(f"  export failed ({exc}), retrying in {WAIT_MINUTES} min...")
                    time.sleep(WAIT_MINUTES * 60)

    if dest == "local":
        return pd.concat(dfs, axis=1)
    return None


if __name__ == "__main__":
    root = "/data/ssd2/swim/sid"
    os.makedirs(root, exist_ok=True)
    sys.setrecursionlimit(5000)

    is_authorized("ee-hoylman")

    beg_year = 2024
    end_year = 2025

    dest = "bucket"
    bucket = "wudr"

    gdf = gpd.read_file(SHAPEFILE)
    county_fids = gdf.groupby("COUNTY_NO")[FEATURE_ID].apply(list).to_dict()

    for county_no, fids in county_fids.items():
        county = f"{county_no:03d}"
        name = gdf.loc[gdf["COUNTY_NO"] == county_no, "COUNTYNAME"].iloc[0]

        for mask_type in ["irr", "inv_irr"]:
            print(f"\n=== County {county} ({name}, {len(fids)} fields) mask={mask_type} ===")

            fc = shapefile_to_feature_collection(SHAPEFILE, FEATURE_ID, select=fids)

            start_time = time.time()
            result = extract_ndvi(
                fc,
                mask_type=mask_type,
                start_yr=beg_year,
                end_yr=end_year,
                feature_id=FEATURE_ID,
                dest=dest,
                bucket=bucket,
                file_prefix=f"sid/{county}",
            )
            elapsed = time.time() - start_time

            if result is not None:
                out_csv = os.path.join(root, f"{county}_ndvi_{mask_type}.csv")
                result.to_csv(out_csv)
                print(
                    f"  {result.shape[0]} fields x {result.shape[1]} scenes "
                    f"in {elapsed:.1f}s -> {out_csv}"
                )
            else:
                print(f"  Export tasks submitted in {elapsed:.1f}s")

# ========================= EOF ====================================================================
