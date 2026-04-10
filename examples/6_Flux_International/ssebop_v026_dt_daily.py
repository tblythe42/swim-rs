# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "openet-ssebop==0.2.6",
#   "earthengine-api",
# ]
# ///
"""Build daily dT images for SSEBop v0.2.6 international use.

Computes daily dT from a global daily meteorology source using
openet.ssebop.model.dt() and exports to an EE ImageCollection asset.

Usage:
    uv run ssebop_v026_dt_daily.py --source-coll ECMWF/ERA5_LAND/DAILY_AGGR \
        --output-coll projects/ee-dgketchum/assets/ssebop/dt_era5land_daily \
        --start-date 2000-01-01 --end-date 2020-12-31
"""

import argparse
import time
from datetime import datetime, timedelta

import ee
from openet.ssebop import model as ssebop_model


def build_dt_daily(
    source_coll,
    output_coll,
    start_date,
    end_date,
    tmax_band="temperature_2m_max",
    tmin_band="temperature_2m_min",
    rs_band=None,
    ea_band=None,
    dewpoint_band="dewpoint_temperature_2m",
    tmax_units="K",
    tmin_units="K",
    rs_units=None,
    dt_min=6.0,
    dt_max=25.0,
    elev_source="USGS/SRTMGL1_003",
    project="ee-dgketchum",
):
    """Build daily dT images and export to EE asset collection."""
    ee.Initialize(project=project)

    # Ensure output collection exists
    try:
        ee.data.createAsset({"type": "ImageCollection"}, output_coll)
        print(f"Created asset collection: {output_coll}")
    except ee.ee_exception.EEException:
        pass  # already exists

    elev = ee.Image(elev_source).select("elevation")

    sdt = datetime.strptime(start_date, "%Y-%m-%d")
    edt = datetime.strptime(end_date, "%Y-%m-%d")

    print("Building daily dT images")
    print(f"  Source: {source_coll}")
    print(f"  Period: {start_date} to {end_date}")
    print(f"  Output: {output_coll}")
    print(f"  Bands: tmax={tmax_band}, tmin={tmin_band}")
    if rs_band:
        print(f"  Rs: {rs_band} ({rs_units})")
    if dewpoint_band:
        print(f"  Dewpoint: {dewpoint_band} → ea")

    n_days = (edt - sdt).days + 1
    submitted = 0

    current = sdt
    while current <= edt:
        date_str = current.strftime("%Y-%m-%d")
        next_str = (current + timedelta(days=1)).strftime("%Y-%m-%d")
        doy = current.timetuple().tm_yday

        daily = ee.ImageCollection(source_coll).filterDate(date_str, next_str).first()

        # Tmax in Kelvin
        tmax = daily.select(tmax_band)
        if tmax_units == "C":
            tmax = tmax.add(273.15)

        # Tmin in Kelvin
        tmin = daily.select(tmin_band)
        if tmin_units == "C":
            tmin = tmin.add(273.15)

        # Solar radiation: convert to MJ m-2 d-1 if provided
        rs = None
        if rs_band:
            rs = daily.select(rs_band)
            if rs_units == "J/m2":
                rs = rs.divide(1e6)  # J → MJ
            elif rs_units == "W/m2":
                rs = rs.multiply(0.0864)  # W/m2 → MJ/m2/d
            # else assume already MJ/m2/d

        # Actual vapor pressure in kPa
        ea = None
        if ea_band:
            ea = daily.select(ea_band)
        elif dewpoint_band:
            # Convert dewpoint (K) to ea (kPa) using Tetens formula
            td = daily.select(dewpoint_band)
            # ERA5 dewpoint is in K → convert to C
            td_c = td.subtract(273.15)
            ea = td_c.multiply(17.27).divide(td_c.add(237.3)).exp().multiply(0.6108)

        # Compute dT
        dt_img = ssebop_model.dt(
            tmax=tmax,
            tmin=tmin,
            elev=elev,
            doy=doy,
            rs=rs,
            ea=ea,
        )

        # Clamp
        dt_img = dt_img.clamp(dt_min, dt_max).rename("dt")

        # Set metadata
        dt_img = dt_img.set(
            {
                "system:time_start": ee.Date(date_str).millis(),
                "date": date_str,
                "year": current.year,
                "month": current.month,
                "day": current.day,
                "doy": doy,
                "source_collection": source_coll,
                "dt_min": dt_min,
                "dt_max": dt_max,
            }
        )

        desc = f"dt_daily_{date_str.replace('-', '')}"
        asset_id = f"{output_coll}/{desc}"

        task = ee.batch.Export.image.toAsset(
            image=dt_img,
            description=desc,
            assetId=asset_id,
            scale=11132,
            maxPixels=1e10,
        )

        try:
            task.start()
            submitted += 1
        except ee.ee_exception.EEException as e:
            print(f"  {date_str}: {e}")
            time.sleep(300)
            task.start()
            submitted += 1

        if submitted % 100 == 0 or submitted == 1:
            print(f"  Submitted {submitted}/{n_days} ({date_str})")

        # Rate limit
        if submitted % 500 == 0:
            time.sleep(30)

        current += timedelta(days=1)

    print(f"All {submitted} daily dT tasks submitted.")


def main():
    parser = argparse.ArgumentParser(description="Build daily dT for SSEBop")
    parser.add_argument("--source-coll", required=True, help="EE daily met collection")
    parser.add_argument("--output-coll", required=True, help="Output EE ImageCollection")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--tmax-band", default="temperature_2m_max")
    parser.add_argument("--tmin-band", default="temperature_2m_min")
    parser.add_argument("--rs-band", default=None, help="Solar radiation band")
    parser.add_argument("--ea-band", default=None, help="Actual vapor pressure band (kPa)")
    parser.add_argument(
        "--dewpoint-band", default="dewpoint_temperature_2m", help="Dewpoint band for ea derivation"
    )
    parser.add_argument("--tmax-units", default="K", choices=["K", "C"])
    parser.add_argument("--tmin-units", default="K", choices=["K", "C"])
    parser.add_argument("--rs-units", default=None, choices=["J/m2", "W/m2", "MJ/m2/d"])
    parser.add_argument("--dt-min", type=float, default=6.0)
    parser.add_argument("--dt-max", type=float, default=25.0)
    parser.add_argument("--elev-source", default="USGS/SRTMGL1_003")
    parser.add_argument("--project", default="ee-dgketchum")
    args = parser.parse_args()

    build_dt_daily(
        source_coll=args.source_coll,
        output_coll=args.output_coll,
        start_date=args.start_date,
        end_date=args.end_date,
        tmax_band=args.tmax_band,
        tmin_band=args.tmin_band,
        rs_band=args.rs_band,
        ea_band=args.ea_band,
        dewpoint_band=args.dewpoint_band,
        tmax_units=args.tmax_units,
        tmin_units=args.tmin_units,
        rs_units=args.rs_units,
        dt_min=args.dt_min,
        dt_max=args.dt_max,
        elev_source=args.elev_source,
        project=args.project,
    )


if __name__ == "__main__":
    main()
