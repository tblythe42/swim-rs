"""Container factory for building hindcast and forecast run containers.

Creates new containers from a calibrated source container, copying static
data (geometry, properties, calibrated parameters) and ingesting
time-varying data for a different date range.
"""

from __future__ import annotations

import os
import tempfile

import geopandas as gpd
import numpy as np
import pandas as pd

from swimrs.container.container import SwimContainer
from swimrs.container.health import health_report_output_dir
from swimrs.container.runs import STATE_FIELDS, SimulationRunResult

CANONICAL_CALIBRATION_RESTART_RUN_ID = "calibration_resolved_state"
CANONICAL_HINDCAST_RESTART_RUN_ID = "hindcast_initial_state"
DEFAULT_HINDCAST_INIT_STRATEGY = "cyclic_spinup"
DEFAULT_HINDCAST_INIT_WINDOW_YEARS = 5
DEFAULT_HINDCAST_INIT_MAX_CYCLES = 6
DEFAULT_HINDCAST_INIT_TOLERANCE = 1e-3


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
    tmp_shp_dir = None

    try:
        # Match target fields to source — the source may have excluded
        # degenerate FIDs at build time (e.g. --exclude-fids 1416).
        fields_shp = config.fields_shapefile
        source_uids = set(source._root["geometry/uid"][:])
        gdf = gpd.read_file(fields_shp, engine="fiona")
        shp_uids = set(gdf[config.feature_id_col].astype(str))
        extra = shp_uids - source_uids
        if extra:
            gdf = gdf[~gdf[config.feature_id_col].astype(str).isin(extra)]
            tmp_shp_dir = tempfile.mkdtemp(prefix="swim_filtered_shp_")
            fields_shp = os.path.join(tmp_shp_dir, "filtered_fields.shp")
            gdf.to_file(fields_shp, engine="fiona")
            print(f"  Excluded {len(extra)} FIDs not in source: {sorted(extra)}")

        # Create target container with the new date range
        target = SwimContainer.create(
            target_path,
            fields_shapefile=fields_shp,
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
            target.report(
                config=health_config,
                raise_on_fail=True,
                output_dir=str(health_report_output_dir(target.uri)),
                health_profile="forward_run",
            )

        default_restart_run_id = _configure_default_restart(
            target=target,
            source=source,
            config=config,
            mode=mode,
            start_dt=start_dt,
            met_source=met_source,
            ndvi_mode=ndvi_mode,
        )

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
                "default_restart_run_id": default_restart_run_id,
            },
        )

        target.save()

    finally:
        if target is not None:
            target.close()
        source.close()
        if tmp_shp_dir is not None:
            import shutil

            shutil.rmtree(tmp_shp_dir, ignore_errors=True)

    print(f"Done: {target_path}")
    return target_path


def _configure_default_restart(
    *,
    target: SwimContainer,
    source: SwimContainer,
    config,
    mode: str,
    start_dt,
    met_source: str,
    ndvi_mode: str,
) -> str | None:
    """Set up the target container's default restart state."""
    if mode == "forecast":
        return _copy_forecast_restart(
            target=target,
            source=source,
            forecast_start=pd.Timestamp(start_dt),
        )
    if mode == "hindcast":
        return _build_hindcast_initializer(
            target=target,
            config=config,
            met_source=met_source,
            ndvi_mode=ndvi_mode,
        )
    return None


def _copy_forecast_restart(
    *,
    target: SwimContainer,
    source: SwimContainer,
    forecast_start: pd.Timestamp,
) -> str | None:
    """Copy the source container's canonical restart state into a forecast container."""
    source_run_id = source.runs.default_restart_run_id()
    if source_run_id is None:
        candidate_path = f"simulation/runs/{CANONICAL_CALIBRATION_RESTART_RUN_ID}"
        if candidate_path in source._root:
            source_run_id = CANONICAL_CALIBRATION_RESTART_RUN_ID
    if source_run_id is None:
        print("  No source restart run found; forecast container will use cold-start defaults")
        return None

    source_meta = source.runs.metadata(source_run_id)
    run_end = pd.Timestamp(source_meta["end_date"])
    if run_end > forecast_start:
        raise ValueError(
            "Source restart state ends after forecast start date: "
            f"{run_end.date()} > {forecast_start.date()}"
        )
    if run_end != source.end_date.normalize():
        print(
            "  WARNING: source default restart does not end at the calibration container end "
            f"date ({run_end.date()} vs {source.end_date.date()})"
        )

    copied_run_id = target.runs.copy_from(
        source,
        source_run_id,
        overwrite=True,
        set_as_default=True,
    )
    print(f"  Copied restart state from source run '{source_run_id}'")
    return copied_run_id


def _build_hindcast_initializer(
    *,
    target: SwimContainer,
    config,
    met_source: str,
    ndvi_mode: str,
) -> str:
    """Generate and persist the hindcast default restart state."""
    strategy = (
        (
            getattr(config, "hindcast_initialization_strategy", None)
            or DEFAULT_HINDCAST_INIT_STRATEGY
        )
        .strip()
        .lower()
    )
    if strategy not in {"cyclic_spinup", "cold_start"}:
        raise ValueError(
            "hindcast initialization strategy must be 'cyclic_spinup' or 'cold_start', "
            f"got {strategy!r}"
        )

    window_years = int(
        getattr(config, "hindcast_initialization_window_years", None)
        or DEFAULT_HINDCAST_INIT_WINDOW_YEARS
    )
    max_cycles = int(
        getattr(config, "hindcast_initialization_cycles", None) or DEFAULT_HINDCAST_INIT_MAX_CYCLES
    )
    tolerance = float(
        getattr(config, "hindcast_initialization_tolerance", None)
        or DEFAULT_HINDCAST_INIT_TOLERANCE
    )

    window_start = target.start_date.normalize()
    window_end = min(
        (window_start + pd.DateOffset(years=window_years) - pd.Timedelta(days=1)).normalize(),
        target.end_date.normalize(),
    )

    common_kwargs = {
        "profile": "state_only",
        "engine": "python",
        "persist": False,
        "use_default_restart": False,
        "start_date": str(window_start.date()),
        "end_date": str(window_end.date()),
        "refet_type": getattr(config, "refet_type", "eto") or "eto",
        "etf_model": getattr(config, "etf_target_model", "ssebop") or "ssebop",
        "met_source": met_source,
        "mask_mode": getattr(config, "mask_mode", "irrigation") or "irrigation",
        "ndvi_mode": ndvi_mode,
    }

    last_result: SimulationRunResult | None = None
    previous_state: dict[str, np.ndarray] | None = None
    convergence_metric = np.inf
    converged = False
    cycles_completed = 0

    target_cycles = max_cycles if strategy == "cyclic_spinup" else 1
    for cycle in range(1, target_cycles + 1):
        result = target.run(spinup_state=previous_state, **common_kwargs)
        cycles_completed = cycle
        if last_result is not None:
            convergence_metric = _max_state_delta(last_result.final_state, result.final_state)
            if strategy == "cyclic_spinup" and convergence_metric <= tolerance:
                last_result = result
                converged = True
                break
        last_result = result
        previous_state = _state_to_dict(result.final_state)

    if last_result is None:
        raise RuntimeError("Failed to generate hindcast initializer state")

    last_result.run_id = CANONICAL_HINDCAST_RESTART_RUN_ID
    target.runs.persist_result(
        last_result,
        overwrite=True,
        refet_type=common_kwargs["refet_type"],
        etf_model=common_kwargs["etf_model"],
        met_source=met_source,
        mask_mode=common_kwargs["mask_mode"],
        ndvi_mode=ndvi_mode,
        command="create_run_container",
        run_attrs={
            "run_role": "initialization",
            "source_context": "hindcast_build",
            "initialization_strategy": strategy,
            "window_start": str(window_start.date()),
            "window_end": str(window_end.date()),
            "n_cycles": cycles_completed,
            "converged": converged,
            "convergence_metric": (
                None if not np.isfinite(convergence_metric) else float(convergence_metric)
            ),
        },
    )
    target.runs.set_default_restart(CANONICAL_HINDCAST_RESTART_RUN_ID)
    print(
        "  Generated hindcast restart state "
        f"({strategy}, {cycles_completed} cycle{'s' if cycles_completed != 1 else ''})"
    )
    return CANONICAL_HINDCAST_RESTART_RUN_ID


def _state_to_dict(state) -> dict[str, np.ndarray]:
    """Convert WaterBalanceState into a plain spinup-state mapping."""
    return {
        name: np.asarray(getattr(state, name), dtype=np.float64).copy() for name in STATE_FIELDS
    }


def _max_state_delta(previous_state, current_state) -> float:
    """Return the maximum absolute state delta between two runs."""
    deltas = []
    for field_name in STATE_FIELDS:
        deltas.append(
            np.max(
                np.abs(
                    np.asarray(getattr(current_state, field_name), dtype=np.float64)
                    - np.asarray(getattr(previous_state, field_name), dtype=np.float64)
                )
            )
        )
    return float(max(deltas)) if deltas else 0.0


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
