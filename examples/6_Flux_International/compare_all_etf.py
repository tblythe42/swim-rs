"""Compare Landsat PT-JPL and ECOSTRESS PT-JPL ETf against flux tower ETf for all 241 sites.

Reads ETf and ETo directly from the existing container — no new container build needed.
Flux ETf = ET_corr / ETo (ERA5-Land), restricted to dates where ETo > 0.5 mm/d.

Usage:
    uv run python examples/6_Flux_International/compare_all_etf.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import r2_score, root_mean_squared_error

from swimrs.container import SwimContainer
from swimrs.swim.config import ProjectConfig

TOML = Path(__file__).resolve().parent / "6_Flux_International.toml"
FLUX_DIRS = [
    Path("/nas/climate/flux_stations/qaqc/ameriflux"),
    Path("/nas/climate/flux_stations/qaqc/fluxnet"),
    Path("/nas/climate/flux_stations/qaqc/icos"),
    Path("/nas/climate/flux_stations/qaqc/ozflux"),
]
START_DATE = "1987-01-01"
OUT_DIR = Path(__file__).resolve().parent
MIN_ETO = 0.5  # mm/d — avoid near-zero division
MIN_PAIRS = 10  # minimum matched obs to compute metrics
ETF_LO, ETF_HI = 0.05, 2.0


def _flux_path(sid: str) -> Path | None:
    for d in FLUX_DIRS:
        p = d / f"{sid}_daily_data.csv"
        if p.exists():
            return p
    return None


def _load_flux_et(sid: str) -> pd.Series | None:
    """Return daily ET_corr Series indexed by date, or None if unavailable."""
    path = _flux_path(sid)
    if path is None:
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    col = "ET_corr" if "ET_corr" in df.columns else ("ET" if "ET" in df.columns else None)
    if col is None:
        return None
    s = df.set_index("date")[col].dropna()
    return s if len(s) > 0 else None


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
    cfg.read_config(str(TOML))

    print("Opening container...")
    container = SwimContainer.open(str(cfg.container_path), mode="r")
    root = container._root
    uids = container.field_uids
    n_days = root["meteorology/era5/eto"].shape[0]
    time_index = pd.date_range(START_DATE, periods=n_days, freq="D")

    print("Loading arrays from container...")
    eto_all = root["meteorology/era5/eto"][:]  # (14214, 241)
    ls_all = root["remote_sensing/etf/landsat/ptjpl/no_mask"][:]
    eco_all = root["remote_sensing/etf/ecostress/ptjpl/no_mask"][:]
    container.close()
    print(f"Arrays loaded. Processing {len(uids)} sites...")

    records = []
    for i, sid in enumerate(uids):
        flux_et = _load_flux_et(sid)
        if flux_et is None:
            records.append({"sid": sid, "flux_file": False})
            continue

        eto = pd.Series(eto_all[:, i], index=time_index)
        ls_etf = pd.Series(ls_all[:, i], index=time_index)
        eco_etf = pd.Series(eco_all[:, i], index=time_index)

        # Flux ETf on valid dates
        eto_on_flux = eto.reindex(flux_et.index)
        valid_eto = (eto_on_flux > MIN_ETO) & np.isfinite(eto_on_flux) & np.isfinite(flux_et)
        flux_etf = (flux_et / eto_on_flux).where(valid_eto)
        flux_etf = flux_etf[(flux_etf >= ETF_LO) & (flux_etf <= ETF_HI)]

        # Landsat: obs-only, valid range, then match flux dates
        ls_valid = ls_etf[(ls_etf >= ETF_LO) & (ls_etf <= ETF_HI)].dropna()
        eco_valid = eco_etf[(eco_etf >= ETF_LO) & (eco_etf <= ETF_HI)].dropna()

        ls_flux2 = pd.concat(
            [ls_valid.rename("ls"), flux_etf.rename("flux")], axis=1, join="inner"
        ).dropna()
        eco_flux2 = pd.concat(
            [eco_valid.rename("eco"), flux_etf.rename("flux")], axis=1, join="inner"
        ).dropna()

        m_ls = calc_metrics(ls_flux2["flux"].values, ls_flux2["ls"].values)
        m_eco = calc_metrics(eco_flux2["flux"].values, eco_flux2["eco"].values)

        # Mean ETf level (growing season: Apr–Oct)
        gs = slice("2018-04-01", "2025-10-31")
        ls_gs = ls_valid[gs]
        eco_gs = eco_valid[gs]
        flux_gs = flux_etf[gs]

        records.append(
            {
                "sid": sid,
                "flux_file": True,
                "n_flux_etf": len(flux_etf),
                # Landsat
                "ls_n": m_ls["n"],
                "ls_bias": m_ls["bias"],
                "ls_rmse": m_ls["rmse"],
                "ls_r2": m_ls["r2"],
                "ls_kge": m_ls["kge"],
                "ls_mean_gs": round(float(ls_gs.mean()), 3) if len(ls_gs) > 0 else np.nan,
                # ECOSTRESS
                "eco_n": m_eco["n"],
                "eco_bias": m_eco["bias"],
                "eco_rmse": m_eco["rmse"],
                "eco_r2": m_eco["r2"],
                "eco_kge": m_eco["kge"],
                "eco_mean_gs": round(float(eco_gs.mean()), 3) if len(eco_gs) > 0 else np.nan,
                # Flux
                "flux_mean_gs": round(float(flux_gs.mean()), 3) if len(flux_gs) > 0 else np.nan,
            }
        )

        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(uids)}")

    df = pd.DataFrame(records)
    out_csv = OUT_DIR / "all_sites_etf_comparison.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved per-site metrics: {out_csv}")

    # Summary stats on sites with enough data
    has_ls = df["ls_n"].fillna(0) >= MIN_PAIRS
    has_eco = df["eco_n"].fillna(0) >= MIN_PAIRS
    print(f"\nSites with >= {MIN_PAIRS} matched Landsat obs: {has_ls.sum()}")
    print(f"Sites with >= {MIN_PAIRS} matched ECOSTRESS obs: {has_eco.sum()}")

    for col, label in [("ls_bias", "Landsat bias"), ("eco_bias", "ECOSTRESS bias")]:
        mask = has_ls if "ls" in col else has_eco
        vals = df.loc[mask, col].dropna()
        print(
            f"{label}: median={vals.median():.3f}  mean={vals.mean():.3f}  "
            f"IQR=[{vals.quantile(0.25):.3f}, {vals.quantile(0.75):.3f}]"
        )

    # ── Plots ──────────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(16, 10))
    fig.suptitle("All sites — Landsat vs ECOSTRESS ETf vs Flux ETf", fontsize=13)

    # 1. Bias histograms
    ax = fig.add_subplot(2, 3, 1)
    ls_bias = df.loc[has_ls, "ls_bias"].dropna()
    eco_bias = df.loc[has_eco, "eco_bias"].dropna()
    bins = np.linspace(-0.8, 0.8, 33)
    ax.hist(
        ls_bias,
        bins=bins,
        alpha=0.6,
        color="steelblue",
        label=f"Landsat (n={len(ls_bias)}, med={ls_bias.median():.2f})",
    )
    ax.hist(
        eco_bias,
        bins=bins,
        alpha=0.6,
        color="tomato",
        label=f"ECOSTRESS (n={len(eco_bias)}, med={eco_bias.median():.2f})",
    )
    ax.axvline(0, color="k", lw=1, ls="--")
    ax.set_xlabel("ETf bias (model − flux)")
    ax.set_ylabel("Sites")
    ax.legend(fontsize=8)
    ax.set_title("ETf bias vs flux tower")

    # 2. RMSE histograms
    ax = fig.add_subplot(2, 3, 2)
    ls_rmse = df.loc[has_ls, "ls_rmse"].dropna()
    eco_rmse = df.loc[has_eco, "eco_rmse"].dropna()
    bins_r = np.linspace(0, 0.8, 33)
    ax.hist(
        ls_rmse,
        bins=bins_r,
        alpha=0.6,
        color="steelblue",
        label=f"Landsat (med={ls_rmse.median():.2f})",
    )
    ax.hist(
        eco_rmse,
        bins=bins_r,
        alpha=0.6,
        color="tomato",
        label=f"ECOSTRESS (med={eco_rmse.median():.2f})",
    )
    ax.set_xlabel("ETf RMSE")
    ax.set_ylabel("Sites")
    ax.legend(fontsize=8)
    ax.set_title("ETf RMSE vs flux tower")

    # 3. KGE histograms
    ax = fig.add_subplot(2, 3, 3)
    ls_kge = df.loc[has_ls, "ls_kge"].dropna()
    eco_kge = df.loc[has_eco, "eco_kge"].dropna()
    bins_k = np.linspace(-2, 1, 31)
    ax.hist(
        ls_kge,
        bins=bins_k,
        alpha=0.6,
        color="steelblue",
        label=f"Landsat (med={ls_kge.median():.2f})",
    )
    ax.hist(
        eco_kge,
        bins=bins_k,
        alpha=0.6,
        color="tomato",
        label=f"ECOSTRESS (med={eco_kge.median():.2f})",
    )
    ax.axvline(0, color="k", lw=1, ls="--")
    ax.set_xlabel("KGE")
    ax.set_ylabel("Sites")
    ax.legend(fontsize=8)
    ax.set_title("ETf KGE vs flux tower")

    # 4. Scatter: Landsat bias vs ECOSTRESS bias (co-located sites)
    ax = fig.add_subplot(2, 3, 4)
    co = df[has_ls & has_eco][["ls_bias", "eco_bias"]].dropna()
    ax.scatter(co["ls_bias"], co["eco_bias"], alpha=0.6, s=18, color="darkorange")
    lim = (
        max(
            abs(co["ls_bias"].max()),
            abs(co["eco_bias"].max()),
            abs(co["ls_bias"].min()),
            abs(co["eco_bias"].min()),
        )
        * 1.1
    )
    ax.axhline(0, color="k", lw=0.8, ls="--")
    ax.axvline(0, color="k", lw=0.8, ls="--")
    ax.plot([-lim, lim], [-lim, lim], "k:", lw=1, alpha=0.5)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("Landsat ETf bias")
    ax.set_ylabel("ECOSTRESS ETf bias")
    ax.set_title(f"Bias per site (n={len(co)} co-located)")

    # 5. Scatter: mean growing-season ETf level
    ax = fig.add_subplot(2, 3, 5)
    gs_df = df[["ls_mean_gs", "eco_mean_gs", "flux_mean_gs"]].dropna()
    ax.scatter(
        gs_df["flux_mean_gs"],
        gs_df["ls_mean_gs"],
        alpha=0.5,
        s=14,
        color="steelblue",
        label="Landsat",
    )
    ax.scatter(
        gs_df["flux_mean_gs"],
        gs_df["eco_mean_gs"],
        alpha=0.5,
        s=14,
        color="tomato",
        label="ECOSTRESS",
        marker="^",
    )
    lim = max(gs_df.max().max(), 0.05) * 1.1
    ax.plot([0, lim], [0, lim], "k--", lw=1)
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("Flux mean ETf (Apr–Oct, 2018–2025)")
    ax.set_ylabel("Remote sensing mean ETf")
    ax.legend(fontsize=8)
    ax.set_title("Mean growing-season ETf level")

    # 6. Boxplot comparison
    ax = fig.add_subplot(2, 3, 6)
    plot_data = [ls_bias, eco_bias]
    bp = ax.boxplot(
        plot_data,
        labels=["Landsat\nPT-JPL", "ECOSTRESS\nPT-JPL"],
        patch_artist=True,
        medianprops={"color": "black", "lw": 2},
    )
    colors_bp = ["steelblue", "tomato"]
    for patch, color in zip(bp["boxes"], colors_bp):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.axhline(0, color="k", lw=1, ls="--")
    ax.set_ylabel("ETf bias (model − flux)")
    ax.set_title("ETf bias distribution")

    plt.tight_layout()
    out_png = OUT_DIR / "all_sites_etf_comparison.png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    print(f"Saved figure: {out_png}")
    plt.close()


if __name__ == "__main__":
    main()
