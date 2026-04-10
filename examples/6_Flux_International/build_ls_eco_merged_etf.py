"""Build merged Landsat/ECOSTRESS PT-JPL ETf CSVs for the 18-site pilot.

Merge rule (per site):
  delta     = median(Landsat_ETf - ECOSTRESS_ETf) from co-located pairs
  LS_adj    = clip(Landsat_ETf - delta, 0.05, 2.0)
  merged    = ECOSTRESS where available (2018+), else LS_adj

Output CSVs (one per site-year, named for the ETf ingestor mask filter):
  {OUT_ETF_DIR}/ptjpl_etf_{sid}_no_mask_{year}.csv
  columns: sid, merged_{YYYYMMDD}, ...

Provenance audit (one row per site-date):
  {RESULTS_DIR}/ls_eco_merged_audit_18site.csv

Usage:
    uv run python examples/6_Flux_International/build_ls_eco_merged_etf.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from swimrs.container import SwimContainer
from swimrs.swim.config import ProjectConfig

TOML = Path(__file__).resolve().parent / "6_Flux_International.toml"
START_DATE = "1987-01-01"
DELTA_CSV = Path("/data/ssd1/swim/6_Flux_International/results/ls_eco_site_delta_18site.csv")
OUT_ETF_DIR = Path(
    "/data/ssd1/swim/6_Flux_International/data/remote_sensing/merged/extracts/etf/no_mask"
)
AUDIT_CSV = Path("/data/ssd1/swim/6_Flux_International/results/ls_eco_merged_audit_18site.csv")
ETF_LO, ETF_HI = 0.05, 2.0
ECO_START = pd.Timestamp("2018-01-01")

PILOT_SITES = [
    "US-Bi1",
    "FR-EM2",
    "CA-TP1",
    "US-SRG",
    "US-Wkg",
    "US-Whs",
    "US-Esm",
    "ES-LMa",
    "US-ONA",
    "IT-TrF",
    "US-Vcm",
    "US-xRM",
    "US-UMd",
    "CA-TPD",
    "IT-BFt",
    "DE-RuW",
    "DE-Hzd",
    "US-Me2",
]


def main():
    delta_df = pd.read_csv(DELTA_CSV, index_col="sid")
    missing_delta = [s for s in PILOT_SITES if s not in delta_df.index]
    if missing_delta:
        raise ValueError(
            f"No delta entry for sites: {missing_delta}. Run build_ls_eco_site_delta.py first."
        )
    no_pairs = delta_df.loc[PILOT_SITES, "n_pairs"][delta_df.loc[PILOT_SITES, "n_pairs"] == 0]
    if len(no_pairs):
        raise ValueError(
            f"Sites with zero co-located pairs cannot be bias-adjusted: {list(no_pairs.index)}"
        )

    cfg = ProjectConfig()
    cfg.read_config(str(TOML))

    container = SwimContainer.open(str(cfg.container_path), mode="r")
    root = container._root
    uids = container.field_uids
    n_days = root["meteorology/era5/eto"].shape[0]
    time_index = pd.date_range(START_DATE, periods=n_days, freq="D")

    pilot_idx = [uids.index(s) for s in PILOT_SITES]

    print("Loading ETf arrays...")
    ls_all = root["remote_sensing/etf/landsat/ptjpl/no_mask"][:, pilot_idx]
    eco_all = root["remote_sensing/etf/ecostress/ptjpl/no_mask"][:, pilot_idx]
    container.close()

    OUT_ETF_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)

    audit_rows = []

    for j, sid in enumerate(PILOT_SITES):
        delta = float(delta_df.loc[sid, "delta_median"])

        ls = pd.Series(ls_all[:, j], index=time_index)
        eco = pd.Series(eco_all[:, j], index=time_index)

        # Valid-range masks (NaN outside)
        ls_v = ls.where((ls >= ETF_LO) & (ls <= ETF_HI))
        eco_v = eco.where((eco >= ETF_LO) & (eco <= ETF_HI))

        # Adjusted Landsat
        ls_adj = (ls_v - delta).clip(ETF_LO, ETF_HI)

        # Merged series: ECO where available (2018+), else LS_adj
        merged = ls_adj.copy()
        eco_available = eco_v.dropna().index
        eco_post_cutoff = eco_available[eco_available >= ECO_START]
        merged.loc[eco_post_cutoff] = eco_v.loc[eco_post_cutoff]

        # Drop dates with no merged value
        merged = merged.dropna()

        if len(merged) == 0:
            print(f"  {sid}: WARNING — no merged observations, skipping")
            continue

        # Per-site provenance
        for date, val in merged.items():
            if date >= ECO_START and date in eco_post_cutoff:
                source = "ecostress"
                eco_val = eco_v.get(date, np.nan)
                ls_adj_val = ls_adj.get(date, np.nan)
            else:
                source = "landsat_adjusted"
                eco_val = np.nan
                ls_adj_val = val
            audit_rows.append(
                {
                    "sid": sid,
                    "date": date.date(),
                    "source": source,
                    "landsat_raw": round(float(ls_v.get(date, np.nan)), 4)
                    if pd.notna(ls_v.get(date, np.nan))
                    else np.nan,
                    "landsat_adjusted": round(float(ls_adj_val), 4)
                    if pd.notna(ls_adj_val)
                    else np.nan,
                    "ecostress": round(float(eco_val), 4) if pd.notna(eco_val) else np.nan,
                    "merged": round(float(val), 4),
                    "delta_site": delta,
                }
            )

        # Write per-year CSVs
        for year, grp in merged.groupby(merged.index.year):
            if grp.empty:
                continue
            col_names = ["merged_" + d.strftime("%Y%m%d") for d in grp.index]
            row = {col: v for col, v in zip(col_names, grp.values)}
            row["sid"] = sid
            out_df = pd.DataFrame([row])
            # Put sid first
            out_df = out_df[["sid"] + col_names]
            fname = OUT_ETF_DIR / f"ptjpl_etf_{sid}_no_mask_{year}.csv"
            out_df.to_csv(fname, index=False)

        n_eco = sum(1 for r in audit_rows if r["sid"] == sid and r["source"] == "ecostress")
        n_ls = sum(1 for r in audit_rows if r["sid"] == sid and r["source"] == "landsat_adjusted")
        print(
            f"  {sid}: {len(merged)} obs total  "
            f"(ECOSTRESS={n_eco}, LS_adj={n_ls})  delta={delta:.4f}"
        )

    audit_df = pd.DataFrame(audit_rows)
    audit_df.to_csv(AUDIT_CSV, index=False)
    print(f"\nSaved ETf CSVs: {OUT_ETF_DIR}")
    print(f"Saved audit: {AUDIT_CSV}")
    eco_total = (audit_df["source"] == "ecostress").sum()
    ls_total = (audit_df["source"] == "landsat_adjusted").sum()
    print(f"Network totals: ECOSTRESS={eco_total}, LS_adjusted={ls_total}")


if __name__ == "__main__":
    main()
