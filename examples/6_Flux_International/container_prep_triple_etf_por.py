"""
Container prep for Triple ETf POR experiment.

Copies the LS Ensemble POR container (which already has Landsat SSEBop + PT-JPL,
met, NDVI, properties) and adds ECOSTRESS PT-JPL ETf, then merges all three
sources via nanmean into `remote_sensing/etf/merged/triple/no_mask`.

Usage:
    python container_prep_triple_etf_por.py [--overwrite]
"""

import os
import shutil
from pathlib import Path

import numpy as np

from swimrs.container import SwimContainer, open_container
from swimrs.swim.config import ProjectConfig

SRC_CONTAINER = (
    "/data/ssd1/swim/6_Flux_International/data/6_Flux_International_ls_ensemble_por.swim"
)
TOML = Path(__file__).resolve().parent / "6_Flux_International_TripleETf_POR.toml"


def _load_config(config_path: str | None = None) -> ProjectConfig:
    conf = Path(config_path) if config_path else TOML
    cfg = ProjectConfig()
    cfg.read_config(str(conf))
    return cfg


def copy_container(cfg: ProjectConfig, overwrite: bool = False) -> SwimContainer:
    dst = cfg.container_path or os.path.join(
        cfg.data_dir, f"{cfg.project_name}_triple_etf_por.swim"
    )

    if os.path.exists(dst) and not overwrite:
        print(f"Opening existing container: {dst}")
        return open_container(dst, mode="r+")

    if os.path.exists(dst):
        print(f"Removing existing: {dst}")
        shutil.rmtree(dst)

    print(f"Copying {SRC_CONTAINER} -> {dst}")
    shutil.copytree(SRC_CONTAINER, dst)
    return open_container(dst, mode="r+")


def ingest_ecostress_etf(container: SwimContainer, cfg: ProjectConfig):
    eco_dir = os.path.join(cfg.ecostress_dir, "extracts", "etf", "no_mask")
    if not os.path.isdir(eco_dir):
        raise FileNotFoundError(f"ECOSTRESS ETf directory not found: {eco_dir}")

    print(f"\n=== Ingesting ECOSTRESS PT-JPL ETf from {eco_dir} ===")
    container.ingest.etf(
        source_dir=eco_dir,
        uid_column=cfg.feature_id_col,
        model="ptjpl",
        instrument="ecostress",
        mask="no_mask",
    )


def merge_etf(container: SwimContainer):
    """Merge Landsat SSEBop + Landsat PT-JPL + ECOSTRESS PT-JPL via nanmean."""
    print("\n=== Merging ETf (nanmean of 3 sources) ===")
    root = container._root

    ls_ssebop = np.array(root["remote_sensing/etf/landsat/ssebop/no_mask"][:])
    ls_ptjpl = np.array(root["remote_sensing/etf/landsat/ptjpl/no_mask"][:])
    eco_ptjpl = np.array(root["remote_sensing/etf/ecostress/ptjpl/no_mask"][:])

    print(f"  Landsat SSEBop: {int((~np.isnan(ls_ssebop)).sum())} valid")
    print(f"  Landsat PT-JPL: {int((~np.isnan(ls_ptjpl)).sum())} valid")
    print(f"  ECOSTRESS PT-JPL: {int((~np.isnan(eco_ptjpl)).sum())} valid")

    stacked = np.stack([ls_ssebop, ls_ptjpl, eco_ptjpl], axis=0)
    merged = np.nanmean(stacked, axis=0)
    all_nan = np.all(np.isnan(stacked), axis=0)
    merged[all_nan] = np.nan

    n_valid = int((~np.isnan(merged)).sum())
    n_ls_only = int((np.isnan(eco_ptjpl) & (~np.isnan(ls_ssebop) | ~np.isnan(ls_ptjpl))).sum())
    n_eco_only = int((np.isnan(ls_ssebop) & np.isnan(ls_ptjpl) & ~np.isnan(eco_ptjpl)).sum())
    n_both = int((~np.isnan(eco_ptjpl) & (~np.isnan(ls_ssebop) | ~np.isnan(ls_ptjpl))).sum())
    print(f"  Merged (triple): {n_valid} valid values")
    print(
        f"  Landsat-only dates: {n_ls_only}, ECOSTRESS-only dates: {n_eco_only}, overlap: {n_both}"
    )

    # Navigate/create group hierarchy
    rs_grp = root["remote_sensing"]
    etf_grp = rs_grp["etf"] if "etf" in rs_grp else rs_grp.create_group("etf")
    merged_grp = etf_grp["merged"] if "merged" in etf_grp else etf_grp.create_group("merged")
    triple_grp = (
        merged_grp["triple"] if "triple" in merged_grp else merged_grp.create_group("triple")
    )

    if "no_mask" in triple_grp:
        del triple_grp["no_mask"]

    triple_grp.create_array("no_mask", data=merged.astype("float32"))
    print(f"  Written to: remote_sensing/etf/merged/triple/no_mask ({merged.shape})")


def recompute_dynamics(container: SwimContainer, cfg: ProjectConfig):
    """Recompute dynamics using the merged triple ETf for irrigation classification."""
    print("\n=== Recomputing Dynamics (triple ETf) ===")
    container.compute.dynamics(
        etf_model="triple",
        masks=("no_mask",),
        instruments=("merged", "sentinel"),
        use_lulc=True,
        irr_threshold=cfg.irrigation_threshold or 0.3,
        met_source=cfg.met_source,
        overwrite=True,
    )


def main(overwrite: bool = False):
    cfg = _load_config()
    container = copy_container(cfg, overwrite=overwrite)

    ingest_ecostress_etf(container, cfg)
    merge_etf(container)
    recompute_dynamics(container, cfg)

    print("\n=== Container Preparation Complete ===")
    root = container._root
    for p in [
        "remote_sensing/etf/landsat/ssebop/no_mask",
        "remote_sensing/etf/landsat/ptjpl/no_mask",
        "remote_sensing/etf/ecostress/ptjpl/no_mask",
        "remote_sensing/etf/merged/triple/no_mask",
    ]:
        arr = np.array(root[p][:])
        print(f"  {p}: shape={arr.shape}, valid={int((~np.isnan(arr)).sum())}")

    container.close()
    print(f"\nContainer saved to: {container.path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build triple ETf POR container from LS Ensemble POR"
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    main(overwrite=args.overwrite)
