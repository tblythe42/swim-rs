# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "earthengine-api",
# ]
# ///
"""Build DOY Tmax climatology for SSEBop v0.2.6 international use.

Computes per-DOY mean (or median) Tmax from a global daily temperature
collection and exports to an EE ImageCollection asset.

Usage:
    uv run ssebop_v026_tmax_climo.py --source-coll ERA5_LAND/DAILY_AGGR \
        --source-band temperature_2m_max --source-units K \
        --output-coll projects/ee-dgketchum/assets/ssebop/tmax_era5land_mean_2000_2020 \
        --start-year 2000 --end-year 2020 --stat mean
"""

import argparse

import ee


def build_tmax_climatology(
    source_coll,
    source_band,
    source_units,
    output_coll,
    start_year,
    end_year,
    stat="mean",
    elr=False,
    project="ee-dgketchum",
):
    """Build DOY Tmax climatology and export to EE asset collection."""
    ee.Initialize(project=project)

    # Ensure output collection exists
    try:
        ee.data.createAsset({"type": "ImageCollection"}, output_coll)
        print(f"Created asset collection: {output_coll}")
    except ee.ee_exception.EEException:
        pass  # already exists

    src = ee.ImageCollection(source_coll).select(source_band)

    # Filter to year range
    src = src.filter(ee.Filter.calendarRange(start_year, end_year, "year"))

    # Convert to Kelvin if needed
    if source_units.upper() == "C":
        src = src.map(lambda img: img.add(273.15).copyProperties(img, img.propertyNames()))
    elif source_units.upper() == "K":
        pass  # already Kelvin
    else:
        raise ValueError(f"Unknown source_units: {source_units}")

    # ELR correction is not implemented here. The upstream v0.2.6 uses
    # model.elr_adjust() which corrects locally elevated terrain relative
    # to surrounding relief, not a blanket lapse-rate subtraction. If ELR
    # is needed, use openet.ssebop.model.elr_adjust() on the output.
    if elr:
        raise NotImplementedError(
            "ELR correction requires openet.ssebop.model.elr_adjust() — "
            "not a simple lapse-rate subtraction. Omit --elr for now."
        )

    print(f"Building {stat} Tmax climatology for DOY 1-366")
    print(f"  Source: {source_coll} [{source_band}] ({source_units})")
    print(f"  Years: {start_year}-{end_year}")
    print(f"  Output: {output_coll}")

    for doy in range(1, 367):
        doy_coll = src.filter(ee.Filter.calendarRange(doy, doy, "day_of_year"))

        if stat == "mean":
            climo_img = doy_coll.mean()
        elif stat == "median":
            climo_img = doy_coll.median()
        else:
            raise ValueError(f"Unknown stat: {stat}")

        climo_img = climo_img.rename("tmax").set(
            {
                "doy": doy,
                "start_year": start_year,
                "end_year": end_year,
                "source_collection": source_coll,
                "source_band": source_band,
                "statistic": stat,
            }
        )

        desc = f"tmax_climo_doy{doy:03d}"
        asset_id = f"{output_coll}/{desc}"

        task = ee.batch.Export.image.toAsset(
            image=climo_img,
            description=desc,
            assetId=asset_id,
            scale=11132,  # ERA5-Land native ~11km
            maxPixels=1e10,
        )
        task.start()

        if doy % 50 == 0 or doy == 1:
            print(f"  Submitted DOY {doy}/366")

    print("All 366 tasks submitted.")


def main():
    parser = argparse.ArgumentParser(description="Build DOY Tmax climatology for SSEBop")
    parser.add_argument("--source-coll", required=True, help="EE ImageCollection ID")
    parser.add_argument("--source-band", required=True, help="Band name for Tmax")
    parser.add_argument(
        "--source-units", required=True, choices=["C", "K"], help="Temperature units"
    )
    parser.add_argument("--output-coll", required=True, help="Output EE ImageCollection asset ID")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--stat", default="mean", choices=["mean", "median"])
    parser.add_argument(
        "--elr", action="store_true", help="Apply environmental lapse rate correction"
    )
    parser.add_argument("--project", default="ee-dgketchum", help="EE project ID")
    args = parser.parse_args()

    build_tmax_climatology(
        source_coll=args.source_coll,
        source_band=args.source_band,
        source_units=args.source_units,
        output_coll=args.output_coll,
        start_year=args.start_year,
        end_year=args.end_year,
        stat=args.stat,
        elr=args.elr,
        project=args.project,
    )


if __name__ == "__main__":
    main()
