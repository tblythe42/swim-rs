# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "openet-ssebop==0.2.6",
#   "earthengine-api",
# ]
# ///
"""Build DOY dT climatology directly from ERA5-Land daily aggregates.

Computes dT for each DOY by:
  1. Filtering ERA5-Land to that DOY across the specified year range
  2. Computing per-year dT via openet.ssebop.model.dt()
  3. Taking the median (or mean) across years

This avoids materializing daily dT images as intermediate EE assets.
Produces the same 366-image DOY climatology that v0.2.6 expects.

Usage:
    uv run ssebop_v026_dt_climo_direct.py \
        --output-coll projects/ee-dgketchum/assets/ssebop/dt_era5land_median_2000_2020 \
        --start-year 2000 --end-year 2020 --stat median \
        --region /path/to/wrs2_union.geojson
"""

import argparse
import json

import ee
from openet.ssebop import model as ssebop_model


def build_dt_climatology_direct(
    output_coll,
    start_year,
    end_year,
    stat="median",
    source_coll="ECMWF/ERA5_LAND/DAILY_AGGR",
    tmax_band="temperature_2m_max",
    tmin_band="temperature_2m_min",
    dewpoint_band="dewpoint_temperature_2m",
    rs_band="surface_solar_radiation_downwards_sum",
    dt_min=6.0,
    dt_max=25.0,
    elev_source="USGS/SRTMGL1_003",
    region_geojson=None,
    project="ee-dgketchum",
):
    """Build DOY dT climatology directly from daily meteorology."""
    ee.Initialize(project=project)

    # Ensure output collection exists
    try:
        ee.data.createAsset({"type": "ImageCollection"}, output_coll)
        print(f"Created asset collection: {output_coll}")
    except ee.ee_exception.EEException as e:
        if "already exists" in str(e).lower():
            pass
        else:
            raise

    # Load export region
    export_region = None
    if region_geojson:
        with open(region_geojson) as f:
            rj = json.load(f)
        if rj.get("type") == "FeatureCollection":
            export_region = ee.FeatureCollection(rj).geometry()
        else:
            export_region = ee.Geometry(rj)
        print(f"  Export region: {region_geojson}")

    elev = ee.Image(elev_source).select("elevation")
    era5 = ee.ImageCollection(source_coll)

    print(f"Building {stat} dT climatology for DOY 1-366")
    print(f"  Source: {source_coll}")
    print(f"  Years: {start_year}-{end_year}")
    print(f"  Output: {output_coll}")

    for doy in range(1, 367):
        # Filter to this DOY across all years
        doy_imgs = era5.filter(ee.Filter.calendarRange(start_year, end_year, "year")).filter(
            ee.Filter.calendarRange(doy, doy, "day_of_year")
        )

        # Compute dT for each daily image, then reduce across years.
        # Bind loop variable via default arg to avoid B023.
        def compute_dt_for_image(img, _doy=doy, _dt_min=dt_min, _dt_max=dt_max):
            tmax = img.select(tmax_band)
            tmin = img.select(tmin_band)

            # Dewpoint (K) to actual vapor pressure (kPa) via Tetens
            td_c = img.select(dewpoint_band).subtract(273.15)
            ea = td_c.multiply(17.27).divide(td_c.add(237.3)).exp().multiply(0.6108)

            # Solar radiation: J/m² → MJ/m²
            rs = img.select(rs_band).divide(1e6)

            dt = ssebop_model.dt(
                tmax=tmax,
                tmin=tmin,
                elev=elev,
                doy=_doy,
                rs=rs,
                ea=ea,
            )
            return (
                dt.clamp(_dt_min, _dt_max).rename("dt").copyProperties(img, ["system:time_start"])
            )

        dt_coll = doy_imgs.map(compute_dt_for_image)

        if stat == "median":
            climo_img = dt_coll.median()
        elif stat == "mean":
            climo_img = dt_coll.mean()
        else:
            raise ValueError(f"Unknown stat: {stat}")

        climo_img = climo_img.rename("dt")

        # Synthetic time_start for EE filtering
        ref_date = ee.Date.fromYMD(2000, 1, 1).advance(doy - 1, "day")
        climo_img = climo_img.set(
            {
                "system:time_start": ref_date.millis(),
                "doy": doy,
                "start_year": start_year,
                "end_year": end_year,
                "source_collection": source_coll,
                "statistic": stat,
                "dt_min": dt_min,
                "dt_max": dt_max,
            }
        )

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

    print("All 366 dT climatology tasks submitted.")


def main():
    parser = argparse.ArgumentParser(description="Build DOY dT climatology directly from ERA5-Land")
    parser.add_argument("--output-coll", required=True, help="Output EE ImageCollection")
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2020)
    parser.add_argument("--stat", default="median", choices=["mean", "median"])
    parser.add_argument("--source-coll", default="ECMWF/ERA5_LAND/DAILY_AGGR")
    parser.add_argument("--dt-min", type=float, default=6.0)
    parser.add_argument("--dt-max", type=float, default=25.0)
    parser.add_argument("--region", default=None, help="GeoJSON file for export region")
    parser.add_argument("--project", default="ee-dgketchum")
    args = parser.parse_args()

    build_dt_climatology_direct(
        output_coll=args.output_coll,
        start_year=args.start_year,
        end_year=args.end_year,
        stat=args.stat,
        source_coll=args.source_coll,
        dt_min=args.dt_min,
        dt_max=args.dt_max,
        region_geojson=args.region,
        project=args.project,
    )


if __name__ == "__main__":
    main()
