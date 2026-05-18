## SWIM-RS: Project Overview

SWIM-RS (Soil Water Inverse Modeling with Remote Sensing) is a field-scale hydrological
modeling framework that calibrates a daily soil water balance directly against satellite
observations of evapotranspiration. Remote sensing provides spatially explicit snapshots of
crop water use on overpass dates; a process-based water balance enforces conservation of
mass and simulates fluxes on every day between those snapshots, including cloudy or smoky
periods when optical and thermal imagery are sparse or unusable. Rather than adding another
satellite ET algorithm to an already mature retrieval literature, SWIM-RS uses
satellite-derived ET fraction (ETf) as a calibration target rather than a final product,
yielding a forward model whose parameters are constrained by what the satellites actually
observed while adding explicit water-balance constraints, continuous daily output, and
modeled estimates of consumptive use.

The process engine is a vectorized FAO-56 soil water balance that steps through every day
and every field in parallel, sequencing roughly twenty Numba-compiled physics kernels: snow
partitioning, SCS runoff, crop-coefficient estimation, soil evaporation, root-zone
transpiration with water stress, irrigation demand, deep percolation, and multi-layer
storage. A forty-year run on a single field completes in under a second.

Remote sensing is the primary observational backbone of the framework. SWIM-RS ingests
field-level zonal statistics from three instrument families — Landsat 8/9 (30 m, ~16-day
revisit), Sentinel-2A/B (10 m, ~5-day revisit), and ECOSTRESS aboard the ISS (70 m,
irregular diurnal sampling) — all extracted via Google Earth Engine. Landsat and Sentinel
surface reflectance are harmonized using spectral band adjustment factors and combined into
a fused NDVI record that resolves within-season phenology at roughly weekly cadence. These
NDVI time series drive the crop coefficient through a calibrated sigmoid curve, replacing
the tabulated phenology schedules that traditional FAO-56 implementations rely on. This
means the model sees actual field-level vegetation development — late plantings, failed
crops, double-cropping, perennial orchards — rather than a regional average.

The calibration targets themselves are capture-date ET fraction (ETf) values produced by six
OpenET algorithms: SSEBop (thermal-based scaling), PT-JPL (Priestley-Taylor with
ecophysiological constraints), SIMS (reflectance-based crop coefficients), disALEXI
(atmospheric boundary-layer disaggregation), eeMETRIC (energy-balance with internal
calibration), and geeSEBAL (surface energy balance). Each algorithm processes Landsat or
Sentinel scenes independently; SWIM-RS can calibrate against any single model or an
ensemble mean, and when ensemble members are available it uses the full member set to
estimate inter-model spread and weight capture-date observations so high-consensus dates
carry more influence than dates where the algorithms disagree. For ECOSTRESS, daily ET
retrievals are converted to ETf by dividing by
ERA5-derived reference ET, extending the observation stream beyond sun-synchronous
platforms. Because ETf normalizes actual ET by reference ET, it isolates the crop and soil
signal from day-to-day weather variation and provides a dimensionless target that is
comparable across climates and instruments. Irrigation status masks derived from IrrMapper
(western U.S.) and LANID (eastern U.S.) allow the framework to treat irrigated and
non-irrigated pixels separately during both extraction and calibration, while a no-mask
workflow supports international sites where those U.S.-specific layers do not exist.

Calibration uses PEST++ IES (Iterative Ensemble Smoother), a Bayesian method that updates
an ensemble of parameter realizations against the satellite ETf observations. Calibrated
parameters include available water capacity, the NDVI-sigmoid shape, evaporation and stress
damping coefficients, and snow-melt factors. Each field is calibrated independently, and the
ensemble yields parameter uncertainty that propagates into uncertainty on simulated ET,
irrigation, and recharge.

All input data — remote sensing time series, gridded meteorology (GridMET for CONUS,
ERA5-Land for international sites), soil properties (SSURGO, HWSD), and SNODAS snow water
equivalent — are organized in a Zarr-based container with provenance tracking and
completeness checks that flag null-filled extractions before they propagate into
calibration. After calibration, the median posterior parameters drive a production run
whose outputs (actual ET, simulated irrigation, deep percolation, and an irrigation-
fraction tracer that partitions consumptive use into precipitation-supplied and
irrigation-supplied components) are written back to the container for export.

Validation against independent flux towers shows that the process model adds skill beyond
the satellite products used as calibration targets. In the current paired Example 4 flux
network benchmark, SWIM-RS is evaluated against energy-balance-corrected ET at 159 sites
daily and 143 sites monthly, with SSEBop scored on the exact same valid days and months.
SWIM-RS reaches a median daily R² of 0.47 and median RMSE of 1.01 mm/day, compared with
0.42 and 1.09 mm/day for SSEBop, and it wins 60% of sites on R². At the
monthly scale, median R² rises to 0.56 with median RMSE of 20.9 mm/month, versus 0.52 and
25.0 mm/month for SSEBop, with a 66% site-level win rate.

The cropland-focused Example 5 study tests whether a multimodel calibration target improves
performance beyond any single OpenET algorithm. In the canonical paired benchmark, SWIM-RS
is calibrated against the mean ETf of six OpenET Landsat models and compared against the
Volk et al. 3×3 ensemble ET product on the exact same valid observations. This matters
because OpenET evaluations have already shown that multimodel ensemble ET generally matches
or exceeds individual-model accuracy. SWIM-RS takes advantage of that result in a stronger
way than simply adopting a precomputed ensemble mean or MAD-style summary product: the six
member ETf series also define capture-date weights from inter-model spread, so calibration
leans more heavily on dates where the ensemble members agree. Across 58 paired sites at the
daily scale, SWIM-RS attains mean and median R² values of 0.392 and 0.652 with mean RMSE of
1.28 mm/day, improving on the ensemble's 0.323 and 0.567 with 1.38 mm/day RMSE. Across 33
paired sites at the monthly scale, SWIM-RS posts slightly higher mean R² (0.814 versus
0.799), nearly identical RMSE (21.45 versus 21.22 mm/month), and far smaller bias (-0.77
versus -5.88 mm/month), showing that assimilating ensemble ETf can recover a temporally
continuous ET signal while sharply reducing systematic underestimation.

That validation framework now extends beyond CONUS-only inputs. The international Example 6
workflow replaces GridMET and SSURGO with ERA5-Land meteorology and HWSD soils; fuses
Landsat and Sentinel NDVI; and operates in no-mask mode using globally available inputs.
The publication-track experiment calibrates 75 cropland flux sites spanning North America,
Europe, Australia, and South America against a Landsat SSEBop + PT-JPL ensemble mean ETf
over the 2013-2025 period of record. In the paired daily benchmark (71 sites with
independent flux validation), SWIM-RS reaches a median R² of 0.62 and median KGE of 0.70,
with near-zero bias (-0.04 mm/day). SWIM-RS beats native Landsat SSEBop on 64% of sites
and matches native PT-JPL, though the interpolated ensemble benchmark slightly outperforms
SWIM-RS on aggregate (median R² 0.65), as expected for a product derived from the
calibration target itself. In other words, SWIM-RS is not limited to U.S. irrigation
products or national gridded forcings: the same inverse-modeling architecture can be
deployed across multiple continents with a consistent global data stack. That design also
helps define the framework's boundary conditions: saturated or open-water wetlands can be
poor targets for a soil water balance model because lateral inflows and standing water can
dominate the local water balance, and because open water violates the assumed monotonic
NDVI-to-Kcb relationship by pairing low NDVI with high ET.

The result is a system that inherits the spatial resolution of satellite remote sensing, the
temporal continuity of a soil water balance, and the statistical rigor of ensemble parameter
estimation — without requiring flux tower data for calibration.
