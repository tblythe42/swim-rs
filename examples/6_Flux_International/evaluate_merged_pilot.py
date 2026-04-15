"""Evaluate merged LS/ECO pilot calibration against flux tower ET.

Reads the iteration-3 parameter ensemble from results/group, takes the
median realization per site, runs the forward model, and compares daily
simulated ET against flux tower ET_corr.

Usage:
    uv run python examples/6_Flux_International/evaluate_merged_pilot.py
"""

import json
import os
import re
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

TOML = Path(__file__).resolve().parent / "merged_pilot.toml"
RESULTS_DIR = Path("/data/ssd1/swim/6_Flux_International/results/group")
PAR_CSV = RESULTS_DIR / "6_Flux_International.3.par.csv"
SPINUP_JSON = RESULTS_DIR / "spinup.json"
OUT_DIR = Path(__file__).resolve().parent

FLUX_DIRS = [
    Path("/nas/climate/flux_stations/qaqc/ameriflux"),
    Path("/nas/climate/flux_stations/qaqc/fluxnet"),
    Path("/nas/climate/flux_stations/qaqc/icos"),
    Path("/nas/climate/flux_stations/qaqc/ozflux"),
]
MIN_ETO = 0.5
MIN_PAIRS = 30


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
    """Return daily ET_corr DataFrame with date column, selecting by most post-2018 days."""
    ECO_START = pd.Timestamp("2018-01-01")
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
        n_post2018 = int((s.index >= ECO_START).sum())
        key = (n_post2018, len(s))
        if key > best_key:
            best = (
                df[["date", "ET_corr"]]
                .rename(columns={"ET_corr": "ET_flux"})
                .dropna(subset=["ET_flux"])
            )
            best_key = key
    return best


def _parse_params(par_csv: Path, uid_lookup: dict[str, str]) -> dict[str, dict[str, float]]:
    """Return {canonical_site_id: {param: median_value}} from ensemble par.csv.

    uid_lookup maps uppercase site ID to canonical container case (e.g. 'DE-RUW' -> 'DE-RuW').
    """
    df = pd.read_csv(par_csv, index_col=0)
    df = df[df.index != "BASE"]
    df = df.apply(pd.to_numeric, errors="coerce")

    result: dict[str, dict[str, float]] = {}
    for col in df.columns:
        m = re.match(r"pname:p_(\w+)_([a-z]{2}-\w+)_", col)
        if not m:
            continue
        param = m.group(1)
        site_upper = m.group(2).upper()
        canonical = uid_lookup.get(site_upper)
        if canonical is None:
            continue
        val = float(df[col].median())
        result.setdefault(canonical, {})[param] = val
    return result


def calc_metrics(obs: np.ndarray, mod: np.ndarray) -> dict:
    mask = np.isfinite(obs) & np.isfinite(mod)
    obs, mod = obs[mask], mod[mask]
    if len(obs) < MIN_PAIRS:
        return dict(n=len(obs), r2=np.nan, rmse=np.nan, bias=np.nan, kge=np.nan)
    r, _ = stats.pearsonr(obs, mod)
    r2 = r2_score(obs, mod)
    rmse = root_mean_squared_error(obs, mod)
    bias = float((mod - obs).mean())
    alpha = np.std(mod) / np.std(obs) if np.std(obs) > 0 else np.nan
    beta = np.mean(mod) / np.mean(obs) if np.mean(obs) > 0 else np.nan
    kge = 1.0 - np.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2)
    return dict(
        n=len(obs), r2=round(r2, 3), rmse=round(rmse, 3), bias=round(bias, 3), kge=round(kge, 3)
    )


def main():
    cfg = ProjectConfig()
    cfg.read_config(str(TOML), calibrate=False)

    # Build uppercase -> canonical case lookup from container
    container = SwimContainer.open(str(cfg.container_path), mode="r")
    uid_lookup = {uid.upper(): uid for uid in container.field_uids}

    print("Parsing parameter ensemble (median)...")
    params = _parse_params(PAR_CSV, uid_lookup)
    sites = sorted(params.keys())
    print(f"  {len(sites)} sites: {sites}")

    fd, params_path = tempfile.mkstemp(suffix=".json", prefix="merged_eval_")
    os.close(fd)
    with open(params_path, "w") as f:
        json.dump(params, f)

    fd, h5_path = tempfile.mkstemp(suffix=".h5", prefix="merged_eval_")
    os.close(fd)
    Path(h5_path).unlink(missing_ok=True)

    try:
        print("Building SwimInput with calibrated parameters...")
        swim_input = build_swim_input(
            container,
            output_h5=h5_path,
            calibrated_params_path=params_path,
            spinup_json_path=str(SPINUP_JSON) if SPINUP_JSON.exists() else None,
            refet_type=getattr(cfg, "refet_type", "eto") or "eto",
            etf_model=getattr(cfg, "etf_target_model", "ptjpl"),
            met_source=getattr(cfg, "met_source", "era5"),
            mask_mode=getattr(cfg, "mask_mode", "none"),
            fields=sites,
        )
        print(f"Running ({swim_input.n_fields} sites × {swim_input.n_days} days)...")
        output, _ = run_daily_loop_fast(swim_input)
        time_index = pd.date_range(swim_input.start_date, periods=swim_input.n_days, freq="D")
        eta = output.eta
    finally:
        Path(h5_path).unlink(missing_ok=True)
        Path(params_path).unlink(missing_ok=True)
    container.close()

    # Load Landsat PT-JPL ETf and ETo from container for head-to-head comparison
    container2 = SwimContainer.open(str(cfg.container_path), mode="r")
    all_uids = container2.field_uids
    root = container2._root
    ls_etf_all = root["remote_sensing/etf/landsat/ptjpl/no_mask"][:]
    eto_all = root["meteorology/era5/eto"][:]
    container2.close()

    print("\nComputing metrics vs flux tower ET_corr...")
    print(f"{'SID':<10}  {'--- SWIM ---':^35}  {'--- Landsat PT-JPL (obs dates) ---':^35}")
    print(
        f"{'':10}  {'n':>5} {'bias':>7} {'rmse':>7} {'r2':>7}  {'n':>5} {'bias':>7} {'rmse':>7} {'r2':>7}"
    )
    print("-" * 88)

    records = []
    for j, sid in enumerate(sites):
        flux_df = _load_flux_et(sid)
        if flux_df is None:
            continue

        cidx = all_uids.index(sid)
        sim = pd.DataFrame({"date": time_index, "ET_sim": eta[:, j]})

        # Landsat ET = ETf * ETo (observation dates only)
        ls_et = ls_etf_all[:, cidx] * eto_all[:, cidx]
        ls_et[~np.isfinite(ls_etf_all[:, cidx])] = np.nan
        ls_df = pd.DataFrame({"date": time_index, "ET_ls": ls_et})

        # Full-record SWIM vs flux
        full = pd.merge(flux_df, sim, on="date", how="inner").dropna()
        m_swim_full = calc_metrics(full["ET_flux"].values, full["ET_sim"].values)

        # On Landsat obs dates only: SWIM, Landsat, flux all matched
        triple = pd.merge(flux_df, sim, on="date", how="inner")
        triple = pd.merge(triple, ls_df, on="date", how="inner").dropna()
        m_swim_ls = calc_metrics(triple["ET_flux"].values, triple["ET_sim"].values)
        m_ls = calc_metrics(triple["ET_flux"].values, triple["ET_ls"].values)

        records.append(
            {
                "sid": sid,
                # Full record
                "swim_n": m_swim_full["n"],
                "swim_bias": m_swim_full["bias"],
                "swim_rmse": m_swim_full["rmse"],
                "swim_r2": m_swim_full["r2"],
                "swim_kge": m_swim_full["kge"],
                # On Landsat dates
                "swim_ls_n": m_swim_ls["n"],
                "swim_ls_bias": m_swim_ls["bias"],
                "swim_ls_rmse": m_swim_ls["rmse"],
                "swim_ls_r2": m_swim_ls["r2"],
                "swim_ls_kge": m_swim_ls["kge"],
                "ls_n": m_ls["n"],
                "ls_bias": m_ls["bias"],
                "ls_rmse": m_ls["rmse"],
                "ls_r2": m_ls["r2"],
                "ls_kge": m_ls["kge"],
            }
        )

        print(
            f"{sid:<10}  {m_swim_ls['n']:5d} {m_swim_ls['bias']:+7.3f} {m_swim_ls['rmse']:7.3f} "
            f"{m_swim_ls['r2']:7.3f}  {m_ls['n']:5d} {m_ls['bias']:+7.3f} {m_ls['rmse']:7.3f} "
            f"{m_ls['r2']:7.3f}"
        )

    eval_df = pd.DataFrame(records)
    out_csv = OUT_DIR / "merged_pilot_evaluation.csv"
    eval_df.to_csv(out_csv, index=False)

    # Attach LULC
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
    eval_df["lulc"] = eval_df["sid"].map(lulc_map).fillna(0).astype(int)
    eval_df["lulc_name"] = eval_df["lulc"].map(lambda x: LULC_NAMES.get(x, f"LC{x}"))
    eval_df.to_csv(out_csv, index=False)

    valid = eval_df.dropna(subset=["swim_ls_bias", "ls_bias"])
    print("-" * 88)
    print(
        f"{'ALL (median)':<10}  {valid['swim_ls_n'].median():5.0f} "
        f"{valid['swim_ls_bias'].median():+7.3f} {valid['swim_ls_rmse'].median():7.3f} "
        f"{valid['swim_ls_r2'].median():7.3f}  "
        f"{valid['ls_n'].median():5.0f} "
        f"{valid['ls_bias'].median():+7.3f} {valid['ls_rmse'].median():7.3f} "
        f"{valid['ls_r2'].median():7.3f}"
    )

    print("\n--- By LULC (median across sites, on Landsat obs dates) ---")
    hdr = f"{'LULC':<12} {'n':>2}  {'SWIM bias':>9} {'SWIM r2':>7}  {'LS bias':>9} {'LS r2':>7}  {'winner':>6}"
    print(hdr)
    print("-" * len(hdr))
    for lc_name, grp in valid.groupby("lulc_name"):
        sw_b = grp["swim_ls_bias"].median()
        sw_r = grp["swim_ls_r2"].median()
        ls_b = grp["ls_bias"].median()
        ls_r = grp["ls_r2"].median()
        winner = "SWIM" if sw_r >= ls_r else "LS"
        print(
            f"{lc_name:<12} {len(grp):2d}  {sw_b:+9.3f} {sw_r:7.3f}  {ls_b:+9.3f} {ls_r:7.3f}  {winner:>6}"
        )

    print(f"\nSaved: {out_csv}")

    # Scatter: SWIM vs Landsat PT-JPL per site, colored by LULC
    lulc_colors = {
        "Cropland": "#e6a817",
        "DBF": "#2ca02c",
        "ENF": "#1a7a1a",
        "MixForest": "#98df8a",
        "WoodySav": "#8c6d3f",
        "Savanna": "#d6b656",
        "Grassland": "#b5cf6b",
        "EBF": "#006400",
        "OpenShrub": "#c49c94",
    }
    fig = plt.figure(figsize=(14, 5))
    fig.suptitle("Merged LS/ECO pilot — SWIM vs Landsat PT-JPL (on Landsat obs dates)", fontsize=11)

    for i, (swim_col, ls_col, xlabel, title) in enumerate(
        [
            ("swim_ls_bias", "ls_bias", "ET bias (mm/d)", "Bias vs flux"),
            ("swim_ls_rmse", "ls_rmse", "RMSE (mm/d)", "RMSE vs flux"),
            ("swim_ls_r2", "ls_r2", "R²", "R² vs flux"),
        ]
    ):
        ax = fig.add_subplot(1, 3, i + 1)
        for _, row in valid.iterrows():
            color = lulc_colors.get(row["lulc_name"], "grey")
            ax.scatter(
                row[ls_col],
                row[swim_col],
                s=60,
                color=color,
                alpha=0.85,
                zorder=3,
                label=row["lulc_name"],
            )
            ax.annotate(
                row["sid"],
                (row[ls_col], row[swim_col]),
                fontsize=6,
                alpha=0.7,
                xytext=(3, 3),
                textcoords="offset points",
            )
        v_swim = valid[swim_col].values
        v_ls = valid[ls_col].values
        lo = min(v_swim.min(), v_ls.min()) - 0.1
        hi = max(v_swim.max(), v_ls.max()) + 0.1
        ax.plot([lo, hi], [lo, hi], "k--", lw=1, alpha=0.5)
        if swim_col == "swim_ls_bias":
            ax.axhline(0, color="grey", lw=0.8, ls=":")
            ax.axvline(0, color="grey", lw=0.8, ls=":")
        ax.set_xlabel(f"Landsat PT-JPL {xlabel}")
        ax.set_ylabel(f"SWIM {xlabel}")
        ax.set_title(title)
        # deduplicated legend on first panel only
        if i == 0:
            seen = {}
            for handle, label in zip(*ax.get_legend_handles_labels()):
                seen[label] = handle
            ax.legend(seen.values(), seen.keys(), fontsize=7, loc="upper left")

    plt.tight_layout()
    out_png = OUT_DIR / "merged_pilot_evaluation.png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_png}")


if __name__ == "__main__":
    main()
