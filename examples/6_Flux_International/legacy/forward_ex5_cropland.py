"""Forward run on Ex6 cropland sites using Ex5 calibrated parameters.

Tests whether OpenET-ensemble-calibrated cropland parameters from CONUS (Ex5)
transfer to the international network under ERA5-Land / PT-JPL forcing.

Usage:
    uv run python forward_ex5_cropland.py
"""

import json
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import r2_score, root_mean_squared_error

from swimrs.container import SwimContainer
from swimrs.process.input import build_swim_input
from swimrs.process.loop_fast import run_daily_loop_fast
from swimrs.swim.config import ProjectConfig

HERE = Path(__file__).resolve().parent
EXAMPLE_DIR = HERE if (HERE / "6_Flux_International.toml").exists() else HERE.parent

QAQC_ROOT = "/nas/climate/flux_stations/qaqc"
QAQC_NETWORKS = ["ameriflux", "fluxnet", "icos", "ozflux"]

SKIP_FIDS = {
    "CA-RBM",
    "PR-xLA",
    "US-HB3",
    "US-TaS",
    "US-TLR",
    "IT-Noe",
    "CA-DSM",
    "US-RRC",
    "FI-Var",
}

# Ex5 cropland median parameters (9 sites, OpenET ensemble target)
EX5_CROPLAND_PARAMS = {
    "aw": 202,
    "ndvi_k": 8.88,
    "ndvi_0": 0.545,
    "mad": 0.115,
    "ks_alpha": 0.280,
    "kr_alpha": 0.334,
    "swe_alpha": 0.337,
    "swe_beta": 1.496,
}


def _load_config():
    conf = EXAMPLE_DIR / "6_Flux_International.toml"
    cfg = ProjectConfig()
    cfg.read_config(str(conf))
    return cfg


def _load_flux_et(sid):
    for network in QAQC_NETWORKS:
        path = os.path.join(QAQC_ROOT, network, f"{sid}_daily_data.csv")
        if os.path.exists(path):
            df = pd.read_csv(path, parse_dates=["date"])
            if "ET_corr" in df.columns:
                return (
                    df[["date", "ET_corr"]]
                    .rename(columns={"ET_corr": "ET_flux"})
                    .dropna(subset=["ET_flux"])
                )
            elif "ET" in df.columns:
                return (
                    df[["date", "ET"]].rename(columns={"ET": "ET_flux"}).dropna(subset=["ET_flux"])
                )
    return None


def calc_metrics(obs, mod):
    mask = np.isfinite(obs) & np.isfinite(mod)
    o, m = obs[mask], mod[mask]
    if len(o) < 10:
        return {k: np.nan for k in ["n", "r2", "rmse", "bias", "kge"]}
    r, _ = stats.pearsonr(o, m)
    r2 = r2_score(o, m)
    rmse = root_mean_squared_error(o, m)
    bias = float((m - o).mean())
    alpha = np.std(m) / np.std(o) if np.std(o) > 0 else np.nan
    beta = np.mean(m) / np.mean(o) if np.mean(o) > 0 else np.nan
    kge = 1.0 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)
    return {"n": len(o), "r2": r2, "rmse": rmse, "bias": bias, "kge": kge}


def main():
    cfg = _load_config()
    container = SwimContainer.open(str(cfg.container_path), mode="r")

    gdf = gpd.read_file(cfg.fields_shapefile, engine="fiona")

    # Select cropland sites: prefer GLC10 (10=crop), fall back to MODIS (12,14)
    from swimrs.container.schema import is_cropland

    def _is_crop(row):
        glc = row.get("glc10_lc")
        if pd.notna(glc) and int(glc) > 0:
            return is_cropland(int(glc), "glc10")
        modis = row.get("modis_lc")
        if pd.notna(modis) and int(modis) > 0:
            return is_cropland(int(modis), "modis")
        return False

    crop_uids = [
        uid
        for uid in container.field_uids
        if _is_crop(gdf.set_index("sid").loc[uid]) and uid not in SKIP_FIDS
        if uid in gdf["sid"].values
    ]
    print(f"Cropland sites: {len(crop_uids)}")

    # Build params JSON: every cropland site gets the Ex5 median
    params = {uid: dict(EX5_CROPLAND_PARAMS) for uid in crop_uids}

    fd, params_path = tempfile.mkstemp(suffix=".json", prefix="ex5_crop_params_")
    os.close(fd)
    with open(params_path, "w") as f:
        json.dump(params, f)

    fd, h5_path = tempfile.mkstemp(suffix=".h5", prefix="swim_ex5crop_")
    os.close(fd)
    Path(h5_path).unlink(missing_ok=True)

    try:
        print("Building SwimInput...")
        swim_input = build_swim_input(
            container,
            output_h5=h5_path,
            calibrated_params_path=params_path,
            refet_type=cfg.refet_type or "eto",
            etf_model=cfg.etf_target_model or "ptjpl",
            met_source=cfg.met_source or "era5",
            mask_mode=cfg.mask_mode or "none",
            fields=crop_uids,
        )
        print(
            f"Running fast daily loop ({swim_input.n_fields} fields, {swim_input.n_days} days)..."
        )
        output, _ = run_daily_loop_fast(swim_input)
        print("Run complete.")

        eta = output.eta
        time_index = pd.date_range(swim_input.start_date, periods=swim_input.n_days, freq="D")
    finally:
        Path(h5_path).unlink(missing_ok=True)
        Path(params_path).unlink(missing_ok=True)

    container.close()

    # Evaluate
    print("\n=== Ex5 Cropland Params on Ex6 Sites ===")

    # Load comparison results
    cal_csv = HERE / "calibrated_evaluation.csv"
    def_csv = HERE / "lulc_defaults_evaluation.csv"
    cal_eval = pd.read_csv(cal_csv) if cal_csv.exists() else pd.DataFrame()
    def_eval = pd.read_csv(def_csv) if def_csv.exists() else pd.DataFrame()

    records = []
    for j, uid in enumerate(crop_uids):
        flux_df = _load_flux_et(uid)
        if flux_df is None:
            continue

        sim = pd.DataFrame({"date": time_index, "ET_sim": eta[:, j]})
        merged = pd.merge(flux_df, sim, on="date", how="inner").dropna(subset=["ET_flux", "ET_sim"])
        if len(merged) < 30:
            continue

        m = calc_metrics(merged["ET_flux"].values, merged["ET_sim"].values)
        records.append({"sid": uid, **m})

    ex5_df = pd.DataFrame(records)
    out_csv = HERE / "ex5_cropland_evaluation.csv"
    ex5_df.to_csv(out_csv, index=False)
    print(f"Saved: {out_csv}")

    # Per-site results
    print(f"\n{'sid':<12} {'n':>6} {'bias':>7} {'RMSE':>7} {'R2':>7} {'KGE':>7}")
    print("-" * 50)
    for _, r in ex5_df.sort_values("kge", ascending=False).iterrows():
        print(f"{r.sid:<12} {r.n:6.0f} {r.bias:7.2f} {r.rmse:7.2f} {r.r2:7.3f} {r.kge:7.3f}")

    # Summary
    print(f"\n{'Model':<20} {'N':>4} {'Bias':>8} {'RMSE':>8} {'R2':>8} {'KGE':>8}")
    print("-" * 56)
    print(
        f"{'Ex5 Params':<20} {len(ex5_df):4d} {ex5_df['bias'].mean():8.2f} "
        f"{ex5_df['rmse'].mean():8.2f} {ex5_df['r2'].mean():8.3f} {ex5_df['kge'].mean():8.3f}"
    )

    # Compare with other configurations on common sites
    common_cal = set(ex5_df["sid"]) & set(cal_eval["sid"]) if len(cal_eval) else set()
    common_def = set(ex5_df["sid"]) & set(def_eval["sid"]) if len(def_eval) else set()
    common = common_cal & common_def

    if common:
        e5 = ex5_df[ex5_df["sid"].isin(common)]
        ca = cal_eval[cal_eval["sid"].isin(common)]
        de = def_eval[def_eval["sid"].isin(common)]

        print(f"\n=== Cropland Comparison ({len(common)} common sites) ===")
        print(f"{'Model':<20} {'Bias':>8} {'RMSE':>8} {'R2':>8} {'KGE':>8}")
        print("-" * 56)
        print(
            f"{'LULC Defaults':<20} {de['bias_mm'].mean():8.2f} {de['rmse_mm'].mean():8.2f} "
            f"{de['r2'].mean():8.3f} {'—':>8}"
        )
        print(
            f"{'Ex6 Calibrated':<20} {ca['bias_mm'].mean():8.2f} {ca['rmse_mm'].mean():8.2f} "
            f"{ca['r2'].mean():8.3f} {ca['kge'].mean():8.3f}"
        )
        print(
            f"{'Ex5 Params':<20} {e5['bias'].mean():8.2f} {e5['rmse'].mean():8.2f} "
            f"{e5['r2'].mean():8.3f} {e5['kge'].mean():8.3f}"
        )


if __name__ == "__main__":
    main()
