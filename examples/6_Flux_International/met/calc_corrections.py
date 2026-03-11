"""Compute monthly ERA5-Land correction factors and IDW-interpolate to flux sites.

For each ISD station:
  - Read QAQC-cleaned obs from qaqc_stations/ (produced by qaqc_stations.py)
  - Pair with ERA5 extraction on matching dates
  - Compute long-term monthly mean ratios (obs/ERA5) for ETo, rsds, u2, vpd
  - Compute long-term monthly mean deltas (obs - ERA5) for tmean

For each flux site:
  - IDW (power=2) of correction factors from its nearest stations

Usage:
    python qaqc_stations.py   # first — produces qaqc_stations/*.csv
    python calc_corrections.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

SELECTED = Path(__file__).parent / "selected_stations.json"
QAQC_DIR = Path(__file__).parent / "qaqc_stations"
ERA5_DIR = Path(__file__).parent / "era5_extractions"
OUT_FILE = Path(__file__).parent / "correction_factors.json"

RATIO_VARS = ["eto", "rsds", "u2", "vpd"]
DELTA_VARS = ["tmean"]
MIN_DAYS = 30  # minimum days per station-month for a valid ratio
RATIO_LO = 0.5  # per-month ratio floor
RATIO_HI = 1.5  # per-month ratio ceiling


def compute_station_ratios(station_id):
    """Compute monthly obs/ERA5 ratios and deltas for one station.

    Returns dict like {"eto": {"1": 0.72, ...}, "tmean": {"1": -0.5, ...}} or None.
    Reads QAQC-cleaned station data — stations filtered upstream (missing ISD/MODIS,
    insufficient overlap) will not have a QAQC CSV and return None.
    """
    qaqc_path = QAQC_DIR / f"{station_id}.csv"
    era5_path = ERA5_DIR / f"{station_id}.csv"

    if not qaqc_path.exists() or not era5_path.exists():
        return None

    obs = pd.read_csv(qaqc_path, parse_dates=["date"], index_col="date")

    era5 = pd.read_csv(era5_path, parse_dates=["date"], index_col="date")

    common = obs.index.intersection(era5.index)
    if len(common) < 30:
        return None

    obs = obs.loc[common]
    era5 = era5.loc[common]

    result = {}

    # Multiplicative ratios
    for var in RATIO_VARS:
        if var not in obs.columns or var not in era5.columns:
            continue

        monthly = {}
        for month in range(1, 13):
            m_mask = obs.index.month == month
            m_obs = obs.loc[m_mask, var].dropna()
            m_era5 = era5.loc[m_mask, var].dropna()

            common_m = m_obs.index.intersection(m_era5.index)
            m_obs = m_obs.loc[common_m]
            m_era5 = m_era5.loc[common_m]

            # Require positive values for ratio
            valid = (m_obs > 0) & (m_era5 > 0)
            m_obs = m_obs[valid]
            m_era5 = m_era5[valid]

            if len(m_obs) >= MIN_DAYS:
                ratio = float(m_obs.mean() / m_era5.mean())
                ratio = max(RATIO_LO, min(ratio, RATIO_HI))
                monthly[str(month)] = round(ratio, 4)

        if monthly:
            result[var] = monthly

    # Additive deltas
    for var in DELTA_VARS:
        if var not in obs.columns or var not in era5.columns:
            continue

        monthly = {}
        for month in range(1, 13):
            m_mask = obs.index.month == month
            m_obs = obs.loc[m_mask, var].dropna()
            m_era5 = era5.loc[m_mask, var].dropna()

            common_m = m_obs.index.intersection(m_era5.index)
            m_obs = m_obs.loc[common_m]
            m_era5 = m_era5.loc[common_m]

            if len(m_obs) >= MIN_DAYS:
                delta = float(m_obs.mean() - m_era5.mean())
                delta = max(-10.0, min(delta, 10.0))
                monthly[str(month)] = round(delta, 4)

        if monthly:
            result[var] = monthly

    return result if result else None


def idw_interpolate(station_ratios, stations, distances_km, power=2):
    """IDW interpolation of correction factors from nearby stations."""
    all_vars = set()
    for station_id in stations:
        if station_id in station_ratios and station_ratios[station_id]:
            all_vars.update(station_ratios[station_id].keys())

    result = {}
    for var in all_vars:
        default = 0.0 if var in DELTA_VARS else 1.0
        monthly = {}
        for month in range(1, 13):
            month_key = str(month)
            values, weights = [], []

            for station_id, dist in zip(stations, distances_km):
                if station_id not in station_ratios or station_ratios[station_id] is None:
                    continue
                if var not in station_ratios[station_id]:
                    continue
                if month_key not in station_ratios[station_id][var]:
                    continue

                values.append(station_ratios[station_id][var][month_key])
                weights.append(1.0 / max(dist, 0.1) ** power)

            if values:
                weighted = sum(v * w for v, w in zip(values, weights)) / sum(weights)
                monthly[month_key] = round(weighted, 4)
            else:
                monthly[month_key] = default

        result[var] = monthly

    return result


def main():
    with open(SELECTED) as f:
        selected = json.load(f)

    # Collect all unique stations
    all_stations = set()
    for site_data in selected.values():
        all_stations.update(site_data["stations"])

    # Compute ratios per station (reads QAQC-cleaned CSVs)
    print("Computing monthly ratios at stations...")
    n_ok, n_skip = 0, 0
    station_ratios = {}
    for station_id in sorted(all_stations):
        ratios = compute_station_ratios(station_id)
        station_ratios[station_id] = ratios

        if ratios and "eto" in ratios:
            eto_vals = list(ratios["eto"].values())
            avg = np.mean(eto_vals)
            n_ok += 1
            print(f"  {station_id}: ok (ETo ratio avg={avg:.3f})")
        else:
            n_skip += 1
            print(f"  {station_id}: skip (no QAQC CSV or insufficient data)")

    print(f"\nStation summary: {n_ok} ok, {n_skip} skip")

    # IDW to flux sites
    print("\nInterpolating to flux sites...")
    no_correction = {
        "eto": {str(m): 1.0 for m in range(1, 13)},
        "rsds": {str(m): 1.0 for m in range(1, 13)},
        "u2": {str(m): 1.0 for m in range(1, 13)},
        "vpd": {str(m): 1.0 for m in range(1, 13)},
        "tmean": {str(m): 0.0 for m in range(1, 13)},
    }

    corrections = {}
    for sid, site_data in selected.items():
        stations = site_data["stations"]
        distances = site_data["distances_km"]

        if not stations:
            corrections[sid] = no_correction
        else:
            corr = idw_interpolate(station_ratios, stations, distances)
            # Fill any missing variables with defaults
            for var in ["eto", "rsds", "u2", "vpd"]:
                if var not in corr:
                    corr[var] = {str(m): 1.0 for m in range(1, 13)}
            if "tmean" not in corr:
                corr["tmean"] = {str(m): 0.0 for m in range(1, 13)}
            corrections[sid] = corr

        eto_vals = list(corrections[sid]["eto"].values())
        print(f"  {sid}: ETo correction avg={np.mean(eto_vals):.3f}")

    print(f"\nWriting {OUT_FILE}")
    with open(OUT_FILE, "w") as f:
        json.dump(corrections, f, indent=2)


if __name__ == "__main__":
    main()
