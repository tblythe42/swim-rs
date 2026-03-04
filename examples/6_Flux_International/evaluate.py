"""Evaluate calibrated SWIM against flux tower ET for international sites.

Runs the calibrated model and compares SWIM ET against energy-balance-corrected
flux tower ET (ET_corr) from the multi-network QAQC archive.

Key differences from CONUS examples:
    - ERA5-Land meteorology (not GridMET)
    - HWSD soils (not SSURGO)
    - No irrigation masking (mask_mode="none")
    - No OpenET reference models (international sites lack coverage)
    - Multi-network flux data search (ameriflux, fluxnet, icos, ozflux)

Usage:
    python evaluate.py [--par-csv PATH] [--sites SITE1,SITE2,...] [--monthly]
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import mean_squared_error, r2_score

from swimrs.container import SwimContainer
from swimrs.process.input import build_swim_input
from swimrs.process.loop_fast import run_daily_loop_fast
from swimrs.swim.config import ProjectConfig

QAQC_ROOT = "/nas/climate/flux_stations/qaqc"
QAQC_NETWORKS = ["ameriflux", "fluxnet", "icos", "ozflux"]


def _load_config():
    project_dir = Path(__file__).resolve().parent
    conf = project_dir / "6_Flux_International.toml"
    cfg = ProjectConfig()
    if os.path.isdir("/data/ssd1/swim"):
        cfg.read_config(str(conf), calibrate=True)
    else:
        cfg.read_config(str(conf), project_root_override=str(project_dir.parent), calibrate=True)
    return cfg


def parse_pest_params(par_csv, fids):
    """Parse PEST++ .par.csv into {fid: {param: value}} using median realization."""
    df = pd.read_csv(par_csv, index_col=0)

    numeric_rows = df.loc[df.index != "base"]
    row = numeric_rows.median()

    params_by_fid = {}
    for col in df.columns:
        parts = col.split("_ptype:")[0]
        parts = parts.replace("pname:p_", "")
        parts = parts.rsplit("_:0", 1)[0]

        matched_fid = None
        for fid in fids:
            if parts.lower().endswith(f"_{fid.lower()}"):
                matched_fid = fid
                param_name = parts[: -(len(fid) + 1)]
                break

        if matched_fid:
            if matched_fid not in params_by_fid:
                params_by_fid[matched_fid] = {}
            params_by_fid[matched_fid][param_name] = float(row[col])

    return params_by_fid


def run_calibrated_model(cfg, container, fids, calibrated_params):
    """Run model with calibrated parameters. Returns {fid: DataFrame}."""
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
        temp_h5 = tmp.name
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
        json.dump(calibrated_params, tmp)
        params_json = tmp.name

    try:
        swim_input = build_swim_input(
            container,
            output_h5=temp_h5,
            calibrated_params_path=params_json,
            start_date=cfg.start_dt,
            end_date=cfg.end_dt,
            refet_type=getattr(cfg, "refet_type", "eto") or "eto",
            etf_model=getattr(cfg, "etf_target_model", "ptjpl"),
            met_source=getattr(cfg, "met_source", "era5"),
            fields=fids,
            empirical_kc_max=True,
            mask_mode=getattr(cfg, "mask_mode", "none"),
        )

        output, _ = run_daily_loop_fast(swim_input)
        dates = pd.date_range(swim_input.start_date, periods=swim_input.n_days, freq="D")
        eto = swim_input.get_time_series("eto")

        results = {}
        for i, fid in enumerate(swim_input.fids):
            results[fid] = pd.DataFrame(
                {
                    "et_act": output.eta[:, i],
                    "etf_model": output.etf[:, i],
                    "etref": eto[:, i],
                    "swe": output.swe[:, i],
                },
                index=dates,
            )

        swim_input.close()
    finally:
        for p in [temp_h5, params_json]:
            if os.path.exists(p):
                os.remove(p)

    return results


def find_flux_file(site_id):
    """Find QAQC flux data file, searching across networks."""
    fname = f"{site_id}_daily_data.csv"
    for network in QAQC_NETWORKS:
        path = os.path.join(QAQC_ROOT, network, fname)
        if os.path.exists(path):
            return path
    return None


def load_flux_et(fid):
    """Load energy-balance-corrected ET from flux tower data."""
    path = find_flux_file(fid)
    if path is None:
        return pd.Series(dtype=float)
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    if "ET_corr" in df.columns:
        series = df["ET_corr"]
    elif "ET" in df.columns:
        series = df["ET"]
    elif "LE_corr" in df.columns:
        series = df["LE_corr"] * 86400 / 2.45e6
    else:
        return pd.Series(dtype=float)
    series.index = series.index.normalize()
    return series


def calc_metrics(obs, mod):
    """Calculate R2, Pearson r, RMSE, bias, KGE between obs and mod arrays."""
    mask = np.isfinite(obs) & np.isfinite(mod)
    obs, mod = obs[mask], mod[mask]
    if len(obs) < 10:
        return {
            "n": len(obs),
            "r2": np.nan,
            "r": np.nan,
            "rmse": np.nan,
            "bias": np.nan,
            "kge": np.nan,
        }
    r, _ = stats.pearsonr(obs, mod)
    r2 = r2_score(obs, mod)
    rmse = np.sqrt(mean_squared_error(obs, mod))
    bias = float((mod - obs).mean())
    alpha = np.std(mod) / np.std(obs) if np.std(obs) > 0 else np.nan
    beta = np.mean(mod) / np.mean(obs) if np.mean(obs) > 0 else np.nan
    kge = 1.0 - np.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2)
    return {"n": len(obs), "r2": r2, "r": r, "rmse": rmse, "bias": bias, "kge": kge}


def find_par_csv(results_dir, project_name):
    """Find the latest .par.csv in results directory."""
    for i in range(10, -1, -1):
        candidate = os.path.join(results_dir, f"{project_name}.{i}.par.csv")
        if os.path.exists(candidate):
            return candidate
    return None


def evaluate(cfg, container, par_csv, fids, results_dir=None):
    """Run calibrated model and evaluate against flux tower ET.

    Returns DataFrame with per-site metrics.
    """
    print(f"Evaluating {len(fids)} sites from {par_csv}")

    calibrated_params = parse_pest_params(par_csv, fids)
    missing = [f for f in fids if f not in calibrated_params]
    if missing:
        print(f"WARNING: No calibrated params for: {missing} — skipping these sites")
        fids = [f for f in fids if f in calibrated_params]
    if not fids:
        print("No sites with calibrated parameters.")
        return pd.DataFrame()

    print("Running calibrated model...")
    model_results = run_calibrated_model(cfg, container, fids, calibrated_params)

    # Write per-site CSVs for publication_figures.py
    if results_dir is not None:
        os.makedirs(results_dir, exist_ok=True)
        for fid, df in model_results.items():
            df.to_csv(os.path.join(results_dir, f"{fid}.csv"))

    rows = []
    for fid in fids:
        flux_et = load_flux_et(fid)
        if flux_et.empty:
            print(f"  {fid}: no flux data, skipping")
            continue

        model_df = model_results[fid]
        swim_et = model_df["et_act"]

        common = swim_et.index.intersection(flux_et.index)
        if len(common) < 10:
            print(f"  {fid}: only {len(common)} overlapping days, skipping")
            continue

        obs = flux_et.loc[common].values
        m = calc_metrics(obs, swim_et.loc[common].values)

        row = {"fid": fid, **m}
        rows.append(row)

        print(
            f"  {fid}: n={m['n']:>5d}  R2={m['r2']:.3f}  KGE={m['kge']:.3f}  "
            f"RMSE={m['rmse']:.2f}  bias={m['bias']:.2f}"
        )

    if not rows:
        print("No sites with sufficient data for evaluation.")
        return pd.DataFrame()

    metrics_df = pd.DataFrame(rows).set_index("fid")

    valid = metrics_df["r2"].notna()
    vdf = metrics_df.loc[valid]

    print(f"\n{'=' * 70}")
    print(f"DAILY AGGREGATE ({len(vdf)} sites)")
    print("=" * 70)
    for stat in ["r2", "r", "rmse", "bias", "kge"]:
        vals = vdf[stat].dropna()
        print(f"  {stat:>6s}:  mean={vals.mean():.3f}  median={vals.median():.3f}")

    # Worst / best
    ranked = vdf.sort_values("kge")
    print("\nWorst 10 (by KGE):")
    for fid, row in ranked.head(10).iterrows():
        print(f"  {fid:<12} KGE={row['kge']:.3f}  R2={row['r2']:.3f}  RMSE={row['rmse']:.2f}")
    print("\nBest 10 (by KGE):")
    for fid, row in ranked.tail(10).iterrows():
        print(f"  {fid:<12} KGE={row['kge']:.3f}  R2={row['r2']:.3f}  RMSE={row['rmse']:.2f}")

    # Write evaluation_summary.csv with 'site' column for publication_figures.py
    if results_dir is not None:
        summary = metrics_df.reset_index().rename(columns={"fid": "site"})
        summary.to_csv(os.path.join(results_dir, "evaluation_summary.csv"), index=False)

    return metrics_df


def evaluate_etf(cfg, container, par_csv, fids, results_dir=None):
    """Compare SWIM ETf against Landsat PT-JPL ETf at overpass dates.

    Isolates ETf model skill from ETo bias: compares the calibrated Kcb curve
    directly against the container's Landsat ETf observations on capture dates
    only. Works for all sites (no tower data needed).
    """
    print(f"ETf evaluation: {len(fids)} sites from {par_csv}")

    calibrated_params = parse_pest_params(par_csv, fids)
    missing = [f for f in fids if f not in calibrated_params]
    if missing:
        print(f"WARNING: No calibrated params for: {missing} — skipping")
        fids = [f for f in fids if f in calibrated_params]
    if not fids:
        return pd.DataFrame()

    print("Running calibrated model...")
    model_results = run_calibrated_model(cfg, container, fids, calibrated_params)

    etf_model = getattr(cfg, "etf_target_model", "ptjpl")
    mask = "no_mask" if getattr(cfg, "mask_mode", "none") == "none" else "irr"
    etf_path = f"remote_sensing/etf/landsat/{etf_model}/{mask}"

    rows = []
    for fid in fids:
        if fid not in model_results:
            continue

        swim_etf = model_results[fid]["etf_model"]

        try:
            obs_df = container.query.dataframe(etf_path, fields=[fid])
        except KeyError:
            print(f"  {fid}: no ETf in container")
            continue

        obs_etf = obs_df[fid].dropna()
        common = swim_etf.index.intersection(obs_etf.index)
        if len(common) < 10:
            print(f"  {fid}: only {len(common)} overpass dates, skipping")
            continue

        o = obs_etf.loc[common].values
        s = swim_etf.loc[common].values
        m = calc_metrics(o, s)

        row = {
            "fid": fid,
            "n_overpass": len(common),
            "obs_etf_mean": float(np.nanmean(o)),
            "swim_etf_mean": float(np.nanmean(s)),
            **m,
        }
        rows.append(row)

        print(
            f"  {fid}: n={len(common):>4d}  R2={m['r2']:.3f}  r={m['r']:.3f}  "
            f"RMSE={m['rmse']:.3f}  bias={m['bias']:+.3f}  "
            f"obs={row['obs_etf_mean']:.3f}  swim={row['swim_etf_mean']:.3f}"
        )

    if not rows:
        return pd.DataFrame()

    metrics_df = pd.DataFrame(rows).set_index("fid")

    valid = metrics_df["r2"].notna()
    vdf = metrics_df.loc[valid]

    print(f"\n{'=' * 70}")
    print(f"ETf AT OVERPASS AGGREGATE ({len(vdf)} sites)")
    print("=" * 70)
    for stat in ["r2", "r", "rmse", "bias", "kge"]:
        vals = vdf[stat].dropna()
        print(f"  {stat:>6s}:  mean={vals.mean():.3f}  median={vals.median():.3f}")
    print(f"  obs_etf_mean:  {vdf['obs_etf_mean'].mean():.3f}")
    print(f"  swim_etf_mean: {vdf['swim_etf_mean'].mean():.3f}")

    if results_dir is not None:
        os.makedirs(results_dir, exist_ok=True)
        metrics_df.to_csv(os.path.join(results_dir, "evaluation_etf_metrics.csv"))

    return metrics_df


def evaluate_monthly(cfg, container, par_csv, fids):
    """Monthly ET totals: SWIM vs flux tower.

    Returns DataFrame with per-site monthly metrics.
    """
    print(f"Monthly evaluation: {len(fids)} sites from {par_csv}")

    calibrated_params = parse_pest_params(par_csv, fids)
    missing = [f for f in fids if f not in calibrated_params]
    if missing:
        print(f"WARNING: No calibrated params for: {missing} — skipping these sites")
        fids = [f for f in fids if f in calibrated_params]
    if not fids:
        print("No sites with calibrated parameters.")
        return pd.DataFrame()

    print("Running calibrated model...")
    model_results = run_calibrated_model(cfg, container, fids, calibrated_params)

    rows = []
    for fid in fids:
        flux_et = load_flux_et(fid)
        if flux_et.empty:
            continue

        model_df = model_results[fid]
        swim_et = model_df["et_act"]

        daily_common = swim_et.index.intersection(flux_et.index)
        if len(daily_common) < 30:
            print(f"  {fid}: only {len(daily_common)} daily overlap, skipping")
            continue

        swim_daily = swim_et.loc[daily_common]
        flux_daily = flux_et.loc[daily_common]

        swim_monthly = swim_daily.resample("MS").sum()
        flux_monthly = flux_daily.resample("MS").sum()

        # Only keep months with >= 20 valid daily flux obs
        flux_count = flux_daily.resample("MS").count()
        valid_months = flux_count[flux_count >= 20].index
        swim_monthly = swim_monthly.loc[swim_monthly.index.isin(valid_months)]
        flux_monthly = flux_monthly.loc[flux_monthly.index.isin(valid_months)]

        common = swim_monthly.index.intersection(flux_monthly.index)
        if len(common) < 6:
            print(f"  {fid}: only {len(common)} months, skipping")
            continue

        obs = flux_monthly.loc[common].values
        m = calc_metrics(obs, swim_monthly.loc[common].values)

        row = {"fid": fid, **m}
        rows.append(row)

        print(
            f"  {fid}: n={m['n']:>3d} mo  R2={m['r2']:.3f}  KGE={m['kge']:.3f}  "
            f"RMSE={m['rmse']:.1f}  bias={m['bias']:.1f}"
        )

    if not rows:
        print("No sites with sufficient data.")
        return pd.DataFrame()

    metrics_df = pd.DataFrame(rows).set_index("fid")

    valid = metrics_df["r2"].notna()
    vdf = metrics_df.loc[valid]

    print(f"\n{'=' * 70}")
    print(f"MONTHLY AGGREGATE ({len(vdf)} sites)")
    print("=" * 70)
    for stat in ["r2", "r", "rmse", "bias", "kge"]:
        vals = vdf[stat].dropna()
        print(f"  {stat:>6s}:  mean={vals.mean():.3f}  median={vals.median():.3f}")

    return metrics_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate calibrated SWIM against flux tower ET (international)"
    )
    parser.add_argument(
        "--par-csv", type=str, default=None, help="Override automatic par.csv discovery"
    )
    parser.add_argument(
        "--sites", type=str, default=None, help="Comma-separated site IDs (default: all)"
    )
    parser.add_argument(
        "--monthly",
        action="store_true",
        help="Monthly ET totals instead of daily",
    )
    parser.add_argument(
        "--etf",
        action="store_true",
        help="Compare SWIM ETf against Landsat ETf at overpass dates",
    )
    parser.add_argument(
        "--container",
        type=str,
        default=None,
        help="Override container path",
    )
    args = parser.parse_args()

    cfg = _load_config()
    results_dir = os.path.join(cfg.project_ws, "results")

    if args.par_csv:
        par_csv = args.par_csv
    else:
        # Search in master dir first, then results/group
        master_dir = os.path.join(cfg.pest_run_dir, "master")
        par_csv = find_par_csv(master_dir, cfg.project_name)
        if par_csv is None:
            group_dir = os.path.join(results_dir, "group")
            par_csv = find_par_csv(group_dir, cfg.project_name)
    if par_csv is None:
        raise FileNotFoundError("No .par.csv found. Run calibration first or provide --par-csv.")
    print(f"Using parameters: {par_csv}")

    if args.container:
        container_path = args.container
    else:
        container_path = os.path.join(cfg.data_dir, f"{cfg.project_name}.swim")
    container = SwimContainer.open(container_path, mode="r")

    if args.sites:
        fids = [s.strip() for s in args.sites.split(",")]
    else:
        fids = container.field_uids

    try:
        if args.etf:
            metrics = evaluate_etf(cfg, container, par_csv, fids, results_dir=results_dir)
            out_csv = os.path.join(results_dir, "evaluation_etf_metrics.csv")
        elif args.monthly:
            metrics = evaluate_monthly(cfg, container, par_csv, fids)
            out_csv = os.path.join(results_dir, "evaluation_monthly_metrics.csv")
        else:
            metrics = evaluate(cfg, container, par_csv, fids, results_dir=results_dir)
            out_csv = os.path.join(results_dir, "evaluation_metrics.csv")
        os.makedirs(results_dir, exist_ok=True)
        metrics.to_csv(out_csv)
        print(f"\nMetrics saved to {out_csv}")
    finally:
        container.close()
