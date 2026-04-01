import os
import time
from datetime import date, timedelta

import ee

try:
    from openet.refetgee import Daily
except ImportError:  # pragma: no cover
    Daily = None

from swimrs.data_extraction.ee.ee_utils import as_ee_feature_collection
from swimrs.units import GEE_ERA5_LAND_HOURLY_DATASET
from swimrs.utils.optional_deps import missing_optional_dependency


def _tag_features_with_utc_offset(fc: ee.FeatureCollection) -> ee.FeatureCollection:
    """Add ``utc_offset_hours`` property to each feature from its centroid longitude.

    Uses the solar time approximation: offset_hours = round(longitude / 15).
    This matches the approach in openet-ptjpl for ERA5-Land reference ET.
    """

    def _tag(feature):
        lon = ee.Number(feature.geometry().centroid(1).coordinates().get(0))
        return feature.set("utc_offset_hours", lon.divide(15).round())

    return fc.map(_tag)


def _get_unique_offsets(fc: ee.FeatureCollection) -> list[int]:
    """Return sorted unique ``utc_offset_hours`` values from a tagged feature collection."""
    offsets = fc.aggregate_array("utc_offset_hours").distinct().sort().getInfo()
    return [int(o) for o in offsets]


def _format_offset_suffix(offset: int) -> str:
    """Format a UTC offset integer as a filename suffix.

    Examples: -4 → ``utc_m04``, 0 → ``utc_p00``, 9 → ``utc_p09``
    """
    sign = "m" if offset < 0 else "p"
    return f"utc_{sign}{abs(offset):02d}"


def _local_day_utc_bounds(day_date: date, utc_offset_hours: ee.Number) -> tuple:
    """Get UTC start/end times for a local day given UTC offset.

    Parameters
    ----------
    day_date : date
        The calendar date (interpreted as local date)
    utc_offset_hours : ee.Number
        Hours offset from UTC (e.g., -7 for Mountain Time)

    Returns
    -------
    tuple[ee.Date, ee.Date]
        (utc_start, utc_end) representing local midnight-to-midnight in UTC
    """
    local_midnight = ee.Date.fromYMD(day_date.year, day_date.month, day_date.day)
    utc_start = local_midnight.advance(utc_offset_hours.multiply(-1), "hour")
    utc_end = utc_start.advance(1, "day")
    return utc_start, utc_end


def _aggregate_hourly_to_daily(hourly_coll: ee.ImageCollection, day_str: str) -> ee.Image:
    """Aggregate 24 hourly images to daily values.

    Parameters
    ----------
    hourly_coll : ee.ImageCollection
        Filtered collection of ~24 hourly ERA5-Land images for one local day
    day_str : str
        Date string in YYYYMMDD format for band naming

    Returns
    -------
    ee.Image
        Multi-band image with daily aggregates
    """
    # Temperature: mean, min, max (K -> C)
    # See ERA5_LAND_HOURLY_UNITS['temperature_2m'].
    temp = hourly_coll.select("temperature_2m")
    tmean_c = temp.mean().subtract(273.15).rename(f"tmean_{day_str}")
    tmin_c = temp.min().subtract(273.15).rename(f"tmin_{day_str}")
    tmax_c = temp.max().subtract(273.15).rename(f"tmax_{day_str}")

    # Precipitation: sum hourly accumulations (m -> mm)
    # See ERA5_LAND_HOURLY_UNITS['total_precipitation_hourly'].
    precip_mm = (
        hourly_coll.select("total_precipitation_hourly")
        .sum()
        .multiply(1000)
        .rename(f"precip_{day_str}")
    )

    # Solar radiation: sum J/m² then convert to daily-mean W/m² (divide by 86400 seconds)
    # See ERA5_LAND_HOURLY_UNITS['surface_solar_radiation_downwards_hourly'].
    srad_wm2 = (
        hourly_coll.select("surface_solar_radiation_downwards_hourly")
        .sum()
        .divide(86400)
        .rename(f"srad_{day_str}")
    )

    # SWE: mean of instantaneous values (m -> mm)
    # See ERA5_LAND_HOURLY_UNITS['snow_depth_water_equivalent'].
    swe_mm = (
        hourly_coll.select("snow_depth_water_equivalent")
        .mean()
        .multiply(1000)
        .rename(f"swe_{day_str}")
    )

    return ee.Image([swe_mm, tmean_c, tmin_c, tmax_c, precip_mm, srad_wm2])


def sample_era5_land_variables_daily(
    shapefile: str,
    bucket: str | None = None,
    debug: bool = False,
    check_dir: str | None = None,
    overwrite: bool = False,
    start_yr: int = 2004,
    end_yr: int = 2023,
    feature_id_col: str = "FID",
    file_prefix: str = "swim",
) -> None:
    """Export daily ERA5-Land variables reduced over features, by month and UTC offset.

    Uses the ERA5-Land HOURLY collection with local-time day boundaries to match
    openet-ptjpl's reference ET calculation. Each feature is assigned its own
    rounded UTC offset (offset_hours = round(lon / 15)) and features are grouped
    by offset for export, so that daily aggregation windows are correct for all
    sites regardless of longitude.

    For each (month, offset_group), builds an ee.Image with per-day bands for:
    - SWE (mm)
    - ETo (mm; via refetgee)
    - Tmean/Tmin/Tmax (°C)
    - precip (mm)
    - srad (W/m^2; derived from daily sum)
    then reduces to feature means and exports to GCS.

    Parameters
    - shapefile: path to local shapefile with polygon features.
    - bucket: str GCS bucket for outputs.
    - debug: bool; if True, prints sample reduction for a feature.
    - check_dir: local directory to skip existing month CSVs.
    - overwrite: bool; if True, re-export even if file present.
    - start_yr, end_yr: int year range inclusive.
    - feature_id_col: property name to include as ID.
    - file_prefix: str prefix for bucket subdirectory (e.g., project name).

    Side Effects
    - Starts ee.batch table exports, one per (month, offset_group), to the `bucket`.
    """
    if Daily is None:  # pragma: no cover
        raise missing_optional_dependency(
            extra="openet",
            purpose="ERA5-Land daily reference ET export (refetgee)",
            import_name="openet-refet-gee",
        )

    fc = as_ee_feature_collection(shapefile, feature_id=feature_id_col)
    era5_land_hourly = ee.ImageCollection(GEE_ERA5_LAND_HOURLY_DATASET)

    # Tag each feature with its own rounded UTC offset and discover unique groups
    fc = _tag_features_with_utc_offset(fc)
    unique_offsets = _get_unique_offsets(fc)
    print(f"UTC offset groups: {unique_offsets}")

    skipped_exports, exported_count = 0, 0
    dtimes = [(y, m) for y in range(start_yr, end_yr + 1) for m in range(1, 13)]

    # Use a scale smaller than feature sizes to ensure reduceRegions finds pixels.
    # ERA5-Land native resolution is ~11km, but small polygons (e.g., 150m buffers)
    # need a finer scale so the image is resampled before reduction.
    scale_era5 = 150

    def _days_in_month(year_: int, month_: int) -> list[date]:
        d0 = date(year_, month_, 1)
        if month_ == 12:
            d1 = date(year_ + 1, 1, 1)
        else:
            d1 = date(year_, month_ + 1, 1)
        out = []
        d = d0
        while d < d1:
            out.append(d)
            d = d + timedelta(days=1)
        return out

    for year, month in dtimes:
        days_in_month = _days_in_month(year, month)
        if not days_in_month:
            continue

        # Build selector list once per month (band names are offset-independent)
        current_month_selectors = [feature_id_col]
        for d in days_in_month:
            ds = d.strftime("%Y%m%d")
            current_month_selectors.extend(
                [
                    f"swe_{ds}",
                    f"eto_{ds}",
                    f"tmean_{ds}",
                    f"tmin_{ds}",
                    f"tmax_{ds}",
                    f"precip_{ds}",
                    f"srad_{ds}",
                ]
            )

        for offset in unique_offsets:
            suffix = _format_offset_suffix(offset)
            desc = f"era5_vars_{year}_{str(month).zfill(2)}_{suffix}"

            if check_dir and not overwrite:
                output_filepath = os.path.join(check_dir, f"{desc}.csv")
                if os.path.exists(output_filepath):
                    skipped_exports += 1
                    continue

            # Filter features to this offset group
            fc_group = fc.filter(ee.Filter.eq("utc_offset_hours", offset))
            utc_offset_hours = ee.Number(offset)

            first_band_in_month = True
            monthly_bands_image = None

            for d in days_in_month:
                day_str_yyyymmdd = d.strftime("%Y%m%d")

                # Get UTC bounds for local day using this group's offset
                utc_start, utc_end = _local_day_utc_bounds(d, utc_offset_hours)
                day_start_ee = ee.Date(d.isoformat())

                # Filter hourly collection for local day
                hourly_for_day = era5_land_hourly.filterDate(utc_start, utc_end)

                # Aggregate hourly to daily
                daily_vars = _aggregate_hourly_to_daily(hourly_for_day, day_str_yyyymmdd)

                # Grass-reference ETo via refetgee using the same local-day hourly collection
                daily_eto_img = Daily.era5_land(hourly_for_day).eto.rename(
                    f"eto_{day_str_yyyymmdd}"
                )

                # Combine all bands and set time property
                all_daily_bands = daily_vars.addBands(daily_eto_img)
                all_daily_bands = all_daily_bands.set("system:time_start", day_start_ee.millis())

                if first_band_in_month:
                    monthly_bands_image = all_daily_bands
                    first_band_in_month = False
                else:
                    monthly_bands_image = monthly_bands_image.addBands(all_daily_bands)

            if monthly_bands_image is None:
                continue

            if debug:
                debug_fc_collection = fc_group.filterMetadata("sid", "equals", "BE-Lon")
                debug_data = monthly_bands_image.reduceRegions(  # noqa: F841
                    collection=debug_fc_collection,
                    reducer=ee.Reducer.mean(),
                    scale=scale_era5,
                ).getInfo()

            output_data = monthly_bands_image.reduceRegions(
                collection=fc_group,
                reducer=ee.Reducer.mean(),
                scale=scale_era5,
            )

            task = ee.batch.Export.table.toCloudStorage(
                collection=output_data,
                description=desc,
                bucket=bucket,
                fileNamePrefix=f"{file_prefix}/meteorology/era5_land/extracts/{desc}",
                fileFormat="CSV",
                selectors=current_month_selectors,
            )

            try:
                task.start()
            except ee.ee_exception.EEException as e:
                print(f"{e}, waiting on ", desc, "......")
                time.sleep(600)
                task.start()
            exported_count += 1


if __name__ == "__main__":
    pass
# ========================= EOF ====================================================================
