"""Container factory for building hindcast and forecast run containers.

Creates new containers from a calibrated source container, copying static
data (geometry, properties, calibrated parameters) and ingesting
time-varying data for a different date range.
"""

from __future__ import annotations

import os

from swimrs.container.container import SwimContainer


def create_run_container(
    config,
    mode: str,
    scenario: str | None = None,
    overwrite: bool = False,
    skip_health: bool = False,
) -> str:
    """Build a hindcast or forecast container from a calibrated source.

    Parameters
    ----------
    config : ProjectConfig
        Parsed project configuration with ``[hindcast]`` and/or
        ``[forecast]`` sections populated.
    mode : str
        ``"hindcast"`` or ``"forecast"``.
    scenario : str, optional
        Forecast scenario identifier (e.g. ``"rcp85_cesm"``).  Required
        when *mode* is ``"forecast"``.
    overwrite : bool
        If True, replace an existing run container.
    skip_health : bool
        If True, skip the post-build health check.

    Returns
    -------
    str
        Path to the newly created run container.
    """
    # Resolve source container
    source_path = config.container_path
    if not source_path or not os.path.exists(source_path):
        raise FileNotFoundError(f"Source (calibration) container not found: {source_path}")

    # Determine target parameters based on mode
    if mode == "hindcast":
        start_dt = config.hindcast_start_dt
        end_dt = config.hindcast_end_dt
        target_path = config.hindcast_container
        met_source = config.hindcast_met_source or config.met_source
        ndvi_mode = config.hindcast_ndvi_mode or "observed"
    elif mode == "forecast":
        if scenario is None:
            raise ValueError("scenario is required for forecast mode")
        start_dt = config.forecast_start_dt
        end_dt = config.forecast_end_dt
        target_path = config.forecast_container
        if target_path and "{scenario}" in target_path:
            target_path = target_path.replace("{scenario}", scenario)
        met_source = config.forecast_met_source or "gridmet"
        ndvi_mode = config.forecast_ndvi_mode or "climatology"
    else:
        raise ValueError(f"mode must be 'hindcast' or 'forecast', got {mode!r}")

    if start_dt is None or end_dt is None:
        raise ValueError(f"[{mode}] start_date and end_date are required in TOML")
    if not target_path:
        raise ValueError(f"[{mode}] container path is required in TOML")

    print(f"Building {mode} container: {target_path}")
    print(f"  Date range: {start_dt.date()} to {end_dt.date()}")
    if scenario:
        print(f"  Scenario: {scenario}")

    # Open source container
    source = SwimContainer.open(source_path, mode="r")
    target = None

    try:
        # Create target container with the new date range
        target = SwimContainer.create(
            target_path,
            fields_shapefile=config.fields_shapefile,
            uid_column=config.feature_id_col,
            start_date=str(start_dt.date()),
            end_date=str(end_dt.date()),
            project_name=config.project_name,
            overwrite=overwrite,
        )

        # Copy static data from calibration container:
        # properties, calibration params, ke_max, kc_max, gwsub_data
        target.copy_static_groups(source)
        print("  Copied static groups (properties, calibration, dynamics)")

        # Ingest meteorology
        _ingest_met(target, config, mode, met_source, scenario)

        # Ingest NDVI and compute irrigation dynamics
        _ingest_ndvi(target, source, config, mode, ndvi_mode)
        _compute_irr_dynamics(target, config, ndvi_mode)

        # No snow ingestion needed — SNODAS SWE observations are only
        # consumed during calibration. The snow model in hindcast/forecast
        # runs from met forcing alone using calibrated swe_alpha/swe_beta
        # parameters (copied via copy_static_groups). No snow_mode config
        # field is required.

        # Health check — run containers have no snow data (SWE is only
        # used during calibration), so exclude snow_source from the
        # health policy to avoid a spurious FAIL.
        if not skip_health:
            print("\n--- Health Check ---")
            health_config = {
                k: v
                for k, v in {
                    "mask_mode": getattr(config, "mask_mode", None),
                    "met_source": met_source,
                }.items()
                if v is not None
            }
            target.report(config=health_config, raise_on_fail=True)

        # Record provenance
        target.provenance.record(
            "create_run_container",
            source=source.uri,
            params={
                "mode": mode,
                "scenario": scenario,
                "start_date": str(start_dt.date()),
                "end_date": str(end_dt.date()),
                "met_source": met_source,
                "ndvi_mode": ndvi_mode,
            },
        )

        target.save()

    finally:
        if target is not None:
            target.close()
        source.close()

    print(f"Done: {target_path}")
    return target_path


def _ingest_met(
    target: SwimContainer,
    config,
    mode: str,
    met_source: str,
    scenario: str | None,
) -> None:
    """Ingest meteorology into the run container."""
    if met_source == "gridmet":
        # Both hindcast and forecast (when LOCA-VIC is in GridMET format)
        # use the same GridMET ingestor with the same or different met_dir
        if mode == "forecast" and config.forecast_met_dir:
            met_dir = config.forecast_met_dir
            if scenario and "{scenario}" in met_dir:
                met_dir = met_dir.replace("{scenario}", scenario)
        else:
            met_dir = config.met_dir

        if not met_dir or not os.path.isdir(met_dir):
            print(f"  WARNING: met directory not found: {met_dir}")
            return

        target.ingest.gridmet(
            met_dir,
            grid_shapefile=config.gridmet_mapping_shp,
            uid_column=config.feature_id_col,
            grid_column=config.gridmet_id_col or config.gridmet_mapping_index_col or "GFID",
            overwrite=True,
        )
        print(f"  Ingested meteorology ({met_source}) from {met_dir}")
    else:
        # TODO: add loca_vic ingestor when data format is finalized
        print(f"  WARNING: unsupported met_source '{met_source}' for {mode}")


def _ingest_ndvi(
    target: SwimContainer,
    source: SwimContainer,
    config,
    mode: str,
    ndvi_mode: str,
) -> None:
    """Ingest NDVI into the run container."""
    masks = ("irr", "inv_irr")

    if ndvi_mode == "observed":
        # Hindcast: ingest raw NDVI for the full period, then merge
        for mask in masks:
            ndvi_dir = os.path.join(config.landsat_dir or "", "extracts", "ndvi", mask)
            if os.path.isdir(ndvi_dir):
                target.ingest.ndvi(
                    ndvi_dir,
                    uid_column=config.feature_id_col,
                    instrument="landsat",
                    mask=mask,
                    overwrite=True,
                )
                print(f"  Ingested Landsat NDVI ({mask})")

        # Merge
        target.compute.merged_ndvi(masks=masks, instruments=("landsat",), overwrite=True)
        print("  Computed merged NDVI")

    elif ndvi_mode == "climatology":
        # Forecast: compute DOY climatology from source, tile across target
        target.compute.ndvi_climatology(
            source_container=source,
            masks=masks,
            overwrite=True,
        )
        print("  Computed NDVI climatology from source container")

        # Tile the 366-day climatology across the target time axis
        _tile_ndvi_climatology(target, masks)
        print("  Tiled NDVI climatology across forecast period")
    else:
        print(f"  WARNING: unknown ndvi_mode '{ndvi_mode}'")


def _compute_irr_dynamics(
    target: SwimContainer,
    config,
    ndvi_mode: str,
) -> None:
    """Compute irrigation windows (irr_data) for the target container.

    Uses only NDVI + irrigation properties (no ETf needed). ke_max,
    kc_max, and gwsub_data are already copied from the calibration
    container by copy_static_groups().
    """
    irr_threshold = getattr(config, "irrigation_threshold", None) or 0.3
    mask_mode = getattr(config, "mask_mode", None) or "irrigation"

    masks = ("irr", "inv_irr") if mask_mode == "irrigation" else ("no_mask",)

    if f"derived/merged_ndvi/{masks[0]}" not in target._root:
        print("  WARNING: merged_ndvi not found, skipping irr_data computation")
        return

    target.compute.compute_irr_data(
        irr_threshold=irr_threshold,
        masks=masks,
        use_mask=(mask_mode == "irrigation"),
        overwrite=True,
    )
    print(f"  Computed irrigation windows (irr_data) from {ndvi_mode} NDVI")


def _tile_ndvi_climatology(target: SwimContainer, masks: tuple[str, ...]) -> None:
    """Tile 366-day NDVI climatology across the container time axis as merged_ndvi."""
    time_index = target._time_index
    doys = time_index.dayofyear.values  # (n_days,)

    for mask in masks:
        clim_path = f"derived/ndvi_climatology/{mask}"
        out_path = f"derived/merged_ndvi/{mask}"

        if clim_path not in target._root:
            continue

        clim = target._root[clim_path][:]  # (366, n_fields)

        # Map DOY (1-366) to 0-based index
        tiled = clim[doys - 1, :]  # (n_days, n_fields)

        # Delete existing merged_ndvi if present (may exist from
        # copy_static_groups or a previous run)
        if out_path in target._root:
            del target._root[out_path]

        # Write as merged_ndvi so build_swim_input can find it
        arr = target._create_timeseries_array(out_path)
        arr[:, :] = tiled
