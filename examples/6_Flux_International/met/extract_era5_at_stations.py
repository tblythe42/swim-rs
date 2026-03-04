"""Extract ERA5-Land variables at ISD station locations and compute PM-ETo.

Reads raw ERA5-Land NetCDF files, extracts nearest-neighbor time series at
each selected ISD station, applies unit conversions, and computes ASCE
standardized reference ET using the refet package.

Output: one CSV per station in met/era5_extractions/{station_id}.csv

Usage:
    python extract_era5_at_stations.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import refet
import xarray as xr

SELECTED = Path(__file__).parent / "selected_stations.json"
ISD_STATIONS = "/nas/climate/isd/indices/stations.parquet"
NC_DIR = Path("/data/ssd1/era5-land/era5_nc_daily_1990-2024")
OUT_DIR = Path(__file__).parent / "era5_extractions"

# NetCDF grid domain (CONUS only)
NC_LAT_MIN = 22.2
NC_LAT_MAX = 60.4
NC_LON_MIN = -129.6
NC_LON_MAX = -63.0

# ERA5-Land NetCDF file stems -> short variable keys
NC_FILES = {
    "tmax": "temperature_2m_max_1990-2024_daily",
    "tmin": "temperature_2m_min_1990-2024_daily",
    "rsds": "surface_solar_radiation_downwards_sum_1990-2024_daily",
    "u10": "u_component_of_wind_10m_1990-2024_daily",
    "v10": "v_component_of_wind_10m_1990-2024_daily",
    "tdew": "dewpoint_temperature_2m_1990-2024_daily",
}

# 10m -> 2m wind conversion factor: 4.87 / ln(67.8*10 - 5.42)
WIND_10M_TO_2M = 4.87 / np.log(67.8 * 10 - 5.42)


def get_unique_stations():
    """Get deduplicated station IDs from selected_stations.json."""
    with open(SELECTED) as f:
        selected = json.load(f)
    stations = set()
    for site_data in selected.values():
        stations.update(site_data["stations"])
    return sorted(stations)


def get_station_meta(station_ids):
    """Get lat/lon/elev for station IDs from ISD stations parquet."""
    stations = pd.read_parquet(ISD_STATIONS)
    stations = stations.set_index("station_id")
    stations = stations.rename(
        columns={"lat": "latitude", "lon": "longitude", "elev_m": "elevation"}
    )
    return stations.loc[stations.index.isin(station_ids), ["latitude", "longitude", "elevation"]]


def extract_nc(nc_stem, lats, lons, station_ids):
    """Extract nearest-neighbor time series from one NC file.

    Returns DataFrame with DatetimeIndex rows and station_id columns.
    Uses chunked reading because netCDF4 doesn't support fancy indexing.
    """
    nc_path = NC_DIR / f"{nc_stem}.nc"
    time_path = NC_DIR / f"{nc_stem}_time.csv"

    print(f"  Reading {nc_path.name}...")
    times = pd.read_csv(time_path, parse_dates=["datetime"])["datetime"].values

    ds = xr.open_dataset(nc_path)
    data_var = [v for v in ds.data_vars if v != "crs"][0]
    da = ds[data_var]

    # Find nearest grid index for each station
    lat_coords = da.coords["latitude"].values
    lon_coords = da.coords["longitude"].values
    lat_idx = np.abs(lat_coords[None, :] - lats[:, None]).argmin(axis=1)
    lon_idx = np.abs(lon_coords[None, :] - lons[:, None]).argmin(axis=1)

    # Extract in time chunks (load slice to numpy, then fancy-index stations)
    n_times = len(times)
    chunk_size = 1000
    chunks = []
    for t0 in range(0, n_times, chunk_size):
        t1 = min(t0 + chunk_size, n_times)
        arr = da.isel(time=slice(t0, t1)).values  # (chunk, lat, lon)
        chunks.append(arr[:, lat_idx, lon_idx])  # (chunk, n_stations)
        print(f"    {nc_stem}: {t1}/{n_times} timesteps")

    values = np.concatenate(chunks, axis=0)  # (n_times, n_stations)
    df = pd.DataFrame(values, index=pd.DatetimeIndex(times), columns=station_ids)
    ds.close()
    return df


def saturation_vp(t_c):
    """Tetens formula: temperature [C] -> saturation vapor pressure [kPa]."""
    return 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading selected stations...")
    station_ids = get_unique_stations()
    print(f"  {len(station_ids)} unique stations")

    meta = get_station_meta(station_ids)
    station_ids = [s for s in station_ids if s in meta.index]
    print(f"  {len(station_ids)} stations with metadata")

    # Partition into in-domain (CONUS NC grid) vs out-of-domain
    in_domain = []
    out_domain = []
    for sid in station_ids:
        lat = meta.loc[sid, "latitude"]
        lon = meta.loc[sid, "longitude"]
        if NC_LAT_MIN <= lat <= NC_LAT_MAX and NC_LON_MIN <= lon <= NC_LON_MAX:
            in_domain.append(sid)
        else:
            out_domain.append(sid)

    if out_domain:
        print(f"  {len(out_domain)} stations outside CONUS NC domain — use extract_era5_ee.py")
    station_ids = in_domain
    print(f"  {len(station_ids)} in-domain stations for NC extraction")

    lats = meta.loc[station_ids, "latitude"].values
    lons = meta.loc[station_ids, "longitude"].values
    elevs = meta.loc[station_ids, "elevation"].values

    # Extract all NC variables
    print("Extracting ERA5-Land variables from NetCDF...")
    data = {}
    for var_key, nc_stem in NC_FILES.items():
        data[var_key] = extract_nc(nc_stem, lats, lons, station_ids)

    # Unit conversions
    print("Applying unit conversions...")

    # Temperature: K -> C
    data["tmax"] = data["tmax"] - 273.15
    data["tmin"] = data["tmin"] - 273.15
    data["tdew"] = data["tdew"] - 273.15

    # Solar radiation: J/m2/day -> MJ/m2/day
    data["rsds"] = data["rsds"] / 1e6

    # Wind: u/v components -> speed at 10m -> 2m
    u10 = data.pop("u10")
    v10 = data.pop("v10")
    ws10 = np.sqrt(u10**2 + v10**2)
    data["u2"] = ws10 * WIND_10M_TO_2M

    # Vapor pressure from dewpoint
    data["ea"] = saturation_vp(data["tdew"])

    # VPD (diagnostic)
    data["vpd"] = (saturation_vp(data["tmax"]) + saturation_vp(data["tmin"])) / 2 - data["ea"]

    # Tmean (diagnostic)
    data["tmean"] = (data["tmax"] + data["tmin"]) / 2

    # Compute PM-ETo with refet (ASCE standardized)
    print("Computing PM-ETo...")
    dates = data["tmax"].index
    doy = dates.dayofyear.values

    eto_frames = {}
    for i, sid in enumerate(station_ids):
        eto_vals = refet.Daily(
            tmin=data["tmin"][sid].values,
            tmax=data["tmax"][sid].values,
            rs=data["rsds"][sid].values,
            uz=data["u2"][sid].values,
            zw=2.0,
            elev=elevs[i],
            lat=lats[i],
            doy=doy,
            ea=data["ea"][sid].values,
        ).eto()
        eto_frames[sid] = eto_vals
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(station_ids)} stations")

    data["eto"] = pd.DataFrame(eto_frames, index=dates)

    # Write per-station CSVs
    print("Writing CSVs...")
    out_vars = ["tmax", "tmin", "tmean", "rsds", "ea", "vpd", "u2", "eto"]
    for sid in station_ids:
        df = pd.DataFrame({v: data[v][sid] for v in out_vars}, index=dates)
        df.index.name = "date"
        df.to_csv(OUT_DIR / f"{sid}.csv")

    print(f"  Wrote {len(station_ids)} CSVs to {OUT_DIR}")


if __name__ == "__main__":
    main()
