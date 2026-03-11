"""QAQC processing for MADIS and ISD station data using agweather-qaqc.

Two-source pipeline:
  - MADIS stations: Read from station_por parquets (have their own rsds)
  - ISD stations: Read from year-partitioned parquets + MODIS DSR for solar

Both paths apply identical QAQC steps: physical bounds, isolated obs removal,
monthly z-score outlier detection, Rs period-ratio drift correction, then
recompute PM-ETo from corrected variables.

Output: one CSV per viable station in met/qaqc_stations/{station_id}.csv

Usage:
    python qaqc_stations.py
"""

import json
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import refet
from agweatherqaqc.input_functions import _daily_realistic_limits, _remove_isolated_observations
from agweatherqaqc.qaqc_functions import modified_z_score_outlier_detection, rs_period_ratio_corr
from refet import calcs

SELECTED = Path(__file__).parent / "selected_stations.json"

# MADIS
MADIS_POR_DIR = Path("/data/ssd2/madis/station_por")

# ISD
ISD_DAILY = Path("/nas/climate/isd/parquet/daily")
ISD_STATIONS = "/nas/climate/isd/indices/stations.parquet"
MODIS_DSR_DIR = Path(__file__).parent / "modis_dsr"

OUT_DIR = Path(__file__).parent / "qaqc_stations"

# Conversion: 1 MJ/m²/d = 11.574 W/m²
MJM2D_TO_WM2 = 1.0 / 0.0864
WM2_TO_MJM2D = 0.0864

# 10m -> 2m wind conversion factor: 4.87 / ln(67.8*10 - 5.42)
WIND_10M_TO_2M = 4.87 / np.log(67.8 * 10 - 5.42)

# MODIS MCD18A1 / MADIS temporal range
YEAR_START = 2000
YEAR_END = 2024

MIN_COMMON_DAYS = 365

LOG_PATH = "/dev/null"


def saturation_vp(t_c):
    """Tetens formula: temperature [C] -> saturation vapor pressure [kPa]."""
    return 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))


def read_madis_station(fid):
    """Read MADIS station_por parquet for one station.

    Returns (DataFrame with DatetimeIndex and columns tmax, tmin, ea, u2, rsds,
             lat, elev) or (None, None, None).
    """
    path = MADIS_POR_DIR / f"{fid}.parquet"
    if not path.exists():
        return None, None, None

    df = pd.read_parquet(path)

    # Strip timezone from index if present
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()

    lat = float(df["latitude"].iloc[0])
    elev = float(df["elevation"].iloc[0])

    # Filter to study period
    df = df[(df.index.year >= YEAR_START) & (df.index.year <= YEAR_END)]

    # MADIS columns: tmax, tmin (°C), rsds (MJ/m²/d), ea (kPa), u2 (m/s)
    required = {"tmax", "tmin", "rsds", "ea", "u2"}
    if not required.issubset(df.columns):
        return None, None, None

    out = df[["tmax", "tmin", "rsds", "ea", "u2"]].copy()

    # Drop rows where all met vars are NaN
    out = out.dropna(how="all")
    if len(out) < MIN_COMMON_DAYS:
        return None, None, None

    return out, lat, elev


def read_isd_station(station_id):
    """Read ISD daily parquets for one station (2000-2024).

    Returns DataFrame with DatetimeIndex and columns:
    tmax_c, tmin_c, dewpoint_mean_c, wind_speed_mean_ms
    """
    frames = []
    for year in range(YEAR_START, YEAR_END + 1):
        path = ISD_DAILY / f"year={year}" / f"{station_id}.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path))

    if not frames:
        return None

    df = pd.concat(frames)
    if "date" in df.columns:
        df.index = pd.DatetimeIndex(pd.to_datetime(df["date"]))
        df = df.drop(columns=["date"], errors="ignore")
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.DatetimeIndex(df.index)

    df.index = df.index.normalize()
    df = df[~df.index.duplicated(keep="first")]
    return df.sort_index()


def get_isd_station_meta(station_id):
    """Get lat and elevation for one ISD station from metadata."""
    stations = pd.read_parquet(ISD_STATIONS)
    row = stations[stations["station_id"] == station_id]
    if row.empty:
        return None, None
    return float(row["lat"].iloc[0]), float(row["elev_m"].iloc[0])


def run_qaqc(tmax, tmin, ea, u2, rsds_mjm2d, dates, lat, elev):
    """Run shared QAQC steps on aligned arrays. Returns cleaned arrays or None."""
    # Convert rsds to W/m² for agweather-qaqc
    rsds_wm2 = rsds_mjm2d * MJM2D_TO_WM2

    # Step 1: Physical bounds
    tmax = _daily_realistic_limits(tmax, LOG_PATH, "temperature")
    tmin = _daily_realistic_limits(tmin, LOG_PATH, "temperature")
    ea = _daily_realistic_limits(ea, LOG_PATH, "vapor_pressure")
    u2 = _daily_realistic_limits(u2, LOG_PATH, "wind_speed")
    rsds_wm2 = _daily_realistic_limits(rsds_wm2, LOG_PATH, "solar_radiation")

    # Step 2: Isolated observation removal
    tmax = _remove_isolated_observations(tmax)
    tmin = _remove_isolated_observations(tmin)
    ea = _remove_isolated_observations(ea)
    u2 = _remove_isolated_observations(u2)
    rsds_wm2 = _remove_isolated_observations(rsds_wm2)

    # Step 3: Monthly z-score outlier detection
    months = dates.month
    for arr in [tmax, tmin, ea, rsds_wm2]:
        for m in range(1, 13):
            mask = months == m
            month_data = arr[mask]
            if np.sum(~np.isnan(month_data)) < 10:
                continue
            cleaned, _ = modified_z_score_outlier_detection(month_data)
            arr[mask] = cleaned

    # Step 4: Rs period-ratio drift correction
    doy = dates.dayofyear.values
    lat_rad = lat * np.pi / 180.0

    ra = calcs._ra_daily(lat_rad, doy)
    rso_mjm2d = calcs._rso_simple(ra, elev)
    rso_wm2 = rso_mjm2d * MJM2D_TO_WM2

    log_writer = StringIO()
    n = len(rsds_wm2)
    period = 60
    n_trunc = (n // period) * period
    if n_trunc >= period:
        try:
            corr_rsds_wm2, _ = rs_period_ratio_corr(
                log_writer, 0, n_trunc, rsds_wm2[:n_trunc], rso_wm2[:n_trunc], 6, period
            )
            rsds_wm2[:n_trunc] = corr_rsds_wm2
        except ValueError:
            pass

    # Convert rsds back to MJ/m²/d
    rsds_mjm2d = rsds_wm2 * WM2_TO_MJM2D

    # Step 5: Recompute PM-ETo
    tmean = (tmax + tmin) / 2.0
    vpd = (saturation_vp(tmax) + saturation_vp(tmin)) / 2.0 - ea

    eto = refet.Daily(
        tmin=tmin,
        tmax=tmax,
        rs=rsds_mjm2d,
        uz=u2,
        zw=2.0,
        elev=elev,
        lat=lat,
        doy=doy,
        ea=ea,
    ).eto()

    return tmax, tmin, tmean, rsds_mjm2d, ea, vpd, u2, eto


def qaqc_madis_station(fid):
    """Run QAQC pipeline on one MADIS station."""
    data, lat, elev = read_madis_station(fid)
    if data is None:
        return None

    # Use dates where all required vars are present
    valid = data[["tmax", "tmin", "rsds", "ea", "u2"]].notna().all(axis=1)
    data = data[valid]
    if len(data) < MIN_COMMON_DAYS:
        return None

    dates = pd.DatetimeIndex(data.index)
    tmax = data["tmax"].values.copy().astype(float)
    tmin = data["tmin"].values.copy().astype(float)
    ea = data["ea"].values.copy().astype(float)
    u2 = data["u2"].values.copy().astype(float)
    rsds_mjm2d = data["rsds"].values.copy().astype(float)

    result = run_qaqc(tmax, tmin, ea, u2, rsds_mjm2d, dates, lat, elev)
    if result is None:
        return None

    tmax, tmin, tmean, rsds_mjm2d, ea, vpd, u2, eto = result

    out_df = pd.DataFrame(
        {
            "tmax": tmax,
            "tmin": tmin,
            "tmean": tmean,
            "rsds": rsds_mjm2d,
            "ea": ea,
            "vpd": vpd,
            "u2": u2,
            "eto": eto,
        },
        index=dates,
    )
    out_df.index.name = "date"
    out_df.to_csv(OUT_DIR / f"{fid}.csv")
    return "ok"


def qaqc_isd_station(station_id):
    """Run QAQC pipeline on one ISD station (with MODIS DSR)."""
    isd = read_isd_station(station_id)
    if isd is None:
        return None

    modis_path = MODIS_DSR_DIR / f"{station_id}.csv"
    if not modis_path.exists():
        return None

    modis = pd.read_csv(modis_path, parse_dates=["date"], index_col="date")
    modis.index = modis.index.normalize()

    lat, elev = get_isd_station_meta(station_id)
    if lat is None:
        return None

    required_cols = {"tmax_c", "tmin_c", "dewpoint_mean_c", "wind_speed_mean_ms"}
    if not required_cols.issubset(isd.columns):
        return None

    isd["ea"] = saturation_vp(isd["dewpoint_mean_c"])
    isd["u2"] = isd["wind_speed_mean_ms"] * WIND_10M_TO_2M

    common = isd.index.intersection(modis.index)
    if len(common) < MIN_COMMON_DAYS:
        return None

    dates = pd.DatetimeIndex(common)
    tmax = isd.loc[common, "tmax_c"].values.copy().astype(float)
    tmin = isd.loc[common, "tmin_c"].values.copy().astype(float)
    ea = isd.loc[common, "ea"].values.copy().astype(float)
    u2 = isd.loc[common, "u2"].values.copy().astype(float)
    rsds_mjm2d = modis.loc[common, "rsds"].values.copy().astype(float)

    result = run_qaqc(tmax, tmin, ea, u2, rsds_mjm2d, dates, lat, elev)
    if result is None:
        return None

    tmax, tmin, tmean, rsds_mjm2d, ea, vpd, u2, eto = result

    out_df = pd.DataFrame(
        {
            "tmax": tmax,
            "tmin": tmin,
            "tmean": tmean,
            "rsds": rsds_mjm2d,
            "ea": ea,
            "vpd": vpd,
            "u2": u2,
            "eto": eto,
        },
        index=dates,
    )
    out_df.index.name = "date"
    out_df.to_csv(OUT_DIR / f"{station_id}.csv")
    return "ok"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(SELECTED) as f:
        selected = json.load(f)

    # Collect stations grouped by source
    madis_stations = set()
    isd_stations = set()
    for site_data in selected.values():
        source = site_data.get("source", "isd")
        if source == "madis":
            madis_stations.update(site_data["stations"])
        else:
            isd_stations.update(site_data["stations"])

    print(f"MADIS stations: {len(madis_stations)}, ISD stations: {len(isd_stations)}")

    # Process MADIS stations
    print(f"\nProcessing {len(madis_stations)} MADIS stations...")
    n_ok, n_skip = 0, 0
    for fid in sorted(madis_stations):
        result = qaqc_madis_station(fid)
        if result == "ok":
            n_ok += 1
            print(f"  {fid}: ok")
        else:
            n_skip += 1
            print(f"  {fid}: skip")

    print(f"MADIS summary: {n_ok} ok, {n_skip} skip")

    # Process ISD stations
    print(f"\nProcessing {len(isd_stations)} ISD stations...")
    n_ok_isd, n_skip_isd = 0, 0
    for station_id in sorted(isd_stations):
        result = qaqc_isd_station(station_id)
        if result == "ok":
            n_ok_isd += 1
            print(f"  {station_id}: ok")
        else:
            n_skip_isd += 1
            print(f"  {station_id}: skip")

    print(f"ISD summary: {n_ok_isd} ok, {n_skip_isd} skip")
    print(f"\nTotal: {n_ok + n_ok_isd} ok, {n_skip + n_skip_isd} skip")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
