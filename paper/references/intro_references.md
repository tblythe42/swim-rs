# Introduction References — Annotated List

Ordered to follow the planned introduction arc: FAO-56 dual crop coefficient
framework and its global impact, lookup-table Kc curves, remote-sensing-derived
Kc curves, remote sensing ET broadly, Landsat-resolution ET algorithms, and OpenET.

---

## 1. FAO-56 Dual Crop Coefficient: Foundations and Global Impact

### Allen et al. (2005) — FAO-56 Dual Crop Coefficient Method
Allen, R.G., Pereira, L.S., Smith, M., Raes, D., Wright, J.L. (2005).
FAO-56 Dual Crop Coefficient Method for Estimating Evaporation from Soil
and Application Extensions. *Journal of Irrigation and Drainage Engineering*,
131(1), 2-13. [599 citations]

**Methods:** Extends the FAO-56 dual crop coefficient approach, partitioning ET
into basal crop transpiration (Kcb x ETo) and soil evaporation (Ke x ETo) using
a daily soil water balance to track top-layer soil moisture.
**Findings:** The dual Kc method reproduces measured ET within 5-10% for a range
of crops and climates, performing substantially better than the single Kc approach
during periods of significant soil evaporation or water stress.
**Impact:** Became the standard operational framework for irrigation scheduling
worldwide, adopted by FAO, ASCE, and most national agencies as the basis for
crop water requirement estimation.

### Pereira et al. (2015) — Crop Evapotranspiration Estimation with FAO56: Past and Future
Pereira, L.S., Allen, R.G., Smith, M., Raes, D. (2015). Crop evapotranspiration
estimation with FAO56: Past and future. *Agricultural Water Management*, 147,
4-20. [710 citations]

**Methods:** Comprehensive review of 17 years of FAO-56 applications across
climates and cropping systems, covering both the single and dual Kc methods
along with major extensions (stress coefficients, partial ground cover, mulch).
**Findings:** The FAO-56 framework is the most widely used ET estimation method
globally, but tabulated Kc values introduce systematic errors because they cannot
capture site-specific cultivar, planting density, and management variability.
**Impact:** Explicitly identified the need for spatially and temporally adaptive
Kc values as the key limitation of the lookup-table approach, motivating the
shift to remote-sensing-based crop coefficients.

### Allen (2000) — Using the FAO-56 Dual Crop Coefficient Method
Allen, R.G. (2000). Using the FAO-56 dual crop coefficient method over an
irrigated region as part of an evapotranspiration intercomparison study.
*Journal of Hydrology*, 229(1-2), 27-41. [481 citations]

**Methods:** Applied the FAO-56 dual Kc method across a diverse irrigated region
in southern Idaho as part of a multi-model ET intercomparison, using local
weather, soil, and crop management data.
**Findings:** The dual Kc approach performed well against lysimeter measurements
and was competitive with more data-intensive energy balance models, validating
its applicability at the regional scale.
**Impact:** Demonstrated that the FAO-56 dual Kc framework could be extended
from field to regional water balance assessments, motivating subsequent
large-scale applications.

---

## 2. Establishing Kc Curves with Lookup Tables and Lysimeters

### Allen et al. (2001) — Revised FAO Procedures for Calculating Evapotranspiration
Allen, R.G., Smith, M., Pereira, L.S., Raes, D., Wright, J.L. (2001). Revised
FAO Procedures for Calculating Evapotranspiration — Irrigation and Drainage Paper
No. 56 with Testing in Idaho. *ASCE Environmental and Water Resources Institute*
(EWRI). [543 citations]

**Methods:** Tested the FAO-56 computational procedures against high-quality
lysimeter data in southern Idaho, covering alfalfa, sugar beet, dry beans, and
other crops across multiple growing seasons.
**Findings:** Tabulated Kc values reproduced seasonal ET within approximately
10-15% for well-managed crops, but required local adjustment of Kc mid-season
and Kc end values to account for cultivar and management differences.
**Impact:** Provided the definitive validation dataset for FAO-56 tabulated
values and established the operational procedures adopted by ASCE and most US
state irrigation guides.

### Piccinni et al. (2009) — Growth-Stage Kc of Maize and Sorghum
Piccinni, G., Ko, J., Marek, T., Howell, T. (2009). Determination of
growth-stage-specific crop coefficients (Kc) of maize and sorghum. *Agricultural
Water Management*, 96(12), 1698-1704. [136 citations]

**Methods:** Used weighing lysimeters in the Texas High Plains to derive
growth-stage-specific Kc values for irrigated maize and sorghum across multiple
growing seasons, comparing results to FAO-56 tabulated curves.
**Findings:** Measured Kc values differed from FAO-56 defaults by 5-20% depending
on growth stage, with the largest deviations during early and late season when
local soil and management conditions dominate.
**Impact:** Showed that site-specific lysimeter calibration substantially improves
ET estimation accuracy but is too expensive and labor-intensive to scale beyond
individual research stations, motivating remote sensing alternatives.

---

## 3. Establishing Kc Curves Using Remote Sensing

### Hunsaker et al. (2003) — Cotton Kc from Multispectral Vegetation Index
Hunsaker, D.J., Pinter, P.J., Barnes, E.M., Kimball, B.A. (2003). Estimating
cotton evapotranspiration crop coefficients with a multispectral vegetation index.
*Irrigation Science*, 22(2), 95-104. [220 citations]

**Methods:** Used ground-based multispectral reflectance to derive a vegetation
index and established a linear relationship with crop coefficients for irrigated
cotton over multiple seasons in Arizona.
**Findings:** The VI-based Kc tracked lysimeter-measured Kc with R2 > 0.9 across
planting densities and irrigation treatments, demonstrating that spectral
reflectance directly captures canopy development that drives transpiration.
**Impact:** First rigorous demonstration that vegetation indices could replace
tabulated Kc curves, laying the foundation for satellite-based crop coefficient
estimation.

### Hunsaker et al. (2005) — Wheat Kcb from NDVI
Hunsaker, D.J., Pinter, P.J., Kimball, B.A. (2005). Wheat basal crop
coefficients determined by normalized difference vegetation index. *Irrigation
Science*, 24(1), 1-14. [166 citations]

**Methods:** Extended the VI-Kc relationship to wheat using NDVI from ground
reflectance measurements, deriving basal crop coefficients (Kcb) aligned with
the FAO-56 dual Kc framework.
**Findings:** NDVI-based Kcb estimates matched lysimeter-derived Kcb within
RMSE < 0.10 throughout the crop cycle, including during water stress periods
where tabulated values failed.
**Impact:** Established the NDVI-Kcb linear relationship that became the
standard approach for satellite-based irrigation scheduling.

### Er-Raki et al. (2007) — FAO-56 + Ground-Based RS for Wheat ET
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
balance with remote-sensing Kc in developing-world agricultural contexts where
lysimeter data are unavailable.

### Glenn et al. (2011) — VI-Based Crop Coefficients Review
Glenn, E.P., Neale, C.M.U., Hunsaker, D.J., Nagler, P.L. (2011). Vegetation
index-based crop coefficients to estimate evapotranspiration by remote sensing in
agricultural and natural ecosystems. *Hydrological Processes*, 25(26), 4050-4062.
[233 citations]

**Methods:** Reviewed two decades of studies establishing relationships between
vegetation indices (NDVI, EVI, SAVI) and crop/vegetation coefficients across
agricultural and natural ecosystems.
**Findings:** Linear NDVI-Kc relationships are robust for crops (R2 typically
0.85-0.95) but weaken for natural vegetation with complex canopy structures;
the approach works best when calibrated by land cover type.
**Impact:** Provided the definitive synthesis motivating transition from tabulated
to satellite-derived crop coefficients and identified the remaining challenges for
non-agricultural land covers.

### Kamble et al. (2013) — MODIS NDVI to Kc
Kamble, B., Kilic, A., Hubbard, K. (2013). Estimating crop coefficients using
remote sensing-based vegetation index. *Remote Sensing*, 5(4), 1588-1602.
[240 citations]

**Methods:** Developed a general linear relationship between MODIS NDVI and
crop coefficient (Kc) using back-calculated Kc from FAO-56 and AmeriFlux eddy
covariance data across US High Plains cropping systems.
**Findings:** A single linear model (Kc = 1.457*NDVI - 0.1725) achieved R2 of
0.90-0.91 and RMSE of 0.16-0.19 across multiple crops and years, demonstrating
the universality of the NDVI-Kc relationship at moderate resolution.
**Impact:** Showed that MODIS-scale NDVI can provide operationally useful Kc
values for regional irrigation water use accounting without crop-specific
calibration.

### Johnson & Trout (2012) — Landsat NDVI Kcb for Vegetable Crops
Johnson, L.F., Trout, T.J. (2012). Satellite NDVI assisted monitoring of
vegetable crop evapotranspiration in California's San Joaquin Valley. *Remote
Sensing*, 4(2), 439-455. [146 citations]

**Methods:** Used Landsat-5 NDVI to derive fractional cover and basal crop
coefficients (Kcb) for 18 crop types in the San Joaquin Valley, linking satellite
observations to prior lysimeter-based Fc-Kcb relationships.
**Findings:** Landsat NDVI tracked seasonal Kcb profiles with daily retrieval
uncertainty < 0.5 mm/d and seasonal water use uncertainty of 6-10%, matching
FAO-56 tabulated values within expected variability.
**Impact:** Demonstrated that Landsat-resolution (30 m) NDVI enables field-scale
Kcb monitoring for diverse crop portfolios in a major US irrigation district,
bridging the gap between point lysimeter data and regional water accounting.

---

## 4. Remote Sensing ET — General Arc

### Bastiaanssen et al. (1998) — SEBAL
Bastiaanssen, W.G.M., Menenti, M., Feddes, R.A., Holtslag, A.A.M. (1998).
A remote sensing surface energy balance algorithm for land (SEBAL). 1. Formulation.
*Journal of Hydrology*, 212-213, 198-212. [2,938 citations]

**Methods:** Formulated the Surface Energy Balance Algorithm for Land (SEBAL),
which uses satellite thermal and visible imagery to solve the energy balance at
each pixel by selecting "hot" and "cold" anchor pixels to self-calibrate the
sensible heat flux computation.
**Findings:** SEBAL reproduced field-measured ET within 15% at daily scales and
within 5% at seasonal scales across diverse irrigated landscapes in arid to
sub-humid climates.
**Impact:** Pioneered operationally practical satellite-based ET mapping by
eliminating the need for ground-based calibration data, enabling ET estimation
over data-sparse regions worldwide. Became the most widely cited RS-ET algorithm.

### Zhang et al. (2016) — Review of RS-Based Actual ET Estimation
Zhang, K., Kimball, J.S., Running, S.W. (2016). A review of remote sensing based
actual evapotranspiration estimation. *WIREs Water*, 3(6), 834-853. [555 citations]

**Methods:** Reviewed the major families of RS-ET approaches — empirical
(vegetation-index-based), Penman-Monteith, Priestley-Taylor, and surface
energy balance — across spatial scales from field to global.
**Findings:** No single model class is universally superior; energy balance models
excel at field-scale mapping but struggle with cloudy conditions, while PM and
PT approaches provide more continuous estimates but require parameterization of
stomatal/aerodynamic resistance.
**Impact:** Established the conceptual framework for multi-model ensemble
approaches by showing that different model families capture complementary
aspects of the ET process.

### Gowda et al. (2008) — ET Mapping for Agricultural Water Management
Gowda, P.H., Chavez, J.L., Colaizzi, P.D., Evett, S.R., Howell, T.A.,
Tolk, J.A. (2008). ET mapping for agricultural water management: present status
and challenges. *Irrigation Science*, 26(3), 223-237. [392 citations]

**Methods:** Reviewed the state of satellite-based ET mapping for agricultural
water management, covering SEBAL, METRIC, TSEB, and vegetation-index methods
with emphasis on validation against lysimeter and eddy covariance data.
**Findings:** Satellite ET methods achieve seasonal accuracy of 10-20% for
irrigated crops but face persistent challenges with temporal gaps between
overpasses, cloud contamination, and spatial resolution limitations.
**Impact:** Identified the field-scale (30 m) spatial resolution as the critical
threshold for individual farm management and motivated the development of
Landsat-based ET algorithms.

---

## 5. Landsat-Resolution ET Algorithms

### Allen et al. (2007) — METRIC
Allen, R.G., Tasumi, M., Trezza, R. (2007). Satellite-based energy balance for
mapping evapotranspiration with internalized calibration (METRIC) — Model.
*Journal of Irrigation and Drainage Engineering*, 133(4), 380-394. [1,823 citations]

**Methods:** Developed METRIC, an energy balance model that uses Landsat thermal
imagery with automated internal calibration against reference ET from local weather
stations, expressing ET as a fraction of reference ET (ETrF) to enable temporal
interpolation between overpasses.
**Findings:** METRIC reproduced lysimeter-measured seasonal ET within 4-10% for
irrigated crops in Idaho and showed strong performance across the western US.
**Impact:** Became the most widely used Landsat-scale ET model in the US, adopted
operationally by state water agencies, and a founding algorithm in the OpenET
ensemble.

### Senay et al. (2013) — SSEBop
Senay, G.B., Bohms, S., Singh, R.K., Gowda, P.H., Velpuri, N.M., Alemu, H.,
Verdin, J.P. (2013). Operational evapotranspiration mapping using remote sensing
and weather datasets: a new parameterization for the SSEB approach. *Journal of the
American Water Resources Association*, 49(3), 577-591. [552 citations]

**Methods:** Parameterized the Simplified Surface Energy Balance (SSEBop) model
to express ET as the product of a reference ET and a thermal-based ET fraction
(ETf), using pre-defined hot/cold reference temperatures derived from climate
normals to simplify the energy balance.
**Findings:** SSEBop reproduced daily ET within 10-20% and seasonal ET within
5-10% across CONUS when validated against eddy covariance flux towers, with the
simplification making it computationally efficient for continental-scale operations.
**Impact:** Enabled the first operational continental-scale Landsat ET product
(USGS SSEBop) and provided the ET fraction (ETf) concept that SWIM-RS uses as
its calibration target.

### Fisher et al. (2008) — PT-JPL
Fisher, J.B., Tu, K.P., Baldocchi, D.D. (2008). Global estimates of the
land-atmosphere water flux based on monthly AVHRR and ISLSCP-II data, validated
at 16 FLUXNET sites. *Remote Sensing of Environment*, 112(3), 901-919.
[1,004 citations]

**Methods:** Developed a Priestley-Taylor-based ET model (PT-JPL) that constrains
potential ET using multiplicative stress factors derived from atmospheric moisture
deficit, soil moisture proxy, and vegetation fraction — requiring no calibration
or resistance parameterization.
**Findings:** PT-JPL reproduced tower-measured ET with R2 = 0.90 across 16
FLUXNET sites spanning forests, grasslands, and crops, outperforming the
Penman-Monteith and MODIS-PM approaches with fewer inputs.
**Impact:** Demonstrated that a parameter-free, satellite-driven ET model could
achieve high accuracy globally, becoming one of the six core OpenET algorithms
and a widely used benchmark.

### Anderson et al. (2011) — ALEXI/DisALEXI
Anderson, M.C., Kustas, W.P., Norman, J.M., Hain, C.R., Mecikalski, J.R.,
Schultz, L., Gonzalez-Dugo, M.P., Cammalleri, C., d'Urso, G., Pimstein, A.,
Gao, F. (2011). Mapping daily evapotranspiration at field to continental scales
using geostationary and polar orbiting satellite imagery. *Hydrology and Earth
System Sciences*, 15, 223-239. [557 citations]

**Methods:** Presented the ALEXI/DisALEXI modeling system, which uses geostationary
satellite thermal imagery to compute daily ET at 5-10 km via the two-source energy
balance, then disaggregates to Landsat-scale (30 m) using polar-orbiting thermal data.
**Findings:** The multi-scale approach reproduced flux tower ET with errors of
15-25% at daily scales and 5-10% seasonally across diverse landscapes including
croplands, forests, and rangelands.
**Impact:** Provided the only RS-ET approach that truly fuses geostationary and
polar-orbiting data for daily field-scale ET mapping, contributing the
ALEXI/DisALEXI component to the OpenET ensemble.

### Senay et al. (2016) — Landsat 8 ET in the Colorado River Basin
Senay, G.B., Friedrichs, M., Singh, R.K., Velpuri, N.M. (2016). Evaluating
Landsat 8 evapotranspiration for water use mapping in the Colorado River Basin.
*Remote Sensing of Environment*, 185, 171-185. [191 citations]

**Methods:** Applied SSEBop to 528 Landsat 8 images to create seamless monthly
and annual ET maps at 100 m across the Colorado River Basin, validating against
eddy covariance towers and water balance closure.
**Findings:** Monthly RMSE ranged from 7.7-13.0 mm (2-35% bias) across diverse
CRB ecosystems; croplands were the largest "blue water" consumers while shrublands
dominated "green water" use.
**Impact:** Demonstrated that Landsat 8 enables basin-scale operational water use
accounting at field resolution, directly motivating the continental-scale OpenET
deployment.

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
**Impact:** Quantified the complementary strengths of energy balance vs.
vegetation-index ET approaches, strengthening the case for ensemble methods that
combine both families.

---

## 6. OpenET

### Melton et al. (2022) — OpenET Framework
Melton, F.S., Huntington, J., Grimm, R., ..., Anderson, R. (2022). OpenET:
Filling a critical data gap in water management for the western United States.
*Journal of the American Water Resources Association*, 58(6), 971-994.
[199 citations]

**Methods:** Built an operational cloud-based platform delivering field-scale
(30 m) ET from an ensemble of six satellite-based models (ALEXI/DisALEXI,
eeMETRIC, geeSEBAL, PT-JPL, SIMS, SSEBop) driven by Landsat imagery and
gridded meteorology, accessible via a web interface and data services.
**Findings:** For 24 cropland flux tower sites, ensemble mean MAE was 13.6 mm/month
(~15%) and weighted mean seasonal ET was within 8% of flux tower totals; ensemble
performance equaled or exceeded any individual model across nearly all accuracy
metrics.
**Impact:** Transformed satellite ET from a research product to a publicly accessible
operational tool, adopted by western US water agencies, irrigation districts, and
conservation programs for water rights administration and deficit irrigation planning.

### Volk et al. (2024) — OpenET Accuracy Assessment
Volk, J.M., Huntington, J.L., Melton, F.S., Allen, R., Anderson, M., Fisher, J.B.,
Kilic, A., Ruhoff, A., Senay, G.B., ..., Yang, Y. (2024). Assessing the accuracy of
OpenET satellite-based evapotranspiration data to support water resource and land
management applications. *Nature Water*, 2, 193-205. [112 citations]

**Methods:** Evaluated OpenET outputs against 152 eddy covariance flux stations
across CONUS, including croplands, shrublands, and forests, providing the largest
independent accuracy assessment of a satellite ET product to date.
**Findings:** Cropland ensemble MAE is 15.8 mm/month (17% of mean ET), MBE is
-5.3 mm/month (6%), and R2 is 0.90; inter-model variability and error increase
for non-cropland land covers, particularly shrublands and forests.
**Impact:** Provided the benchmark accuracy statistics that water managers
require for adoption, while clearly identifying the remaining accuracy gap for
non-agricultural land covers that motivates complementary modeling approaches.
