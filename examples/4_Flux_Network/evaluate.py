"""Evaluate calibrated SWIM against flux tower ET and SSEBop NHM.

Runs the calibrated model in forecast mode and compares SWIM ET against
energy-balance-corrected flux tower ET (ET_corr) alongside interpolated
SSEBop NHM ET (ETf × ETo).

Usage:
    python evaluate.py [--par-csv PATH] [--sites SITE1,SITE2]
    python evaluate.py --etf  # compare SWIM ETf vs SSEBop NHM ETf at capture dates
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

IRR_THRESHOLD = 0.3


def load_config():
    project_dir = Path(__file__).resolve().parent
    conf = project_dir / "4_Flux_Network.toml"
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
            fields=fids,
            empirical_kc_max=True,
            mask_mode=getattr(cfg, "mask_mode", "irrigation"),
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


def load_ssebop_etf(container, fid, irr_data):
    """Load SSEBop NHM ETf from the container with year-appropriate mask.

    Returns pd.Series of ETf values, or None if no data available.
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

    # Load both masks
    etf_inv = etf_irr = None
    for mask in ["inv_irr", "irr"]:
        etf_path = f"remote_sensing/etf/landsat/ssebop/{mask}"
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

    inv_valid = etf_inv is not None and etf_inv.notna().any()
    irr_valid = etf_irr is not None and etf_irr.notna().any()

    if not inv_valid and not irr_valid:
        return None

    # Default to inv_irr, switch to irr for irrigated years
    if inv_valid:
        combined = etf_inv.copy()
    else:
        combined = pd.Series(np.nan, index=etf_irr.index)

    if irr_valid and irr_years:
        irr_mask = combined.index.year.isin(irr_years)
        combined.loc[irr_mask] = etf_irr.loc[irr_mask]

    if not inv_valid and irr_valid:
        combined = etf_irr.copy()

    return combined


def load_ssebop_etf_no_mask(container, fid):
    """Load SSEBop NHM ETf from the no_mask path (full footprint)."""
    etf_path = "remote_sensing/etf/landsat/ssebop/no_mask"
    try:
        etf_df = container.query.dataframe(etf_path, fields=[fid])
        if fid in etf_df.columns:
            return etf_df[fid]
    except Exception:
        pass
    return None


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


def evaluate(cfg, container, par_csv, fids, flux_dir, no_mask=False):
    """Run calibrated model and evaluate against flux tower ET and SSEBop NHM.

    Returns DataFrame with per-field metrics for SWIM and SSEBop NHM.
    """
    print(f"Evaluating {len(fids)} fields from {par_csv}")

    # Load irrigation data from container
    if no_mask:
        irr_data = {}
    else:
        try:
            dynamics = container.export._get_dynamics_dict(fids)
            irr_data = dynamics.get("irr", {})
        except Exception:
            irr_data = {}

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

        # SSEBop NHM metrics (interpolated ETf × ETo)
        if no_mask:
            etf_series = load_ssebop_etf_no_mask(container, fid)
        else:
            etf_series = load_ssebop_etf(container, fid, irr_data)
        if etf_series is not None:
            etf_interp = etf_series.interpolate(method="linear")
            ssebop_et = etf_interp * etref
            ssebop_on_common = ssebop_et.reindex(common)

            valid = np.isfinite(ssebop_on_common.values) & np.isfinite(obs)
            if valid.sum() >= 10:
                m = calc_metrics(obs, ssebop_on_common.values)
            else:
                m = {"r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}
        else:
            m = {"r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}

        for k in ["r2", "r", "rmse", "bias"]:
            row[f"{k}_ssebop"] = m[k]

        rows.append(row)

        print(
            f"  {fid}: n={row['n']:>5d}  "
            f"R2_swim={row['r2_swim']:.3f}  R2_ssebop={row['r2_ssebop']:.3f}  "
            f"RMSE_swim={row['rmse_swim']:.3f}  RMSE_ssebop={row['rmse_ssebop']:.3f}"
        )

    if not rows:
        print("No fields with sufficient data for evaluation.")
        return pd.DataFrame()

    metrics_df = pd.DataFrame(rows).set_index("fid")

    # Aggregate summary
    has_both = metrics_df["r2_swim"].notna() & metrics_df["r2_ssebop"].notna()
    common_df = metrics_df.loc[has_both]

    print("\n" + "=" * 80)
    print(f"AGGREGATE ({len(common_df)} fields with both SWIM and SSEBop estimates)")
    print("=" * 80)
    header = f"{'model':<12}"
    for stat in ["r2", "r", "rmse", "bias"]:
        header += f"  {stat + '_mean':>10}  {stat + '_med':>10}"
    print(header)
    print("-" * len(header))

    for model_name in ["swim", "ssebop"]:
        line = f"{model_name:<12}"
        for stat in ["r2", "r", "rmse", "bias"]:
            col = f"{stat}_{model_name}"
            if col in common_df.columns:
                vals = common_df[col].dropna()
                line += f"  {vals.mean():>10.3f}  {vals.median():>10.3f}"
            else:
                line += f"  {'n/a':>10}  {'n/a':>10}"
        print(line)

    return metrics_df


def _monthly_sum(daily_series, max_interp=5):
    """Resample daily series to monthly sums, interpolating up to max_interp gaps per month.

    Returns monthly Series with NaN for months that had more than max_interp missing days.
    """
    monthly = daily_series.resample("MS").apply(lambda grp: _interp_and_sum(grp, max_interp))
    return monthly


def _interp_and_sum(grp, max_interp):
    """Interpolate up to max_interp NaNs in a month, then sum. Return NaN if too many gaps."""
    n_missing = grp.isna().sum()
    if n_missing > max_interp:
        return np.nan
    if n_missing > 0:
        grp = grp.interpolate(method="linear", limit=max_interp)
    return grp.sum()


def evaluate_monthly(cfg, container, par_csv, fids, flux_dir, max_interp=5, no_mask=False):
    """Monthly aggregation of ET evaluation.

    Resamples daily ET to monthly totals (mm/month), interpolating up to
    max_interp missing flux days per month before summing.
    """
    print(f"Monthly evaluation: {len(fids)} fields from {par_csv}")

    if no_mask:
        irr_data = {}
    else:
        try:
            dynamics = container.export._get_dynamics_dict(fids)
            irr_data = dynamics.get("irr", {})
        except Exception:
            irr_data = {}

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
            continue

        model_df = model_results[fid]
        swim_et = model_df["et_act"]
        etref = model_df["etref"]

        # Build aligned daily frame on common dates
        common_dates = swim_et.index.intersection(flux_et.index)
        if len(common_dates) < 30:
            continue

        # Full daily index spanning the overlap
        full_idx = pd.date_range(common_dates.min(), common_dates.max(), freq="D")
        flux_daily = flux_et.reindex(full_idx)
        swim_daily = swim_et.reindex(full_idx)

        # Monthly sums (ET) with interpolation limit on flux
        flux_monthly = _monthly_sum(flux_daily, max_interp)
        swim_monthly = swim_daily.resample("MS").sum()

        # SSEBop monthly ET (sum) and ETf (mean)
        if no_mask:
            etf_series = load_ssebop_etf_no_mask(container, fid)
        else:
            etf_series = load_ssebop_etf(container, fid, irr_data)
        if etf_series is not None:
            etf_interp = etf_series.reindex(full_idx).interpolate(method="linear")
            ssebop_daily = etf_interp * etref.reindex(full_idx)
            ssebop_monthly = ssebop_daily.resample("MS").sum()
        else:
            ssebop_monthly = pd.Series(np.nan, index=swim_monthly.index)

        # Keep only months where flux is valid
        valid_months = flux_monthly.dropna().index
        common_months = valid_months.intersection(swim_monthly.index)
        if len(common_months) < 6:
            continue

        obs = flux_monthly.loc[common_months].values
        row = {"fid": fid}

        m = calc_metrics(obs, swim_monthly.loc[common_months].values)
        row["n_months"] = m["n"]
        for k in ["r2", "r", "rmse", "bias"]:
            row[f"{k}_swim"] = m[k]

        ssebop_vals = ssebop_monthly.reindex(common_months).values
        valid_ssebop = np.isfinite(ssebop_vals) & np.isfinite(obs)
        if valid_ssebop.sum() >= 6:
            m = calc_metrics(obs, ssebop_vals)
        else:
            m = {"r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}

        for k in ["r2", "r", "rmse", "bias"]:
            row[f"{k}_ssebop"] = m[k]

        rows.append(row)
        print(
            f"  {fid}: n_months={row['n_months']:>4d}  "
            f"R2_swim={row['r2_swim']:.3f}  R2_ssebop={row['r2_ssebop']:.3f}  "
            f"RMSE_swim={row['rmse_swim']:.2f}  RMSE_ssebop={row['rmse_ssebop']:.2f}"
        )

    if not rows:
        print("No fields with sufficient monthly data.")
        return pd.DataFrame()

    metrics_df = pd.DataFrame(rows).set_index("fid")

    has_both = metrics_df["r2_swim"].notna() & metrics_df["r2_ssebop"].notna()
    common_df = metrics_df.loc[has_both]

    print("\n" + "=" * 80)
    print(f"MONTHLY AGGREGATE ({len(common_df)} fields with both SWIM and SSEBop)")
    print("=" * 80)
    header = f"{'model':<12}"
    for stat in ["r2", "r", "rmse", "bias"]:
        header += f"  {stat + '_mean':>10}  {stat + '_med':>10}"
    print(header)
    print("-" * len(header))

    for model_name in ["swim", "ssebop"]:
        line = f"{model_name:<12}"
        for stat in ["r2", "r", "rmse", "bias"]:
            col = f"{stat}_{model_name}"
            if col in common_df.columns:
                vals = common_df[col].dropna()
                line += f"  {vals.mean():>10.3f}  {vals.median():>10.3f}"
            else:
                line += f"  {'n/a':>10}  {'n/a':>10}"
        print(line)

    return metrics_df


def evaluate_etf(cfg, container, par_csv, fids, no_mask=False):
    """Compare SWIM ETf against SSEBop NHM ETf at Landsat capture dates.

    Isolates model skill from ETo conversion issues by comparing ETf directly.

    Returns DataFrame with per-field ETf metrics.
    """
    print(f"ETf evaluation: {len(fids)} fields from {par_csv}")

    calibrated_params = parse_pest_params(par_csv, fids)
    model_results = run_calibrated_model(cfg, container, fids, calibrated_params)

    # Load irrigation data for mask selection
    if no_mask:
        irr_data = {}
    else:
        try:
            dynamics = container.export._get_dynamics_dict(fids)
            irr_data = dynamics.get("irr", {})
        except Exception:
            irr_data = {}

    rows = []
    for fid in fids:
        if fid not in model_results:
            continue
        swim_etf = model_results[fid]["etf_model"]

        if no_mask:
            etf_series = load_ssebop_etf_no_mask(container, fid)
        else:
            etf_series = load_ssebop_etf(container, fid, irr_data)
        if etf_series is None:
            continue

        obs_etf = etf_series.dropna()
        obs_etf = obs_etf[obs_etf > 0]
        if len(obs_etf) < 10:
            continue

        common = swim_etf.index.intersection(obs_etf.index)
        if len(common) < 10:
            continue

        s = swim_etf.loc[common].values
        o = obs_etf.loc[common].values
        valid = np.isfinite(s) & np.isfinite(o)
        s, o = s[valid], o[valid]
        if len(s) < 10:
            continue

        m = calc_metrics(o, s)
        rows.append({"fid": fid, **m})

    if not rows:
        print("No fields with sufficient ETf data.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    print("\n" + "=" * 70)
    print("ETf: SWIM vs SSEBop NHM (at Landsat capture dates)")
    print("=" * 70)
    print(
        f"  Fields: {len(df)}  "
        f"R2_mean={df['r2'].mean():.3f}  R2_med={df['r2'].median():.3f}  "
        f"RMSE_mean={df['rmse'].mean():.3f}  bias_mean={df['bias'].mean():.3f}"
    )

    # Worst / best fields
    ranked = df.sort_values("r2")
    print("\nWorst 10 fields:")
    for _, row in ranked.head(10).iterrows():
        print(f"  {row['fid']:<20} R2={row['r2']:.3f}  RMSE={row['rmse']:.3f}")
    print("\nBest 10 fields:")
    for _, row in ranked.tail(10).iterrows():
        print(f"  {row['fid']:<20} R2={row['r2']:.3f}  RMSE={row['rmse']:.3f}")

    return df


def find_par_csv(results_dir, project_name):
    """Find the latest .par.csv in results directory."""
    for i in range(10, -1, -1):
        candidate = os.path.join(results_dir, f"{project_name}.{i}.par.csv")
        if os.path.exists(candidate):
            return candidate
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate calibrated SWIM against flux tower ET and SSEBop NHM"
    )
    parser.add_argument(
        "--par-csv", type=str, default=None, help="Override automatic par.csv discovery"
    )
    parser.add_argument(
        "--sites", type=str, default=None, help="Comma-separated site IDs (default: all)"
    )
    parser.add_argument(
        "--etf",
        action="store_true",
        help="Compare SWIM ETf vs SSEBop NHM ETf at capture dates (instead of ET vs flux)",
    )
    parser.add_argument(
        "--monthly",
        action="store_true",
        help="Evaluate at monthly time step (sum ET, mean ETf)",
    )
    parser.add_argument(
        "--container",
        type=str,
        default=None,
        help="Override container path (default: derived from config)",
    )
    parser.add_argument(
        "--no-mask",
        action="store_true",
        help="Use no_mask ETf (full footprint) instead of irr/inv_irr switching",
    )
    args = parser.parse_args()

    cfg = load_config()
    flux_dir = os.path.join(cfg.data_dir, "daily_flux_files")
    results_dir = os.path.join(cfg.project_ws, "results")

    if args.par_csv:
        par_csv = args.par_csv
    else:
        par_csv = find_par_csv(results_dir, cfg.project_name)
    if par_csv is None:
        raise FileNotFoundError(f"No .par.csv found in {results_dir}")
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
        if args.monthly:
            metrics = evaluate_monthly(
                cfg, container, par_csv, fids, flux_dir, no_mask=args.no_mask
            )
            out_csv = os.path.join(results_dir, "evaluation_monthly_metrics.csv")
        elif args.etf:
            metrics = evaluate_etf(cfg, container, par_csv, fids, no_mask=args.no_mask)
            out_csv = os.path.join(results_dir, "evaluation_etf_metrics.csv")
        else:
            metrics = evaluate(cfg, container, par_csv, fids, flux_dir, no_mask=args.no_mask)
            out_csv = os.path.join(results_dir, "evaluation_metrics.csv")
        os.makedirs(results_dir, exist_ok=True)
        metrics.to_csv(out_csv)
        print(f"\nMetrics saved to {out_csv}")
    finally:
        container.close()
