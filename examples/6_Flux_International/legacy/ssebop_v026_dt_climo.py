# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "earthengine-api",
# ]
# ///
"""Reduce daily dT collection into DOY climatology for SSEBop v0.2.6.

Takes the daily dT ImageCollection produced by ssebop_v026_dt_daily.py
and computes per-DOY mean (or median) to create the climatology collection
that SSEBop v0.2.6 expects via dt_source.

Usage:
    uv run ssebop_v026_dt_climo.py \
        --daily-coll projects/ee-dgketchum/assets/ssebop/dt_era5land_daily \
        --output-coll projects/ee-dgketchum/assets/ssebop/dt_era5land_median_2000_2020 \
        --start-year 2000 --end-year 2020 --stat median
"""

import argparse

import ee


def build_dt_climatology(
    daily_coll,
    output_coll,
    start_year,
    end_year,
    stat="median",
    scale_factor=None,
    region_geojson=None,
    project="ee-dgketchum",
):
    """Reduce daily dT to DOY climatology and export to EE asset collection."""
    ee.Initialize(project=project)

    # Load export region
    export_region = None
    if region_geojson:
        import json as _json

        with open(region_geojson) as f:
            rj = _json.load(f)
        if rj.get("type") == "FeatureCollection":
            export_region = ee.FeatureCollection(rj).geometry()
        else:
            export_region = ee.Geometry(rj)
        print(f"  Export region: {region_geojson}")

    # Ensure output collection exists
    try:
        ee.data.createAsset({"type": "ImageCollection"}, output_coll)
        print(f"Created asset collection: {output_coll}")
    except ee.ee_exception.EEException as e:
        if "already exists" in str(e).lower():
            pass
        else:
            raise

    src = ee.ImageCollection(daily_coll).filter(
        ee.Filter.calendarRange(start_year, end_year, "year")
    )

    print(f"Building {stat} dT climatology for DOY 1-366")
    print(f"  Source: {daily_coll}")
    print(f"  Years: {start_year}-{end_year}")
    print(f"  Output: {output_coll}")
    if scale_factor:
        print(f"  Scale factor: {scale_factor}")

    # Reference year for synthetic system:time_start
    ref_year = 2000

    for doy in range(1, 367):
        doy_coll = src.filter(ee.Filter.calendarRange(doy, doy, "day_of_year"))

        if stat == "mean":
            climo_img = doy_coll.mean()
        elif stat == "median":
            climo_img = doy_coll.median()
        else:
            raise ValueError(f"Unknown stat: {stat}")

        climo_img = climo_img.rename("dt")

        # Synthetic time_start for consistent EE filtering
        # Use Jan 1 of ref_year + (doy-1) days
        ref_date = ee.Date.fromYMD(ref_year, 1, 1).advance(doy - 1, "day")

        props = {
            "system:time_start": ref_date.millis(),
            "doy": doy,
            "start_year": start_year,
            "end_year": end_year,
            "source_collection": daily_coll,
            "statistic": stat,
        }
        if scale_factor is not None:
            props["scale_factor"] = scale_factor

        climo_img = climo_img.set(props)

        desc = f"dt_climo_doy{doy:03d}"
        asset_id = f"{output_coll}/{desc}"

        export_kwargs = dict(
            image=climo_img,
            description=desc,
            assetId=asset_id,
            scale=11132,
            maxPixels=1e10,
        )
        if export_region is not None:
            export_kwargs["region"] = export_region
        task = ee.batch.Export.image.toAsset(**export_kwargs)
        task.start()

        if doy % 50 == 0 or doy == 1:
            print(f"  Submitted DOY {doy}/366")

    print("All 366 tasks submitted.")


def main():
    parser = argparse.ArgumentParser(description="Build DOY dT climatology for SSEBop")
    parser.add_argument("--daily-coll", required=True, help="Daily dT EE ImageCollection")
    parser.add_argument("--output-coll", required=True, help="Output EE ImageCollection")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--stat", default="median", choices=["mean", "median"])
    parser.add_argument("--scale-factor", type=float, default=None)
    parser.add_argument("--region", default=None, help="GeoJSON file for export region")
    parser.add_argument("--project", default="ee-dgketchum")
    args = parser.parse_args()

    build_dt_climatology(
        daily_coll=args.daily_coll,
        output_coll=args.output_coll,
        start_year=args.start_year,
        end_year=args.end_year,
        stat=args.stat,
        scale_factor=args.scale_factor,
        region_geojson=args.region,
        project=args.project,
    )


if __name__ == "__main__":
    main()
