"""
Evaluate SWIM model against flux tower observations for international sites.

This module runs the model for international flux sites and compares against
flux tower observations.

Key differences from CONUS examples:
    - Uses ERA5-Land meteorology (not GridMET)
    - Uses HWSD soils (not SSURGO)
    - No irrigation masking (mask_mode="none")
    - ETf from PT-JPL only

Usage:
    python evaluate.py [--output-dir PATH] [--sites SITE1,SITE2,...] [--gap-tolerance N]
"""

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error, r2_score

from swimrs.container import SwimContainer
from swimrs.process.input import build_swim_input
from swimrs.process.loop import run_daily_loop
from swimrs.swim.config import ProjectConfig

# QAQC flux data is organized by network
QAQC_ROOT = "/nas/climate/flux_stations/qaqc"
QAQC_NETWORKS = ["ameriflux", "fluxnet", "icos", "ozflux"]


def output_to_dataframe(output, swim_input, field_idx: int) -> pd.DataFrame:
    """Convert DailyOutput arrays to DataFrame for a single field."""
    dates = pd.date_range(swim_input.start_date, periods=output.n_days, freq="D")

    df = pd.DataFrame(
        {
            "et_act": output.eta[:, field_idx],
            "kc_act": output.etf[:, field_idx],
            "kc_bas": output.kcb[:, field_idx],
            "ke": output.ke[:, field_idx],
            "ks": output.ks[:, field_idx],
            "kr": output.kr[:, field_idx],
            "runoff": output.runoff[:, field_idx],
            "rain": output.rain[:, field_idx],
            "melt": output.melt[:, field_idx],
            "swe": output.swe[:, field_idx],
            "depl_root": output.depl_root[:, field_idx],
            "dperc": output.dperc[:, field_idx],
            "irrigation": output.irr_sim[:, field_idx],
            "soil_water": output.gw_sim[:, field_idx],
        },
        index=dates,
    )

    return df


def input_to_dataframe(swim_input, field_idx: int) -> pd.DataFrame:
    """Extract input time series for a field."""
    dates = pd.date_range(swim_input.start_date, periods=swim_input.n_days, freq="D")

    # ERA5 uses 'eto' as the reference ET variable
    try:
        etr = swim_input.get_time_series("eto")
    except (KeyError, ValueError):
        etr = swim_input.get_time_series("etr")

    prcp = swim_input.get_time_series("prcp")
    tmin = swim_input.get_time_series("tmin")
    tmax = swim_input.get_time_series("tmax")

    df = pd.DataFrame(
        {
            "etref": etr[:, field_idx],
            "ppt": prcp[:, field_idx],
            "tmin": tmin[:, field_idx],
            "tmax": tmax[:, field_idx],
        },
        index=dates,
    )

    # Add ETf observations if available (no mask for international)
    try:
        etf = swim_input.get_time_series("etf_no_mask")
        df["etf"] = etf[:, field_idx]
    except (KeyError, ValueError):
        pass

    return df


def run_flux_site(fid: str, cfg: ProjectConfig, container: SwimContainer, outfile: str) -> None:
    """Run SWIM model for a single flux site and save output."""
    start_time = time.time()

    # Build swim_input.h5 for this site (use temp location)
    h5_path = outfile.replace(".csv", ".h5")

    swim_input = build_swim_input(
        container,
        output_h5=h5_path,
        spinup_json_path=None,
        etf_model=cfg.etf_target_model,  # "ptjpl" for international
        met_source="era5",  # ERA5-Land for international
        fields=[fid],
    )

    # Run simulation
    output, final_state = run_daily_loop(swim_input)

    print(f"\nExecution time: {time.time() - start_time:.2f} seconds\n")

    # Convert to DataFrame
    field_idx = swim_input.fids.index(fid)
    out_df = output_to_dataframe(output, swim_input, field_idx)
    in_df = input_to_dataframe(swim_input, field_idx)
    df = pd.concat([out_df, in_df], axis=1)

    # Filter to config date range
    df = df.loc[cfg.start_dt : cfg.end_dt]
    df.to_csv(outfile)


def find_flux_file(site_id: str, flux_dir: str = None) -> str | None:
    """Find QAQC flux data file for a site, searching across networks.

    Looks first in a local flux_dir (if provided), then across the
    QAQC network directories on /nas/.

    Returns path to daily_data CSV or None.
    """
    fname = f"{site_id}_daily_data.csv"

    # Check local directory first
    if flux_dir:
        local = os.path.join(flux_dir, fname)
        if os.path.exists(local):
            return local

    # Search QAQC network directories
    for network in QAQC_NETWORKS:
        path = os.path.join(QAQC_ROOT, network, fname)
        if os.path.exists(path):
            return path

    return None


def compare_with_flux(fid: str, model_output: str, flux_file: str, return_comparison: bool = False):
    """Compare model output against flux tower observations.

    Args:
        fid: Site ID
        model_output: Path to model output CSV
        flux_file: Path to flux tower data CSV
        return_comparison: If True, return comparison dict

    Returns:
        Comparison dict if return_comparison=True, else None
    """
    if not os.path.exists(flux_file):
        print(f"  Flux file not found: {flux_file}")
        return None

    try:
        # Load model output
        model_df = pd.read_csv(model_output, index_col=0, parse_dates=True)

        # Load flux data
        flux_df = pd.read_csv(flux_file, index_col="date", parse_dates=True)

        # Find common dates
        common_idx = model_df.index.intersection(flux_df.index)
        if len(common_idx) < 10:
            print(f"  Insufficient overlapping data ({len(common_idx)} days)")
            return None

        # Get ET values: prefer energy-balance-corrected ET
        model_et = model_df.loc[common_idx, "et_act"]

        if "ET_corr" in flux_df.columns:
            flux_et = flux_df.loc[common_idx, "ET_corr"]
        elif "ET" in flux_df.columns:
            flux_et = flux_df.loc[common_idx, "ET"]
        elif "LE_corr" in flux_df.columns:
            # Convert latent heat flux to ET (mm/day)
            # LE (W/m2) * 86400 / 2.45e6 = ET (mm/day)
            flux_et = flux_df.loc[common_idx, "LE_corr"] * 86400 / 2.45e6
        else:
            print("  No ET/ET_corr/LE_corr column in flux file")
            return None

        # Drop NaN values
        valid_mask = ~(model_et.isna() | flux_et.isna())
        model_et = model_et[valid_mask]
        flux_et = flux_et[valid_mask]

        if len(model_et) < 10:
            print(f"  Insufficient valid data ({len(model_et)} days)")
            return None

        # Calculate metrics
        rmse = np.sqrt(mean_squared_error(flux_et, model_et))
        r2 = r2_score(flux_et, model_et)
        bias = (model_et - flux_et).mean()
        kge = _kling_gupta(model_et.values, flux_et.values)

        comparison = {
            "n_samples": len(model_et),
            "rmse": rmse,
            "r2": r2,
            "bias": bias,
            "kge": kge,
            "mean_flux": flux_et.mean(),
            "mean_model": model_et.mean(),
        }

        print(
            f"  n={comparison['n_samples']}, RMSE={rmse:.2f}, R2={r2:.3f}, Bias={bias:.2f}, KGE={kge:.3f}"
        )

        if return_comparison:
            return comparison
        return None

    except Exception as exc:
        print(f"  Error comparing {fid}: {exc}")
        return None


def _kling_gupta(sim: np.ndarray, obs: np.ndarray) -> float:
    """Compute Kling-Gupta Efficiency (KGE)."""
    r = np.corrcoef(sim, obs)[0, 1]
    alpha = np.std(sim) / np.std(obs)
    beta = np.mean(sim) / np.mean(obs)
    return 1.0 - np.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate SWIM model against flux tower observations for international sites"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: {project_ws}/results)",
    )
    parser.add_argument(
        "--sites",
        type=str,
        default=None,
        help="Comma-separated site IDs to evaluate (default: all)",
    )
    parser.add_argument(
        "--gap-tolerance",
        type=int,
        default=5,
        help="Gap tolerance for evaluation (default: 5)",
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    conf = project_dir / "6_Flux_International.toml"

    cfg = ProjectConfig()
    cfg.read_config(str(conf))

    # Filter sites if specified via CLI, otherwise use container
    if args.sites:
        sites = [s.strip() for s in args.sites.split(",")]
    else:
        sites = None

    # Local flux directory (if data has been copied there)
    flux_dir = os.path.join(cfg.data_dir, "daily_flux_files")

    # Use output-dir if specified, otherwise default to project_ws/results
    if args.output_dir:
        run_dir = args.output_dir
    else:
        run_dir = os.path.join(cfg.project_ws, "results")
    os.makedirs(run_dir, exist_ok=True)

    # Open container
    container_path = cfg.container_path
    if not os.path.exists(container_path):
        raise FileNotFoundError(
            f"Container not found at {container_path}. "
            "Run container_prep.py first to create the container."
        )

    container = SwimContainer.open(container_path, mode="r")

    if sites is None:
        sites = container.field_uids

    complete, incomplete = [], []
    results = []

    try:
        for i, site_id in enumerate(sites):
            print(f"\n{i} {site_id}")

            flux_file = find_flux_file(site_id, flux_dir=flux_dir)
            out_csv = os.path.join(run_dir, f"{site_id}.csv")

            try:
                run_flux_site(site_id, cfg, container, out_csv)
            except Exception as exc:
                print(f"{site_id} error: {exc}")
                incomplete.append(site_id)
                continue

            if flux_file:
                result = compare_with_flux(site_id, out_csv, flux_file, return_comparison=True)
                if result:
                    results.append((site_id, result))
            else:
                print(f"  No flux data found for {site_id}")
            complete.append(site_id)

        print(f"\n{'=' * 60}")
        print(f"Complete: {len(complete)}")
        print(f"Incomplete: {len(incomplete)}")

        if results:
            print("\nSummary Statistics:")
            rmses = [r[1]["rmse"] for r in results]
            r2s = [r[1]["r2"] for r in results]
            kges = [r[1]["kge"] for r in results]
            print(f"  Mean RMSE: {np.mean(rmses):.2f} mm/day")
            print(f"  Mean R2: {np.mean(r2s):.3f}")
            print(f"  Mean KGE: {np.mean(kges):.3f}")

            # Save results summary
            results_csv = os.path.join(run_dir, "evaluation_summary.csv")
            rows = [{"site": s, **m} for s, m in results]
            pd.DataFrame(rows).to_csv(results_csv, index=False)
            print(f"  Saved to: {results_csv}")

    finally:
        container.close()
