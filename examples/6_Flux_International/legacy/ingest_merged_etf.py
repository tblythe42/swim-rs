"""Ingest merged LS/ECO ETf CSVs into the container for the 18-site pilot.

Reads from:
  /data/ssd1/swim/.../remote_sensing/merged/extracts/etf/no_mask/

Writes to container path:
  remote_sensing/etf/merged/ptjpl/no_mask

Then prints a per-site inventory (observation counts, date range, source breakdown)
from the audit CSV produced by build_ls_eco_merged_etf.py.

Usage:
    uv run python examples/6_Flux_International/ingest_merged_etf.py
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
ETF_DIR = Path(
    "/data/ssd1/swim/6_Flux_International/data/remote_sensing/merged/extracts/etf/no_mask"
)
AUDIT_CSV = Path("/data/ssd1/swim/6_Flux_International/results/ls_eco_merged_audit_18site.csv")
INVENTORY_CSV = Path("/data/ssd1/swim/6_Flux_International/results/merged_etf_inventory_18site.csv")

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
    if not ETF_DIR.exists() or not any(ETF_DIR.glob("*.csv")):
        raise FileNotFoundError(
            f"No merged ETf CSVs found in {ETF_DIR}. Run build_ls_eco_merged_etf.py first."
        )

    cfg = ProjectConfig()
    cfg.read_config(str(TOML))

    print("Opening container (r+)...")
    container = SwimContainer.open(str(cfg.container_path), mode="r+")

    print("Ingesting merged ETf...")
    event = container.ingest.etf(
        source_dir=ETF_DIR,
        uid_column="sid",
        instrument="merged",
        model="ptjpl",
        mask="no_mask",
        fields=PILOT_SITES,
        overwrite=True,
        min_etf=0.05,
    )
    print(f"Ingest complete: {event}")

    # Verify destination array
    path = "remote_sensing/etf/merged/ptjpl/no_mask"
    root = container._root
    if path not in root:
        print(f"ERROR: {path} not found in container after ingest")
        container.close()
        return

    arr = root[path][:]
    uids = container.field_uids
    n_days = arr.shape[0]
    time_index = pd.date_range(START_DATE, periods=n_days, freq="D")
    container.close()

    # Per-site inventory from container array
    audit_df = pd.read_csv(AUDIT_CSV, parse_dates=["date"]) if AUDIT_CSV.exists() else None

    records = []
    print(f"\n{'Site':<12} {'n_obs':>6} {'first':>12} {'last':>12} {'n_eco':>7} {'n_ls_adj':>9}")
    print("-" * 62)

    for sid in PILOT_SITES:
        if sid not in uids:
            print(f"  {sid}: not in container")
            continue
        idx = uids.index(sid)
        col = arr[:, idx]
        valid = np.isfinite(col) & (col > 0)
        n_obs = int(valid.sum())
        first = time_index[valid][0].date() if n_obs > 0 else None
        last = time_index[valid][-1].date() if n_obs > 0 else None

        n_eco = n_ls = 0
        if audit_df is not None:
            site_audit = audit_df[audit_df["sid"] == sid]
            n_eco = int((site_audit["source"] == "ecostress").sum())
            n_ls = int((site_audit["source"] == "landsat_adjusted").sum())

        records.append(
            {
                "sid": sid,
                "n_obs": n_obs,
                "first_date": first,
                "last_date": last,
                "n_ecostress": n_eco,
                "n_landsat_adjusted": n_ls,
            }
        )
        print(f"  {sid:<10} {n_obs:>6} {str(first):>12} {str(last):>12} {n_eco:>7} {n_ls:>9}")

    inv_df = pd.DataFrame(records)
    INVENTORY_CSV.parent.mkdir(parents=True, exist_ok=True)
    inv_df.to_csv(INVENTORY_CSV, index=False)
    print(f"\nSaved inventory: {INVENTORY_CSV}")

    zero_obs = inv_df[inv_df["n_obs"] == 0]
    if len(zero_obs):
        print(
            f"WARNING: {len(zero_obs)} sites have zero merged ETf observations: "
            f"{list(zero_obs['sid'])}"
        )
    else:
        print("All pilot sites have merged ETf observations.")


if __name__ == "__main__":
    main()
