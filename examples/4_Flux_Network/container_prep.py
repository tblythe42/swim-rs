"""
Container-based data preparation workflow for 4_Flux_Network.

The container workflow:
    1. Create container from shapefile
    2. Ingest meteorology (GridMET)
    3. Ingest remote sensing (NDVI, ETf from Landsat/Sentinel)
    4. Ingest snow (SNODAS)
    5. Ingest properties (soils, LULC, irrigation)
    6. Compute fused NDVI (Landsat + Sentinel)
    7. Compute dynamics (irrigation, groundwater, ke_max, kc_max)

Usage:
    python container_prep.py [--overwrite] [--sites SITE1,SITE2,...] [--skip-sentinel]

    # Or use functions directly:
    from container_prep import create_project_container, prep_all
    container = create_project_container(overwrite=True)
    prep_all(container)
"""

import os
from pathlib import Path

from swimrs.container import SwimContainer, create_container, open_container
from swimrs.swim.config import ProjectConfig
from swimrs.utils.flux_stations import create_master_shapefile

# Canonical source data (shipped with the repo)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FOOTPRINTS_SHP = _REPO_ROOT / "examples" / "data" / "flux_footprints_3p_clean.shp"
_METADATA_CSV = _REPO_ROOT / "examples" / "data" / "station_metadata.csv"


def _load_config() -> ProjectConfig:
    """Load project configuration from TOML file."""
    project_dir = Path(__file__).resolve().parent
    conf = project_dir / "4_Flux_Network.toml"

    cfg = ProjectConfig()
    if os.path.isdir("/data/ssd1/swim"):
        cfg.read_config(str(conf))
    else:
        cfg.read_config(str(conf), project_root_override=str(project_dir.parent))
    return cfg


def build_shapefile(cfg: ProjectConfig, overwrite: bool = False):
    """Regenerate the flux fields shapefile from canonical repo data.

    Builds a master shapefile from shipped footprints and metadata (all
    land-cover types, no classification filter).

    Args:
        cfg: ProjectConfig instance.
        overwrite: Replace an existing shapefile.
    """
    output_shp = cfg.fields_shapefile
    if os.path.exists(output_shp) and not overwrite:
        print(f"Shapefile already exists: {output_shp}")
        return

    os.makedirs(os.path.dirname(output_shp), exist_ok=True)
    print("\n=== Building flux fields shapefile (all land covers) ===")
    print(f"  Footprints: {_FOOTPRINTS_SHP}")
    print(f"  Metadata:   {_METADATA_CSV}")

    gdf = create_master_shapefile(
        str(_FOOTPRINTS_SHP), str(_METADATA_CSV), output_shp, overwrite=overwrite
    )
    print(f"  Created {len(gdf)} stations → {output_shp}")


def build_gridmet_mapping(cfg: ProjectConfig, overwrite: bool = False):
    """Create the GridMET mapping shapefile (flux_fields_gfid.shp).

    This spatial-joins the fields shapefile with GridMET centroids so that
    each site_id gets a GFID (GridMET cell ID).  The resulting shapefile is
    required by ``ingest_meteorology`` to look up parquet files by GFID.

    Args:
        cfg: ProjectConfig instance.
        overwrite: Replace an existing mapping shapefile.
    """
    from swimrs.data_extraction.gridmet.gridmet import assign_gridmet_ids

    mapping_shp = cfg.gridmet_mapping_shp
    if os.path.exists(mapping_shp) and not overwrite:
        print(f"GridMET mapping already exists: {mapping_shp}")
        return

    print("\n=== Building GridMET mapping shapefile ===")
    assign_gridmet_ids(
        fields=cfg.fields_shapefile,
        fields_join=mapping_shp,
        gridmet_points=cfg.gridmet_centroids,
        feature_id=cfg.feature_id_col,
        gridmet_id_col=cfg.gridmet_id_col,
    )
    print(f"  Created mapping → {mapping_shp}")


def create_project_container(cfg: ProjectConfig = None, overwrite: bool = False) -> SwimContainer:
    """
    Create a new SwimContainer for this project.

    Args:
        cfg: ProjectConfig instance (loaded if None)
        overwrite: If True, overwrite existing container

    Returns:
        SwimContainer instance
    """
    if cfg is None:
        cfg = _load_config()

    container_path = os.path.join(cfg.data_dir, f"{cfg.project_name}.swim")

    if os.path.exists(container_path) and not overwrite:
        print(f"Opening existing container: {container_path}")
        return open_container(container_path, mode="r+")

    print(f"Creating new container: {container_path}")
    container = create_container(
        uri=container_path,
        fields_shapefile=cfg.fields_shapefile,
        uid_column=cfg.feature_id_col,
        start_date=cfg.start_dt,
        end_date=cfg.end_dt,
        project_name=cfg.project_name,
        overwrite=overwrite,
    )

    return container


def ingest_meteorology(container: SwimContainer, cfg: ProjectConfig, overwrite: bool = False):
    """
    Ingest GridMET meteorology data into the container.

    Args:
        container: SwimContainer instance
        cfg: ProjectConfig instance
        overwrite: If True, replace existing data
    """
    print("\n=== Ingesting Meteorology (GridMET) ===")

    # Check if already ingested
    if "meteorology/gridmet/eto" in container._root and not overwrite:
        print("GridMET data already ingested, skipping")
        return

    # Parquet files are named by site_id (e.g. US-ARM.parquet) — each flux
    # site has its own file, so we use direct mode (no grid mapping).
    container.ingest.gridmet(
        source_dir=cfg.met_dir,
        uid_column=cfg.feature_id_col,
        variables=[
            "eto",
            "etr",
            "eto_corr",
            "etr_corr",
            "prcp",
            "tmin",
            "tmax",
            "srad",
            "u2",
            "ea",
        ],
        overwrite=overwrite,
    )


def ingest_remote_sensing(
    container: SwimContainer,
    cfg: ProjectConfig,
    sites: list = None,
    overwrite: bool = False,
    add_sentinel: bool = True,
):
    """
    Ingest remote sensing data (NDVI, ETf) into the container.

    Args:
        container: SwimContainer instance
        cfg: ProjectConfig instance
        sites: Optional list of site IDs to include
        overwrite: If True, replace existing data
        add_sentinel: If True, also ingest Sentinel NDVI
    """
    print("\n=== Ingesting Remote Sensing ===")

    masks = ["irr", "inv_irr", "no_mask"]
    etf_masks = ["irr", "inv_irr", "no_mask"]
    # SSEBop NHM is the sole ETf model for this example
    models = [cfg.etf_target_model]
    n_workers = cfg.workers or 1

    # Ingest Landsat NDVI
    for mask in masks:
        ndvi_dir = os.path.join(cfg.landsat_dir, "extracts", "ndvi", mask)
        if os.path.isdir(ndvi_dir):
            print(f"Ingesting Landsat NDVI ({mask})...")
            container.ingest.ndvi(
                source_dir=ndvi_dir,
                uid_column=cfg.feature_id_col,
                instrument="landsat",
                mask=mask,
                fields=sites,
                overwrite=overwrite,
                workers=n_workers,
            )

    # Ingest Sentinel NDVI
    if add_sentinel:
        for mask in masks:
            sentinel_dir = getattr(cfg, "sentinel_dir", None)
            if sentinel_dir is None:
                sentinel_dir = cfg.landsat_dir.replace("landsat", "sentinel")
            ndvi_dir = os.path.join(sentinel_dir, "extracts", "ndvi", mask)
            if os.path.isdir(ndvi_dir):
                print(f"Ingesting Sentinel NDVI ({mask})...")
                container.ingest.ndvi(
                    source_dir=ndvi_dir,
                    uid_column=cfg.feature_id_col,
                    instrument="sentinel",
                    mask=mask,
                    fields=sites,
                    overwrite=overwrite,
                    workers=n_workers,
                )

    # Ingest ETf for each model
    for model in models:
        for mask in etf_masks:
            etf_dir = os.path.join(cfg.landsat_dir, "extracts", f"{model}_etf", mask)
            if os.path.isdir(etf_dir):
                print(f"Ingesting ETf ({model}, {mask})...")
                container.ingest.etf(
                    source_dir=etf_dir,
                    uid_column=cfg.feature_id_col,
                    instrument="landsat",
                    model=model,
                    mask=mask,
                    fields=sites,
                    overwrite=overwrite,
                    workers=n_workers,
                )


def ingest_snow(container: SwimContainer, cfg: ProjectConfig, overwrite: bool = False):
    """
    Ingest SNODAS snow data into the container.

    Args:
        container: SwimContainer instance
        cfg: ProjectConfig instance
        overwrite: If True, replace existing data
    """
    print("\n=== Ingesting Snow (SNODAS) ===")

    if "snow/snodas/swe" in container._root and not overwrite:
        print("SNODAS data already ingested, skipping")
        return

    if cfg.snodas_in_dir and os.path.isdir(cfg.snodas_in_dir):
        container.ingest.snodas(
            source_dir=cfg.snodas_in_dir,
            uid_column=cfg.feature_id_col,
            overwrite=overwrite,
        )
    else:
        print("Warning: No SNODAS extracts found, skipping")


def ingest_properties(container: SwimContainer, cfg: ProjectConfig, overwrite: bool = False):
    """
    Ingest field properties (soils, LULC, irrigation) into the container.

    Args:
        container: SwimContainer instance
        cfg: ProjectConfig instance
        overwrite: If True, replace existing data
    """
    print("\n=== Ingesting Properties ===")

    container.ingest.properties(
        soils_csv=cfg.ssurgo_csv,
        lulc_csv=cfg.lulc_csv,
        irr_csv=cfg.irr_csv,
        uid_column=cfg.feature_id_col,
        overwrite=overwrite,
    )


def compute_fused_ndvi(container: SwimContainer, overwrite: bool = False):
    """
    Compute fused NDVI from Landsat and Sentinel observations.

    Args:
        container: SwimContainer instance
        overwrite: If True, replace existing fused NDVI
    """
    print("\n=== Computing Fused NDVI ===")

    container.compute.fused_ndvi(
        masks=("irr", "inv_irr", "no_mask"),
        overwrite=overwrite,
    )


def compute_dynamics(container: SwimContainer, cfg: ProjectConfig, overwrite: bool = False):
    """
    Compute irrigation, groundwater subsidy, and K parameters.

    Args:
        container: SwimContainer instance
        cfg: ProjectConfig instance
        overwrite: If True, replace existing dynamics
    """
    print("\n=== Computing Dynamics ===")

    container.compute.dynamics(
        etf_model=cfg.etf_target_model,
        masks=("irr", "inv_irr", "no_mask"),
        irr_threshold=cfg.irrigation_threshold or 0.3,
        use_mask=True,
        use_lulc=False,
        lookback=5,
        overwrite=overwrite,
    )


def prep_all(
    container: SwimContainer,
    cfg: ProjectConfig = None,
    sites: list = None,
    overwrite: bool = False,
    add_sentinel: bool = True,
):
    """
    Run the complete data preparation workflow.

    Args:
        container: SwimContainer instance
        cfg: ProjectConfig instance (loaded if None)
        sites: Optional list of site IDs to include
        overwrite: If True, replace existing data
        add_sentinel: If True, include Sentinel NDVI
    """
    if cfg is None:
        cfg = _load_config()

    # Step 0: Rebuild shapefile from canonical repo data
    build_shapefile(cfg, overwrite=overwrite)

    # Step 1: Ingest meteorology
    ingest_meteorology(container, cfg, overwrite=overwrite)

    # Step 2: Ingest remote sensing (NDVI, ETf)
    ingest_remote_sensing(
        container, cfg, sites=sites, overwrite=overwrite, add_sentinel=add_sentinel
    )

    # Step 3: Ingest snow
    ingest_snow(container, cfg, overwrite=overwrite)

    # Step 4: Ingest properties
    ingest_properties(container, cfg, overwrite=overwrite)

    # Step 5: Compute fused NDVI
    compute_fused_ndvi(container, overwrite=overwrite)

    # Step 6: Compute dynamics
    compute_dynamics(container, cfg, overwrite=overwrite)

    print("\n=== Container Preparation Complete ===")
    print(container.inventory)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Container-based data preparation for 4_Flux_Network"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing container",
    )
    parser.add_argument(
        "--sites",
        type=str,
        default=None,
        help="Comma-separated site IDs to process (default: all)",
    )
    parser.add_argument(
        "--skip-sentinel",
        action="store_true",
        help="Skip Sentinel NDVI ingestion",
    )
    args = parser.parse_args()

    # Parse sites argument
    select_sites = None
    if args.sites:
        select_sites = [s.strip() for s in args.sites.split(",")]

    # Load configuration
    config = _load_config()

    # Create or open container
    container = create_project_container(config, overwrite=args.overwrite)

    # Run full preparation workflow
    prep_all(
        container,
        config,
        sites=select_sites,
        overwrite=args.overwrite,
        add_sentinel=not args.skip_sentinel,
    )

    # Close container to ensure data is saved
    container.close()

    print(f"\nContainer saved to: {container.path}")
    print("\nTo run the model:")
    print("  python run.py --site US-ARM")
