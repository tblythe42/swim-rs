"""Compute per-site Landsat–ECOSTRESS PT-JPL ETf offset for the 18-site pilot.

For each site in the pilot subset, finds exact-date co-located observations
(both instruments valid on the same day) and computes the site-level median
and mean offset (Landsat − ECOSTRESS).

Output CSV columns:
    sid, n_pairs, delta_median, delta_mean, delta_std,
    overlap_start, overlap_end

Usage:
    uv run python examples/6_Flux_International/build_ls_eco_site_delta.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from swimrs.container import SwimContainer
from swimrs.swim.config import ProjectConfig

HERE = Path(__file__).resolve().parent
EXAMPLE_DIR = HERE if (HERE / "6_Flux_International.toml").exists() else HERE.parent
TOML = EXAMPLE_DIR / "6_Flux_International.toml"
START_DATE = "1987-01-01"
OUT_CSV = Path("/data/ssd1/swim/6_Flux_International/results/ls_eco_site_delta_18site.csv")
ETF_LO, ETF_HI = 0.05, 2.0

PILOT_SITES = [
    "US-Bi1",
    "FR-EM2",
    "CA-TP1",  # Cropland
    "US-SRG",
    "US-Wkg",
    "US-Whs",  # Grassland
    "US-Esm",
    "ES-LMa",
    "US-ONA",  # Savanna
    "IT-TrF",
    "US-Vcm",
    "US-xRM",  # WoodySav
    "US-UMd",
    "CA-TPD",
    "IT-BFt",  # DBF
    "DE-RuW",
    "DE-Hzd",
    "US-Me2",  # ENF
]


def main():
    cfg = ProjectConfig()
    cfg.read_config(str(TOML))

    container = SwimContainer.open(str(cfg.container_path), mode="r")
    root = container._root
    uids = container.field_uids
    n_days = root["meteorology/era5/eto"].shape[0]
    time_index = pd.date_range(START_DATE, periods=n_days, freq="D")

    pilot_idx = [uids.index(s) for s in PILOT_SITES]

    print("Loading ETf arrays...")
    ls_cols = root["remote_sensing/etf/landsat/ptjpl/no_mask"][:, pilot_idx]
    eco_cols = root["remote_sensing/etf/ecostress/ptjpl/no_mask"][:, pilot_idx]
    container.close()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    records = []
    for j, sid in enumerate(PILOT_SITES):
        ls = pd.Series(ls_cols[:, j], index=time_index)
        eco = pd.Series(eco_cols[:, j], index=time_index)

        ls_valid = ls[(ls >= ETF_LO) & (ls <= ETF_HI)]
        eco_valid = eco[(eco >= ETF_LO) & (eco <= ETF_HI)]

        both = pd.concat(
            [ls_valid.rename("ls"), eco_valid.rename("eco")], axis=1, join="inner"
        ).dropna()

        if len(both) == 0:
            print(f"  {sid}: no co-located pairs")
            records.append(
                {
                    "sid": sid,
                    "n_pairs": 0,
                    "delta_median": np.nan,
                    "delta_mean": np.nan,
                    "delta_std": np.nan,
                    "overlap_start": pd.NaT,
                    "overlap_end": pd.NaT,
                }
            )
            continue

        diff = both["ls"] - both["eco"]
        records.append(
            {
                "sid": sid,
                "n_pairs": len(both),
                "delta_median": round(diff.median(), 4),
                "delta_mean": round(diff.mean(), 4),
                "delta_std": round(diff.std(), 4),
                "overlap_start": both.index.min().date(),
                "overlap_end": both.index.max().date(),
            }
        )
        print(
            f"  {sid}: n={len(both)}  delta_median={diff.median():.4f}  "
            f"delta_mean={diff.mean():.4f}"
        )

    df = pd.DataFrame(records)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")
    print(f"Sites with co-located pairs: {(df['n_pairs'] > 0).sum()}/{len(df)}")
    print(f"Network median delta: {df['delta_median'].median():.4f}")


if __name__ == "__main__":
    main()
