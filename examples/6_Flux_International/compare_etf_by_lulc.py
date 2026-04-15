"""
ECOSTRESS ETf bias by MODIS LULC class vs flux-tower-implied ETf and Landsat PT-JPL ETf.

For each LULC class with ≥3 sites:
  - Flux-implied ETf = ET_corr / ERA5 ETo
  - Landsat PT-JPL ETf (filtered to [0.05, 2.0])
  - ECOSTRESS ETf (filtered to [0.05, 2.0])
  - Bias = mean(instrument) - mean(flux)
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("/data/ssd1/swim/6_Flux_International/data")
LULC_CSV = DATA / "properties/6_Flux_International_landcover.csv"
ERA5_DIR = DATA / "meteorology/era5_land"
ECO_ETF_DIR = DATA / "remote_sensing/ecostress/extracts/etf/no_mask"
LS_ETF_DIR = DATA / "remote_sensing/landsat/extracts/ptjpl_etf/no_mask"
FLUX_NETWORKS = Path("/nas/climate/flux_stations/qaqc")

MIN_ETF = 0.05
MAX_ETF = 2.0
MIN_ETO = 0.5

MODIS_NAMES = {
    1: "Evg Needleleaf Forest",
    2: "Evg Broadleaf Forest",
    3: "Dec Needleleaf Forest",
    4: "Dec Broadleaf Forest",
    5: "Mixed Forest",
    6: "Closed Shrublands",
    7: "Open Shrublands",
    8: "Woody Savannas",
    9: "Savannas",
    10: "Grasslands",
    11: "Wetlands",
    12: "Croplands",
    13: "Urban",
    14: "Cropland/NV Mosaic",
    17: "Water",
}


def load_lulc():
    from swimrs.container.schema import GLC10_TO_MODIS_ROOTING

    df = pd.read_csv(LULC_CSV)
    result = {}
    for _, row in df.iterrows():
        sid = str(row["sid"])
        glc = row.get("glc10_lc")
        if pd.notna(glc) and int(glc) > 0:
            result[sid] = GLC10_TO_MODIS_ROOTING.get(int(glc), int(glc))
        else:
            modis = row.get("modis_lc")
            result[sid] = int(modis) if pd.notna(modis) and not pd.isna(modis) else -1
    return result


def find_flux_file(sid):
    for net_dir in FLUX_NETWORKS.iterdir():
        p = net_dir / f"{sid}_daily_data.csv"
        if p.exists():
            return p
    return None


def load_flux_et(sid):
    fp = find_flux_file(sid)
    if fp is None:
        return None
    df = pd.read_csv(fp, parse_dates=["date"])
    col = "ET_corr" if "ET_corr" in df.columns else ("ET" if "ET" in df.columns else None)
    if col is None:
        return None
    s = df.set_index("date")[col].dropna()
    s = s[s > 0]
    return s if not s.empty else None


def load_era5_eto(sites):
    site_set = set(sites)
    all_series = {s: {} for s in sites}
    for csv_file in sorted(ERA5_DIR.glob("era5_vars_*.csv")):
        df = pd.read_csv(csv_file)
        uid_col = next((c for c in df.columns if c.lower() in ("sid", "fid")), None)
        if uid_col is None:
            continue
        df[uid_col] = df[uid_col].astype(str)
        df = df[df[uid_col].isin(site_set)]
        if df.empty:
            continue
        for _, row in df.iterrows():
            site = str(row[uid_col])
            for col in [c for c in df.columns if c.startswith("eto_")]:
                date_str = col[4:]
                if len(date_str) == 8 and date_str.isdigit() and pd.notna(row[col]):
                    all_series[site][date_str] = float(row[col])
    result = {}
    for site in sites:
        if all_series[site]:
            dates = pd.to_datetime(list(all_series[site].keys()))
            result[site] = pd.Series(list(all_series[site].values()), index=dates).sort_index()
    return result


def load_ecostress_etf(sites):
    site_set = set(sites)
    data = {}
    for csv in sorted(ECO_ETF_DIR.glob("etf_*_no_mask_*.csv")):
        m = re.match(r"etf_(.+)_no_mask_\d{4}\.csv", csv.name)
        if not m or m.group(1) not in site_set:
            continue
        site = m.group(1)
        df = pd.read_csv(csv)
        uid_col = next((c for c in df.columns if c.lower() in ("sid", "fid")), None)
        if uid_col is None:
            continue
        for _, row in df.iterrows():
            for col in [c for c in df.columns if c.startswith("ETF_")]:
                val = row[col]
                if pd.notna(val) and MIN_ETF <= float(val) <= MAX_ETF:
                    data.setdefault(site, []).append(
                        (pd.to_datetime(col[4:], format="%Y%m%d"), float(val))
                    )
    result = {}
    for s, pairs in data.items():
        if pairs:
            dates, vals = zip(*pairs)
            result[s] = pd.Series(list(vals), index=pd.DatetimeIndex(dates), name=s).sort_index()
    return result


def load_landsat_etf(sites):
    site_set = set(sites)
    data = {}
    for csv in sorted(LS_ETF_DIR.glob("ptjpl_etf_*_no_mask_*.csv")):
        m = re.match(r"ptjpl_etf_(.+)_no_mask_\d{4}_b\d+\.csv", csv.name)
        if not m or m.group(1) not in site_set:
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
                if pd.notna(val) and MIN_ETF <= float(val) <= MAX_ETF:
                    data.setdefault(site, []).append(
                        (pd.to_datetime(col[-8:], format="%Y%m%d"), float(val))
                    )
    result = {}
    for s, pairs in data.items():
        if pairs:
            dates, vals = zip(*pairs)
            result[s] = pd.Series(list(vals), index=pd.DatetimeIndex(dates), name=s).sort_index()
    return result


def main():
    lulc = load_lulc()
    all_sites = list(lulc.keys())
    print(f"Total sites: {len(all_sites)}", flush=True)

    print("Loading ERA5 ETo...", flush=True)
    eto = load_era5_eto(all_sites)
    print(f"  {len(eto)} sites with ETo", flush=True)

    print("Loading ECOSTRESS ETf...", flush=True)
    eco = load_ecostress_etf(all_sites)
    print(f"  {len(eco)} sites", flush=True)

    print("Loading Landsat PT-JPL ETf...", flush=True)
    ls = load_landsat_etf(all_sites)
    print(f"  {len(ls)} sites", flush=True)

    # Per-site flux ETf means
    site_results = {}
    for sid in all_sites:
        flux_et = load_flux_et(sid)
        if flux_et is None or sid not in eto:
            continue
        eto_s = eto[sid][eto[sid] >= MIN_ETO]
        common = flux_et.index.intersection(eto_s.index)
        if len(common) < 30:
            continue
        flux_etf = (flux_et.loc[common] / eto_s.loc[common]).clip(0, MAX_ETF)
        flux_etf = flux_etf[flux_etf >= MIN_ETF]
        if flux_etf.empty:
            continue

        site_results[sid] = {
            "lulc": lulc.get(sid, -1),
            "flux_etf": flux_etf.mean(),
            "n_flux": len(flux_etf),
            "ls_etf": ls[sid].mean() if sid in ls else np.nan,
            "n_ls": len(ls[sid]) if sid in ls else 0,
            "eco_etf": eco[sid].mean() if sid in eco else np.nan,
            "n_eco": len(eco[sid]) if sid in eco else 0,
        }

    df = pd.DataFrame(site_results).T
    df["lulc"] = df["lulc"].astype(int)
    df["flux_etf"] = df["flux_etf"].astype(float)
    df["ls_etf"] = df["ls_etf"].astype(float)
    df["eco_etf"] = df["eco_etf"].astype(float)
    df["ls_bias"] = df["ls_etf"] - df["flux_etf"]
    df["eco_bias"] = df["eco_etf"] - df["flux_etf"]

    print(f"\nSites with flux data: {len(df)}", flush=True)

    # Group by LULC
    print("\n" + "=" * 90)
    print(
        f"{'LULC':>4}  {'Class':<25} {'N':>4} {'Flux':>7} {'LS':>7} {'ECO':>7} "
        f"{'LS bias':>8} {'ECO bias':>9} {'ECO/Flux':>9}"
    )
    print("=" * 90)

    for lc in sorted(df["lulc"].unique()):
        sub = df[df["lulc"] == lc]
        n = len(sub)
        if n < 2:
            continue
        has_eco = sub["eco_etf"].notna() & (sub["n_eco"] >= 5)
        has_ls = sub["ls_etf"].notna() & (sub["n_ls"] >= 5)
        has_flux = sub["flux_etf"].notna()

        flux_mean = sub.loc[has_flux, "flux_etf"].mean()
        ls_mean = sub.loc[has_ls & has_flux, "ls_etf"].mean()
        eco_mean = sub.loc[has_eco & has_flux, "eco_etf"].mean()
        ls_bias = ls_mean - flux_mean if not np.isnan(ls_mean) else np.nan
        eco_bias = eco_mean - flux_mean if not np.isnan(eco_mean) else np.nan
        eco_ratio = eco_mean / flux_mean if not np.isnan(eco_mean) and flux_mean > 0 else np.nan
        name = MODIS_NAMES.get(lc, f"LC{lc}")

        print(
            f"{lc:>4}  {name:<25} {n:>4} {flux_mean:>7.3f} {ls_mean:>7.3f} {eco_mean:>7.3f} "
            f"{ls_bias:>+8.3f} {eco_bias:>+9.3f} {eco_ratio:>9.3f}"
        )

    # Overall
    has_eco_all = df["eco_etf"].notna() & (df["n_eco"] >= 5)
    has_ls_all = df["ls_etf"].notna() & (df["n_ls"] >= 5)
    flux_all = df["flux_etf"].mean()
    ls_all = df.loc[has_ls_all, "ls_etf"].mean()
    eco_all = df.loc[has_eco_all, "eco_etf"].mean()
    print("=" * 90)
    print(
        f"{'ALL':>4}  {'(all classes)':<25} {len(df):>4} {flux_all:>7.3f} {ls_all:>7.3f} "
        f"{eco_all:>7.3f} {ls_all - flux_all:>+8.3f} {eco_all - flux_all:>+9.3f} "
        f"{eco_all / flux_all:>9.3f}"
    )

    # Per-site detail sorted by ECO bias
    print("\n--- Per-site detail (sorted by ECO bias) ---")
    detail = df[has_eco_all & has_ls_all & df["flux_etf"].notna()].copy()
    detail = detail.sort_values("eco_bias")
    detail["lulc_name"] = detail["lulc"].map(MODIS_NAMES)
    print(
        f"{'Site':<12} {'LULC':<22} {'Flux':>7} {'LS':>7} {'ECO':>7} {'LS bias':>8} {'ECO bias':>9}"
    )
    for sid, row in detail.iterrows():
        print(
            f"{sid:<12} {row['lulc_name']:<22} {row['flux_etf']:>7.3f} {row['ls_etf']:>7.3f} "
            f"{row['eco_etf']:>7.3f} {row['ls_bias']:>+8.3f} {row['eco_bias']:>+9.3f}"
        )


if __name__ == "__main__":
    main()
