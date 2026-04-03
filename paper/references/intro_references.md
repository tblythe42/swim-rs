# Introduction References — Annotated List

Ordered to follow the planned introduction arc: direct ET measurement and its
limitations, FAO-56 dual crop coefficient framework and its global impact,
lookup-table Kc curves, remote-sensing-derived Kc curves, remote sensing ET
broadly, Landsat-resolution ET algorithms, and OpenET.

---

## 0. Direct ET Measurement: Value and Limitations

### Baldocchi et al. (2001) — FLUXNET
Baldocchi, D., Falge, E., Gu, L., Olson, R., Hollinger, D., Running, S., ...
& Wofsy, S. (2001). FLUXNET: A new tool to study the temporal and spatial
variability of ecosystem-scale carbon dioxide, water vapor, and energy flux
densities. *Bulletin of the American Meteorological Society*, 82(11), 2415-2434.
[3,508 citations]

**Methods:** Established a global network of eddy covariance flux towers
(FLUXNET) to measure continuous ecosystem-scale exchanges of CO2, water vapor,
and energy across >140 sites spanning major climate and vegetation types.
**Findings:** The network provides high-temporal-resolution observations of ET
and carbon fluxes, but tower footprints are limited to ~1 km2 and the global
network remains spatially sparse relative to the heterogeneity of land surfaces.
**Impact:** Created the observational backbone for validating remote sensing and
model-based ET estimates, while simultaneously demonstrating that tower
measurements alone cannot provide wall-to-wall ET accounting at regional to
continental scales.

### Novick et al. (2018) — The AmeriFlux Network
Novick, K.A., Biederman, J.A., Desai, A.R., Litvak, M.E., Moore, D.J.P.,
Scott, R.L., & Torn, M.S. (2018). The AmeriFlux network: A coalition of the
willing. *Agricultural and Forest Meteorology*, 249, 444-456. [262 citations]

**Methods:** Described the structure, governance, and scientific contributions of
the AmeriFlux network — the North American component of FLUXNET — which operates
>200 eddy covariance sites across diverse ecosystems and climate zones.
**Findings:** AmeriFlux has enabled synthesis studies spanning water, carbon, and
energy cycling, but the network's voluntary, PI-driven model means that site
selection is uneven, with croplands and forests overrepresented relative to
grasslands, shrublands, and managed landscapes.
**Impact:** Established AmeriFlux as the primary long-term observational
infrastructure for validating remote sensing and model-based ET estimates across
North America, while highlighting spatial gaps that limit validation coverage for
operational ET products.

### Rana & Katerji (2000) — Field ET Measurement Review
Rana, G. & Katerji, N. (2000). Measurement and estimation of actual
evapotranspiration in the field under Mediterranean climate: a review.
*European Journal of Agronomy*, 13(2-3), 125-153. [652 citations]

**Methods:** Reviewed the principal methods for direct field measurement of
ET — weighing lysimeters, eddy covariance, Bowen ratio energy balance, and
sap flow — evaluating their accuracy, cost, spatial representativeness, and
practical constraints.
**Findings:** Lysimeters provide the most accurate point measurements but are
expensive, immobile, and labor-intensive; eddy covariance is the most versatile
tower-based method but requires careful quality control and is subject to energy
balance non-closure of 10-30%.
**Impact:** Documented the fundamental tradeoff between measurement accuracy and
spatial scalability that motivates the use of model-based and remote-sensing
approaches for regional ET estimation.

### Wilson et al. (2002) — Energy Balance Closure at FLUXNET Sites
Wilson, K., Goldstein, A., Falge, E., Aubinet, M., Baldocchi, D., Berbigier, P.,
... & Verma, S. (2002). Energy balance closure at FLUXNET sites. *Agricultural
and Forest Meteorology*, 113(1-4), 223-243. [2,282 citations]

**Methods:** Analyzed energy balance closure across 22 FLUXNET eddy covariance
sites, comparing the sum of measured turbulent fluxes (sensible + latent heat)
to available energy (net radiation minus ground heat flux).
**Findings:** Turbulent fluxes accounted for only 80% of available energy on
average, with closure ratios ranging from 0.53 to 0.99 across sites, indicating
a systematic underestimation of ET by 10-30% at most towers.
**Impact:** Established that even well-maintained flux towers have inherent
measurement uncertainties that propagate into any ET validation or upscaling
exercise, reinforcing the need for independent, spatially distributed approaches
to constrain regional ET.

---

## 0b. Early Irrigation Water Requirement Methods

### Blaney & Criddle (1962) — Consumptive Use and Irrigation Water Requirements
Blaney, H.F. & Criddle, W.D. (1962). Determining consumptive use and irrigation
water requirements. *USDA Technical Bulletin No. 1275*, 59 pp. [256 citations]

**Methods:** Developed a temperature-based empirical formula relating monthly
consumptive use to mean air temperature and percentage of annual daytime hours,
multiplied by crop-specific seasonal coefficients.
**Findings:** The method provided operationally practical consumptive use estimates
using only temperature and crop type, enabling irrigation planning across the
western US where detailed meteorological data were unavailable.
**Impact:** Became the standard USDA/SCS method for irrigation water requirement
estimation for decades; its simplicity enabled widespread adoption but the
temperature-only formulation systematically underperforms in arid, windy, or
humid climates where radiation and vapor pressure deficit dominate ET dynamics.

### Allen & Pruitt (1986) — Rational Use of the FAO Blaney-Criddle Formula
Allen, R.G. & Pruitt, W.O. (1986). Rational use of the FAO Blaney-Criddle
formula. *Journal of Irrigation and Drainage Engineering*, 112(2), 139-155.
[165 citations]

**Methods:** Evaluated the FAO-24 Blaney-Criddle formula against lysimeter data
across diverse climates and proposed correction factors for humidity, wind speed,
and sunshine duration to reduce systematic bias.
**Findings:** The uncorrected Blaney-Criddle formula produced errors of 25-40%
in arid and windy environments; correction factors reduced errors substantially
but could not fully overcome the method's lack of explicit radiation and vapor
pressure deficit terms.
**Impact:** Documented the fundamental limitations of temperature-only ET methods
and motivated the transition to physically based reference ET approaches
culminating in FAO-56 Penman-Monteith.

### Jensen et al. (1990) — Evapotranspiration and Irrigation Water Requirements
Jensen, M.E., Burman, R.D., Allen, R.G. (1990). Evapotranspiration and irrigation
water requirements. *ASCE Manual of Practice No. 70*, 332 pp. [1,829 citations]

**Methods:** Comprehensive ASCE manual comparing 20+ ET estimation methods —
including Blaney-Criddle, Hargreaves, Priestley-Taylor, and Penman variants —
against lysimeter data from 11 global locations.
**Findings:** Temperature-based methods (Blaney-Criddle, Thornthwaite) performed
poorly outside their calibration regions, while combination methods incorporating
radiation, wind, and humidity were more robust across climates.
**Impact:** Established the comparative framework that led to adoption of
Penman-Monteith as the ASCE/FAO standard reference ET method and provided the
definitive documentation of irrigation water requirement estimation procedures
used by NRCS and western US water agencies.

### Amatya et al. (1995) — Comparison of Methods for Estimating REF-ET
Amatya, D.M., Skaggs, R.W., & Gregory, J.D. (1995). Comparison of methods for
estimating REF-ET. *Journal of Irrigation and Drainage Engineering*, 121(6),
427-435. [243 citations]

**Methods:** Compared Penman-Monteith, Priestley-Taylor, Turc, Blaney-Criddle,
and Thornthwaite reference ET methods against pan evaporation in the humid
Southeast United States over multiple years.
**Findings:** Temperature-based methods (Blaney-Criddle, Thornthwaite) produced
seasonal biases of 15-30% relative to Penman-Monteith, with Blaney-Criddle
overestimating in summer and Thornthwaite underestimating during high-radiation
periods; radiation-based methods performed better but still required local
calibration.
**Impact:** Demonstrated that simpler empirical methods introduce climate-dependent
biases that compound when used for irrigation scheduling, reinforcing the case
for physically based reference ET approaches.

### Almorox et al. (2015) — Global Performance Ranking of Temperature-Based ET
Almorox, J., Quej, V.H., & Marti, P. (2015). Global performance ranking of
temperature-based approaches for evapotranspiration estimation considering Köppen
climate classes. *Journal of Hydrology*, 528, 514-522. [179 citations]

**Methods:** Evaluated six temperature-based ET methods (Hargreaves-Samani,
Thornthwaite, Blaney-Criddle, and three others) against FAO-56 Penman-Monteith
across 4,652 stations covering all Köppen climate classes worldwide.
**Findings:** No single temperature-based method performs acceptably across all
climates; Hargreaves-Samani was the least biased overall but still showed errors
exceeding 20% in humid tropical and cold climates, and Blaney-Criddle ranked
among the worst performers globally.
**Impact:** Provided the definitive global evidence that temperature-only ET
methods are not transferable across climate regions, establishing a quantitative
basis for the transition to physically complete reference ET formulations.

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

### Er-Raki et al. (2007) — Combining FAO-56 and Ground-Based Remote Sensing
Er-Raki, S., Chehbouni, A., Guemouria, N., Duchemin, B., Ezzahar, J., &
Hadria, R. (2007). Combining FAO-56 model and ground-based remote sensing to
estimate water consumptions of wheat crops in a semi-arid region. *Agricultural
Water Management*, 87(1), 41-54. [294 citations]

**Methods:** Compared FAO-56 ET estimates using tabulated Kc values against
estimates using locally calibrated Kc derived from ground-based NDVI measurements
for wheat in semi-arid Morocco, validating both against eddy covariance data.
**Findings:** Tabulated FAO-56 Kc values overestimated seasonal ET by up to 30%
relative to flux tower observations, while NDVI-derived Kc reduced errors to
within 10%, primarily because the tabulated curves misrepresented local planting
dates, cultivar vigor, and stress timing.
**Impact:** Provided direct field evidence that replacing fixed Kc tables with
remotely sensed crop condition substantially improves soil water balance accuracy,
motivating the integration of remote sensing into FAO-56-type frameworks.

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

---

## 7. Foundational Thermal RS-ET and Two-Source Models

### Norman et al. (1995) — Two-Source Energy Balance Model
Norman, J.M., Kustas, W.P., & Humes, K.S. (1995). Source approach for estimating
soil and vegetation energy fluxes in observations of directional radiometric surface
temperature. *Agricultural and Forest Meteorology*, 77(3-4), 263-293. [1,651 citations]

**Methods:** Developed a two-source (soil + canopy) model that partitions thermal
radiometric surface temperature into separate soil and vegetation components to
independently estimate sensible and latent heat fluxes from each source.
**Findings:** The two-source approach substantially improved flux estimates over
sparse canopies compared to single-source models, which conflate soil and vegetation
temperatures and systematically overestimate sensible heat in partially vegetated
landscapes.
**Impact:** Established the theoretical foundation for multi-source thermal ET
algorithms including ALEXI/disALEXI and TSEB, which became the dominant physically
based approach for disaggregating satellite thermal imagery into component fluxes.

### Anderson et al. (1997) — ALEXI Time-Integrated Two-Source Model
Anderson, M.C., Norman, J.M., Diak, G.R., Kustas, W.P., & Mecikalski, J.R.
(1997). A two-source time-integrated model for estimating surface fluxes using
thermal infrared remote sensing. *Remote Sensing of Environment*, 60(2), 195-216.
[785 citations]

**Methods:** Coupled the Norman et al. (1995) two-source model with an atmospheric
boundary layer (ABL) growth model, using the morning rise in land surface
temperature from geostationary satellites to constrain the surface energy balance
without requiring absolute LST calibration.
**Findings:** The time-differencing approach reduced sensitivity to errors in
atmospheric correction and surface emissivity, producing robust regional flux
estimates from GOES thermal imagery at 5-10 km resolution.
**Impact:** Introduced the ALEXI framework that became the basis for continental-
scale ET mapping and the multi-scale disaggregation strategy (disALEXI) used in
OpenET.

### Anderson et al. (2004) — DisALEXI Disaggregation
Anderson, M.C., Norman, J.M., Mecikalski, J.R., Torn, R.D., Kustas, W.P., &
Basara, J.B. (2004). A multiscale remote sensing model for disaggregating regional
fluxes to micrometeorological scales. *Journal of Hydrometeorology*, 5(2), 343-363.
[225 citations]

**Methods:** Developed the DisALEXI algorithm to spatially disaggregate ALEXI
regional fluxes to Landsat-scale (30 m) resolution using higher-resolution thermal
imagery from polar-orbiting satellites.
**Findings:** Disaggregated fluxes agreed well with eddy covariance tower
measurements across cropland and grassland sites, demonstrating that the multi-scale
strategy preserves regional energy balance constraints while resolving field-level
variability.
**Impact:** Made the ALEXI framework applicable at field scale, enabling its
integration into OpenET and other operational agricultural ET monitoring systems.

### Anderson et al. (2011) — ALEXI/DisALEXI Continental Mapping
Anderson, M.C., Kustas, W.P., Norman, J.M., Hain, C.R., Mecikalski, J.R.,
Schultz, L., ..., Gao, F. (2011). Mapping daily evapotranspiration at field to
continental scales using geostationary and polar orbiting satellite imagery.
*Hydrology and Earth System Sciences*, 15, 223-239. [557 citations]

**Methods:** Presented the operational ALEXI/DisALEXI multi-sensor framework for
routine daily ET mapping from geostationary (GOES) and polar-orbiting (Landsat,
MODIS) thermal imagery, covering field to continental scales.
**Findings:** The system produced daily ET maps over the US with demonstrated
accuracy against flux towers and compatibility with multiple geostationary satellite
systems worldwide.
**Impact:** Established ALEXI/DisALEXI as an operational continental-scale ET
monitoring capability and demonstrated the feasibility of global thermal ET mapping
using multiple geostationary satellite networks.

---

## 8. Global ET Products

### Mu et al. (2011) — MOD16 Global ET Algorithm
Mu, Q., Zhao, M., & Running, S.W. (2011). Improvements to a MODIS global
terrestrial evapotranspiration algorithm. *Remote Sensing of Environment*, 115(8),
1781-1800. [2,496 citations]

**Methods:** Improved the Penman-Monteith-based MOD16 algorithm for estimating
global terrestrial ET from MODIS FPAR/LAI, albedo, and reanalysis meteorology at
1 km resolution and 8-day compositing.
**Findings:** Global annual ET was estimated at ~62,800 km3 with validated
performance against 46 AmeriFlux eddy covariance towers (average correlation 0.86);
the improved algorithm better captured ET dynamics in arid and cold environments.
**Impact:** Produced the first operationally sustained global satellite ET product
(MOD16A2), widely used for large-scale water budget analyses, drought monitoring,
and land surface model benchmarking.

### Martens et al. (2017) — GLEAM v3
Martens, B., Miralles, D.G., Lievens, H., van der Schalie, R., de Jeu, R.A.M.,
Fernandez-Prieto, D., Beck, H.E., Dorigo, W.A., & Verhoest, N.E.C. (2017).
GLEAM v3: satellite-based land evaporation and root-zone soil moisture.
*Geoscientific Model Development*, 10, 1903-1925. [2,114 citations]

**Methods:** Extended the GLEAM Priestley-Taylor framework with revised evaporative
stress formulations, optimized drainage, and microwave soil moisture assimilation
to produce three global ET datasets spanning 1980-2015 at 0.25 degree resolution.
**Findings:** Validated against 91 eddy covariance towers with average correlations
of 0.78-0.81 for evaporation and improved root-zone soil moisture estimates
relative to v2 (correlations increased from 0.47 to 0.53 for the second soil layer).
**Impact:** Provided the longest-record global satellite ET dataset, widely used for
climate trend analysis and as a benchmark for land surface models and other RS ET
products.

---

## 9. ECOSTRESS and Sentinel-2 Extensions

### Hulley et al. (2017) — ECOSTRESS Mission
Hulley, G., Hook, S., Fisher, J., & Lee, C. (2017). ECOSTRESS, a NASA
Earth-Ventures Instrument for studying links between the water cycle and plant
health over the diurnal cycle. *IEEE International Geoscience and Remote Sensing
Symposium (IGARSS)*, 5394-5396. [66 citations]

**Methods:** Described the ECOSTRESS thermal infrared instrument on the
International Space Station, designed to measure land surface temperature at
~70 m resolution with a precessing orbit that samples the diurnal temperature
cycle.
**Findings:** The non-sun-synchronous orbit enables thermal measurements at
varying times of day, capturing diurnal ET dynamics inaccessible to Landsat or
other fixed-overpass satellites.
**Impact:** Provides complementary thermal observations that increase the temporal
density of field-scale ET retrievals when combined with Landsat/Sentinel-2, and
enables new science on plant water stress timing and diurnal water use patterns.

### Xiao et al. (2021) — Emerging Satellite Observations for Diurnal Cycling
Xiao, J., Fisher, J.B., Hashimoto, H., Ichii, K., & Parazoo, N.C. (2021).
Emerging satellite observations for diurnal cycling of ecosystem processes.
*Nature Plants*, 7, 877-887. [142 citations]

**Methods:** Reviewed new satellite capabilities — including ECOSTRESS, OCO-2/3,
TROPOMI, and GOES-R — for observing diurnal cycles of photosynthesis, ET, and
thermal stress that fixed-overpass sensors miss.
**Findings:** Diurnal sampling reveals systematic biases in daytime-only ET
estimates and captures afternoon plant stress that morning-overpass sensors
underestimate.
**Impact:** Motivates the integration of non-sun-synchronous sensors like
ECOSTRESS into operational ET frameworks such as OpenET to improve temporal
sampling and stress detection.

---

## 10. ET Partitioning Limitations and Hybrid RS + SWB Approaches

### Melton et al. (2012) — SIMS Framework
Melton, F.S., Johnson, L.F., Lund, C.P., Pierce, L.L., Michaelis, A.R., Hiatt, S.,
..., Nemani, R. (2012). Satellite Irrigation Management Support with the Terrestrial
Observation and Prediction System. *IEEE Journal of Selected Topics in Applied Earth
Observations and Remote Sensing*, 5(6), 1709-1721. [116 citations]

**Methods:** Developed the SIMS framework for estimating crop ET from satellite
reflectance-derived fractional cover and the Allen-Pereira crop coefficient approach,
integrated with gridded weather data and soil water balance modeling.
**Findings:** SIMS provided ET estimates within 10-15% of lysimeter and flux tower
measurements for multiple California crops without requiring thermal imagery,
demonstrating the viability of reflectance-only ET estimation for irrigation
scheduling support.
**Impact:** Established the optical/reflectance-based crop coefficient approach as
a complement to thermal energy-balance methods, and became one of the six core
models in the OpenET ensemble.

### Pearson et al. (2024) — Upper Colorado Historical ET and Consumptive Use
Pearson, C., Minor, B., Morton, C., Volk, J., Dunkerly, C., Jensen, E., ReVelle, P.,
Kilic, A., Allen, R., & Huntington, J.L. (2024). Historical evapotranspiration and
consumptive use of irrigated areas of the Upper Colorado River Basin. *DRI Report*,
41304.

**Methods:** Combined FAO-56-style ET-Demands modeling with eeMETRIC satellite ET
to estimate historical irrigated consumptive use across the Upper Colorado River
Basin, separating irrigation-supplied ET from precipitation-supplied ET over a
multi-decade record.
**Findings:** The hybrid RS + process-model workflow produced basin-wide consumptive
use estimates that were spatially explicit and temporally continuous, demonstrating
that merging satellite ET with soil water balance models can advance ET partitioning
beyond either approach alone.
**Impact:** Represents the closest operational precedent to the SWIM-RS approach,
but relies on regionally assigned crop coefficients rather than field-specific
calibration — the limitation that SWIM-RS addresses directly.

### Glenn et al. (2011) — Vegetation Index Crop Coefficients Review
Glenn, E.P., Neale, C.M.U., Hunsaker, D.J., & Nagler, P.L. (2011). Vegetation
index-based crop coefficients to estimate evapotranspiration by remote sensing in
agricultural and natural ecosystems. *Hydrological Processes*, 25(26), 4050-4062.
[233 citations]

**Methods:** Reviewed the theoretical basis and empirical evidence for deriving
crop coefficients from vegetation indices (NDVI, EVI, SAVI), synthesizing results
across agricultural and riparian ecosystems.
**Findings:** VI-Kc relationships are robust across crop types when properly
calibrated, but relationships vary with sensor, VI choice, and canopy architecture;
the review identified standardization of VI-Kc protocols as a key need.
**Impact:** Provided the conceptual framework for replacing tabulated Kc with
satellite-observed vegetation condition, directly motivating NDVI-based
calibration approaches like those used in SWIM-RS.
