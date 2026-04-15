"""Forward run using LULC-based global parameter defaults (no calibration).

Runs the full 241-site container with per-site parameters derived from
LULC-specific medians of the Example 4 calibration, then evaluates
against flux tower ET data.

Uses run_daily_loop_fast for speed (no persistence needed).

Usage:
    uv run python forward_lulc_defaults.py
    uv run python forward_lulc_defaults.py --sites US-ARM,US-Var
"""

import argparse
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
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
    "IT-Noe",  # zero ERA5 met
    "CA-DSM",
    "US-RRC",  # NaN AWC (soil properties)
    "FI-Var",  # 20% NaN ETo — propagates NaN through daily loop
}


def _glc10_lulc_map(gdf):
    """Build sid -> LULC code map, preferring GLC10 with MODIS fallback.

    GLC10 codes are mapped to MODIS equivalents for display consistency
    with existing LULC_NAMES dicts.
    """
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
    conf = project_dir / "6_Flux_International_lulc_defaults.toml"
    cfg = ProjectConfig()
    cfg.read_config(str(conf))
    return cfg


def _load_flux_et(sid):
    """Load QAQC flux ET for a site. Returns daily DataFrame with 'date' and 'ET_flux'."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", type=str, default=None)
    args = parser.parse_args()

    cfg = _load_config()
    params_json = Path("/data/ssd1/swim/6_Flux_International/lulc_global_params.json")

    if not params_json.exists():
        raise FileNotFoundError(f"LULC params not found: {params_json}")

    container_path = cfg.container_path
    print(f"Container: {container_path}")
    print(f"Params: {params_json}")

    container = SwimContainer.open(str(container_path), mode="r")
    all_uids = container.field_uids
    run_uids = [u for u in all_uids if u not in SKIP_FIDS]

    if args.sites:
        select = set(s.strip() for s in args.sites.split(","))
        run_uids = [u for u in run_uids if u in select]

    print(f"Running {len(run_uids)} sites (skipping {len(all_uids) - len(run_uids)})")

    # Build SwimInput and run with fast engine
    fd, h5_path = tempfile.mkstemp(suffix=".h5", prefix="swim_lulc_fwd_")
    os.close(fd)
    Path(h5_path).unlink(missing_ok=True)

    try:
        print("Building SwimInput...")
        swim_input = build_swim_input(
            container,
            output_h5=h5_path,
            calibrated_params_path=str(params_json),
            refet_type=cfg.refet_type or "eto",
            etf_model=cfg.etf_target_model or "ptjpl",
            met_source=cfg.met_source or "era5",
            mask_mode=cfg.mask_mode or "none",
            fields=run_uids,
        )

        print(
            f"Running fast daily loop ({swim_input.n_fields} fields, {swim_input.n_days} days)..."
        )
        output, _state = run_daily_loop_fast(swim_input)
        print("Run complete.")

        # Extract eta array: shape (n_days, n_fields)
        eta = output.eta
        time_index = pd.date_range(swim_input.start_date, periods=swim_input.n_days, freq="D")

    finally:
        Path(h5_path).unlink(missing_ok=True)

    container.close()

    # --- Evaluate against flux tower ET ---
    print("\n=== Evaluating against flux tower ET ===")

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

        bias = (merged["ET_sim"] - merged["ET_flux"]).mean()
        rmse = root_mean_squared_error(merged["ET_flux"], merged["ET_sim"])
        r2 = r2_score(merged["ET_flux"], merged["ET_sim"])
        lc = int(lulc_map.get(uid, 0))

        records.append(
            {
                "sid": uid,
                "lulc": lc,
                "lulc_name": LULC_NAMES.get(lc, f"LC{lc}"),
                "n_days": len(merged),
                "bias_mm": round(bias, 3),
                "rmse_mm": round(rmse, 3),
                "r2": round(r2, 3),
            }
        )

    if not records:
        print("No sites with sufficient overlapping data.")
        return

    eval_df = pd.DataFrame(records)
    out_csv = Path(__file__).resolve().parent / "lulc_defaults_evaluation.csv"
    eval_df.to_csv(out_csv, index=False)
    print(f"\nSaved: {out_csv}")

    # Summary by LULC
    print(f"\n{'LULC':<12} {'N':>4} {'Bias':>8} {'RMSE':>8} {'R2':>8}")
    print("-" * 44)
    for lc_name, grp in eval_df.groupby("lulc_name"):
        print(
            f"{lc_name:<12} {len(grp):4d} {grp['bias_mm'].mean():8.2f} "
            f"{grp['rmse_mm'].mean():8.2f} {grp['r2'].mean():8.3f}"
        )
    print("-" * 44)
    print(
        f"{'ALL':<12} {len(eval_df):4d} {eval_df['bias_mm'].mean():8.2f} "
        f"{eval_df['rmse_mm'].mean():8.2f} {eval_df['r2'].mean():8.3f}"
    )


if __name__ == "__main__":
    main()
