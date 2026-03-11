"""Select nearest ag-met stations per flux site for ERA5-Land bias correction.

Two-source pipeline:
  - CONUS/CA flux sites: MADIS cropland stations (with measured rsds)
  - EU/AU flux sites: ISD cropland stations (GLC10-filtered)

Both pools require mandatory GLC10 cropland filtering (mode==10).

Usage:
    python select_stations.py
"""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod

FLUX_SHP = "/data/ssd1/swim/6_Flux_International/data/gis/flux_intl_buffers_150m_06JAN2026.shp"

# MADIS
MADIS_GLC10_CSV = Path(__file__).parent / "madis_glc10_cropland.csv"
MADIS_POR_DIR = Path("/data/ssd2/madis/station_por")

# ISD
ISD_GLC10_CSV = Path(__file__).parent / "isd_glc10_cropland.csv"
ISD_STATIONS = "/nas/climate/isd/indices/stations.parquet"
ISD_COVERAGE = "/nas/climate/isd/indices/daily_coverage.shp"

OUT_DIR = Path(__file__).parent
OUT_FILE = OUT_DIR / "selected_stations.json"

# FROM-GLC10 cropland class
GLC10_CROPLAND = 10
N_NEIGHBORS = 10
MIN_OBS_DAYS = 365

# NC domain bounds (CONUS)
NC_LAT_MIN = 22.2
NC_LAT_MAX = 60.4
NC_LON_MIN = -129.6
NC_LON_MAX = -63.0


def in_nc_domain(lat, lon):
    """Check if a point is inside the CONUS NC grid domain."""
    return NC_LAT_MIN <= lat <= NC_LAT_MAX and NC_LON_MIN <= lon <= NC_LON_MAX


def load_flux_sites():
    """Load all flux sites and partition into CONUS/CA vs EU/AU."""
    flux = gpd.read_file(FLUX_SHP, engine="fiona")
    conus = flux[flux.apply(lambda r: in_nc_domain(r["lat"], r["lon"]), axis=1)]
    exconus = flux[~flux.index.isin(conus.index)]
    return conus, exconus


def load_madis_cropland_pool():
    """Load MADIS cropland stations with >365 days of rsds and eto.

    Returns DataFrame with columns: fid, latitude, longitude, elevation,
    rsds_count, eto_count.
    """
    glc10 = pd.read_csv(MADIS_GLC10_CSV)
    glc10["mode"] = pd.to_numeric(glc10["mode"], errors="coerce")
    cropland_fids = set(glc10[glc10["mode"].round() == GLC10_CROPLAND]["fid"])
    print(f"    {len(cropland_fids)} MADIS stations on cropland (mode==10)")

    records = []
    for i, fid in enumerate(sorted(cropland_fids)):
        path = MADIS_POR_DIR / f"{fid}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["rsds", "eto", "latitude", "longitude", "elevation"])
        rsds_n = int(df["rsds"].notna().sum())
        eto_n = int(df["eto"].notna().sum())
        if rsds_n >= MIN_OBS_DAYS and eto_n >= MIN_OBS_DAYS:
            records.append(
                {
                    "fid": fid,
                    "latitude": float(df["latitude"].iloc[0]),
                    "longitude": float(df["longitude"].iloc[0]),
                    "elevation": float(df["elevation"].iloc[0]),
                    "rsds_count": rsds_n,
                    "eto_count": eto_n,
                }
            )
        if (i + 1) % 500 == 0:
            print(f"    scanned {i + 1}/{len(cropland_fids)} parquets...")

    pool = pd.DataFrame(records)
    print(f"    {len(pool)} MADIS stations with >{MIN_OBS_DAYS} days rsds and eto")
    return pool


def load_isd_cropland_pool():
    """Load ISD cropland stations outside NC domain with sufficient coverage.

    Returns DataFrame with columns: station_id, lat, lon, elev_m.
    """
    glc10 = pd.read_csv(ISD_GLC10_CSV)
    glc10["mode"] = pd.to_numeric(glc10["mode"], errors="coerce")
    cropland_sids = set(glc10[glc10["mode"].round() == GLC10_CROPLAND]["station_id"])
    print(f"    {len(cropland_sids)} ISD stations on cropland (mode==10)")

    # Filter by coverage
    coverage = gpd.read_file(ISD_COVERAGE, engine="fiona")
    mask = (
        (coverage["n_tmax_c"] > MIN_OBS_DAYS)
        & (coverage["n_tmin_c"] > MIN_OBS_DAYS)
        & (coverage["n_dewpoint"] > MIN_OBS_DAYS)
        & (coverage["n_wind_spe"] > MIN_OBS_DAYS)
    )
    coverage = coverage[mask].copy()
    print(f"    {len(coverage)} ISD stations pass coverage filters")

    # Intersect with cropland
    coverage = coverage[coverage["station_id"].isin(cropland_sids)].copy()
    print(f"    {len(coverage)} after cropland intersection")

    # Join with metadata for lat/lon/elev
    stations = pd.read_parquet(ISD_STATIONS)
    merged = coverage.merge(
        stations[["station_id", "lat", "lon", "elev_m"]],
        on="station_id",
        how="inner",
    )
    merged = merged[merged["elev_m"].notna()].copy()
    print(f"    {len(merged)} with valid elevation")

    # Filter to outside NC domain (EU/AU only)
    outside = merged[~merged.apply(lambda r: in_nc_domain(r["lat"], r["lon"]), axis=1)].copy()
    print(f"    {len(outside)} outside NC domain (EU/AU)")

    return outside


def find_nearest(flux_sites, stations, station_id_col, lat_col, lon_col, source, n=N_NEIGHBORS):
    """For each flux site, find n nearest stations by geodesic distance."""
    geod = Geod(ellps="WGS84")
    result = {}

    s_lons = stations[lon_col].values
    s_lats = stations[lat_col].values
    s_sids = stations[station_id_col].values

    for _, site in flux_sites.iterrows():
        _, _, dists = geod.inv(
            np.full(len(s_lons), site["lon"]),
            np.full(len(s_lats), site["lat"]),
            s_lons,
            s_lats,
        )
        dists_km = np.abs(dists) / 1000.0
        k = min(n, len(s_sids))
        idx = np.argsort(dists_km)[:k]
        result[site["sid"]] = {
            "stations": s_sids[idx].tolist(),
            "distances_km": [round(dists_km[i], 2) for i in idx],
            "source": source,
        }

    return result


def main():
    print("Loading flux sites...")
    conus_sites, exconus_sites = load_flux_sites()
    print(f"  {len(conus_sites)} CONUS/CA sites, {len(exconus_sites)} EU/AU sites")

    # --- CONUS/CA pass: MADIS ---
    print("\nLoading MADIS cropland station pool...")
    madis_pool = load_madis_cropland_pool()

    print(f"\nFinding {N_NEIGHBORS} nearest MADIS stations per CONUS/CA site...")
    conus_selected = find_nearest(
        conus_sites, madis_pool, "fid", "latitude", "longitude", source="madis"
    )

    # --- EU/AU pass: ISD ---
    print("\nLoading ISD cropland station pool...")
    isd_pool = load_isd_cropland_pool()

    print(f"\nFinding {N_NEIGHBORS} nearest ISD stations per EU/AU site...")
    exconus_selected = find_nearest(
        exconus_sites, isd_pool, "station_id", "lat", "lon", source="isd"
    )

    # Merge
    selected = {}
    selected.update(conus_selected)
    selected.update(exconus_selected)

    for sid, data in sorted(selected.items()):
        dists = data["distances_km"]
        nearest = f"{dists[0]:.0f}" if dists else "N/A"
        farthest = f"{dists[-1]:.0f}" if dists else "N/A"
        print(f"    {sid} ({data['source']}): nearest={nearest} km, farthest={farthest} km")

    print(f"\nWriting {OUT_FILE}")
    with open(OUT_FILE, "w") as f:
        json.dump(selected, f, indent=2)

    n_madis = sum(1 for v in selected.values() if v["source"] == "madis")
    n_isd = sum(1 for v in selected.values() if v["source"] == "isd")
    print(f"  {n_madis} MADIS sites, {n_isd} ISD sites")


if __name__ == "__main__":
    main()
