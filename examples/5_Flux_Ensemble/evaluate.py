"""Evaluate calibrated SWIM against flux tower ET and OpenET models.

Runs the calibrated model in forecast mode and compares SWIM ET against
energy-balance-corrected flux tower ET (ET_corr) alongside 4 open-source
OpenET models (geeSEBAL, PT-JPL, SSEBop, SIMS) plus their ensemble mean.

OpenET model ET is computed directly from per-model ETf stored in the
container (ETf × ETo), not from external CSV files.

Usage:
    python evaluate.py [--par-csv PATH] [--sites SITE1,SITE2]
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

OPEN_SOURCE_MODELS = ["geesebal", "ptjpl", "ssebop", "sims"]
IRR_THRESHOLD = 0.3


def load_config():
    project_dir = Path(__file__).resolve().parent
    conf = project_dir / "5_Flux_Ensemble.toml"
    cfg = ProjectConfig()
    if os.path.isdir("/data/ssd2/swim"):
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
            runoff_process=getattr(cfg, "runoff_process", "cn"),
            refet_type=getattr(cfg, "refet_type", "eto") or "eto",
            fields=fids,
        )

        output, _ = run_daily_loop_fast(swim_input)
        dates = pd.date_range(swim_input.start_date, periods=swim_input.n_days, freq="D")
        etr = swim_input.get_time_series("etr")

        results = {}
        for i, fid in enumerate(swim_input.fids):
            results[fid] = pd.DataFrame(
                {
                    "et_act": output.eta[:, i],
                    "etf_model": output.etf[:, i],
                    "etref": etr[:, i],
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


def load_flux_et(fid, flux_dir):
    """Load energy-balance-corrected ET from flux tower data."""
    path = os.path.join(flux_dir, f"{fid}_daily_data.csv")
    if not os.path.exists(path):
        return pd.Series(dtype=float)
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    if "ET_corr" in df.columns:
        return df["ET_corr"]
    return pd.Series(dtype=float)


def load_openet_etf(container, fid, irr_data):
    """Load per-model ETf from the container and select irr/inv_irr mask by year.

    Returns {model_name: pd.Series} of ETf values with year-appropriate mask applied.
    """
    field_irr = irr_data.get(fid, {})
    irr_years = set()
    for k, v in field_irr.items():
        if k == "fallow_years":
            continue
        try:
            if isinstance(v, dict) and v.get("f_irr", 0.0) >= IRR_THRESHOLD:
                irr_years.add(int(k))
        except (ValueError, TypeError):
            continue

    etf_by_model = {}
    for model in OPEN_SOURCE_MODELS:
        # Load both masks
        etf_inv = etf_irr = None
        for mask in ["inv_irr", "irr"]:
            etf_path = f"remote_sensing/etf/landsat/{model}/{mask}"
            try:
                etf_df = container.query.dataframe(etf_path, fields=[fid])
                if fid in etf_df.columns:
                    series = etf_df[fid]
                    if mask == "inv_irr":
                        etf_inv = series
                    else:
                        etf_irr = series
            except Exception:
                pass

        if etf_inv is None and etf_irr is None:
            continue

        # Default to inv_irr, switch to irr for irrigated years
        if etf_inv is not None:
            combined = etf_inv.copy()
        else:
            combined = pd.Series(np.nan, index=etf_irr.index)

        if etf_irr is not None and irr_years:
            irr_mask = combined.index.year.isin(irr_years)
            combined.loc[irr_mask] = etf_irr.loc[irr_mask]

        etf_by_model[model] = combined

    return etf_by_model


def calc_metrics(obs, mod):
    """Calculate R2, Pearson r, RMSE, bias between obs and mod arrays."""
    mask = np.isfinite(obs) & np.isfinite(mod)
    obs, mod = obs[mask], mod[mask]
    if len(obs) < 10:
        return {"n": len(obs), "r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}
    r, _ = stats.pearsonr(obs, mod)
    r2 = r2_score(obs, mod)
    rmse = np.sqrt(mean_squared_error(obs, mod))
    bias = float((mod - obs).mean())
    return {"n": len(obs), "r2": r2, "r": r, "rmse": rmse, "bias": bias}


def evaluate(cfg, container, par_csv, fids, flux_dir):
    """Run calibrated model and evaluate against flux tower ET and OpenET models.

    Returns DataFrame with per-field metrics for SWIM and each OpenET model.
    """
    print(f"Evaluating {len(fids)} fields from {par_csv}")

    # Load irrigation data from container
    irr_data = {}
    try:
        props = container.query.properties()
        for fid in fids:
            if fid in props and "irr" in props[fid]:
                irr_data[fid] = props[fid]["irr"]
    except Exception:
        pass

    calibrated_params = parse_pest_params(par_csv, fids)
    missing = [f for f in fids if f not in calibrated_params]
    if missing:
        print(f"WARNING: No calibrated params for: {missing}")

    print("Running calibrated model...")
    model_results = run_calibrated_model(cfg, container, fids, calibrated_params)

    rows = []
    for fid in fids:
        flux_et = load_flux_et(fid, flux_dir)
        if flux_et.empty:
            print(f"  {fid}: no flux data, skipping")
            continue

        model_df = model_results[fid]
        swim_et = model_df["et_act"]
        etref = model_df["etref"]

        # Common dates between model and flux
        common = swim_et.index.intersection(flux_et.index)
        if len(common) < 10:
            print(f"  {fid}: only {len(common)} overlapping days, skipping")
            continue

        obs = flux_et.loc[common].values

        # SWIM metrics
        row = {"fid": fid}
        m = calc_metrics(obs, swim_et.loc[common].values)
        row["n"] = m["n"]
        for k in ["r2", "r", "rmse", "bias"]:
            row[f"{k}_swim"] = m[k]

        # Per-model OpenET metrics (ET = ETf × ETo on capture dates)
        etf_by_model = load_openet_etf(container, fid, irr_data)
        model_et_on_common = {}

        for model_name in OPEN_SOURCE_MODELS:
            if model_name not in etf_by_model:
                for k in ["r2", "r", "rmse", "bias"]:
                    row[f"{k}_{model_name}"] = np.nan
                continue

            etf_series = etf_by_model[model_name]
            et_series = etf_series * etref
            et_on_common = et_series.reindex(common)

            valid = np.isfinite(et_on_common.values) & np.isfinite(obs)
            if valid.sum() >= 10:
                model_et_on_common[model_name] = et_on_common.values
                m = calc_metrics(obs, et_on_common.values)
            else:
                m = {"r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}

            for k in ["r2", "r", "rmse", "bias"]:
                row[f"{k}_{model_name}"] = m[k]

        # Open-source ensemble (nanmean of available models)
        if model_et_on_common:
            stack = np.column_stack(list(model_et_on_common.values()))
            ensemble_et = np.nanmean(stack, axis=1)
            m = calc_metrics(obs, ensemble_et)
        else:
            m = {"r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}

        for k in ["r2", "r", "rmse", "bias"]:
            row[f"{k}_ensemble"] = m[k]

        rows.append(row)

        print(
            f"  {fid}: n={row['n']:>5d}  "
            f"R2_swim={row['r2_swim']:.3f}  R2_ens={row['r2_ensemble']:.3f}  "
            f"RMSE_swim={row['rmse_swim']:.3f}  RMSE_ens={row['rmse_ensemble']:.3f}"
        )

    if not rows:
        print("No fields with sufficient data for evaluation.")
        return pd.DataFrame()

    metrics_df = pd.DataFrame(rows).set_index("fid")

    # Aggregate summary
    all_models = ["swim"] + OPEN_SOURCE_MODELS + ["ensemble"]
    print("\n" + "=" * 80)
    print(f"AGGREGATE ({len(metrics_df)} fields)")
    print("=" * 80)
    header = f"{'model':<12}"
    for stat in ["r2", "r", "rmse", "bias"]:
        header += f"  {stat + '_mean':>10}  {stat + '_med':>10}"
    print(header)
    print("-" * len(header))

    for model_name in all_models:
        line = f"{model_name:<12}"
        for stat in ["r2", "r", "rmse", "bias"]:
            col = f"{stat}_{model_name}"
            if col in metrics_df.columns:
                vals = metrics_df[col].dropna()
                line += f"  {vals.mean():>10.3f}  {vals.median():>10.3f}"
            else:
                line += f"  {'n/a':>10}  {'n/a':>10}"
        print(line)

    return metrics_df


def find_par_csv(results_dir, project_name):
    """Find the latest .par.csv in results directory."""
    for i in range(10, -1, -1):
        candidate = os.path.join(results_dir, f"{project_name}.{i}.par.csv")
        if os.path.exists(candidate):
            return candidate
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate calibrated SWIM against flux tower ET and OpenET models"
    )
    parser.add_argument(
        "--par-csv", type=str, default=None, help="Override automatic par.csv discovery"
    )
    parser.add_argument(
        "--sites", type=str, default=None, help="Comma-separated site IDs (default: all)"
    )
    args = parser.parse_args()

    cfg = load_config()
    flux_dir = os.path.join(cfg.data_dir, "flux")
    results_dir = os.path.join(cfg.project_ws, "results")

    if args.par_csv:
        par_csv = args.par_csv
    else:
        par_csv = find_par_csv(results_dir, cfg.project_name)
    if par_csv is None:
        raise FileNotFoundError(f"No .par.csv found in {results_dir}")
    print(f"Using parameters: {par_csv}")

    container_path = os.path.join(cfg.data_dir, f"{cfg.project_name}.swim")
    container = SwimContainer.open(container_path, mode="r")

    if args.sites:
        fids = [s.strip() for s in args.sites.split(",")]
    else:
        fids = container.field_uids

    try:
        metrics = evaluate(cfg, container, par_csv, fids, flux_dir)
        out_csv = os.path.join(results_dir, "evaluation_metrics.csv")
        os.makedirs(results_dir, exist_ok=True)
        metrics.to_csv(out_csv)
        print(f"\nMetrics saved to {out_csv}")
    finally:
        container.close()
