# Similar Work — Annotated Reference List

Papers most closely related to SWIM-RS, organized by methodological cluster.
These establish both the lineage and the novelty gap our paper fills.

---

## 1. RS-Driven Soil Water Balance with Satellite Kc/ETf

These papers use satellite vegetation indices or ET fractions to drive a
FAO-56-style soil water balance. They are the closest methodological
predecessors to SWIM-RS but operate at far smaller scales (1-2 sites) and
without formal inverse calibration.

### Campos et al. (2016) — Inverting Soil Water Capacity from RS-Driven Water Balance
Campos, I., Gonzalez-Piqueras, J., Carrara, A., Villodre, J., Calera, A.
(2016). Estimation of total available water in the soil layer by integrating
actual evapotranspiration data in a remote sensing-driven soil water balance.
*Journal of Hydrology*, 534, 427-439. [35 citations]

**Methods:** Ran a daily FAO-56 soil water balance driven by satellite-derived
actual ET and inverted total available water (TAW) by minimizing the mismatch
between modeled and RS-observed soil moisture depletion at a single irrigated
site in Spain.
**Findings:** The inverted TAW reproduced independent soil moisture probe
measurements with R2 > 0.80; the approach recovered physically plausible
hydraulic parameters from the ET signal alone without requiring soil sampling.
**Impact:** Most directly analogous to SWIM-RS in concept — using satellite ET
to invert soil water parameters — but limited to one site, one parameter, and
no ensemble uncertainty framework. SWIM-RS extends this to 160 sites, 8
parameters per site, and 200-member ensemble inversion.

### Padilla et al. (2011) — VI-Driven FAO-56 Water Balance for Corn and Wheat
Padilla, F.L.M., Gonzalez-Dugo, M.P., Gavilan, P., Dominguez, J. (2011).
Integration of vegetation indices into a water balance model to estimate
evapotranspiration of wheat and corn. *Hydrology and Earth System Sciences*,
15, 1213-1225. [39 citations]

**Methods:** Replaced tabulated Kcb curves with NDVI-derived basal crop
coefficients in the FAO-56 daily water balance for irrigated corn and wheat,
using both field radiometry and Landsat 5/7 imagery; validated against eddy
covariance and weighing lysimeters.
**Findings:** Daily ET overestimation averaged 8-11% with field radiometry and
6-9% with satellite NDVI; the model successfully detected water stress periods
during the 2009 growing season that correlated with observed yield reductions.
**Impact:** Demonstrated that satellite NDVI can replace field radiometry for
driving a dual-Kc water balance without significant accuracy loss, but operated
at only 2 sites with no formal parameter estimation — the Kc-NDVI relationship
was assumed, not calibrated.

### Er-Raki et al. (2007) — FAO-56 + Ground RS for Wheat ET
Er-Raki, S., Chehbouni, A., Guemouria, N., Duchemin, B., Ezzahar, J., Hadria, R.
(2007). Combining FAO-56 model and ground-based remote sensing to estimate water
consumptions of wheat crops in a semi-arid region. *Agricultural Water Management*,
87(1), 41-54. [294 citations]

**Methods:** Combined the FAO-56 dual Kc model with ground-measured NDVI to
derive spatially explicit basal crop coefficients for wheat in semi-arid Morocco,
replacing tabulated Kc values with NDVI-derived curves.
**Findings:** The NDVI-updated FAO-56 model reduced ET estimation error from
20-25% (tabulated Kc) to 8-12% (NDVI-derived Kc) when validated against eddy
covariance measurements.
**Impact:** Demonstrated the operational advantage of coupling FAO-56 soil water
balance with remote-sensing Kc in developing-world agricultural contexts. The
NDVI-Kc relationship was empirically tuned but not formally inverted or
uncertainty-quantified.

---

## 2. RS ET Data Assimilation into Hydrological/Land Surface Models

These papers assimilate satellite ET or related variables into process models
to estimate parameters. They share the inverse-modeling philosophy of SWIM-RS
but operate at watershed or continental scale with coarser-resolution data and
different model structures.

### Herman et al. (2018) — RS ET for Improving Hydrological Model Predictability
Herman, M.R., Nejadhashemi, A.P., Abouali, M., Hernandez-Suarez, J.S.,
Daneshvar, F., Zhang, Z., Anderson, M.C., Sadeghi, A.M., Hain, C.R.,
Sharifi, A. (2018). Evaluating the role of evapotranspiration remote sensing
data in improving hydrological modeling predictability. *Journal of Hydrology*,
556, 39-49. [146 citations]

**Methods:** Calibrated the SWAT watershed model using DisALEXI satellite ET
in addition to streamflow, testing whether RS ET data improves predictions of
distributed water balance components across multiple sub-basins.
**Findings:** Adding RS ET to calibration improved spatial ET predictions
(NSE 0.4-0.7) over streamflow-only calibration, particularly in headwater
catchments with sparse gauging; streamflow accuracy was maintained.
**Impact:** Showed that satellite ET constrains hydrological model parameters
more effectively than streamflow alone, supporting the use of RS ET as a
calibration target. Differs from SWIM-RS in model type (watershed vs field-scale
soil water), spatial scale, and calibration method (SWAT-CUP vs PEST++ IES).

### Khaki et al. (2020) — Multi-Satellite Data Assimilation for Land Model Parameters
Khaki, M., Hendricks Franssen, H.-J., Han, S.-C. (2020). Multi-mission satellite
remote sensing data for improving land hydrological models via data assimilation.
*Scientific Reports*, 10, 18791. [53 citations]

**Methods:** Used an unsupervised weak-constrained ensemble Kalman filter
(UWCEnKF) to simultaneously assimilate soil moisture (SMOS, AMSR-E), terrestrial
water storage (GRACE), and LAI (AVHRR) into a land surface model, jointly
estimating states and parameters over the Murray-Darling and Mississippi basins.
**Findings:** Multi-variable assimilation with parameter estimation reduced
groundwater RMSE by ~32% and increased soil moisture correlation from 0.66 to
0.85 during calibration; improvements persisted during forecast (14% RMSE
reduction), demonstrating durable parameter learning.
**Impact:** Closest to SWIM-RS in its ensemble-based parameter estimation from
RS data, but operates at continental scale (~25 km) with land surface model
physics. SWIM-RS uses field-scale (30 m) Landsat ETf and a simpler soil water
model with PEST++ IES, targeting irrigation management rather than large-scale
hydrology.

### Olioso et al. (1999) — RS Data Assimilation into SVAT Models
Olioso, A., Chauki, H., Courault, D., Wigneron, J.-P. (1999). Estimation of
evapotranspiration and photosynthesis by assimilation of remote sensing data into
SVAT models. *Remote Sensing of Environment*, 68(3), 341-356. [180 citations]

**Methods:** Assimilated surface temperature, NDVI, and microwave brightness
temperature into a soil-vegetation-atmosphere transfer (SVAT) model to estimate
soil hydraulic and vegetation parameters using variational data assimilation.
**Findings:** Assimilation of thermal IR data improved ET estimates by 20-40%
over open-loop runs; combining visible and thermal data provided complementary
constraints on vegetation and soil parameters.
**Impact:** Established the theoretical framework for RS data assimilation into
physically based land surface models. Published in RSE. Differs from SWIM-RS in
using variational (adjoint) methods rather than ensemble inversion, and in
operating at point/patch scale rather than across many sites.

### Boegh et al. (2009) — RS-Based ET and Runoff Modeling Across Land Covers
Boegh, E., Poulsen, R.N., Butts, M., Abrahamsen, P., Dellwik, E., Hansen, S.,
Hasager, C.B., Ibrom, A., Loerup, J.-K., Pilegaard, K., Soegaard, H. (2009).
Remote sensing based evapotranspiration and runoff modeling of agricultural, forest
and urban flux sites in Denmark: from field to macro-scale. *Journal of Hydrology*,
377(3-4), 300-316. [78 citations]

**Methods:** Drove a process-based soil-vegetation-atmosphere model with Landsat
and MODIS data across agricultural, forest, and urban flux sites in Denmark,
evaluating ET and runoff predictions at field to catchment scales.
**Findings:** RS-driven ET achieved R2 of 0.7-0.9 against flux tower measurements
across land cover types; accuracy degraded from field to catchment scale due to
sub-pixel heterogeneity and mixed pixels.
**Impact:** One of few studies to evaluate RS-driven process models across
multiple land cover types (agriculture, forest, urban) at the field scale,
analogous to SWIM-RS's multi-LULC evaluation. However, no formal parameter
inversion was performed — the model used literature parameters.

---

## 3. Multi-Site ET Model Intercomparison and Benchmarking

These papers define the accuracy benchmarks and evaluation methodology that
SWIM-RS builds upon and competes against.

### Volk et al. (2024) — OpenET Accuracy Assessment
Volk, J.M., Huntington, J.L., Melton, F.S., Allen, R., Anderson, M., Fisher,
J.B., Kilic, A., Ruhoff, A., Senay, G.B., et al. (2024). Assessing the accuracy
of OpenET satellite-based evapotranspiration data to support water resource and
land management applications. *Nature Water*, 2, 193-205. [112 citations]

**Methods:** Evaluated OpenET outputs (6 models + ensemble) against 152 eddy
covariance flux stations across CONUS, covering croplands, shrublands, and
forests — the largest independent satellite ET accuracy assessment to date.
**Findings:** Cropland ensemble MAE is 15.8 mm/month (17% of mean ET), MBE is
-5.3 mm/month, and R2 is 0.90; inter-model variability and error increase
substantially for non-cropland land covers.
**Impact:** Provides the benchmark dataset and accuracy statistics against which
SWIM-RS is directly compared. Our 45-site cropland comparison uses the same Volk
3x3 extraction methodology. The non-cropland accuracy gap identified by Volk
motivates SWIM-RS's multi-LULC evaluation (160 sites, 6 land cover classes).

### Gonzalez-Dugo et al. (2009) — Comparison of Operational RS ET Models
Gonzalez-Dugo, M.P., Neale, C.M.U., Mateos, L., Kustas, W.P., Prueger, J.H.,
Anderson, M.C., Li, F. (2009). A comparison of operational remote sensing-based
models for estimating crop evapotranspiration. *Irrigation Science*, 28(1), 87-98.
[219 citations]

**Methods:** Compared four operational satellite ET models (TSEB, METRIC, VI-Kc,
and SEBAL) against tower flux data over irrigated corn and soybean in Iowa.
**Findings:** All models reproduced daily ET within 10-20%, but energy balance
models (TSEB, METRIC) outperformed VI-Kc under advective conditions while VI-Kc
was more robust under cloudy-sky data gaps.
**Impact:** Established the methodology of head-to-head multi-model comparison
at flux tower sites that OpenET and SWIM-RS both extend. Limited to a single
site — SWIM-RS performs this comparison at 45-160 sites.

---

## 4. SSEBop ETf as a Calibration Signal

These papers characterize the ET fraction (ETf) product that SWIM-RS uses as
its primary calibration target.

### Senay et al. (2013) — SSEBop
Senay, G.B., Bohms, S., Singh, R.K., Gowda, P.H., Velpuri, N.M., Alemu, H.,
Verdin, J.P. (2013). Operational evapotranspiration mapping using remote sensing
and weather datasets: a new parameterization for the SSEB approach. *Journal of the
American Water Resources Association*, 49(3), 577-591. [552 citations]

**Methods:** Parameterized the SSEBop model to express ET as the product of
reference ET and a thermal-based ET fraction (ETf), using pre-defined hot/cold
reference temperatures derived from climate normals.
**Findings:** SSEBop reproduced daily ET within 10-20% and seasonal ET within
5-10% across CONUS when validated against eddy covariance flux towers.
**Impact:** Defined the ETf concept that SWIM-RS uses as its calibration target.
The ETf is a dimensionless ratio (0-1) representing the fraction of reference ET
achieved by a given pixel, analogous to the crop coefficient but derived from
thermal remote sensing rather than lookup tables.

### Chen et al. (2016) — SSEBop Uncertainty Analysis at Multiple Flux Tower Sites
Chen, M., Senay, G.B., Singh, R.K., Verdin, J.P. (2016). Uncertainty analysis of
the Operational Simplified Surface Energy Balance (SSEBop) model at multiple flux
tower sites. *Journal of Hydrology*, 536, 384-399. [84 citations]

**Methods:** Performed sensitivity and uncertainty analysis of the SSEBop model
at 42 AmeriFlux tower sites across diverse biomes and climates, using MODIS LST
and tower meteorological data.
**Findings:** SSEBop achieved R2 = 0.86 overall and R2 = 0.92 for croplands
(RMSE = 13 mm/month); random errors from input variables and parameters produced
monthly ET estimates with relative errors < 20% across biomes. Model is most
sensitive to LST, ETo, differential temperature (dT), and maximum ET scalar.
**Impact:** Validates the SSEBop ETf signal that SWIM-RS calibrates against,
establishing that the signal has sufficient accuracy and precision to serve as
a calibration target. The 42-site, multi-biome evaluation parallels SWIM-RS's
own multi-site design.

---

## Summary: The Gap SWIM-RS Fills

| Dimension | Closest prior work | SWIM-RS |
|-----------|-------------------|---------|
| Inverse calibration | Campos 2016 (1 site, 1 param) | 160 sites, 8 params/site |
| Ensemble uncertainty | Khaki 2020 (EnKF, ~25 km) | PEST++ IES, 200 members, 30 m |
| RS-driven soil water balance | Padilla 2011 (2 sites, no inversion) | 160 sites, formal inversion |
| Multi-LULC validation | Boegh 2009 (3 land covers, no inversion) | 6 land cover classes |
| Benchmark against OpenET | Volk 2024 (RS models only) | Process model vs 6 RS models |
| Head-to-head at scale | Gonzalez-Dugo 2009 (1 site, 4 models) | 45-160 sites, 8 models |

No published work combines formal ensemble inverse modeling of soil water
parameters against satellite ETf, at >100 sites across multiple land covers,
with a head-to-head benchmark against the full OpenET model suite.
