# Changelog

All notable changes to SWIM-RS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `mask_mode` configuration parameter: `"none"` uses unmasked NDVI/ETf, `"irrigation"` splits by irrigation mask
- `ensemble_source` flag: choose pre-computed OpenET ensemble or DIY mean of individual models
- Full 6-model OpenET ETf pipeline: SSEBop, PT-JPL, SIMS, geeSEBAL, eeMETRIC, DisALEXI (v2.1)
- EE asset copy and extraction scripts (`copy_openet_assets.py`, `etf_asset_extract.py`)
- Volk 3×3 daily/monthly benchmarking in `evaluate.py` across all 6 OpenET models
- Monthly ET evaluation mode (`evaluate.py --monthly`)
- ETf-vs-ETf comparison mode (`evaluate.py --etf`)
- NDVI/ETf container guardrails: calibration fails early if required mask variants are missing
- Example 4 modernized: new `evaluate.py`, `setup_shapefile.py`, SSEBop NHM extraction
- Example 5 Run 11 reference calibration: 60 US cropland sites, 1995–2025, 8-param PEST++ IES
- Example 6 ECOSTRESS ETf conversion and publication figure scripts
- SID (Statewide Irrigation Dataset) extraction and diagnostic scripts
- `test_ingestor.py` unit tests

### Changed
- Root depth and perennial flag sourced from container land-cover lookup; removed `zr_mult` PEST parameter
- Dropped `m_kc` multiplier from PEST parameter set (8 params/site, down from 10)
- Raised kc_max floor from 1.25 to 1.35
- Raised max_irr_rate from 25 to 100 mm/day
- Example 5 extended from 2016–2025 to 1995–2025 (11,323 days)
- Example 5 consolidated: replaced `calibrate_by_station.py`, `evaluate_group.py`, `openet_evaluation.py`, `run.py` with unified `calibrate.py` and `evaluate.py`
- Removed container `workflow/` subpackage (~1,175 lines of unused orchestration code)
- Removed `viz/__init__.py` (unused)
- CLI integration tests refactored and simplified

### Fixed
- irr_flag NDVI fallback: include `ndvi_no_mask` in lookup so irrigation is not suppressed in no-mask mode
- `data_extract.py`: guard `runoff_process` config attribute with `getattr` fallback
- GridMET single-cell squeeze bug
- Substring match bug in `_drop_conflicts` causing KeyError on field `S2`
- `load_openet_etf`: treat all-NaN `inv_irr` as missing, fall back to `irr`
- Obs pipeline: export real ETf targets from container, not SWIM baseline output

## [0.1.0] - 2025-01-28

### Added
- Initial public release
- SwimContainer API for Zarr-based data management with provenance tracking
- CLI commands: `swim extract`, `swim prep`, `swim calibrate`, `swim evaluate`, `swim inspect`
- Numba-accelerated FAO-56 simulation kernels
- PEST++ IES integration for ensemble calibration via pyemu
- Earth Engine data extraction for Landsat/Sentinel NDVI and OpenET ETf
- GridMET and ERA5-Land meteorology support
- SNODAS snow water equivalent integration
- Five complete examples (Boulder, Fort Peck, Crane, Flux Network, Flux Ensemble)
- MkDocs documentation site with API reference
- CI/CD via GitHub Actions with Codecov integration

[Unreleased]: https://github.com/dgketchum/swim-rs/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dgketchum/swim-rs/releases/tag/v0.1.0
