"""Data extraction for 4_Flux_Network.

Extraction functions for NDVI, SSEBop NHM ETf, SNODAS, properties, and GridMET.
The SSEBop NHM ETf uses the USGS asset ``projects/usgs-gee-nhm-ssebop/assets/ssebop/landsat/c02``
via the sparse_sample_etf extractor with ``usgs_nhm=True``.

Usage:
    python data_extract.py [--extract {all,nhm,ndvi,snodas,properties,gridmet}]
"""

import os
from pathlib import Path

from swimrs.data_extraction.ee.ee_utils import is_authorized
from swimrs.swim.config import ProjectConfig


def _load_config() -> ProjectConfig:
    project_dir = Path(__file__).resolve().parent
    conf = project_dir / "4_Flux_Network.toml"

    cfg = ProjectConfig()
    if os.path.isdir("/data/ssd1/swim"):
        cfg.read_config(str(conf))
    else:
        cfg.read_config(str(conf), project_root_override=str(project_dir.parent))
    return cfg


def extract_snodas(cfg: ProjectConfig) -> None:
    is_authorized()
    from swimrs.data_extraction.ee.snodas_export import sample_snodas_swe

    sample_snodas_swe(
        feature_coll=cfg.fields_shapefile,
        bucket=cfg.ee_bucket,
        dest="bucket",
        debug=False,
        check_dir=None,
        feature_id=cfg.feature_id_col,
        file_prefix=cfg.project_name,
    )


def extract_properties(cfg: ProjectConfig) -> None:
    is_authorized()
    from swimrs.data_extraction.ee.ee_props import (
        get_cdl,
        get_irrigation,
        get_landcover,
        get_ssurgo,
    )

    project = cfg.project_name
    get_cdl(
        cfg.fields_shapefile,
        f"{project}_cdl",
        selector=cfg.feature_id_col,
        dest="bucket",
        bucket=cfg.ee_bucket,
        file_prefix=project,
    )
    get_irrigation(
        cfg.fields_shapefile,
        f"{project}_irr",
        debug=True,
        selector=cfg.feature_id_col,
        lanid=True,
        dest="bucket",
        bucket=cfg.ee_bucket,
        file_prefix=project,
    )
    get_ssurgo(
        cfg.fields_shapefile,
        f"{project}_ssurgo",
        debug=False,
        selector=cfg.feature_id_col,
        dest="bucket",
        bucket=cfg.ee_bucket,
        file_prefix=project,
    )
    get_landcover(
        cfg.fields_shapefile,
        f"{project}_landcover",
        debug=False,
        selector=cfg.feature_id_col,
        out_fmt="CSV",
        dest="bucket",
        bucket=cfg.ee_bucket,
        file_prefix=project,
    )


def extract_ndvi(cfg: ProjectConfig, sites=None, get_sentinel: bool = True, masks=None) -> None:
    """Extract NDVI zonal stats for Landsat (and optionally Sentinel)."""
    is_authorized()
    from swimrs.data_extraction.ee.ndvi_export import sparse_sample_ndvi

    if masks is None:
        masks = ["irr", "inv_irr", "no_mask"]
    for mask in masks:
        dst = os.path.join(cfg.landsat_dir, "extracts", "ndvi", mask)
        sparse_sample_ndvi(
            cfg.fields_shapefile,
            bucket=cfg.ee_bucket,
            dest="bucket",
            debug=False,
            mask_type=mask,
            check_dir=dst,
            start_yr=cfg.start_dt.year,
            end_yr=cfg.end_dt.year,
            feature_id=cfg.feature_id_col,
            satellite="landsat",
            state_col=cfg.state_col,
            select=sites,
            file_prefix=cfg.project_name,
        )

        if get_sentinel:
            dst = os.path.join(cfg.sentinel_dir, "extracts", "ndvi", mask)
            sparse_sample_ndvi(
                cfg.fields_shapefile,
                bucket=cfg.ee_bucket,
                dest="bucket",
                debug=False,
                mask_type=mask,
                check_dir=dst,
                start_yr=max(2017, cfg.start_dt.year),
                end_yr=cfg.end_dt.year,
                feature_id=cfg.feature_id_col,
                satellite="sentinel",
                state_col=cfg.state_col,
                select=sites,
                file_prefix=cfg.project_name,
            )


def extract_nhm_ssebop(cfg: ProjectConfig, sites=None, masks=None) -> None:
    """Extract SSEBop NHM ETf from the USGS EE asset.

    Uses ``projects/usgs-gee-nhm-ssebop/assets/ssebop/landsat/c02`` with
    ``et_fraction`` band divided by 10000.  West/east irrigation masking is
    handled by the sparse extractor (IrrMapper for west, LANID for east).
    """
    is_authorized()
    from ssebop_etf import extract_ssebop_nhm_etf

    if masks is None:
        masks = ["irr", "inv_irr", "no_mask"]
    for mask in masks:
        dst = os.path.join(cfg.landsat_dir, "extracts", "ssebop_etf", mask)
        extract_ssebop_nhm_etf(
            cfg.fields_shapefile,
            mask_type=mask,
            check_dir=dst,
            feature_id=cfg.feature_id_col,
            select=sites,
            start_yr=cfg.start_dt.year,
            end_yr=cfg.end_dt.year,
            state_col=cfg.state_col,
            dest="bucket",
            bucket=cfg.ee_bucket,
            file_prefix=cfg.project_name,
        )


def extract_gridmet(cfg: ProjectConfig, sites=None) -> None:
    from swimrs.data_extraction.gridmet.gridmet import (
        assign_gridmet_ids,
        download_gridmet,
        sample_gridmet_corrections,
    )

    nldas_needed = cfg.runoff_process == "ier"
    join_path = cfg.gridmet_mapping_shp
    factors_path = cfg.gridmet_factors

    assign_gridmet_ids(
        fields=cfg.fields_shapefile,
        fields_join=join_path,
        gridmet_points=cfg.gridmet_centroids,
        field_select=sites,
        feature_id=cfg.feature_id_col,
        gridmet_id_col=cfg.gridmet_id_col,
    )

    if cfg.correction_tifs:
        sample_gridmet_corrections(
            fields_join=join_path,
            gridmet_ras=cfg.correction_tifs,
            factors_js=factors_path,
            gridmet_id_col=cfg.gridmet_id_col,
        )

    download_gridmet(
        join_path,
        factors_path,
        cfg.met_dir,
        start=str(cfg.start_dt.date()),
        end=str(cfg.end_dt.date()),
        overwrite=False,
        append=True,
        use_nldas=nldas_needed,
        feature_id=cfg.gridmet_mapping_index_col,
        target_fields=sites,
        gridmet_id_col=cfg.gridmet_id_col,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Data extraction for 4_Flux_Network")
    parser.add_argument(
        "--extract",
        choices=["all", "nhm", "ndvi", "snodas", "properties", "gridmet"],
        default="all",
        help="Which extraction to run (default: all)",
    )
    parser.add_argument(
        "--sites",
        type=str,
        default=None,
        help="Comma-separated site IDs (default: all)",
    )
    parser.add_argument(
        "--masks",
        type=str,
        default=None,
        help="Comma-separated mask types to extract (default: irr,inv_irr,no_mask)",
    )
    args = parser.parse_args()

    config = _load_config()
    select_sites = [s.strip() for s in args.sites.split(",")] if args.sites else None
    select_masks = [m.strip() for m in args.masks.split(",")] if args.masks else None

    if args.extract in ("all", "snodas"):
        extract_snodas(config)
    if args.extract in ("all", "properties"):
        extract_properties(config)
    if args.extract in ("all", "ndvi"):
        extract_ndvi(config, select_sites, get_sentinel=True, masks=select_masks)
    if args.extract in ("all", "nhm"):
        extract_nhm_ssebop(config, select_sites, masks=select_masks)
    if args.extract in ("all", "gridmet"):
        extract_gridmet(config, select_sites)
