"""Evaluate SSEBop-ETA-normalized 18-site calibration against flux ET.

Mirror of evaluate_ssebop.py with two changes:
  - Loads the SSEBop-ETA container (ETF rebuilt as native_ETA / ERA5_ETo).
  - Benchmark column is product-native SSEBop ETA (from eta_json/) instead
    of ETF * ERA5_ETo reconstruction.

The training target and validation reference are now both expressed in the
same physical units (mm/d) and on the same reference ET basis.

Usage:
    uv run python examples/6_Flux_International/evaluate_ssebop_eta.py
"""

from __future__ import annotations

import importlib.util
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

from swimrs.container import SwimContainer
from swimrs.process.input import build_swim_input
from swimrs.process.loop_fast import run_daily_loop_fast
from swimrs.swim.config import ProjectConfig

# Reuse policy machinery from the reconstruction-evaluator
_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("evaluate_ssebop_mod", _HERE / "evaluate_ssebop.py")
_eval_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_eval_mod)

_load_flux_et = _eval_mod._load_flux_et
_load_manifest_metadata = _eval_mod._load_manifest_metadata
_extract_params_from_container = _eval_mod._extract_params_from_container
qualifies_for_headline = _eval_mod.qualifies_for_headline
primary_metrics = _eval_mod.primary_metrics
weighted_agg = _eval_mod.weighted_agg
pooled_r2_and_slope = _eval_mod.pooled_r2_and_slope

MIN_DAILY_OBS = _eval_mod.MIN_DAILY_OBS
MIN_QUALIFYING_MONTHS = _eval_mod.MIN_QUALIFYING_MONTHS
MIN_DAYS_PER_MONTH = _eval_mod.MIN_DAYS_PER_MONTH
EXCLUDED_SITES = _eval_mod.EXCLUDED_SITES

TOML = _HERE / "6_Flux_International_SSEBop_ETA.toml"
OUT_DIR = _HERE
ETA_JSON_DIR = Path(
    "/data/ssd1/swim/6_Flux_International/data/remote_sensing/espa/extracts/eta_json"
)


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


def _load_native_eta(site: str) -> pd.DataFrame:
    """Concat all per-year native ETA JSONs for a site -> DataFrame[date, ET_native]."""
    rows = []
    for p in sorted(ETA_JSON_DIR.glob(f"{site}_*_eta.json")):
        with open(p) as f:
            payload = json.load(f)
        site_data = payload.get(site) or next(iter(payload.values()), {})
        for date_key, stats in site_data.items():
            mean_val = stats.get("mean")
            if mean_val is None or not np.isfinite(mean_val):
                continue
            rows.append({"date": pd.Timestamp(date_key), "ET_ls": float(mean_val)})
    if not rows:
        return pd.DataFrame(columns=["date", "ET_ls"])
    return pd.DataFrame(rows).drop_duplicates("date").sort_values("date").reset_index(drop=True)


def main() -> None:
    cfg = ProjectConfig()
    cfg.read_config(str(TOML), calibrate=False)

    container = SwimContainer.open(str(cfg.container_path), mode="r")
    all_uids = container.field_uids

    print("Extracting calibrated parameters from container...")
    params = _extract_params_from_container(container)
    sites = sorted(s for s in params.keys() if s not in EXCLUDED_SITES)
    print(f"  {len(sites)} calibrated sites (after policy exclusions)")

    fd, params_path = tempfile.mkstemp(suffix=".json", prefix="ssebop_eta_eval_")
    os.close(fd)
    with open(params_path, "w") as f:
        json.dump(params, f)

    fd, h5_path = tempfile.mkstemp(suffix=".h5", prefix="ssebop_eta_eval_")
    os.close(fd)
    Path(h5_path).unlink(missing_ok=True)

    try:
        print("Building SwimInput with calibrated parameters...")
        swim_input = build_swim_input(
            container,
            output_h5=h5_path,
            calibrated_params_path=params_path,
            refet_type=getattr(cfg, "refet_type", "eto") or "eto",
            etf_model=getattr(cfg, "etf_target_model", "ssebop_eta"),
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
    container.close()

    site_idx = {sid: j for j, sid in enumerate(sites)}
    manifest_md = _load_manifest_metadata().set_index("site_id")

    print(
        f"\nApplying site minimum data filter "
        f"(>= {MIN_DAILY_OBS} valid days AND >= {MIN_QUALIFYING_MONTHS} months "
        f"with >= {MIN_DAYS_PER_MONTH} days)..."
    )

    eligible_records = []
    excluded_records = []

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
        sim = pd.DataFrame({"date": time_index, "ET_sim": eta[:, j]})

        # Native ETA on overpass dates (mm/d)
        native_df = _load_native_eta(sid)

        # Daily SWIM vs flux (continuous-daily-product policy)
        daily = pd.merge(flux_df, sim, on="date", how="inner").dropna()
        m_swim_daily = primary_metrics(daily["ET_flux"].values, daily["ET_sim"].values)
        if np.isfinite(m_swim_daily["bias"]):
            paired_swim_daily[sid] = (daily["ET_flux"].values, daily["ET_sim"].values)

        # Paired overpass dates: SWIM and native SSEBop ETA scored on identical valid days
        triple = pd.merge(flux_df, sim, on="date", how="inner")
        triple = pd.merge(triple, native_df, on="date", how="inner").dropna()
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
                "swim_daily_n": m_swim_daily["n"],
                "swim_daily_bias": m_swim_daily["bias"],
                "swim_daily_mae": m_swim_daily["mae"],
                "swim_daily_rmse": m_swim_daily["rmse"],
                "swim_daily_r2": m_swim_daily["r2"],
                "swim_daily_r": m_swim_daily["r"],
                "swim_daily_kge": m_swim_daily["kge"],
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

    eligible_df.to_csv(OUT_DIR / "ssebop_eta_evaluation.csv", index=False)
    excluded_df.to_csv(OUT_DIR / "ssebop_eta_evaluation_excluded.csv", index=False)

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

    # ----- Per-site headline (paired Landsat overpass dates, native ETA bench) -----
    print("\n" + "=" * 95)
    print(
        "HEADLINE: SWIM vs SSEBop NATIVE ETA, paired Landsat overpass dates "
        "(common-date comparison)"
    )
    print("=" * 95)
    hdr = (
        f"{'SID':<10} {'class':>5} {'n':>5}  "
        f"{'SWIM bias':>9} {'SWIM mae':>8} {'SWIM rmse':>9} {'SWIM r2':>7} "
        f"{'SWIM sl':>7}  "
        f"{'NAT bias':>9} {'NAT mae':>8} {'NAT rmse':>9} {'NAT r2':>7} {'NAT sl':>7}"
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

    # ----- By LULC -----
    print("\n--- By LULC (paired overpass dates, primary metrics) ---")
    hdr = (
        f"{'LULC':<12} {'sites':>5} {'n':>6}  "
        f"{'SWIM bias':>9} {'SWIM rmse':>9} {'SWIM r2p':>8}  "
        f"{'NAT bias':>9} {'NAT rmse':>9} {'NAT r2p':>8}  {'winner':>6}"
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
        winner = "SWIM" if sw_rm_lc <= ls_rm_lc else "NAT"
        print(
            f"{lc_name:<12} {len(grp):5d} {n_total:6d}  "
            f"{sw_b_lc:+9.3f} {sw_rm_lc:9.3f} {sw_r2_lc:8.3f}  "
            f"{ls_b_lc:+9.3f} {ls_rm_lc:9.3f} {ls_r2_lc:8.3f}  {winner:>6}"
        )

    # ----- Supplemental -----
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
            f"NAT median KGE={valid_op['ls_op_kge'].median():.3f}  "
            f"NAT median r={valid_op['ls_op_r'].median():.3f}"
        )
    if not valid_daily.empty:
        print(
            f"Daily (supplemental):     "
            f"SWIM median KGE={valid_daily['swim_daily_kge'].median():.3f}  "
            f"SWIM median r={valid_daily['swim_daily_r'].median():.3f}"
        )

    print(f"\nSaved: {OUT_DIR / 'ssebop_eta_evaluation.csv'}")
    print(f"Saved: {OUT_DIR / 'ssebop_eta_evaluation_excluded.csv'}")

    # ----- Plot -----
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
        f"SSEBop-ETA 18-site calibration - SWIM vs SSEBop NATIVE ETA, overpass dates only. "
        f"Eligible n={len(valid_op)} ({', '.join(f'{k}={v}' for k, v in class_counts.items())}).",
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
        ax.set_xlabel(f"SSEBop NATIVE {xlabel}")
        ax.set_ylabel(f"SWIM {xlabel}")
        ax.set_title(title)
        if i == 0:
            ax.legend(fontsize=6, loc="upper left")

    plt.tight_layout()
    out_png = OUT_DIR / "ssebop_eta_evaluation.png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_png}")


if __name__ == "__main__":
    main()
