"""Build ablation container families for Ex4 Study 1.

Each container family shares the same meteorology, snow, properties, and ETf,
but differs in NDVI source:
  - ls_only:     merged NDVI from Landsat only
  - ls_s2_fused: merged NDVI from Landsat + Sentinel-2

Usage (called by run_ablations.py, not directly):
    from container_build import build_ablation_container
    build_ablation_container(cfg, "ls_only", family_spec, "/path/to/ls_only.swim")
"""

import os
import sys
from pathlib import Path

# Add parent directory so we can import container_prep functions
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swimrs.container import create_container
from swimrs.swim.config import ProjectConfig


def build_ablation_container(
    cfg: ProjectConfig,
    family_name: str,
    family_spec: dict,
    output_path: str,
    overwrite: bool = False,
    sites: list[str] | None = None,
) -> str:
    """Build one container family for ablation experiments.

    Args:
        cfg: ProjectConfig loaded from 4_Flux_Network.toml.
        family_name: Container family identifier (e.g. "ls_only").
        family_spec: Dict with keys: add_sentinel, merged_ndvi_instruments.
        output_path: Filesystem path for the .swim container.
        overwrite: Replace existing container if True.
        sites: Optional subset of sites to process.

    Returns:
        The output_path.
    """
    from container_prep import (
        build_gridmet_mapping,
        build_shapefile,
        ingest_meteorology,
        ingest_properties,
        ingest_remote_sensing,
        ingest_snow,
    )

    # Ensure shapefile and gridmet mapping exist
    build_shapefile(cfg, overwrite=False)
    build_gridmet_mapping(cfg, overwrite=False)

    if os.path.exists(output_path) and not overwrite:
        from swimrs.container import open_container

        print(f"Opening existing container: {output_path}")
        container = open_container(output_path, mode="r+")
    else:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        print(f"Creating container: {output_path} (family={family_name})")
        container = create_container(
            uri=output_path,
            fields_shapefile=cfg.fields_shapefile,
            uid_column=cfg.feature_id_col,
            start_date=cfg.start_dt,
            end_date=cfg.end_dt,
            project_name=f"{cfg.project_name}_{family_name}",
            overwrite=overwrite,
        )

    add_sentinel = family_spec["add_sentinel"]
    instruments = tuple(family_spec["merged_ndvi_instruments"])

    # Force single-threaded ingest — ProcessPoolExecutor hangs when called
    # from the ablation orchestrator's nested import path.
    saved_workers = cfg.workers
    cfg.workers = 1

    ingest_meteorology(container, cfg, overwrite=overwrite)
    ingest_remote_sensing(
        container,
        cfg,
        sites=sites,
        overwrite=overwrite,
        add_sentinel=add_sentinel,
    )

    cfg.workers = saved_workers
    ingest_snow(container, cfg, overwrite=overwrite)
    ingest_properties(container, cfg, overwrite=overwrite)

    print(f"\n=== Computing Merged NDVI (instruments={instruments}) ===")
    container.compute.merged_ndvi(
        masks=("no_mask",),
        instruments=instruments,
        overwrite=overwrite,
    )

    print("\n=== Computing Dynamics (no_mask only) ===")
    container.compute.dynamics(
        etf_model=cfg.etf_target_model,
        masks=("no_mask",),
        irr_threshold=cfg.irrigation_threshold or 0.3,
        use_mask=True,
        use_lulc=False,
        lookback=5,
        overwrite=overwrite,
    )

    container.close()
    print(f"\nContainer saved: {output_path}")
    return output_path
