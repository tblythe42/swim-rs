"""
Compare seasonal ETf structure for cropland sites:
  - Flux-tower-implied ETf (ET_corr / ERA5 ETo)
  - PT-JPL ETf (Landsat)
  - ECOSTRESS ETf

Replicates the seasonal table in CROPLAND_DIAGNOSTIC.md and adds ECOSTRESS column.
Cropland = MODIS LC 12 or 14.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA = Path("/data/ssd1/swim/6_Flux_International/data")
LULC_CSV = DATA / "properties/6_Flux_International_landcover.csv"
ERA5_DIR = DATA / "meteorology/era5_land"
ECO_ETF_DIR = DATA / "remote_sensing/ecostress/extracts/etf/no_mask"
LS_ETF_DIR = DATA / "remote_sensing/landsat/extracts/ptjpl_etf/no_mask"
FLUX_NETWORKS = Path("/nas/climate/flux_stations/qaqc")

MIN_ETF = 0.05
MAX_ETF = 2.0
MIN_ETO = 0.5  # mm/day — avoid dividing by near-zero ETo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_cropland_sites(min_eto=MIN_ETO):
    from swimrs.container.schema import is_cropland

    df = pd.read_csv(LULC_CSV)
    # Per-site fallback: prefer GLC10, fall back to MODIS for each row
    glc = df["glc10_lc"].fillna(-1).astype(int)
    modis = df["modis_lc"].fillna(-1).astype(int)
    mask = glc.apply(lambda c: is_cropland(c, "glc10")) | (
        (glc <= 0) & modis.apply(lambda c: is_cropland(c, "modis"))
    )
    return sorted(df.loc[mask, "sid"].astype(str).tolist())


def find_flux_file(sid: str):
    for net_dir in FLUX_NETWORKS.iterdir():
        p = net_dir / f"{sid}_daily_data.csv"
        if p.exists():
            return p
    return None


def load_flux_et(sid: str) -> pd.Series | None:
    """Load ET_corr (mm/day) from flux file."""
    fp = find_flux_file(sid)
    if fp is None:
        return None
    df = pd.read_csv(fp, parse_dates=["date"])
    if "ET_corr" not in df.columns:
        if "ET" not in df.columns:
            return None
        col = "ET"
    else:
        col = "ET_corr"
    df = df.set_index("date")[col].dropna()
    df = df[df > 0]
    return df if not df.empty else None


def load_era5_eto(sites: list[str]) -> pd.DataFrame:
    """Load ERA5-Land daily ETo for given sites."""
    csv_files = sorted(ERA5_DIR.glob("era5_vars_*.csv"))
    site_set = set(sites)
    all_series: dict[str, dict] = {s: {} for s in sites}

    for csv_file in csv_files:
        df = pd.read_csv(csv_file)
        uid_col = next((c for c in df.columns if c.lower() in ("sid", "fid")), None)
        if uid_col is None:
            continue
        df[uid_col] = df[uid_col].astype(str)
        df = df[df[uid_col].isin(site_set)]
        if df.empty:
            continue
        eto_cols = [c for c in df.columns if c.startswith("eto_")]
        for _, row in df.iterrows():
            site = str(row[uid_col])
            for col in eto_cols:
                date_str = col.split("_", 1)[1]
                if len(date_str) == 8 and date_str.isdigit():
                    val = row[col]
                    if pd.notna(val):
                        all_series[site][date_str] = float(val)

    result = {}
    for site in sites:
        if all_series[site]:
            dates = pd.to_datetime(list(all_series[site].keys()))
            vals = list(all_series[site].values())
            result[site] = pd.Series(vals, index=dates, name=site).sort_index()
    return pd.DataFrame(result)


def load_ecostress_etf(sites: set) -> dict[str, pd.Series]:
    site_data: dict[str, list] = {}
    for csv in sorted(ECO_ETF_DIR.glob("etf_*_no_mask_*.csv")):
        m = re.match(r"etf_(.+)_no_mask_\d{4}\.csv", csv.name)
        if not m or m.group(1) not in sites:
            continue
        site = m.group(1)
        df = pd.read_csv(csv)
        uid_col = next((c for c in df.columns if c.lower() in ("sid", "fid")), None)
        if uid_col is None:
            continue
        for _, row in df.iterrows():
            for col in [c for c in df.columns if c.startswith("ETF_")]:
                val = row[col]
                if pd.notna(val):
                    val = float(val)
                    if MIN_ETF <= val <= MAX_ETF:
                        site_data.setdefault(site, []).append(
                            (pd.to_datetime(col[4:], format="%Y%m%d"), val)
                        )
    result = {}
    for site, pairs in site_data.items():
        dates, vals = zip(*pairs)
        result[site] = pd.Series(vals, index=pd.DatetimeIndex(dates), name=site).sort_index()
    return result


def load_landsat_etf(sites: set) -> dict[str, pd.Series]:
    site_data: dict[str, list] = {}
    for csv in sorted(LS_ETF_DIR.glob("ptjpl_etf_*_no_mask_*.csv")):
        m = re.match(r"ptjpl_etf_(.+)_no_mask_\d{4}_b\d+\.csv", csv.name)
        if not m or m.group(1) not in sites:
            continue
        site = m.group(1)
        df = pd.read_csv(csv)
        uid_col = next((c for c in df.columns if c.lower() in ("sid", "fid")), None)
        if uid_col is None:
            continue
        scene_cols = [
            c for c in df.columns if c != uid_col and re.match(r"[A-Z]{2}\d+_.+_\d{8}", c)
        ]
        for _, row in df.iterrows():
            for col in scene_cols:
                val = row[col]
                if pd.notna(val):
                    val = float(val)
                    if MIN_ETF <= val <= MAX_ETF:
                        site_data.setdefault(site, []).append(
                            (pd.to_datetime(col[-8:], format="%Y%m%d"), val)
                        )
    result = {}
    for site, pairs in site_data.items():
        dates, vals = zip(*pairs)
        result[site] = pd.Series(vals, index=pd.DatetimeIndex(dates), name=site).sort_index()
    return result


def season(month: int) -> str:
    return {
        12: "DJF",
        1: "DJF",
        2: "DJF",
        3: "MAM",
        4: "MAM",
        5: "MAM",
        6: "JJA",
        7: "JJA",
        8: "JJA",
        9: "SON",
        10: "SON",
        11: "SON",
    }[month]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    cropland = get_cropland_sites()
    print(f"Cropland sites (MODIS 12/14): {len(cropland)}", flush=True)

    # ERA5 ETo
    print("Loading ERA5 ETo...", flush=True)
    eto_df = load_era5_eto(cropland)
    print(f"  {len(eto_df.columns)} sites with ETo", flush=True)

    # ECOSTRESS ETf
    print("Loading ECOSTRESS ETf...", flush=True)
    eco = load_ecostress_etf(set(cropland))
    print(f"  {len(eco)} sites", flush=True)

    # Landsat PT-JPL ETf
    print("Loading Landsat PT-JPL ETf...", flush=True)
    ls = load_landsat_etf(set(cropland))
    print(f"  {len(ls)} sites", flush=True)

    # Collect seasonal records
    seasons = ["DJF", "MAM", "JJA", "SON"]
    records = {s: {"flux": [], "ptjpl": [], "eco": []} for s in seasons}
    sites_used = []

    for sid in cropland:
        flux_et = load_flux_et(sid)
        if flux_et is None or sid not in eto_df.columns:
            continue

        eto = eto_df[sid].dropna()
        eto = eto[eto >= MIN_ETO]

        # Flux-implied ETf: daily ET_corr / ETo on same dates
        common_flux = flux_et.index.intersection(eto.index)
        if len(common_flux) < 30:
            continue
        flux_etf = (flux_et.loc[common_flux] / eto.loc[common_flux]).clip(0, MAX_ETF)
        flux_etf = flux_etf[flux_etf >= MIN_ETF]

        has_eco = sid in eco and len(eco[sid]) >= 5
        has_ls = sid in ls and len(ls[sid]) >= 5

        if not (has_eco or has_ls):
            continue

        sites_used.append(sid)

        # Bin flux ETf by season
        for dt, val in flux_etf.items():
            records[season(dt.month)]["flux"].append(val)

        # Bin PT-JPL ETf by season
        if has_ls:
            for dt, val in ls[sid].items():
                records[season(dt.month)]["ptjpl"].append(val)

        # Bin ECOSTRESS ETf by season
        if has_eco:
            for dt, val in eco[sid].items():
                records[season(dt.month)]["eco"].append(val)

    print(f"\nSites contributing: {len(sites_used)}", flush=True)

    # Seasonal table
    print(
        f"\n{'Season':<6} {'N(flux)':>8} {'Flux ETf':>10} {'PT-JPL ETf':>12} "
        f"{'ECOSTRESS ETf':>14} {'Ratio ECO/Flux':>15} {'Ratio LS/Flux':>14}"
    )
    print("-" * 82)
    for s in seasons:
        f_vals = np.array(records[s]["flux"])
        l_vals = np.array(records[s]["ptjpl"])
        e_vals = np.array(records[s]["eco"])
        f_mean = f_vals.mean() if len(f_vals) else np.nan
        l_mean = l_vals.mean() if len(l_vals) else np.nan
        e_mean = e_vals.mean() if len(e_vals) else np.nan
        eco_ratio = e_mean / f_mean if f_mean > 0 else np.nan
        ls_ratio = l_mean / f_mean if f_mean > 0 else np.nan
        print(
            f"{s:<6} {len(f_vals):>8,} {f_mean:>10.3f} {l_mean:>12.3f} "
            f"{e_mean:>14.3f} {eco_ratio:>15.3f} {ls_ratio:>14.3f}"
        )

    # Overall summary
    all_flux = np.concatenate([records[s]["flux"] for s in seasons])
    all_ls = np.concatenate([records[s]["ptjpl"] for s in seasons])
    all_eco = np.concatenate([records[s]["eco"] for s in seasons])
    print("-" * 82)
    print(
        f"{'ALL':<6} {len(all_flux):>8,} {all_flux.mean():>10.3f} {all_ls.mean():>12.3f} "
        f"{all_eco.mean():>14.3f} {all_eco.mean() / all_flux.mean():>15.3f} "
        f"{all_ls.mean() / all_flux.mean():>14.3f}"
    )

    # Seasonal amplitude (ratio of JJA to DJF mean)
    print("\n--- Seasonal amplitude (JJA mean / DJF mean) ---")
    for label, key in [("Flux (truth)", "flux"), ("PT-JPL", "ptjpl"), ("ECOSTRESS", "eco")]:
        jja = np.array(records["JJA"][key]).mean()
        djf = np.array(records["DJF"][key]).mean()
        print(f"  {label:<16}: {jja:.3f} / {djf:.3f} = {jja / djf:.2f}x")

    # Per-site summary for sites with all three
    print("\n--- Per-site summary (sites with flux + ECOSTRESS + Landsat) ---")
    print(
        f"{'Site':<12} {'N_eco':>6} {'N_ls':>6} {'Flux_mean':>10} {'LS_mean':>8} {'ECO_mean':>9} {'LS_bias':>8} {'ECO_bias':>9}"
    )
    for sid in sorted(sites_used):
        flux_et = load_flux_et(sid)
        if flux_et is None or sid not in eto_df.columns:
            continue
        eto = eto_df[sid].dropna()
        eto = eto[eto >= MIN_ETO]
        common = flux_et.index.intersection(eto.index)
        if len(common) < 30:
            continue
        flux_etf_s = (flux_et.loc[common] / eto.loc[common]).clip(0, MAX_ETF)
        flux_etf_s = flux_etf_s[flux_etf_s >= MIN_ETF]
        f_mean = flux_etf_s.mean()
        n_eco = len(eco[sid]) if sid in eco else 0
        n_ls = len(ls[sid]) if sid in ls else 0
        ls_mean = ls[sid].mean() if sid in ls else np.nan
        eco_mean = eco[sid].mean() if sid in eco else np.nan
        print(
            f"{sid:<12} {n_eco:>6} {n_ls:>6} {f_mean:>10.3f} {ls_mean:>8.3f} {eco_mean:>9.3f} "
            f"{ls_mean - f_mean:>+8.3f} {eco_mean - f_mean:>+9.3f}"
        )


if __name__ == "__main__":
    main()
