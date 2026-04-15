"""Evaluate SSEBop 18-site calibration against flux tower ET (policy-compliant).

Implements the common validation policy in examples/VALIDATION_POLICY.md and
the Ex6-specific intercomparison policy in
examples/6_Flux_International/notes/INTERCOMPARISON_POLICY.

Headline policy (Volk-style):
  - Primary benchmark: ET_corr from /nas/climate/flux_stations/qaqc/...
  - Site minimum data: >=90 valid daily ET_corr obs AND >=3 qualifying
    months (>=20 valid days each).
  - SWIM vs Landsat SSEBop head-to-head is paired on Landsat overpass
    dates only (both products scored on identical valid days).
  - Primary metrics: bias, MAE, RMSE, pooled R2, regression slope.
  - Per-site error stats (bias, MAE, RMSE) aggregated with sqrt(n_paired)
    weighting; pooled R2 computed from stacked paired observations.
  - KGE, Pearson r, and median-across-sites are reported as secondary
    diagnostics.
  - Supplemental block: full-daily SWIM vs flux (continuous daily product
    policy).

Usage:
    uv run python examples/6_Flux_International/evaluate_ssebop.py
"""

import json
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import r2_score, root_mean_squared_error

from swimrs.container import SwimContainer
from swimrs.process.input import build_swim_input
from swimrs.process.loop_fast import run_daily_loop_fast
from swimrs.swim.config import ProjectConfig

TOML = Path(__file__).resolve().parent / "6_Flux_International_SSEBop.toml"
OUT_DIR = Path(__file__).resolve().parent

FLUX_DIRS = [
    Path("/nas/climate/flux_stations/qaqc/ameriflux"),
    Path("/nas/climate/flux_stations/qaqc/fluxnet"),
    Path("/nas/climate/flux_stations/qaqc/icos"),
    Path("/nas/climate/flux_stations/qaqc/ozflux"),
]
MANIFEST = Path("/nas/climate/flux_stations/reports/manifest.csv")

# Common-framework thresholds (examples/VALIDATION_POLICY.md)
MIN_DAILY_OBS = 90
MIN_QUALIFYING_MONTHS = 3
MIN_DAYS_PER_MONTH = 20
GROUP_DAILY_INCL_THRESHOLD = 6  # Ex6 intercomparison policy

# Per-policy excluded sites
EXCLUDED_SITES = {"MB_Pch"}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


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


def _load_flux_et(sid: str) -> pd.DataFrame | None:
    """Return daily ET_corr DataFrame, selecting by most post-2018 days.

    ET_corr is already benchmark-compliant per BENCHMARK_BUILD_POLICY.md:
    any day with finite ET_corr has been observed-and-closure-corrected from
    sub-daily fluxes with gap limits enforced. Days that failed the benchmark
    build are left as NaN and naturally excluded from paired-day metrics.
    """
    eco_start = pd.Timestamp("2018-01-01")
    candidates = [
        d / f"{sid}_daily_data.csv" for d in FLUX_DIRS if (d / f"{sid}_daily_data.csv").exists()
    ]
    best = None
    best_key = (-1, -1)
    for path in candidates:
        df = pd.read_csv(path, parse_dates=["date"])
        if "ET_corr" not in df.columns:
            continue
        s = df.set_index("date")["ET_corr"].dropna()
        if len(s) == 0:
            continue
        n_post2018 = int((s.index >= eco_start).sum())
        key = (n_post2018, len(s))
        if key > best_key:
            best = (
                df[["date", "ET_corr"]]
                .rename(columns={"ET_corr": "ET_flux"})
                .dropna(subset=["ET_flux"])
            )
            best_key = key
    return best


def _load_manifest_metadata() -> pd.DataFrame:
    """Load station class and benchmark-tier metadata for cohort reporting."""
    m = pd.read_csv(MANIFEST)
    cols = ["site_id", "network", "station_class", "benchmark_tier", "strict_eligible"]
    return m[[c for c in cols if c in m.columns]].drop_duplicates("site_id")


def _extract_params_from_container(container: SwimContainer) -> dict[str, dict[str, float]]:
    uids = container.field_uids
    root = container._root
    cal = np.array(root["calibration/metadata/calibrated"][:])
    params: dict[str, dict[str, float]] = {}
    for pname in root["calibration/parameters"]:
        arr = np.array(root[f"calibration/parameters/{pname}"][:])
        for i, uid in enumerate(uids):
            if cal[i] and not np.isnan(arr[i]):
                params.setdefault(uid, {})[pname] = float(arr[i])
    return params


# ---------------------------------------------------------------------------
# Policy gates
# ---------------------------------------------------------------------------


def qualifies_for_headline(flux_df: pd.DataFrame) -> tuple[bool, int, int]:
    """Check site minimum data per common framework.

    Returns (passes, n_valid_days, n_qualifying_months).
    """
    if flux_df is None or flux_df.empty:
        return False, 0, 0
    s = flux_df.dropna(subset=["ET_flux"])
    n_days = len(s)
    month_counts = s.assign(ym=s["date"].dt.to_period("M")).groupby("ym").size()
    n_qualifying = int((month_counts >= MIN_DAYS_PER_MONTH).sum())
    passes = n_days >= MIN_DAILY_OBS and n_qualifying >= MIN_QUALIFYING_MONTHS
    return passes, n_days, n_qualifying


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def primary_metrics(obs: np.ndarray, mod: np.ndarray) -> dict:
    """Volk-style primary metrics: bias, MAE, RMSE, R2, Pearson r, KGE.

    Per-site metrics. Aggregation (sqrt-n weighting, pooled R2) is done
    separately at the group level.
    """
    mask = np.isfinite(obs) & np.isfinite(mod)
    obs, mod = obs[mask], mod[mask]
    n = len(obs)
    if n < GROUP_DAILY_INCL_THRESHOLD:
        return dict(
            n=n, bias=np.nan, mae=np.nan, rmse=np.nan, r2=np.nan, r=np.nan, kge=np.nan, slope=np.nan
        )
    bias = float((mod - obs).mean())
    mae = float(np.abs(mod - obs).mean())
    rmse = float(root_mean_squared_error(obs, mod))
    r2 = float(r2_score(obs, mod))
    r, _ = stats.pearsonr(obs, mod)
    r = float(r)
    # Ordinary least squares slope of mod on obs
    if np.std(obs) > 0:
        slope = float(np.cov(obs, mod, ddof=0)[0, 1] / np.var(obs))
    else:
        slope = np.nan
    # KGE (secondary diagnostic)
    alpha = float(np.std(mod) / np.std(obs)) if np.std(obs) > 0 else np.nan
    beta = float(np.mean(mod) / np.mean(obs)) if np.mean(obs) > 0 else np.nan
    kge = 1.0 - float(np.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2))
    return dict(n=n, bias=bias, mae=mae, rmse=rmse, r2=r2, r=r, kge=kge, slope=slope)


def weighted_agg(df: pd.DataFrame, value_col: str, n_col: str) -> float:
    """sqrt(n)-weighted aggregation of per-site values (Ex6 policy)."""
    sub = df.dropna(subset=[value_col, n_col])
    if sub.empty:
        return np.nan
    w = np.sqrt(sub[n_col].astype(float).values)
    v = sub[value_col].astype(float).values
    return float(np.sum(w * v) / np.sum(w))


def pooled_r2_and_slope(
    paired_by_site: dict[str, tuple[np.ndarray, np.ndarray]],
) -> tuple[float, float]:
    """Pool all paired obs across sites in a group, compute one R2 and slope."""
    if not paired_by_site:
        return np.nan, np.nan
    obs_all = np.concatenate([p[0] for p in paired_by_site.values()])
    mod_all = np.concatenate([p[1] for p in paired_by_site.values()])
    mask = np.isfinite(obs_all) & np.isfinite(mod_all)
    obs_all, mod_all = obs_all[mask], mod_all[mask]
    if len(obs_all) < GROUP_DAILY_INCL_THRESHOLD:
        return np.nan, np.nan
    r2 = float(r2_score(obs_all, mod_all))
    if np.std(obs_all) > 0:
        slope = float(np.cov(obs_all, mod_all, ddof=0)[0, 1] / np.var(obs_all))
    else:
        slope = np.nan
    return r2, slope


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    cfg = ProjectConfig()
    cfg.read_config(str(TOML), calibrate=False)

    container = SwimContainer.open(str(cfg.container_path), mode="r")
    all_uids = container.field_uids

    print("Extracting calibrated parameters from container...")
    params = _extract_params_from_container(container)
    sites = sorted(s for s in params.keys() if s not in EXCLUDED_SITES)
    print(f"  {len(sites)} calibrated sites (after policy exclusions)")

    fd, params_path = tempfile.mkstemp(suffix=".json", prefix="ssebop_eval_")
    os.close(fd)
    with open(params_path, "w") as f:
        json.dump(params, f)

    fd, h5_path = tempfile.mkstemp(suffix=".h5", prefix="ssebop_eval_")
    os.close(fd)
    Path(h5_path).unlink(missing_ok=True)

    try:
        print("Building SwimInput with calibrated parameters...")
        swim_input = build_swim_input(
            container,
            output_h5=h5_path,
            calibrated_params_path=params_path,
            refet_type=getattr(cfg, "refet_type", "eto") or "eto",
            etf_model=getattr(cfg, "etf_target_model", "ssebop"),
            met_source=getattr(cfg, "met_source", "era5"),
            mask_mode=getattr(cfg, "mask_mode", "none"),
            empirical_kc_max=True,
            fields=sites,
        )
        print(f"Running forward model ({swim_input.n_fields} sites x {swim_input.n_days} days)...")
        output, _ = run_daily_loop_fast(swim_input)
        time_index = pd.date_range(swim_input.start_date, periods=swim_input.n_days, freq="D")
        eta = output.eta
    finally:
        Path(h5_path).unlink(missing_ok=True)
        Path(params_path).unlink(missing_ok=True)

    site_idx = {sid: j for j, sid in enumerate(sites)}

    # Resolve ETo path the same way build_swim_input does (prefer eto_corr).
    root = container._root
    ls_etf_all = root["remote_sensing/etf/landsat/ssebop/no_mask"][:]
    met_source = getattr(cfg, "met_source", "era5")
    refet_type = getattr(cfg, "refet_type", "eto") or "eto"
    eto_corr_path = f"meteorology/{met_source}/{refet_type}_corr"
    eto_path = f"meteorology/{met_source}/{refet_type}"
    eto_resolved = eto_corr_path if eto_corr_path in root else eto_path
    print(f"Using ETo path for Landsat benchmark: {eto_resolved}")
    eto_all = root[eto_resolved][:]
    container.close()

    # Manifest metadata (station class per site)
    manifest_md = _load_manifest_metadata().set_index("site_id")

    # Per-site filtering and per-site metrics
    print(
        f"\nApplying site minimum data filter "
        f"(>= {MIN_DAILY_OBS} valid days AND >= {MIN_QUALIFYING_MONTHS} months "
        f"with >= {MIN_DAYS_PER_MONTH} days)..."
    )

    eligible_records = []
    excluded_records = []

    # Keep paired arrays per site for pooled stats
    paired_swim_overpass: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    paired_ls_overpass: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    paired_swim_daily: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    for sid in sites:
        flux_df = _load_flux_et(sid)
        passes, n_days, n_q_months = qualifies_for_headline(flux_df)
        st_class = manifest_md.loc[sid]["station_class"] if sid in manifest_md.index else "UNK"

        if not passes:
            excluded_records.append(
                {
                    "sid": sid,
                    "n_flux_days": n_days,
                    "n_qualifying_months": n_q_months,
                    "station_class": st_class,
                    "reason": f"below threshold ({n_days} days, {n_q_months} months)",
                }
            )
            continue

        j = site_idx[sid]
        cidx = all_uids.index(sid)
        sim = pd.DataFrame({"date": time_index, "ET_sim": eta[:, j]})

        # Landsat SSEBop ET on overpass dates
        ls_et = ls_etf_all[:, cidx] * eto_all[:, cidx]
        ls_et[~np.isfinite(ls_etf_all[:, cidx])] = np.nan
        ls_df = pd.DataFrame({"date": time_index, "ET_ls": ls_et})

        # Daily SWIM vs flux (continuous-daily-product policy)
        daily = pd.merge(flux_df, sim, on="date", how="inner").dropna()
        m_swim_daily = primary_metrics(daily["ET_flux"].values, daily["ET_sim"].values)
        if np.isfinite(m_swim_daily["bias"]):
            paired_swim_daily[sid] = (daily["ET_flux"].values, daily["ET_sim"].values)

        # Paired overpass dates: SWIM and SSEBop scored on identical valid days
        triple = pd.merge(flux_df, sim, on="date", how="inner")
        triple = pd.merge(triple, ls_df, on="date", how="inner").dropna()
        m_swim_op = primary_metrics(triple["ET_flux"].values, triple["ET_sim"].values)
        m_ls_op = primary_metrics(triple["ET_flux"].values, triple["ET_ls"].values)
        if np.isfinite(m_swim_op["bias"]) and np.isfinite(m_ls_op["bias"]):
            paired_swim_overpass[sid] = (triple["ET_flux"].values, triple["ET_sim"].values)
            paired_ls_overpass[sid] = (triple["ET_flux"].values, triple["ET_ls"].values)

        eligible_records.append(
            {
                "sid": sid,
                "station_class": st_class,
                "n_flux_days": n_days,
                "n_qualifying_months": n_q_months,
                # Continuous-daily SWIM (all paired non-null ET_corr days)
                "swim_daily_n": m_swim_daily["n"],
                "swim_daily_bias": m_swim_daily["bias"],
                "swim_daily_mae": m_swim_daily["mae"],
                "swim_daily_rmse": m_swim_daily["rmse"],
                "swim_daily_r2": m_swim_daily["r2"],
                "swim_daily_r": m_swim_daily["r"],
                "swim_daily_kge": m_swim_daily["kge"],
                # Head-to-head: overpass dates
                "op_n": m_swim_op["n"],
                "swim_op_bias": m_swim_op["bias"],
                "swim_op_mae": m_swim_op["mae"],
                "swim_op_rmse": m_swim_op["rmse"],
                "swim_op_r2": m_swim_op["r2"],
                "swim_op_r": m_swim_op["r"],
                "swim_op_kge": m_swim_op["kge"],
                "swim_op_slope": m_swim_op["slope"],
                "ls_op_bias": m_ls_op["bias"],
                "ls_op_mae": m_ls_op["mae"],
                "ls_op_rmse": m_ls_op["rmse"],
                "ls_op_r2": m_ls_op["r2"],
                "ls_op_r": m_ls_op["r"],
                "ls_op_kge": m_ls_op["kge"],
                "ls_op_slope": m_ls_op["slope"],
            }
        )

    eligible_df = pd.DataFrame(eligible_records)
    excluded_df = pd.DataFrame(excluded_records)

    # LULC attachment
    LULC_NAMES = {
        1: "ENF",
        2: "EBF",
        3: "DNF",
        4: "DBF",
        5: "MixForest",
        6: "ClosedShrub",
        7: "OpenShrub",
        8: "WoodySav",
        9: "Savanna",
        10: "Grassland",
        12: "Cropland",
        14: "CropNatMos",
    }
    gdf = gpd.read_file(cfg.fields_shapefile, engine="fiona")
    lulc_map = _glc10_lulc_map(gdf)
    eligible_df["lulc"] = eligible_df["sid"].map(lulc_map).fillna(0).astype(int)
    eligible_df["lulc_name"] = eligible_df["lulc"].map(lambda x: LULC_NAMES.get(x, f"LC{x}"))

    # Save CSVs
    eligible_df.to_csv(OUT_DIR / "ssebop_evaluation.csv", index=False)
    excluded_df.to_csv(OUT_DIR / "ssebop_evaluation_excluded.csv", index=False)

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print(
        f"\nEligible cohort (headline): {len(eligible_df)} sites. "
        f"Excluded (below threshold): {len(excluded_df)} sites."
    )
    if not excluded_df.empty:
        for _, r in excluded_df.iterrows():
            print(f"  EXCLUDED {r['sid']} ({r['station_class']}): {r['reason']}")
    print(
        f"Station classes in eligible cohort: {dict(eligible_df['station_class'].value_counts())}"
    )

    # ----- Per-site headline table (overpass-paired, Volk-style primary) ----
    print("\n" + "=" * 95)
    print(
        "HEADLINE: SWIM vs Landsat SSEBop, paired Landsat overpass dates (common-date comparison)"
    )
    print("=" * 95)
    hdr = (
        f"{'SID':<10} {'class':>5} {'n':>5}  "
        f"{'SWIM bias':>9} {'SWIM mae':>8} {'SWIM rmse':>9} {'SWIM r2':>7} "
        f"{'SWIM sl':>7}  "
        f"{'LS bias':>9} {'LS mae':>8} {'LS rmse':>9} {'LS r2':>7} {'LS sl':>7}"
    )
    print(hdr)
    print("-" * len(hdr))
    valid_op = eligible_df.dropna(subset=["swim_op_bias", "ls_op_bias"]).sort_values("sid")
    for _, r in valid_op.iterrows():
        print(
            f"{r['sid']:<10} {r['station_class']:>5} {int(r['op_n']):5d}  "
            f"{r['swim_op_bias']:+9.3f} {r['swim_op_mae']:8.3f} {r['swim_op_rmse']:9.3f} "
            f"{r['swim_op_r2']:7.3f} {r['swim_op_slope']:7.3f}  "
            f"{r['ls_op_bias']:+9.3f} {r['ls_op_mae']:8.3f} {r['ls_op_rmse']:9.3f} "
            f"{r['ls_op_r2']:7.3f} {r['ls_op_slope']:7.3f}"
        )

    # ----- Headline aggregate (sqrt-n weighted, pooled R2) -----
    print("-" * len(hdr))
    sw_bias = weighted_agg(valid_op, "swim_op_bias", "op_n")
    sw_mae = weighted_agg(valid_op, "swim_op_mae", "op_n")
    sw_rmse = weighted_agg(valid_op, "swim_op_rmse", "op_n")
    ls_bias = weighted_agg(valid_op, "ls_op_bias", "op_n")
    ls_mae = weighted_agg(valid_op, "ls_op_mae", "op_n")
    ls_rmse = weighted_agg(valid_op, "ls_op_rmse", "op_n")
    sw_r2_pooled, sw_slope_pooled = pooled_r2_and_slope(paired_swim_overpass)
    ls_r2_pooled, ls_slope_pooled = pooled_r2_and_slope(paired_ls_overpass)

    total_op_n = int(valid_op["op_n"].sum())
    print(
        f"{'AGGREGATE':<10} {'':>5} {total_op_n:5d}  "
        f"{sw_bias:+9.3f} {sw_mae:8.3f} {sw_rmse:9.3f} {sw_r2_pooled:7.3f} "
        f"{sw_slope_pooled:7.3f}  "
        f"{ls_bias:+9.3f} {ls_mae:8.3f} {ls_rmse:9.3f} {ls_r2_pooled:7.3f} "
        f"{ls_slope_pooled:7.3f}"
    )
    print(
        "  (bias/MAE/RMSE: sqrt(n)-weighted across sites; R2/slope: pooled across all paired obs)"
    )
    print(f"  Station-class composition: {dict(valid_op['station_class'].value_counts())}")

    # ----- By LULC (paired overpass, primary metrics) -----
    print("\n--- By LULC (paired overpass dates, primary metrics) ---")
    hdr = (
        f"{'LULC':<12} {'sites':>5} {'n':>6}  "
        f"{'SWIM bias':>9} {'SWIM rmse':>9} {'SWIM r2p':>8}  "
        f"{'LS bias':>9} {'LS rmse':>9} {'LS r2p':>8}  {'winner':>6}"
    )
    print(hdr)
    print("-" * len(hdr))
    for lc_name, grp in sorted(valid_op.groupby("lulc_name"), key=lambda x: -len(x[1])):
        grp_sites = list(grp["sid"])
        pool_sw = {s: paired_swim_overpass[s] for s in grp_sites if s in paired_swim_overpass}
        pool_ls = {s: paired_ls_overpass[s] for s in grp_sites if s in paired_ls_overpass}
        sw_r2_lc, _ = pooled_r2_and_slope(pool_sw)
        ls_r2_lc, _ = pooled_r2_and_slope(pool_ls)
        sw_b_lc = weighted_agg(grp, "swim_op_bias", "op_n")
        sw_rm_lc = weighted_agg(grp, "swim_op_rmse", "op_n")
        ls_b_lc = weighted_agg(grp, "ls_op_bias", "op_n")
        ls_rm_lc = weighted_agg(grp, "ls_op_rmse", "op_n")
        n_total = int(grp["op_n"].sum())
        # Winner: lower RMSE is better for paired Volk-style
        winner = "SWIM" if sw_rm_lc <= ls_rm_lc else "LS"
        print(
            f"{lc_name:<12} {len(grp):5d} {n_total:6d}  "
            f"{sw_b_lc:+9.3f} {sw_rm_lc:9.3f} {sw_r2_lc:8.3f}  "
            f"{ls_b_lc:+9.3f} {ls_rm_lc:9.3f} {ls_r2_lc:8.3f}  {winner:>6}"
        )

    # ----- Supplemental: continuous-daily SWIM vs flux -----
    print("\n" + "=" * 70)
    print("SUPPLEMENTAL: continuous-daily SWIM vs flux (all paired non-null ET_corr days)")
    print("=" * 70)
    valid_daily = eligible_df.dropna(subset=["swim_daily_bias"])
    sw_d_bias = weighted_agg(valid_daily, "swim_daily_bias", "swim_daily_n")
    sw_d_mae = weighted_agg(valid_daily, "swim_daily_mae", "swim_daily_n")
    sw_d_rmse = weighted_agg(valid_daily, "swim_daily_rmse", "swim_daily_n")
    sw_d_r2_pooled, sw_d_slope_pooled = pooled_r2_and_slope(paired_swim_daily)
    total_daily_n = int(valid_daily["swim_daily_n"].sum())
    print(
        f"sites={len(valid_daily)}  n_paired_days={total_daily_n}  "
        f"bias={sw_d_bias:+.3f}  mae={sw_d_mae:.3f}  rmse={sw_d_rmse:.3f}  "
        f"pooled_R2={sw_d_r2_pooled:.3f}  pooled_slope={sw_d_slope_pooled:.3f}"
    )

    # ----- Secondary diagnostics -----
    print("\n--- Secondary diagnostics (KGE, Pearson r, median across sites) ---")
    if not valid_op.empty:
        print(
            f"Overpass (headline paired): "
            f"SWIM median KGE={valid_op['swim_op_kge'].median():.3f}  "
            f"SWIM median r={valid_op['swim_op_r'].median():.3f}  "
            f"LS median KGE={valid_op['ls_op_kge'].median():.3f}  "
            f"LS median r={valid_op['ls_op_r'].median():.3f}"
        )
    if not valid_daily.empty:
        print(
            f"Daily (supplemental):     "
            f"SWIM median KGE={valid_daily['swim_daily_kge'].median():.3f}  "
            f"SWIM median r={valid_daily['swim_daily_r'].median():.3f}"
        )

    print(f"\nSaved: {OUT_DIR / 'ssebop_evaluation.csv'}")
    print(f"Saved: {OUT_DIR / 'ssebop_evaluation_excluded.csv'}")

    # ----- Plot: SWIM vs LS per-site primary metrics, colored by LULC -----
    lulc_colors = {
        "Cropland": "#e6a817",
        "CropNatMos": "#daa520",
        "DBF": "#2ca02c",
        "DNF": "#66c266",
        "EBF": "#006400",
        "ENF": "#1a7a1a",
        "MixForest": "#98df8a",
        "WoodySav": "#8c6d3f",
        "Savanna": "#d6b656",
        "Grassland": "#b5cf6b",
        "OpenShrub": "#c49c94",
        "ClosedShrub": "#a0522d",
    }
    fig = plt.figure(figsize=(15, 5))
    class_counts = dict(valid_op["station_class"].value_counts())
    fig.suptitle(
        f"SSEBop 18-site calibration - SWIM vs Landsat SSEBop, Landsat overpass dates only. "
        f"Eligible n={len(valid_op)} ({', '.join(f'{k}={v}' for k, v in class_counts.items())}). "
        f"Headline primary metrics.",
        fontsize=10,
    )
    for i, (swim_col, ls_col, xlabel, title) in enumerate(
        [
            ("swim_op_bias", "ls_op_bias", "bias (mm/d)", "Bias"),
            ("swim_op_rmse", "ls_op_rmse", "RMSE (mm/d)", "RMSE"),
            ("swim_op_mae", "ls_op_mae", "MAE (mm/d)", "MAE"),
        ]
    ):
        ax = fig.add_subplot(1, 3, i + 1)
        plotted_labels = set()
        for _, row in valid_op.iterrows():
            lbl = row["lulc_name"]
            color = lulc_colors.get(lbl, "grey")
            ax.scatter(
                row[ls_col],
                row[swim_col],
                s=30,
                color=color,
                alpha=0.7,
                zorder=3,
                label=lbl if lbl not in plotted_labels else None,
            )
            plotted_labels.add(lbl)
        v_swim = valid_op[swim_col].values
        v_ls = valid_op[ls_col].values
        lo = min(np.nanmin(v_swim), np.nanmin(v_ls)) - 0.1
        hi = max(np.nanmax(v_swim), np.nanmax(v_ls)) + 0.1
        ax.plot([lo, hi], [lo, hi], "k--", lw=1, alpha=0.5)
        if swim_col == "swim_op_bias":
            ax.axhline(0, color="grey", lw=0.8, ls=":")
            ax.axvline(0, color="grey", lw=0.8, ls=":")
        ax.set_xlabel(f"Landsat SSEBop {xlabel}")
        ax.set_ylabel(f"SWIM {xlabel}")
        ax.set_title(title)
        if i == 0:
            ax.legend(fontsize=6, loc="upper left")

    plt.tight_layout()
    out_png = OUT_DIR / "ssebop_evaluation.png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_png}")


if __name__ == "__main__":
    main()
