"""Evaluate calibrated SWIM against flux tower ET — reads params from container.

Uses run_daily_loop_fast with calibrated parameters stored in the container.
Compares against the LULC defaults baseline.

Usage:
    uv run python evaluate_calibrated.py
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


def _glc10_lulc_map(gdf):
    from swimrs.container.schema import GLC10_TO_MODIS_ROOTING

    result = {}
    for _, row in gdf.iterrows():
        sid = row["sid"]
        glc = row.get("glc10_lc")
        if pd.notna(glc) and int(glc) > 0:
            result[sid] = GLC10_TO_MODIS_ROOTING.get(int(glc), int(glc))
        else:
            modis = row.get("modis_lc")
            result[sid] = int(modis) if pd.notna(modis) else 0
    return result


def _load_config():
    project_dir = Path(__file__).resolve().parent
    conf = project_dir / "6_Flux_International.toml"
    cfg = ProjectConfig()
    cfg.read_config(str(conf))
    return cfg


def _load_flux_et(sid):
    for network in QAQC_NETWORKS:
        path = os.path.join(QAQC_ROOT, network, f"{sid}_daily_data.csv")
        if os.path.exists(path):
            df = pd.read_csv(path, parse_dates=["date"])
            if "ET_corr" in df.columns:
                df = df[["date", "ET_corr"]].rename(columns={"ET_corr": "ET_flux"})
            elif "ET" in df.columns:
                df = df[["date", "ET"]].rename(columns={"ET": "ET_flux"})
            else:
                continue
            df = df.dropna(subset=["ET_flux"])
            if len(df) > 0:
                return df
    return None


def _extract_calibrated_params(container, uids):
    """Extract calibrated params from container into a JSON-style dict."""
    root = container._root
    params_grp = root["calibration"]["parameters"]
    all_uids = container.field_uids

    # Map internal names to JSON names
    name_map = {"kr_damp": "kr_alpha", "ks_damp": "ks_alpha"}

    result = {}
    for uid in uids:
        idx = all_uids.index(uid)
        site_params = {}
        for key in params_grp.keys():
            val = float(params_grp[key][:][idx])
            if np.isnan(val):
                break
            json_name = name_map.get(key, key)
            site_params[json_name] = val
        else:
            result[uid] = site_params
    return result


def calc_metrics(obs, mod):
    mask = np.isfinite(obs) & np.isfinite(mod)
    obs, mod = obs[mask], mod[mask]
    if len(obs) < 10:
        return {"n": len(obs), "r2": np.nan, "rmse": np.nan, "bias": np.nan, "kge": np.nan}
    r, _ = stats.pearsonr(obs, mod)
    r2 = r2_score(obs, mod)
    rmse = root_mean_squared_error(obs, mod)
    bias = float((mod - obs).mean())
    alpha = np.std(mod) / np.std(obs) if np.std(obs) > 0 else np.nan
    beta = np.mean(mod) / np.mean(obs) if np.mean(obs) > 0 else np.nan
    kge = 1.0 - np.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2)
    return {"n": len(obs), "r2": r2, "rmse": rmse, "bias": bias, "kge": kge}


def main():
    cfg = _load_config()
    container = SwimContainer.open(str(cfg.container_path), mode="r")
    all_uids = container.field_uids

    # Get calibrated sites (non-NaN params)
    cal_params = _extract_calibrated_params(container, [u for u in all_uids if u not in SKIP_FIDS])
    run_uids = list(cal_params.keys())
    print(f"Calibrated sites: {len(run_uids)}")

    # Write params to temp JSON for build_swim_input
    fd, params_path = tempfile.mkstemp(suffix=".json", prefix="cal_params_")
    os.close(fd)
    with open(params_path, "w") as f:
        json.dump(cal_params, f)

    fd, h5_path = tempfile.mkstemp(suffix=".h5", prefix="swim_cal_eval_")
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
            fields=run_uids,
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
    print("\n=== Evaluating calibrated model against flux tower ET ===")

    gdf = gpd.read_file(cfg.fields_shapefile, engine="fiona")
    lulc_map = _glc10_lulc_map(gdf)
    LULC_NAMES = {
        1: "ENF",
        2: "EBF",
        4: "DBF",
        5: "MixForest",
        7: "OpenShrub",
        8: "WoodySav",
        9: "Savanna",
        10: "Grassland",
        12: "Cropland",
        13: "Urban",
        14: "CropNatMos",
        17: "LC17",
    }

    records = []
    for j, uid in enumerate(run_uids):
        flux_df = _load_flux_et(uid)
        if flux_df is None:
            continue

        sim_series = pd.DataFrame({"date": time_index, "ET_sim": eta[:, j]})
        merged = pd.merge(flux_df, sim_series, on="date", how="inner")
        merged = merged.dropna(subset=["ET_flux", "ET_sim"])

        if len(merged) < 30:
            continue

        m = calc_metrics(merged["ET_flux"].values, merged["ET_sim"].values)
        lc = int(lulc_map.get(uid, 0))

        records.append(
            {
                "sid": uid,
                "lulc": lc,
                "lulc_name": LULC_NAMES.get(lc, f"LC{lc}"),
                "n_days": m["n"],
                "bias_mm": round(m["bias"], 3),
                "rmse_mm": round(m["rmse"], 3),
                "r2": round(m["r2"], 3),
                "kge": round(m["kge"], 3),
            }
        )

    eval_df = pd.DataFrame(records)
    out_csv = Path(__file__).resolve().parent / "calibrated_evaluation.csv"
    eval_df.to_csv(out_csv, index=False)
    print(f"\nSaved: {out_csv}")

    # Summary by LULC
    print(f"\n{'LULC':<12} {'N':>4} {'Bias':>8} {'RMSE':>8} {'R2':>8} {'KGE':>8}")
    print("-" * 52)
    for lc_name, grp in eval_df.groupby("lulc_name"):
        print(
            f"{lc_name:<12} {len(grp):4d} {grp['bias_mm'].mean():8.2f} "
            f"{grp['rmse_mm'].mean():8.2f} {grp['r2'].mean():8.3f} {grp['kge'].mean():8.3f}"
        )
    print("-" * 52)
    print(
        f"{'ALL':<12} {len(eval_df):4d} {eval_df['bias_mm'].mean():8.2f} "
        f"{eval_df['rmse_mm'].mean():8.2f} {eval_df['r2'].mean():8.3f} {eval_df['kge'].mean():8.3f}"
    )

    # Compare with LULC defaults if available
    defaults_csv = Path(__file__).resolve().parent / "lulc_defaults_evaluation.csv"
    if defaults_csv.exists():
        print("\n=== Comparison: Calibrated vs LULC Defaults ===")
        defaults_df = pd.read_csv(defaults_csv)
        common_sids = set(eval_df["sid"]) & set(defaults_df["sid"])
        cal = eval_df[eval_df["sid"].isin(common_sids)].set_index("sid")
        uncal = defaults_df[defaults_df["sid"].isin(common_sids)].set_index("sid")
        print(f"Common sites: {len(common_sids)}")
        print(f"              {'Bias':>8} {'RMSE':>8} {'R2':>8}")
        print(
            f"  Defaults    {uncal['bias_mm'].mean():8.2f} {uncal['rmse_mm'].mean():8.2f} {uncal['r2'].mean():8.3f}"
        )
        print(
            f"  Calibrated  {cal['bias_mm'].mean():8.2f} {cal['rmse_mm'].mean():8.2f} {cal['r2'].mean():8.3f}"
        )


if __name__ == "__main__":
    main()
