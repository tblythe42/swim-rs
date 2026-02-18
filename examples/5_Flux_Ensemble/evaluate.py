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

OPEN_SOURCE_MODELS = ["geesebal", "ptjpl", "ssebop", "sims", "eemetric", "disalexi"]
VOLK_COLUMN_MAP = {
    "GEESEBAL_3x3": "geesebal",
    "PTJPL_3x3": "ptjpl",
    "SSEBOP_3x3": "ssebop",
    "SIMS_3x3": "sims",
    "EEMETRIC_3x3": "eemetric",
    "DISALEXI_3x3": "disalexi",
}
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
            refet_type=getattr(cfg, "refet_type", "eto") or "eto",
            fields=fids,
            empirical_kc_max=True,
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


def load_openet_etf_nomask(container, fid):
    """Load per-model ETf from the container using no_mask (unmasked) data.

    Returns {model_name: pd.Series} of ETf values without irrigation masking.
    """
    etf_by_model = {}
    for model in OPEN_SOURCE_MODELS:
        etf_path = f"remote_sensing/etf/landsat/{model}/no_mask"
        try:
            etf_df = container.query.dataframe(etf_path, fields=[fid])
            if fid in etf_df.columns:
                series = etf_df[fid]
                if series.notna().any():
                    etf_by_model[model] = series
        except Exception:
            pass
    return etf_by_model


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

        # Treat all-NaN series as missing
        inv_valid = etf_inv is not None and etf_inv.notna().any()
        irr_valid = etf_irr is not None and etf_irr.notna().any()

        if not inv_valid and not irr_valid:
            continue

        # Default to inv_irr, switch to irr for irrigated years
        if inv_valid:
            combined = etf_inv.copy()
        else:
            combined = pd.Series(np.nan, index=etf_irr.index)

        if irr_valid and irr_years:
            irr_mask = combined.index.year.isin(irr_years)
            combined.loc[irr_mask] = etf_irr.loc[irr_mask]

        # If inv_irr had no valid data, fall back entirely to irr
        if not inv_valid and irr_valid:
            combined = etf_irr.copy()

        etf_by_model[model] = combined

    return etf_by_model


def load_volk_openet_et(fid, openet_daily_dir):
    """Load per-model daily ET from Volk OpenET 3x3 extractions.

    These CSVs contain actual ET (mm/day), not ETf fractions.
    Returns {model_name: pd.Series} of sparse ET on Landsat dates.
    """
    path = os.path.join(openet_daily_dir, f"{fid}.csv")
    if not os.path.exists(path):
        return {}

    df = pd.read_csv(path, index_col="DATE", parse_dates=True)

    et_by_model = {}
    for raw_col, model_name in VOLK_COLUMN_MAP.items():
        if raw_col in df.columns:
            et_by_model[model_name] = df[raw_col].astype(float)

    if "ensemble_mean_3x3" in df.columns:
        et_by_model["ensemble"] = df["ensemble_mean_3x3"].astype(float)

    return et_by_model


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


def _get_diy_openet(container, fid, irr_data, etref):
    """DIY: interpolate our sparse ETf to daily, then multiply by daily ETo.

    Tries no_mask ETf first (unmasked, for fair OpenET comparison), then
    falls back to irr/inv_irr masked ETf.

    Returns {model_name: pd.Series} of daily ET (interpolated ETf × ETo).
    """
    etf_by_model = load_openet_etf_nomask(container, fid)
    if not etf_by_model:
        etf_by_model = load_openet_etf(container, fid, irr_data)
    et_daily = {}
    for model_name, etf_series in etf_by_model.items():
        etf_interp = etf_series.interpolate(method="linear")
        et_daily[model_name] = etf_interp * etref
    return et_daily


def _get_volk_openet(fid, openet_daily_dir):
    """Volk: load pre-computed daily ET from OpenET 3x3 CSVs.

    Returns {model_name: pd.Series} of sparse ET (already mm/day on Landsat dates).
    """
    return load_volk_openet_et(fid, openet_daily_dir)


def evaluate(cfg, container, par_csv, fids, flux_dir, openet_source="diy"):
    """Run calibrated model and evaluate against flux tower ET and OpenET models.

    Parameters
    ----------
    openet_source : str
        'diy' — use our own ETf extracts from the container (ETf × ETo).
        'volk' — use Volk OpenET 3x3 daily ET extractions (already mm/day).

    Returns DataFrame with per-field metrics for SWIM and each OpenET model.
    """
    print(f"Evaluating {len(fids)} fields from {par_csv} (openet_source={openet_source})")

    # Load irrigation data from container
    irr_data = {}
    try:
        props = container.query.properties()
        for fid in fids:
            if fid in props and "irr" in props[fid]:
                irr_data[fid] = props[fid]["irr"]
    except Exception:
        pass

    if openet_source == "volk":
        openet_daily_dir = os.path.join(cfg.data_dir, "openet_flux", "daily_data")

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

        # Per-model OpenET metrics
        if openet_source == "diy":
            # DIY returns daily ET (already interpolated ETf × ETo)
            et_daily_by_model = _get_diy_openet(container, fid, irr_data, etref)
        else:
            # Volk returns sparse ET on Landsat dates; interpolate to daily
            et_sparse_by_model = _get_volk_openet(fid, openet_daily_dir)
            et_daily_by_model = {}
            for mn, s in et_sparse_by_model.items():
                et_daily_by_model[mn] = s.interpolate(method="linear")

        model_et_on_common = {}
        for model_name in OPEN_SOURCE_MODELS:
            if model_name not in et_daily_by_model:
                for k in ["r2", "r", "rmse", "bias"]:
                    row[f"{k}_{model_name}"] = np.nan
                continue

            et_daily = et_daily_by_model[model_name]
            et_on_common = et_daily.reindex(common)

            valid = np.isfinite(et_on_common.values) & np.isfinite(obs)
            if valid.sum() >= 10:
                model_et_on_common[model_name] = et_on_common.values
                m = calc_metrics(obs, et_on_common.values)
            else:
                m = {"r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}

            for k in ["r2", "r", "rmse", "bias"]:
                row[f"{k}_{model_name}"] = m[k]

        # Ensemble: use Volk pre-computed if available, else container, else nanmean
        if "ensemble" in et_daily_by_model:
            # Volk pre-computed ensemble_mean_3x3 (already interpolated above)
            ens_on_common = et_daily_by_model["ensemble"].reindex(common)
            valid = np.isfinite(ens_on_common.values) & np.isfinite(obs)
            if valid.sum() >= 10:
                m = calc_metrics(obs, ens_on_common.values)
            else:
                m = {"r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}
        else:
            ensemble_source = getattr(cfg, "ensemble_source", "computed")
            if ensemble_source == "openet":
                ens_etf = None
                for mask in ["no_mask", "inv_irr", "irr"]:
                    ens_path = f"remote_sensing/etf/landsat/ensemble/{mask}"
                    try:
                        ens_df = container.query.dataframe(ens_path, fields=[fid])
                        if fid in ens_df.columns and ens_df[fid].notna().any():
                            ens_etf = ens_df[fid]
                            break
                    except Exception:
                        pass
                if ens_etf is not None:
                    ens_et_daily = ens_etf.interpolate(method="linear") * etref
                    ens_on_common = ens_et_daily.reindex(common)
                    m = calc_metrics(obs, ens_on_common.values)
                else:
                    m = {"r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}
            elif model_et_on_common:
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

    # Aggregate summary — only sites where both SWIM and ensemble have metrics
    all_models = ["swim"] + OPEN_SOURCE_MODELS + ["ensemble"]
    has_both = metrics_df["r2_swim"].notna() & metrics_df["r2_ensemble"].notna()
    common_df = metrics_df.loc[has_both]

    print("\n" + "=" * 80)
    print(f"AGGREGATE ({len(common_df)} fields with both SWIM and ensemble estimates)")
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
            if col in common_df.columns:
                vals = common_df[col].dropna()
                line += f"  {vals.mean():>10.3f}  {vals.median():>10.3f}"
            else:
                line += f"  {'n/a':>10}  {'n/a':>10}"
        print(line)

    return metrics_df


def evaluate_etf(cfg, container, par_csv, fids):
    """Compare SWIM ETf against OpenET ETf from the container at capture dates.

    Runs the calibrated model and compares predicted ETf directly against
    per-model ETf observations stored in the container (at Landsat overpass
    dates only).  This isolates model skill from ETo conversion issues.

    Returns DataFrame with per-field, per-model ETf metrics.
    """
    print(f"ETf evaluation: {len(fids)} fields from {par_csv}")

    calibrated_params = parse_pest_params(par_csv, fids)
    model_results = run_calibrated_model(cfg, container, fids, calibrated_params)

    # Load irrigation data for mask selection
    irr_data = {}
    try:
        props = container.query.properties()
        for fid in fids:
            if fid in props and "irr" in props[fid]:
                irr_data[fid] = props[fid]["irr"]
    except Exception:
        pass

    rows = []
    for fid in fids:
        if fid not in model_results:
            continue
        swim_etf = model_results[fid]["etf_model"]

        # Determine irrigated years for mask selection
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

        # Try no_mask ETf first for this field
        nomask_etf = load_openet_etf_nomask(container, fid)

        for model in OPEN_SOURCE_MODELS:
            # Prefer no_mask ETf; fall back to irr/inv_irr masked
            if model in nomask_etf:
                combined = nomask_etf[model]
            else:
                etf_inv = etf_irr = None
                for mask in ["inv_irr", "irr"]:
                    path = f"remote_sensing/etf/landsat/{model}/{mask}"
                    try:
                        etf_df = container.query.dataframe(path, fields=[fid])
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

                inv_valid = etf_inv is not None and etf_inv.dropna().any()
                irr_valid = etf_irr is not None and etf_irr.dropna().any()

                if inv_valid and irr_valid:
                    combined = etf_inv.copy()
                    if irr_years:
                        irr_mask = combined.index.year.isin(irr_years)
                        combined.loc[irr_mask] = etf_irr.loc[irr_mask]
                elif irr_valid:
                    combined = etf_irr
                elif inv_valid:
                    combined = etf_inv
                else:
                    continue

            obs_etf = combined.dropna()
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
            rows.append({"fid": fid, "model": model, **m})

    if not rows:
        print("No fields with sufficient ETf data.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Per-field summary (median across models)
    by_fid = df.groupby("fid").agg(
        n=("n", "sum"),
        r2_median=("r2", "median"),
        rmse_median=("rmse", "median"),
        bias_median=("bias", "median"),
    )

    # Per-model summary
    print("\n" + "=" * 70)
    print("ETf: SWIM vs OpenET (at Landsat capture dates)")
    print("=" * 70)
    header = f"{'model':<12}  {'combos':>6}  {'r2_mean':>8}  {'r2_med':>8}  {'rmse_mean':>10}  {'bias_mean':>10}"
    print(header)
    print("-" * len(header))
    for model in OPEN_SOURCE_MODELS:
        sub = df[df["model"] == model]
        if sub.empty:
            continue
        print(
            f"{model:<12}  {len(sub):>6}  {sub['r2'].mean():>8.3f}  "
            f"{sub['r2'].median():>8.3f}  {sub['rmse'].mean():>10.3f}  "
            f"{sub['bias'].mean():>10.3f}"
        )
    print(
        f"{'ALL':<12}  {len(df):>6}  {df['r2'].mean():>8.3f}  "
        f"{df['r2'].median():>8.3f}  {df['rmse'].mean():>10.3f}  "
        f"{df['bias'].mean():>10.3f}"
    )

    # Worst / best fields
    ranked = by_fid.sort_values("r2_median")
    print("\nWorst 10 fields (median R2 across models):")
    for fid, row in ranked.head(10).iterrows():
        print(f"  {fid:<20} R2={row['r2_median']:.3f}  RMSE={row['rmse_median']:.3f}")
    print("\nBest 10 fields:")
    for fid, row in ranked.tail(10).iterrows():
        print(f"  {fid:<20} R2={row['r2_median']:.3f}  RMSE={row['rmse_median']:.3f}")

    return df


def load_volk_monthly_et(fid, monthly_dir):
    """Load Volk OpenET monthly ET totals (mm/month).

    Returns {model_name: pd.Series} indexed by month start date.
    """
    path = os.path.join(monthly_dir, f"{fid}.csv")
    if not os.path.exists(path):
        return {}

    df = pd.read_csv(path, index_col="DATE", parse_dates=True)

    et_by_model = {}
    for raw_col, model_name in VOLK_COLUMN_MAP.items():
        if raw_col in df.columns:
            et_by_model[model_name] = df[raw_col].astype(float)

    if "ensemble_mean_3x3" in df.columns:
        et_by_model["ensemble"] = df["ensemble_mean_3x3"].astype(float)

    return et_by_model


def evaluate_monthly(cfg, container, par_csv, fids, flux_dir):
    """Monthly ET comparison: SWIM vs flux vs Volk 3x3 monthly totals."""
    monthly_dir = os.path.join(cfg.data_dir, "openet_flux", "monthly_data")
    print(f"Monthly evaluation: {len(fids)} fields from {par_csv}")

    calibrated_params = parse_pest_params(par_csv, fids)
    print("Running calibrated model...")
    model_results = run_calibrated_model(cfg, container, fids, calibrated_params)

    all_models = OPEN_SOURCE_MODELS + ["ensemble"]
    rows = []
    for fid in fids:
        flux_et = load_flux_et(fid, flux_dir)
        if flux_et.empty:
            continue

        model_df = model_results[fid]
        swim_et = model_df["et_act"]

        # Intersect daily indices first, then aggregate to monthly
        daily_common = swim_et.index.intersection(flux_et.index)
        if len(daily_common) < 30:
            print(f"  {fid}: only {len(daily_common)} daily overlap, skipping")
            continue

        swim_daily = swim_et.loc[daily_common]
        flux_daily = flux_et.loc[daily_common]

        # Aggregate to monthly totals
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

        row = {"fid": fid}
        m = calc_metrics(obs, swim_monthly.loc[common].values)
        row["n"] = m["n"]
        for k in ["r2", "r", "rmse", "bias"]:
            row[f"{k}_swim"] = m[k]

        # Volk monthly
        volk_monthly = load_volk_monthly_et(fid, monthly_dir)
        for model_name in all_models:
            if model_name not in volk_monthly:
                for k in ["r2", "r", "rmse", "bias"]:
                    row[f"{k}_{model_name}"] = np.nan
                continue

            volk_on_common = volk_monthly[model_name].reindex(common)
            valid = np.isfinite(volk_on_common.values) & np.isfinite(obs)
            if valid.sum() >= 6:
                m = calc_metrics(obs, volk_on_common.values)
            else:
                m = {"r2": np.nan, "r": np.nan, "rmse": np.nan, "bias": np.nan}

            for k in ["r2", "r", "rmse", "bias"]:
                row[f"{k}_{model_name}"] = m[k]

        rows.append(row)
        print(
            f"  {fid}: n={row['n']:>3d} mo  "
            f"R2_swim={row['r2_swim']:.3f}  R2_ens={row['r2_ensemble']:.3f}  "
            f"RMSE_swim={row['rmse_swim']:.1f}  RMSE_ens={row['rmse_ensemble']:.1f}"
        )

    if not rows:
        print("No fields with sufficient data.")
        return pd.DataFrame()

    metrics_df = pd.DataFrame(rows).set_index("fid")

    # Aggregate
    has_both = metrics_df["r2_swim"].notna() & metrics_df["r2_ensemble"].notna()
    common_df = metrics_df.loc[has_both]

    print("\n" + "=" * 80)
    print(f"MONTHLY AGGREGATE ({len(common_df)} fields with both SWIM and ensemble)")
    print("=" * 80)
    header = f"{'model':<12}  {'r2_mean':>10}  {'r2_med':>10}  {'r_mean':>10}  {'r_med':>10}  {'rmse_mean':>10}  {'rmse_med':>10}  {'bias_mean':>10}  {'bias_med':>10}"
    print(header)
    print("-" * len(header))

    for model_name in ["swim"] + all_models:
        r2_col = f"r2_{model_name}"
        if r2_col not in common_df.columns:
            continue
        vals = common_df[r2_col].dropna()
        if vals.empty:
            continue
        line = f"{model_name:<12}"
        for stat in ["r2", "r", "rmse", "bias"]:
            col = f"{stat}_{model_name}"
            s = common_df[col].dropna()
            line += f"  {s.mean():>10.3f}  {s.median():>10.3f}"
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
    parser.add_argument(
        "--openet-source",
        type=str,
        choices=["diy", "volk"],
        default="volk",
        help="'diy' = our ETf extracts × ETo, 'volk' = OpenET 3x3 daily ET CSVs",
    )
    parser.add_argument(
        "--etf",
        action="store_true",
        help="Compare SWIM ETf vs OpenET ETf at capture dates (instead of ET vs flux)",
    )
    parser.add_argument(
        "--monthly",
        action="store_true",
        help="Monthly ET totals: SWIM vs flux vs Volk 3x3 monthly CSVs",
    )
    parser.add_argument(
        "--container",
        type=str,
        default=None,
        help="Override container path (default: derived from config)",
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
            metrics = evaluate_monthly(cfg, container, par_csv, fids, flux_dir)
            out_csv = os.path.join(results_dir, "evaluation_monthly_metrics.csv")
        elif args.etf:
            metrics = evaluate_etf(cfg, container, par_csv, fids)
            out_csv = os.path.join(results_dir, "evaluation_etf_metrics.csv")
        else:
            metrics = evaluate(cfg, container, par_csv, fids, flux_dir, args.openet_source)
            out_csv = os.path.join(results_dir, "evaluation_metrics.csv")
        os.makedirs(results_dir, exist_ok=True)
        metrics.to_csv(out_csv)
        print(f"\nMetrics saved to {out_csv}")
    finally:
        container.close()
