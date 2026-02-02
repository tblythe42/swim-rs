# Loose Ends - Model Diagnostics and Structural Issues

## Overview

This document tracks unresolved structural issues discovered during the fc removal work (2026-01-27). Rather than patching symptoms, we need to understand the root causes.

## Active Investigation: What is the model doing wrong?

### Symptoms Observed

1. **MAD collapse**: Both sites calibrate MAD to near-zero (~0.01-0.05), regardless of irrigation status
   - Fort Peck (unirrigated): 0.6 → 0.047
   - Crane (irrigated): 0.02 → 0.011
   - This is physically unrealistic - suggests compensating behavior

2. **Site-dependent ndvi_0**: Dramatic divergence in calibrated values
   - Fort Peck (grassland): 0.21
   - Crane (alfalfa): 0.82
   - May indicate land-cover-dependent physics not captured

3. **Asymmetric fc removal impact**:
   - Fort Peck: Performance **improved** after fc removal
   - Crane: Performance **degraded** after fc removal
   - Same structural change, opposite effects - why?

### Diagnostic Questions

1. **On days with large errors, what is the model state?**
   - Is soil too wet or too dry?
   - Is atmospheric demand (ETo) extreme?
   - Is NDVI in a transition period?
   - Is there recent precipitation or irrigation?

2. **Are errors systematic or random?**
   - Seasonal patterns?
   - Correlated with specific conditions?
   - Over-prediction vs under-prediction asymmetry?

3. **Which component is failing?**
   - Kcb calculation (NDVI → transpiration)?
   - Ke calculation (soil evaporation)?
   - Ks stress response?
   - Water balance (runoff, deep percolation)?

## Diagnostic Approach

See `examples/diagnostics/` for exploratory analysis code.

### Phase 1: Error Characterization (Fort Peck)
- Load model output + flux observations
- Compute residuals (model - observed)
- Identify worst-performing days (|residual| > threshold)
- Profile conditions on those days

### Phase 2: Conditional Analysis
- Group errors by:
  - Season (growing vs dormant)
  - Soil moisture state (wet/dry)
  - Atmospheric demand (high/low ETo)
  - Vegetation state (NDVI quartiles)
  - Recent precipitation (wet/dry antecedent)

### Phase 3: Component Isolation
- Run model with fixed Kcb (bypass NDVI calculation)
- Run model with fixed Ks (bypass stress)
- Run model with fixed Ke (bypass evaporation)
- Identify which component contributes most to error

### Phase 4: Parameter Sensitivity on Error Days
- On worst days, which parameters most affect the residual?
- Does adjusting ndvi_0, mad, or aw fix specific error patterns?

## Confounded Changes to Isolate

Multiple commits changed behavior simultaneously:

| Commit | Change | Potential Impact |
|--------|--------|------------------|
| `5a610ec` | FC removal from kc_act | Direct - removes transpiration scaling |
| `8ec4c52` | Water balance improvements | Indirect - changes soil moisture dynamics |
| `1b9e7c8` | kc_max to properties | Indirect - changes how ceiling is applied |

Need A/B testing to isolate effects.

## Structural Issues to Investigate

### 1. kcb_max vs kc_max Conflation

Current code uses `kc_max` for:
- Sigmoid amplitude: `Kcb = kc_max / (1 + exp(...))`
- Kc_act ceiling: `kc_act = min(ks*kcb + ke, kc_max)`

FAO-56 conceptually separates:
- `Kcb_max` - maximum basal coefficient (full-cover transpiration)
- `Kc_max` - maximum total coefficient (includes soil evaporation)

After removing fc, using kc_max as basal amplitude may inflate transpiration.

### 2. Irrigation Trigger Logic

If MAD → 0 gives better fit, the model may be:
- Triggering irrigation too aggressively
- Using irrigation to compensate for structural ET errors
- Masking problems in the water balance

### 3. NDVI-Kcb Relationship by Land Cover

The dramatic ndvi_0 difference (0.21 vs 0.82) suggests:
- Grassland and crops have fundamentally different NDVI-transpiration relationships
- A single sigmoid may not capture both
- May need land-cover-specific parameterization

## Files

- `examples/diagnostics/` - Diagnostic scripts (untracked)
- `examples/diagnostics/error_analysis.py` - Main diagnostic module
- `examples/diagnostics/fort_peck_diagnosis.py` - Fort Peck specific analysis

## Diagnostic Results: Fort Peck (2026-01-27)

### Key Finding: Model Cannot Reach High ET Values

**The model systematically under-predicts on high ET days.**

| Observed ET Quartile | Obs Mean | Model Mean | Bias |
|---------------------|----------|------------|------|
| Q1 (low) | 0.07 mm/day | 0.19 mm/day | **+0.12** (over) |
| Q2 | 0.29 mm/day | 0.36 mm/day | +0.07 |
| Q3 | 0.87 mm/day | 0.93 mm/day | +0.06 |
| Q4 (high) | 2.68 mm/day | 2.26 mm/day | **-0.43** (under) |

On 50 worst under-prediction days: observed ET = 5.09 mm/day, model = 2.42 mm/day

### Temporal Pattern: Summer Problem

| Season | Bias | MAE |
|--------|------|-----|
| Winter (DJF) | +0.02 | 0.11 mm/day |
| Spring (MAM) | -0.07 | 0.46 mm/day |
| Summer (JJA) | **-0.25** | 0.84 mm/day |
| Fall (SON) | +0.10 | 0.30 mm/day |

Worst month: **July (bias = -0.56 mm/day)**

### Condition-Specific Findings

1. **High ETo days** (top 25%): bias = -0.14 mm/day
   - Model can't keep up with atmospheric demand

2. **Post-rain** (>10mm in 3 days): **bias = -0.50 mm/day**
   - Evaporation not responding enough to wet soil?

3. **NDVI transitions**: MAE doubles (0.39 → 0.75 mm/day)
   - NDVI-Kcb relationship breaks during rapid greenup/senescence

4. **High NDVI days** (Q4): bias = -0.17 mm/day
   - Full canopy transpiration under-estimated

### Component Analysis

On worst **under-prediction** days:
- Transpiration: 2.23 mm/day
- Evaporation: 1.56 mm/day
- Total model: 2.42 mm/day
- **Observed: 5.09 mm/day** (gap of 2.67 mm/day!)

Both transpiration AND evaporation are too low. The model fundamentally cannot produce enough ET.

### Parameter Sensitivity

**ndvi_0**: Optimal = **0.10** (R² = 0.656)
- Fort Peck wants LOW ndvi_0 (opposite of Crane's 0.82)
- Confirms land-cover-dependent optimal values

### Structural Hypotheses

1. **Kc_max ceiling too low**: With kc_max ≈ 1.2, maximum model ET = 1.2 × ETo.
   But flux tower shows ET can exceed ETo on some days (advection, wet canopy evaporation)

2. **Evaporation (Ke) capped too aggressively**: After rain, Ke should spike but may hit ke_max ceiling

3. **Stress (Ks) kicking in too early**: Even with Ks = 0.94, model under-predicts

4. **NDVI-Kcb saturates**: Sigmoid flattens at high NDVI, limiting transpiration response

### CRITICAL FINDING: Model Ceiling Problem Confirmed

**The model's maximum kc_act = 0.734, but flux requires ETf up to 1.6+**

```
Worst under-prediction days (June-July 2005):
Date        Flux_ET  Model_ET  FluxETf  ModelETf  Kcb   Ks
2005-06-15   9.13     4.05      1.58     0.46    0.56  0.98
2005-06-19   9.39     4.51      1.46     0.46    0.60  0.99
2005-06-30   8.11     3.68      1.62     0.46    0.66  1.00
2005-07-03   8.20     3.97      1.44     0.52    0.52  1.00
```

**Key observations:**
- Flux ETf exceeds 1.0 (ET > ETo) on 57 days (3.3% of record)
- Flux ETf exceeds 1.2 on 33 days
- Model kc_act never exceeds 0.734
- Even when Ks ≈ 1.0 (no stress), model under-predicts by 50%

**Why flux can exceed ETo:**
1. Advection (hot dry air over wet surface)
2. Wet canopy evaporation after rain
3. GridMET ETo may underestimate actual atmospheric demand

**Why model cannot reach these values:**
1. Kcb saturates via sigmoid - max ≈ kc_max/2 at ndvi_0
2. Ke is capped by ke_max
3. Total Ks*Kcb + Ke cannot exceed ~0.75 in practice

### Proposed Fixes

1. **Increase kc_max** from 1.2 to 1.4-1.5 for grassland
2. **Remove or relax ke_max** ceiling after rain events
3. **Add advection correction** when conditions suggest it
4. **Re-examine sigmoid saturation** - does high NDVI → high Kcb work?

### Experiment: Increasing kc_max

**Surprising result: Higher kc_max makes R² WORSE**

| kc_max | R² | Bias | max_kc_act |
|--------|-----|------|------------|
| 1.0 | **0.671** | -0.089 | 0.94 |
| 1.2 | 0.633 | -0.082 | 1.08 |
| 1.4 | 0.580 | -0.077 | 1.21 |
| 1.6 | 0.517 | -0.072 | 1.28 |
| 2.0 | 0.388 | -0.065 | 1.37 |

**Why this happens:**
- Higher kc_max increases ET on ALL days, not just high-error days
- Model already over-predicts on low-demand days (Q1 bias = +0.12)
- Scaling up makes those over-predictions worse
- Net effect: worse overall fit

**The real problem is not a simple ceiling - it's a dynamic range issue:**
1. Model compresses the range: low ET too high, high ET too low
2. The NDVI → Kcb sigmoid doesn't capture full variability
3. Need a fix that increases high-ET days WITHOUT increasing low-ET days

### Possible Structural Fixes

1. **Nonlinear NDVI-Kcb relationship** - steeper response at high NDVI
2. **Condition-dependent kc_max** - higher ceiling when ETo is high
3. **Better evaporation model** - Ke spikes after rain, but currently smoothed
4. **Advection term** - add when (dry air + wet soil) detected

### Sigmoid Parameter Sensitivity (Fort Peck)

Best sigmoid parameters: **k=15, ndvi_0=0.1** (R²=0.672)
- Opposite of Crane's calibrated: k=7.65, ndvi_0=0.82

| ndvi_0 | k=7 R² | k=15 R² |
|--------|--------|---------|
| 0.1 | 0.656 | **0.672** |
| 0.2 | 0.602 | 0.638 |
| 0.4 | 0.442 | 0.448 |

**Critical trade-off discovered:**
| Config | Overall R² | Q4 (high-ET) bias | Q1 (low-ET) bias |
|--------|------------|-------------------|------------------|
| Default (k=7, ndvi_0=0.4) | 0.442 | -0.317 | +0.111 |
| Optimal (k=15, ndvi_0=0.1) | **0.672** | **-0.572** (worse!) | +0.142 |

**The sigmoid cannot fix both problems simultaneously!**
- Low ndvi_0: Fixes low-ET over-prediction, worsens high-ET under-prediction
- High ndvi_0: Fixes high-ET, worsens low-ET

### "Needed Kcb" Analysis

Back-calculated what Kcb would need to be to match flux (given model's Ks and Ke):

| NDVI Bin | Model Kcb | Needed Kcb | Model Too High By |
|----------|-----------|------------|-------------------|
| 0-0.15 | 0.112 | 0.070 | 0.042 |
| 0.15-0.25 | 0.215 | 0.045 | **0.170** |
| 0.25-0.35 | 0.321 | 0.082 | **0.239** |
| 0.35-0.45 | 0.503 | 0.281 | **0.223** |

**Surprising: Model Kcb is TOO HIGH at all NDVI levels!**

But Kc_act (total) is too LOW at high NDVI:
| NDVI Bin | Model Kc | Needed Kc | Gap |
|----------|----------|-----------|-----|
| 0.35-0.45 | 0.505 | 0.564 | +0.059 |
| 0.45-0.55 | 0.658 | 0.765 | **+0.107** |

**Implication: The problem is NOT in the sigmoid (Kcb)!**
The issue is likely in **Ke (soil evaporation)** being too low on high-ET days.

Linear fit to "needed" Kcb:
```
Kcb_needed ≈ -0.143 + 0.926 * NDVI
```
Much flatter than current sigmoid, with negative intercept (nearly zero at low NDVI).

### Revised Hypothesis

The sigmoid functional form may be fine. The issue is likely:
1. **Ke is underestimated** on high-ET days (post-rain, high demand)
2. ke_max may be capping evaporation too aggressively
3. The TEW/REW evaporation model may not respond enough to wet conditions

### Next Steps

- [x] ~~Check if observed ET/ETo > 1.2 on high-error days~~ **CONFIRMED**
- [x] ~~Test with kc_max = 1.5~~ **Made things worse**
- [x] ~~Test sigmoid shape changes~~ **Trade-off problem, can't fix both**
- [x] ~~Analyze "needed Kcb"~~ **Kcb is actually too high, Ke is the issue**
- [x] ~~Investigate Ke component~~ **Kr is the problem - see below**
- [x] ~~Check Ke on post-rain high-ET days~~ **Kr doesn't respond to rain**
- [x] ~~Compare few (wetted fraction)~~ **few is fine (0.83-0.95 median)**
- [x] ~~Investigate TEW/REW/depl_ze~~ **depl_ze is fine, issue is damping**
- [x] ~~Check kr_damp parameter settings~~ **FOUND IT - default 0.2 is too aggressive**
- [ ] Recommend structural fix: increase default kr_damp to 0.7-1.0

## CRITICAL FINDING: Kr Never Reaches 1.0 (2026-01-27)

### The Problem: Kr is Energy-Limited on 100% of Worst Days

On the 50 worst under-prediction days:
- **Ke constraint:** 100% energy-limited (Kr too low), 0% area-limited (few)
- **Mean Kr (implied):** 0.378 (should be ~1.0 on wet surface days)
- **Mean Ke actual:** 0.300
- **Mean Ke needed:** 0.636 (gap = 0.336)

### Kr Distribution Shows Surface Always Depleted

```
Kr (implied) distribution across ALL days:
  Min: 0.002
  25th: 0.151
  50th: 0.294
  75th: 0.473
  Max: 0.688  <-- Never reaches 1.0!
```

### Kr Doesn't Respond to Rain

| Condition | Kr (implied) | Bias |
|-----------|--------------|------|
| Wet antecedent (>10mm in 3d) | **0.483** | -0.501 mm/day |
| Dry antecedent (<=1mm in 3d) | 0.298 | +0.023 mm/day |

**Even after >10mm of rain, Kr only reaches 0.48 on average.**

For a wet surface after rain:
- Kr SHOULD be ~1.0 (saturated surface layer)
- Kr IS ~0.48 (model thinks surface is half-depleted)

### Why This Matters

Kr = (TEW - De) / (TEW - REW)

Where:
- TEW = Total Evaporable Water (~25mm default)
- REW = Readily Evaporable Water (~9mm default)
- De = Depletion of surface layer (mm)

For Kr = 0.48:
- De = TEW - Kr × (TEW - REW)
- De = 25 - 0.48 × 16 = 17.3mm

The model thinks the surface is depleted by 17mm even after rain.

### Possible Causes

1. **TEW too high?** If TEW = 40mm instead of 25mm, surface takes longer to wet up
2. **REW too low?** If REW = 5mm, the "readily evaporable" stage ends quickly
3. **kr_damp too aggressive?** Damping prevents Kr from spiking after rain
4. **Surface layer too thick?** Ze (evaporation layer depth) might be set too deep
5. **Rain not wetting surface correctly?** Precipitation might be going deeper, not wetting top soil

### Next Investigation

1. Check what TEW/REW/Ze values are being used for Fort Peck
2. Check kr_damp settings
3. Trace depl_ze through a rain event to see if it responds
4. Test with different TEW/REW values

## ROOT CAUSE CONFIRMED: kr_damp Too Aggressive (2026-01-27)

### Sensitivity Study Results

| kr_damp | R² | RMSE | Bias |
|---------|-------|------|------|
| 0.2 (default) | 0.442 | 0.915 | -0.047 |
| 0.3 | 0.451 | 0.907 | -0.046 |
| 0.4 | 0.463 | 0.898 | -0.048 |
| 0.5 | 0.477 | 0.886 | -0.051 |
| 0.6 | 0.490 | 0.874 | -0.053 |
| 0.7 | 0.501 | 0.865 | -0.056 |
| 0.8 | 0.510 | 0.857 | -0.059 |
| 0.9 | 0.517 | 0.851 | -0.061 |
| 1.0 (no damping) | **0.522** | **0.847** | -0.064 |

**Improvement with kr_damp = 1.0:**
- ΔR²: +0.080 (18% improvement)
- ΔRMSE: -0.068

### Why This Fixes the Problem

With default kr_damp = 0.2:
- Kr moves only 20% toward target each day
- After rain: 10 days to reach Kr = 0.9
- Surface evaporation throttled during recovery period
- Under-prediction on post-rain days

With kr_damp = 1.0 (no damping):
- Kr responds immediately to surface wetting
- Evaporation spikes correctly after rain
- Better match to flux observations

### Physical Interpretation

The purpose of Kr damping was to smooth unrealistic jumps in evaporation.
But aggressive damping (0.2) prevents realistic evaporation response.

For daily time steps, there's no physical reason to heavily damp Kr:
- Soil surface can wet/dry significantly within a single day
- Rain events should immediately increase evaporation potential
- The TEW/REW model already handles gradual drying correctly

### Combined Parameter Optimization (kr_damp + ndvi_0)

Grid search over kr_damp × ndvi_0 for Fort Peck:

| kr_damp | ndvi_0 | R² |
|---------|--------|-------|
| 0.2 | 0.4 (default) | 0.442 |
| 1.0 | 0.4 | 0.522 |
| 0.2 | 0.1 | 0.656 |
| **1.0** | **0.1** | **0.672** |

**Best combination: kr_damp = 1.0, ndvi_0 = 0.1**
- R² improvement: +0.230 (52% better than default)
- RMSE: 0.701 (vs 0.915 baseline)

### Recommendation

1. **Increase default kr_damp from 0.2 to 0.8-1.0**
2. **For grassland sites: use ndvi_0 ~ 0.1-0.2** (low NDVI onset)
3. Consider making kr_damp asymmetric (fast wetting, slower drying)
4. Add kr_damp as a calibration parameter for site-specific tuning

## Status

- [x] Phase 1: Error characterization ✓
- [x] Phase 2: Conditional analysis ✓
- [x] Phase 3: Component isolation ✓
- [x] Phase 4: Ke investigation ✓ **ROOT CAUSE: Kr not responding to rain**
- [x] Phase 5: kr_damp investigation ✓ **SOLUTION FOUND**
- [x] Phase 6: Multi-parameter grid search ✓ **ndvi_0 is primary driver**
- [x] Phase 7: Crane validation ✓ **Opposite ndvi_0 required (0.9 vs 0.1)**
- [ ] Phase 8: Holdout site validation (MR, ALARC2_Smith6, US-Blo)
- [ ] Implement land-cover-specific parameter defaults

## Holdout Sites for Validation (2026-01-27)

Three sites held out from main calibration for independent validation:

| Site ID | Classification | Location | ET Obs | Date Range | Status |
|---------|---------------|----------|--------|------------|--------|
| **MR** | Wetland/Riparian | Nevada | 316 | 2003-2006 | RS data ready |
| **US-Blo** | Evergreen Forest | California | 1611 | 1997-2007 | Needs data extraction |
| **ALARC2_Smith6** | Croplands (irrigated) | Arizona (Yuma) | 121 | Jan-Jun 2018 | RS data ready |

### Data Locations

- Flux data: `/data/ssd2/swim/4_Flux_Network/data/daily_flux_files/`
- Container prep needed - sites not in current 4_Flux_Network container (29 sites)

### Site Characteristics

**MR (Mesquite Riparian)**
- Groundwater-subsidized riparian zone (Las Vegas area)
- Bowen Ratio measurements (USGS NWSC)
- Expected: High baseline ET, less sensitive to rainfall
- Hypothesis: May need high f_sub, different mad behavior

**US-Blo (Blodgett Forest)**
- Ponderosa pine plantation, Sierra Nevada (1315m elevation)
- AmeriFlux eddy covariance
- Expected: Lower ET than crops, strong seasonality
- Hypothesis: May need different ndvi_0 than grassland or crops

**ALARC2_Smith6 (Yuma Irrigated)**
- Irrigated wheat field, southern Arizona (45m elevation)
- USDA-ARS eddy covariance
- Expected: High ET, similar to Crane (irrigated crop)
- Hypothesis: Should behave like Crane - high ndvi_0 (~0.8-0.9), low mad (~0.1)

### Data Status

- **MR**: In 5_Flux_Ensemble prepped_input.json ✓ (ready to run)
- **ALARC2_Smith6**: In 5_Flux_Ensemble prepped_input.json ✓ (ready to run)
- **US-Blo**: RS data in 4_Flux_Network/rs_tables, met data exists, but NOT in prepped_input
  - Needs container prep or manual SwimInput build

### Data Locations

| Site | RS Tables | Met Data | prepped_input | Flux Data |
|------|-----------|----------|---------------|-----------|
| MR | 5_Flux_Ensemble ✓ | ✓ | 5_Flux_Ensemble ✓ | 4_Flux_Network ✓ |
| ALARC2_Smith6 | 5_Flux_Ensemble ✓ | ✓ | 5_Flux_Ensemble ✓ | 4_Flux_Network ✓ |
| US-Blo | 4_Flux_Network ✓ | GFID=12 ✓ | ✗ | 4_Flux_Network ✓ |

### Next Steps

1. Build container for MR from 5_Flux_Ensemble data
2. Extract Earth Engine data for US-Blo (or use 4_Flux_Network full prep)
3. Execute grid search with land-cover-appropriate parameter ranges:
   - MR (riparian): Test higher f_sub, variable mad
   - US-Blo (forest): Test intermediate ndvi_0

## Recommended Parameter Defaults by Land Cover

Based on Fort Peck (grassland) and Crane (alfalfa) grid search results:

| Land Cover | ndvi_0 | mad | kr_damp | ndvi_k | Rationale |
|------------|--------|-----|---------|--------|-----------|
| **Grassland** | 0.1-0.15 | 0.4-0.5 | 0.8-1.0 | 7-10 | Transpires at low NDVI |
| **Dryland crops** | 0.3-0.4 | 0.4-0.5 | 0.5-0.8 | 7-10 | Moderate NDVI onset |
| **Irrigated crops** | 0.8-0.9 | 0.1-0.2 | 0.2-0.5 | 10-15 | Full canopy needed, trigger irrigation early |
| **Forest** (expected) | 0.3-0.5 | 0.5-0.6 | 0.2-0.5 | 7-10 | Evergreen, moderate stress tolerance |
| **Riparian** (expected) | 0.2-0.4 | 0.6-0.8 | 0.5-1.0 | 7-10 | GW-subsidized, high stress tolerance |

### Physical Interpretation

**ndvi_0** (sigmoid midpoint):
- Low (0.1): Transpiration begins at sparse cover (grassland)
- High (0.9): Transpiration only at full canopy (dense crops)

**mad** (management allowed depletion):
- Low (0.1): Irrigate early, minimal stress (irrigated)
- High (0.6+): Tolerate significant depletion (dryland, riparian)

**kr_damp** (evaporation response):
- High (1.0): Fast evaporation response to rain (important for dryland)
- Low (0.2): Damped response (less critical when irrigated)

## Investigation Summary (2026-01-27)

### The Problem
After removing the fc term from Kc_act calculation, we observed:
- Fort Peck (grassland): R² **improved** (0.627 → 0.680)
- Crane (alfalfa): R² **degraded** (0.618 → 0.543)

We investigated why the model systematically under-predicts on high ET days.

### Root Cause Chain
1. Model under-predicts on high-ET days (summer, post-rain)
2. Under-prediction is NOT due to Kcb (sigmoid) - Kcb is actually too HIGH
3. Under-prediction is due to **Ke (evaporation) being too low**
4. Ke is limited by **Kr (evaporation reduction coefficient)**
5. Kr never reaches 1.0 because **kr_damp = 0.2 is too aggressive**
6. After rain, Kr takes **10 days to reach 0.9** (should be immediate)

### Solution
**Increase kr_damp from 0.2 to 0.8-1.0**

| Configuration | R² | RMSE |
|--------------|-----|------|
| Default (kr_damp=0.2, ndvi_0=0.4) | 0.442 | 0.915 |
| kr_damp=1.0, ndvi_0=0.4 | 0.522 | 0.847 |
| kr_damp=1.0, ndvi_0=0.1 | **0.672** | **0.701** |

**52% improvement in R² with optimized parameters.**

### Files Created
- `examples/diagnostics/error_analysis.py` - Reusable diagnostic module
- `examples/diagnostics/fort_peck_diagnosis.py` - Full Fort Peck analysis
- `examples/diagnostics/test_kcb_functions.py` - Sigmoid functional form tests
- `examples/diagnostics/ke_investigation.py` - Ke/Kr analysis
- `examples/diagnostics/test_kr_damp.py` - Kr damping visualization
- `examples/diagnostics/run_kr_damp_study.py` - Sensitivity study
- `examples/diagnostics/combined_params_test.py` - Combined optimization

### Next Actions
1. ~~Update default kr_damp in `state.py` from 0.2 to 0.8~~ **See update below**
2. ~~Consider land-cover-specific ndvi_0 defaults~~ **Grid search confirms: grassland ~0.1, crops TBD**
3. ~~Add kr_damp to PEST calibration parameters~~ **Already present as kr_alpha**
4. Re-run Crane diagnostics to validate findings on irrigated site
5. **NEW:** Update PEST initial values based on grid search (ndvi_0=0.2, mad by land cover)
6. **NEW:** Consider land-cover-specific default parameter sets

## Update: Parameter Interaction Discovery (2026-01-27)

### The Simple Fix Doesn't Work

**Attempted:** Change kr_damp default from 0.2 to 0.8 in isolation.

**Result:** Uncalibrated model performance **degraded significantly**.

| Metric | Before (kr_damp=0.2) | After (kr_damp=0.8) | Change |
|--------|---------------------|---------------------|--------|
| R² (Full Series) | 0.680 | 0.510 | **-0.170** |
| R² (Capture Dates) | 0.673 | 0.474 | **-0.199** |
| mean ks | 0.676 | 0.265 | **-0.411** |
| max kc_act | 0.753 | 1.199 | +0.446 |

### Root Cause: Parameter Coupling

With faster kr_damp (higher value), the model exhibits a cascade effect:

1. **Faster evaporation response** → Ke spikes quickly after rain ✓
2. **Faster soil depletion** → Root zone dries out faster
3. **Increased transpiration stress** → Ks drops dramatically (0.676 → 0.265)
4. **Lower transpiration** → Even though evaporation is better, overall ET fit is worse

The diagnostic study found optimal R² = 0.672 with **both** kr_damp=1.0 **AND** ndvi_0=0.1.
Changing kr_damp alone without adjusting ndvi_0 disrupts the balance.

### Why the Diagnostic Study Gave Different Results

The combined parameter test (`combined_params_test.py`) showed:

| kr_damp | ndvi_0 | R² |
|---------|--------|-----|
| 0.2 (default) | 0.4 (default) | 0.442 |
| 1.0 | 0.4 | 0.522 |
| 0.2 | 0.1 | 0.656 |
| **1.0** | **0.1** | **0.672** |

The improvement comes from the **combination**, not kr_damp alone.

But Fort Peck notebook uncalibrated results showed R² = 0.680 with current defaults.
This is **higher** than the diagnostic study baseline (0.442).

**Possible explanations:**
1. Different evaluation period (diagnostics may have used subset)
2. Different flux data alignment
3. Container data pipeline changes since diagnostics
4. fc removal already improved baseline

### Revised Recommendations

1. **Do NOT change kr_damp default in isolation** - it makes things worse
2. **PEST calibration handles this** - kr_alpha is already a calibration parameter
   - Previous Fort Peck calibration found kr_alpha = 0.818 (63% increase)
   - This works because calibration adjusts multiple parameters together
3. **For uncalibrated runs:** Keep defaults as-is. The current defaults work
   reasonably well (R² = 0.68) for Fort Peck without calibration
4. **For calibrated runs:** Let PEST optimize kr_alpha along with other parameters

### Key Insight

The model parameters form a coupled system. Changing one parameter shifts the
optimal values of others. This is exactly what PEST calibration is designed
to handle - it optimizes all parameters simultaneously.

The diagnostic study was valuable for understanding **which parameters matter**
and **why the model under-predicts on high-ET days**, but the optimal values
found in isolation don't transfer to the full model without adjusting other
parameters too.

### Files Changed and Reverted
- `src/swimrs/process/state.py:472` - kr_damp default (0.2 → 0.8 → 0.2)
- `src/swimrs/process/input.py:896` - kr_damp default (0.2 → 0.8 → 0.2)
- `src/swimrs/calibrate/pest_builder.py:751` - kr_alpha initial (0.5 → 0.8 → 0.5)

## Multi-Parameter Grid Search (2026-01-27)

### Approach

Rather than changing parameters in isolation, we ran a grid search over the key
parameters simultaneously to find the optimal combination for Fort Peck.

**Parameters tested:**
- `kr_damp`: [0.2, 0.6, 1.0] - evaporation reduction damping
- `ndvi_0`: [0.1, 0.2, 0.4] - sigmoid midpoint for NDVI-Kcb relationship
- `ndvi_k`: [7.0, 12.0] - sigmoid steepness
- `mad`: [0.4, 0.6] - management allowed depletion (stress onset)

Note: `mad` is in `FieldProperties` (has informed prior from land use), while
the others are in `CalibrationParameters`. Both are tunable by PEST.

### Results: Top 10 Combinations

| kr_damp | ndvi_0 | ndvi_k | mad | R² |
|---------|--------|--------|-----|------|
| 1.0 | 0.1 | 7.0 | 0.4 | **0.692** |
| 0.6 | 0.1 | 7.0 | 0.4 | 0.686 |
| 1.0 | 0.1 | 12.0 | 0.4 | 0.681 |
| 0.6 | 0.1 | 12.0 | 0.4 | 0.679 |
| 0.2 | 0.1 | 12.0 | 0.4 | 0.676 |
| 0.2 | 0.1 | 7.0 | 0.4 | 0.674 |
| 1.0 | 0.2 | 12.0 | 0.4 | 0.671 |
| 1.0 | 0.2 | 7.0 | 0.4 | 0.670 |
| 0.6 | 0.2 | 12.0 | 0.4 | 0.663 |
| 0.6 | 0.2 | 7.0 | 0.4 | 0.658 |

### Parameter Importance

Ranked by impact on mean R² across all combinations:

| Rank | Parameter | Best Value | Mean R² (best) | Mean R² (worst) | ΔR² |
|------|-----------|------------|----------------|-----------------|------|
| 1 | **ndvi_0** | 0.1 | 0.658 | 0.475 | **+0.183** |
| 2 | **mad** | 0.4 | 0.621 | 0.548 | **+0.073** |
| 3 | kr_damp | 1.0 | 0.602 | 0.566 | +0.036 |
| 4 | ndvi_k | 12.0 | 0.591 | 0.578 | +0.013 |

### Key Findings

1. **ndvi_0 is the most important parameter** for Fort Peck grassland.
   - Low ndvi_0 (0.1) allows transpiration to begin at lower NDVI values
   - This matches grassland phenology where even sparse cover transpires

2. **mad = 0.4 consistently outperforms 0.6** for this unirrigated site.
   - Lower MAD means stress (Ks reduction) kicks in earlier
   - For dryland sites, this may better capture actual plant behavior
   - Current default MAD for perennials may be too high

3. **kr_damp helps but isn't the primary driver**.
   - Once ndvi_0 and mad are optimized, kr_damp provides incremental improvement
   - The previous finding that kr_damp alone made things worse was because
     other parameters weren't adjusted

4. **Best uncalibrated R² (0.692) exceeds previous calibrated R² (0.674)**.
   - This suggests PEST may not be finding the global optimum
   - Or the calibrated model was run with different PEST settings
   - Grid search can inform better PEST initial values and bounds

### Recommendations

1. **For grassland sites (Fort Peck type):**
   - ndvi_0 = 0.1-0.2 (lower than default 0.4)
   - mad = 0.4-0.5 (lower than perennial default ~0.6)
   - kr_damp = 0.6-1.0 (higher than default 0.2)

2. **Update PEST initial values:**
   - ndvi_0: initial = 0.2 (was 0.4), tighter bounds for grassland
   - mad: consider land-cover-specific initial values

3. **Land-cover-specific defaults:**
   - Grassland: ndvi_0 ~ 0.1, mad ~ 0.4
   - Crops (alfalfa): ndvi_0 ~ 0.4-0.5, mad ~ 0.5-0.6

### Files Created
- `examples/diagnostics/grid_search.py` - Multi-parameter grid search script
- `examples/diagnostics/grid_search_results_fort_peck.csv` - Fort Peck results
- `examples/diagnostics/grid_search_results_crane.csv` - Crane initial results
- `examples/diagnostics/grid_search_results_crane_extended.csv` - Crane extended results

## Crane Grid Search (2026-01-27)

### Initial Results: Parameter Range Too Narrow

First grid search with ndvi_0 = [0.1, 0.2, 0.4] produced **negative R² values**
(model worse than mean prediction) with +1.2 mm/day over-prediction bias.

This indicated ndvi_0 was too low for irrigated alfalfa.

### Extended Grid Results

Tested ndvi_0 = [0.4, 0.6, 0.8, 0.9] with mad = [0.1, 0.3, 0.5]:

| kr_damp | ndvi_0 | ndvi_k | mad | R² |
|---------|--------|--------|-----|------|
| 0.2 | 0.9 | 12.0 | 0.1 | **0.632** |
| 0.2 | 0.9 | 12.0 | 0.3 | 0.631 |
| 0.2 | 0.9 | 7.0 | 0.5 | 0.623 |
| 1.0 | 0.9 | 12.0 | 0.1 | 0.620 |
| 0.6 | 0.9 | 12.0 | 0.1 | 0.620 |

### Parameter Importance: Crane vs Fort Peck

| Parameter | Fort Peck (grassland) | Crane (alfalfa) |
|-----------|----------------------|-----------------|
| **ndvi_0** | 0.1 (low) | 0.9 (high) |
| **mad** | 0.4 | 0.1 |
| kr_damp | 1.0 (helps) | 0.2 (minimal effect) |
| ndvi_k | 7.0 | 12.0 |
| **Best R²** | 0.692 | 0.632 |

### Key Insight: ndvi_0 Reflects Vegetation Structure

The dramatic difference in optimal ndvi_0 reflects land cover characteristics:

- **Grassland (ndvi_0 ~ 0.1):** Transpiration begins at low NDVI because even
  sparse grass cover transpires. The sigmoid inflection occurs early.

- **Alfalfa (ndvi_0 ~ 0.9):** Transpiration increases slowly until near-full
  canopy cover. The sigmoid inflection occurs late - alfalfa doesn't reach
  maximum transpiration rate until NDVI is very high.

This is physically sensible:
- Grass: continuous ground cover, transpiring proportionally to greenness
- Alfalfa: distinct growth stages, full transpiration only at canopy closure

### mad Difference

- **Fort Peck (mad=0.4):** Unirrigated, stress onset earlier
- **Crane (mad=0.1):** Irrigated, triggers irrigation before any stress

### Implications for Defaults

Current default ndvi_0 = 0.4 is a poor compromise:
- Too high for grassland (wants 0.1)
- Too low for alfalfa (wants 0.9)

**Recommendation:** Land-cover-specific ndvi_0 defaults:
- Grassland/rangeland: ndvi_0 = 0.15
- Row crops: ndvi_0 = 0.4-0.5
- Alfalfa/dense crops: ndvi_0 = 0.8-0.9

## Experiment: fc from NDVI vs fc from Kcb (2026-01-27)

### Background

During diagnostic analysis, we identified that soil evaporation (Ke) was too high
for dense canopy at the Crane site. The issue: fc (fractional cover) is computed
from Kcb, but Kcb is constrained by the sigmoid function. At high NDVI (0.81),
the model computed:

- Kcb = 0.36 (constrained by sigmoid with ndvi_0=0.82)
- fc = 0.43 (from Kcb)
- few = 0.57 (exposed soil fraction)
- Ke = 0.51 (too high for dense canopy)

But at NDVI=0.81, actual vegetation cover should be ~90%, giving fc≈0.9 and
few≈0.1, which would reduce Ke substantially.

### Hypothesis

Computing fc directly from NDVI (rather than from Kcb) would decouple canopy
shading from transpiration demand, properly limiting soil evaporation under
dense canopy.

### Implementation

Added `fractional_cover_from_ndvi()` function using Carlson & Ripley (1997):

```
fc = (NDVI - NDVI_bare) / (NDVI_full - NDVI_bare)
```

Where:
- NDVI_bare = 5th percentile of site NDVI record
- NDVI_full = 95th percentile of site NDVI record

### Results: Crane Site

| Metric | fc from Kcb | fc from NDVI |
|--------|-------------|--------------|
| Overall R² | **0.669** | 0.458 |
| Overall Bias | **-0.043 mm/day** | -0.652 mm/day |
| Growing season R² | **0.396** | -0.014 |
| Post-irrigation Bias | +0.296 mm/day | -0.853 mm/day |
| Growing season Ke | 0.465 | 0.058 |

**The NDVI-based fc performed substantially worse.**

### Calibrated Parameters Comparison

| Parameter | fc from Kcb | fc from NDVI |
|-----------|-------------|--------------|
| ndvi_k | 7.24 | 11.59 |
| ndvi_0 | 0.815 | 0.686 |
| aw | 213 mm | 210 mm |

### Analysis

The structural change had the intended effect on Ke (reduced from 0.465 to 0.058
in growing season), but overall model performance degraded because:

1. **Kcb and fc are empirically coupled**: The sigmoid parameters were tuned
   assuming fc would be derived from Kcb. Decoupling them requires re-tuning
   the entire parameterization.

2. **Calibration compensates**: With fc from Kcb, calibration finds parameter
   combinations where the coupled Kcb-fc relationship gives good total ET
   estimates, even if individual components (Kcb, Ke) aren't perfectly physical.

3. **Under-prediction cascade**: With lower Ke, the model needs higher Kcb to
   compensate. But the sigmoid constrains Kcb, resulting in systematic
   under-prediction.

### Conclusion

**The fc-from-Kcb formulation should be retained.**

While the theoretical concern about excessive Ke under dense canopy is valid,
the empirical performance is substantially better when keeping fc coupled to Kcb.
The coupled system allows calibration to find parameter combinations that produce
accurate total ET, even if the partitioning between transpiration and evaporation
isn't perfectly physical.

This is a pragmatic trade-off: the model prioritizes accurate ET estimation over
physically "correct" component partitioning.

### Files Changed and Reverted

- `src/swimrs/process/loop.py` - fc calculation (NDVI-based → Kcb-based)
- `src/swimrs/process/loop_fast.py` - fc calculation (NDVI-based → Kcb-based)
- `src/swimrs/process/kernels/cover.py` - Added `fractional_cover_from_ndvi()` (retained for future use)
- `src/swimrs/process/state.py` - Added `ndvi_bare`, `ndvi_full` properties (retained)
- `src/swimrs/process/input.py` - Compute NDVI percentiles (retained)

### Future Considerations

If component partitioning becomes important (e.g., for water balance studies
where transpiration vs evaporation matters), consider:

1. **Hybrid approach**: Use NDVI-based fc for Ke calculation only, keep Kcb
   independent
2. **Re-parameterization**: Develop new sigmoid parameters calibrated with
   NDVI-based fc from the start
3. **Separate calibration targets**: Add observations that constrain Ke
   independently (e.g., soil moisture, lysimeter data)

## Experiment: Restoring fc to kc_act Equation (2026-01-27)

### Background

After the previous experiment showed that fc from NDVI performed worse than fc from Kcb,
we tested whether including fc in the kc_act equation improves performance. The change:

```python
# Previous (fc removed):
kc_act = ks * kcb + ke

# Current (fc restored):
kc_act = fc * ks * kcb + ke
```

This scales transpiration by fractional cover - less canopy means less transpiration.

### Parameter Search Results (Crane, irrigated alfalfa)

Grid search over ndvi_k × ndvi_0 with fc in kc_act:

| ndvi_k | Best ndvi_0 | R² (vs ETf) |
|--------|-------------|-------------|
| 7.0 | 0.50 | 0.520 |
| 9.0 | 0.50-0.60 | 0.529 |
| 11.0 | 0.60 | **0.531** |
| 13.0 | 0.60 | 0.509 |

**Best uncalibrated:** ndvi_k=11, ndvi_0=0.60, R²=0.531

Parameter ranges with R² > 0.5: ndvi_k [7, 20], ndvi_0 [0.50, 0.60]

### Updated PEST Builder Initial Values

Based on the parameter search, updated `pest_builder.py`:

| Parameter | Old Initial (irrigated) | New Initial (irrigated) |
|-----------|------------------------|-------------------------|
| ndvi_0 | 0.85 | 0.55 |
| ndvi_k | 7.0 | 10.0 |
| ndvi_0 bounds | [0.05, 0.95] | [0.10, 0.80] |

### Calibration Results (Crane)

**Calibrated parameters (mean across ensemble):**
- ndvi_k = 8.70
- ndvi_0 = 0.58
- mad = 0.01 (at lower bound)
- aw = 228 mm
- ks_alpha = 0.54
- kr_alpha = 0.33

**Performance vs Flux Tower ET (ET_corr):**

| Configuration | R² | Bias (mm/day) |
|--------------|-----|---------------|
| Uncalibrated (fc in kc_act) | 0.642 | -0.181 |
| **Calibrated (fc in kc_act)** | **0.734** | **-0.031** |
| OpenET (reference) | 0.738 | +0.093 |

### Comparison: With vs Without fc

| Configuration | R² vs Flux ET | Bias |
|--------------|---------------|------|
| Without fc (previous) | 0.669 | -0.043 |
| **With fc (current)** | **0.734** | **-0.031** |

**Restoring fc to kc_act improved R² from 0.669 to 0.734** (+0.065).

### Key Findings

1. **fc in kc_act improves performance** for this irrigated site when properly calibrated
2. **Optimal ndvi_0 shifted lower** (0.58 vs 0.82) - transpiration begins earlier in the sigmoid
3. **Model now matches OpenET** (R² 0.734 vs 0.738), with less bias
4. **mad still collapses to lower bound** - this structural issue persists

### Physical Interpretation

With fc scaling transpiration:
- At low fc (sparse canopy): transpiration is reduced proportionally
- At high fc (full canopy): transpiration approaches ks × kcb
- This allows the sigmoid (ndvi_0, ndvi_k) to control Kcb independently of canopy shading

The lower optimal ndvi_0 (0.58 vs 0.82) suggests that with fc explicitly scaling transpiration,
the sigmoid doesn't need to delay Kcb onset as much - the fc term handles the canopy cover effect.

### Files Changed

- `src/swimrs/process/loop_fast.py:317` - `kc_act = fc * ks * kcb + ke`
- `src/swimrs/process/kernels/water_balance.py:268` - `kc_raw = fc[i] * ks[i] * kcb[i] + ke[i]`
- `src/swimrs/calibrate/pest_builder.py` - Updated ndvi_0, ndvi_k initial values and bounds

### Status

**Current recommended configuration:** fc in kc_act equation with updated PEST bounds.

Further validation needed on:
- Fort Peck (non-irrigated grassland)
- Other flux sites in the network

## Experiment: Power-Modified Sigmoid (kcb_beta) Without fc (2026-01-28)

### Motivation

The `fc * kcb` term in `kc_act = fc * ks * kcb + ke` effectively "squares a fraction" since both
fc and kcb are derived from NDVI via the sigmoid. This creates parameter overloading where the
sigmoid parameters (ndvi_0, ndvi_k) control both:
1. Transpiration demand (Kcb)
2. Canopy shading effect (fc)

We hypothesized that a power-modified sigmoid could replace the fc*kcb coupling with a more
interpretable single parameter:

```
Kcb = kc_max × sigmoid(NDVI)^β
```

Where β > 1 compresses low values similar to fc × kcb, but with explicit control over the
compression strength.

### Theoretical Analysis

For the standard formulation:
- `kcb = kc_max × sigmoid`
- `fc = ((kcb/kc_max) + 0.004)^0.5 - 0.004` (FAO-56 approximation)
- Effective: `fc × kcb ≈ kc_max × sigmoid^1.5` at high sigmoid values

This suggests β ≈ 1.5-2.5 should theoretically replicate fc × kcb behavior.

### Implementation

1. **Added kcb_beta parameter** to `CalibrationParameters` in `state.py`
2. **Modified kcb_sigmoid** in `crop_coefficient.py` to accept optional kcb_beta
3. **Removed fc from kc_act equation** in both `loop_fast.py` and `water_balance.py`:
   ```python
   # Before: kc_act = fc * ks * kcb + ke
   # After:  kc_act = ks * kcb + ke
   ```
4. **Added kcb_beta to PEST calibration** in `pest_builder.py`

### Parameter Search Results (Crane, irrigated alfalfa)

Grid search over kcb_beta × ndvi_0 × ndvi_k × mad:

| kcb_beta | ndvi_0 | ndvi_k | mad | R² |
|----------|--------|--------|-----|------|
| 3.0 | 0.8 | 5.0 | 0.1 | -0.038 |
| 3.5 | 0.8 | 5.0 | 0.1 | -0.044 |
| 2.5 | 0.8 | 5.0 | 0.1 | -0.051 |
| 3.0 | 0.85 | 5.0 | 0.1 | -0.058 |
| 4.0 | 0.8 | 5.0 | 0.1 | -0.062 |

Note: Negative R² indicates uncalibrated model is worse than mean prediction, but values
near zero indicate low bias. The key is that calibration can improve from this baseline.

**Best uncalibrated configuration:** kcb_beta=3.0, ndvi_0=0.8, ndvi_k=5.0, mad=0.1

### Updated PEST Builder Parameters

| Parameter | Initial Value | Lower Bound | Upper Bound |
|-----------|---------------|-------------|-------------|
| kcb_beta | 3.0 | 1.5 | 5.0 |
| ndvi_0 | 0.8 | 0.4 | 0.95 |
| ndvi_k | 5.0 | 3.0 | 15.0 |

### Calibration Results (Crane)

**PEST++ IES Settings:** 3 iterations, 20 realizations

**Calibrated parameters (mean across ensemble):**
- kcb_beta = 3.1 (range: 1.9 - 5.0, one realization hit upper bound)
- ndvi_0 = 0.80
- ndvi_k = 7.7
- mad = 0.03
- aw = 130 mm

### Validation Against Flux Tower

| Metric | Uncalibrated | Calibrated | Change |
|--------|--------------|------------|--------|
| R² | 0.642 | **0.733** | **+0.092** |
| Pearson r | 0.817 | **0.868** | **+0.050** |
| Bias (mm/day) | -0.181 | **-0.029** | **+0.151** |
| RMSE (mm/day) | 1.276 | **1.100** | **-0.176** |

### Comparison with OpenET Ensemble

| Metric | SWIM (Calibrated) | OpenET Ensemble |
|--------|-------------------|-----------------|
| R² | 0.733 | 0.738 |
| Pearson r | **0.868** | 0.863 |
| Bias (mm/day) | **-0.029** | 0.093 |
| RMSE (mm/day) | 1.100 | 1.091 |

**SWIM now performs nearly identically to OpenET ensemble** against independent flux tower
observations, with slightly better bias and correlation.

### Key Findings

1. **Power-modified sigmoid works**: Removing fc and using kcb_beta achieved comparable
   performance to the fc × kcb formulation after calibration.

2. **More interpretable parameters**: Single kcb_beta parameter controls transpiration
   compression instead of the implicit fc × kcb coupling.

3. **kcb_beta clusters around 2.8-4.0**: Higher than the theoretical β ≈ 1.5-2.5, suggesting
   the power sigmoid can capture dynamics beyond simple fc × kcb replication.

4. **Mass balance conserved**: 0.67% error over 13,149 days (acceptable).

### Files Changed

- `src/swimrs/process/state.py` - Added kcb_beta to CalibrationParameters
- `src/swimrs/process/kernels/crop_coefficient.py` - Added kcb_beta to kcb_sigmoid
- `src/swimrs/process/loop_fast.py` - Added kcb_beta, removed fc from kc_act
- `src/swimrs/process/kernels/water_balance.py` - Removed fc from actual_et kernel
- `src/swimrs/process/input.py` - Added kcb_beta HDF5 serialization
- `src/swimrs/calibrate/pest_builder.py` - Added kcb_beta as calibration parameter
- `examples/3_Crane/parameter_search_beta.py` - Parameter search script

### Comparison: fc × kcb vs kcb_beta

| Formulation | R² (Calibrated) | Bias | Parameters |
|-------------|-----------------|------|------------|
| fc × kcb (kc_act = fc*ks*kcb + ke) | 0.734 | -0.031 | ndvi_0=0.58, ndvi_k=8.7 |
| **kcb_beta (kc_act = ks*kcb + ke)** | **0.733** | **-0.029** | kcb_beta=3.1, ndvi_0=0.80 |

**Both formulations achieve essentially identical performance** when properly calibrated.
The kcb_beta approach offers:
- Explicit control over transpiration compression
- More interpretable sigmoid parameters (ndvi_0 closer to physical meaning)
- Simpler equation structure

### Status

**Current state:** kcb_beta implementation validated on Crane (irrigated alfalfa).

**Next experiment:** Test simple linear NDVI-Kcb model with alpha and beta coefficients.

## Experiment: Linear NDVI-Kcb Model (2026-01-28)

### Motivation

Both the sigmoid and power-modified sigmoid require 2-3 parameters to describe the NDVI-Kcb
relationship. A simpler alternative is a linear model:

```
Kcb = α + β × NDVI
```

Where:
- α (alpha) = intercept (Kcb at NDVI=0)
- β (beta) = slope (Kcb change per unit NDVI)

This has several potential advantages:
1. Only 2 parameters instead of 3 (ndvi_0, ndvi_k, kcb_beta)
2. Directly interpretable coefficients
3. May be sufficient if the sigmoid's nonlinearity isn't essential

### Physical Constraints

For physical plausibility:
- α ≈ 0 (bare soil has ~zero transpiration)
- β ≈ 1.0-1.5 (scales NDVI to Kcb)
- Kcb capped at kc_max

### Implementation

Added `kcb_linear_simple` kernel and `linear_alpha`, `linear_beta` to CalibrationParameters.
Modified `run_daily_loop_fast` to accept `kcb_model` parameter (0=sigmoid, 1=linear).

### Parameter Search Results (Crane, irrigated alfalfa)

Extended grid search over alpha × beta:

| alpha | beta | R² | RMSE | Bias |
|-------|------|------|------|------|
| -0.40 | 0.80 | **-0.037** | 0.415 | +0.025 |
| -0.20 | 0.50 | -0.037 | 0.415 | +0.022 |
| -0.40 | 0.70 | -0.040 | 0.416 | +0.002 |
| -0.30 | 0.60 | -0.040 | 0.416 | +0.009 |
| -0.20 | 0.40 | -0.046 | 0.417 | -0.005 |

**Best linear:** α=-0.40, β=0.80 → Kcb = -0.40 + 0.80 × NDVI

### Comparison: Linear vs Sigmoid

| Model | Parameters | R² | RMSE | Bias |
|-------|-----------|-----|------|------|
| **Linear** | α=-0.40, β=0.80 | **-0.037** | **0.415** | +0.025 |
| Sigmoid | kcb_beta=3.0, ndvi_0=0.8, ndvi_k=5.0 | -0.038 | 0.416 | +0.004 |

**ΔR² = +0.001** (linear marginally better)

### Key Findings

1. **Linear model matches sigmoid performance**: The simple 2-parameter linear model
   achieves essentially identical R² to the 3-parameter power-modified sigmoid.

2. **Parameter importance** (mean R² by value):
   - alpha: -0.40 best (R²=-0.065), 0.00 worst (R²=-0.563)
   - beta: 0.40 best (R²=-0.089), 1.00 worst (R²=-0.487)

3. **Physical interpretation** of optimal linear model:
   - Kcb = -0.40 + 0.80 × NDVI
   - At NDVI=0.5: Kcb = 0.0 (transpiration starts at NDVI=0.5)
   - At NDVI=0.8: Kcb = 0.24
   - At NDVI=1.0: Kcb = 0.40

4. **Low Kcb values compensated by Ke**: Both the linear and power-sigmoid models
   produce surprisingly low Kcb values. The total ETf (kc_act = ks×kcb + ke) is
   correct because soil evaporation (Ke) compensates for low transpiration.

5. **Parameter identifiability issue**: Multiple parameterizations can produce
   similar total ET, suggesting Kcb and Ke are not independently identifiable
   from total ET observations alone. This explains why:
   - fc removal worked (different Kcb-Ke split, same total)
   - Linear matches sigmoid (different Kcb curves, same total)
   - Calibration finds diverse solutions (ensemble variability)

### Implications

1. **Model structure doesn't matter much**: For total ET prediction, the NDVI-Kcb
   functional form is less important than having enough parameters to fit the data.

2. **Simpler may be better**: The 2-parameter linear model is as good as the
   3-parameter sigmoid, and easier to interpret.

3. **Partitioning is uncertain**: Without independent observations of transpiration
   and evaporation, we cannot validate the E/T split. Calibrated models may have
   physically unrealistic component values even with correct total ET.

4. **For calibration**: Consider using the linear model for simplicity, or if
   sigmoid is preferred, acknowledge that the nonlinearity may not be necessary.

### Files Changed

- `src/swimrs/process/kernels/crop_coefficient.py` - Added `kcb_linear_simple`
- `src/swimrs/process/state.py` - Added `linear_alpha`, `linear_beta`
- `src/swimrs/process/loop_fast.py` - Added `kcb_model` parameter support
- `examples/3_Crane/parameter_search_linear.py` - Parameter search script

### Status: ABANDONED

The linear model achieves parity with the sigmoid for total ET, but both approaches
(without fc) produce unrealistic E/T partitioning. See next section.

## Critical Finding: fc Is Essential for Realistic E/T Partitioning (2026-01-28)

### The Experiment

We compared E/T partitioning across three model configurations:
1. **Sigmoid+fc**: kc_act = fc × ks × kcb + ke (original FAO-56)
2. **Sigmoid-fc**: kc_act = ks × kcb + ke (fc removed, power-modified sigmoid)
3. **Linear-fc**: kc_act = ks × kcb + ke (fc removed, linear Kcb model)

### Results: Overall Statistics

| Component | Sigmoid+fc | Sigmoid-fc | Linear |
|-----------|------------|------------|--------|
| Mean Kcb | **0.337** | 0.023 | 0.041 |
| Mean Ke | 0.407 | 0.468 | 0.468 |
| Mean ETf | 0.595 | 0.484 | 0.502 |
| **T fraction** | **32%** | 3.5% | 5.8% |
| **E fraction** | **68%** | 96.5% | 94.2% |

### Results: At High NDVI (>0.7) - Full Canopy

| Model | Kcb | Ke | T fraction |
|-------|-----|-----|------------|
| **Sigmoid+fc** | **1.087** | 0.111 | **91%** |
| Sigmoid-fc | 0.144 | 0.504 | 21% |
| Linear | 0.230 | 0.503 | 30% |

### Results: By NDVI Bin

| NDVI Range | Sigmoid+fc T_frac | Sigmoid-fc T_frac | Linear T_frac |
|------------|-------------------|-------------------|---------------|
| [0.0, 0.3) | 6% | 0% | 0% |
| [0.3, 0.5) | 28% | 0% | 0% |
| [0.5, 0.7) | **61%** | 5% | 12% |
| [0.7, 0.9) | **91%** | 21% | 30% |

### Key Finding

**The fc term is essential for realistic E/T partitioning:**

- **With fc**: At full canopy (NDVI>0.7), T=91%, E=9% - transpiration dominates as
  expected for irrigated alfalfa
- **Without fc**: At full canopy, T=21-30%, E=70-79% - evaporation dominates,
  which is physically unrealistic

The models without fc achieve similar total ET by inflating soil evaporation
(Ke ≈ 0.50) to compensate for suppressed transpiration (Kcb ≈ 0.02-0.23). While
this produces correct total ET, the partitioning is implausible.

### Physical Reasoning

For an irrigated alfalfa field at full canopy:
- **Expected**: ~80-90% of ET should be transpiration, ~10-20% evaporation
- **With fc**: Model produces 91% T, 9% E (realistic)
- **Without fc**: Model produces 21-30% T, 70-79% E (unrealistic)

The fc term scales transpiration by fractional canopy cover:
- At low fc (sparse canopy): Reduces transpiration proportionally
- At high fc (full canopy): Allows full transpiration (fc × ks × kcb ≈ ks × kcb)
- Also constrains Ke through the few (exposed soil fraction) term

Without fc, the model has no mechanism to limit evaporation as canopy closes.

### Decision: Restore fc

Based on this analysis, we **restore fc to the kc_act equation** as the default.

The kcb_beta power-modified sigmoid experiment showed that:
1. It can achieve similar total ET to fc × kcb
2. But it cannot replicate the E/T partitioning
3. The parameter "compression" doesn't constrain Ke

### Files Changed (Restoration)

Reverted experimental changes:
- `src/swimrs/process/loop_fast.py` - Restored fc in kc_act equation
- `src/swimrs/process/kernels/water_balance.py` - Restored fc in actual_et kernel
- `src/swimrs/process/kernels/crop_coefficient.py` - Removed kcb_beta from sigmoid
- `src/swimrs/process/state.py` - Removed kcb_beta, linear_alpha, linear_beta
- `src/swimrs/process/input.py` - Removed kcb_beta serialization
- `src/swimrs/calibrate/pest_builder.py` - Removed kcb_beta from calibration

### Updated Default Parameters

Based on calibration results with fc restored:
- `ndvi_k`: 10.0 (was 7.0) - steeper sigmoid transition
- `ndvi_0`: 0.55 for irrigated, 0.15 for non-irrigated (was 0.85/0.15)

### Lessons Learned

1. **Total ET ≠ physical correctness**: A model can predict total ET accurately
   while having unrealistic component values.

2. **Parameter identifiability**: Kcb and Ke are not independently identifiable
   from total ET observations alone. Multiple parameterizations produce similar
   total ET.

3. **fc serves two roles**:
   - Scales transpiration by canopy cover
   - Constrains evaporation through few = 1 - fc

4. **Simpler is not always better**: The 2-parameter linear model matched the
   3-parameter sigmoid for total ET, but both failed on partitioning without fc.

5. **Validation matters**: Without independent E/T observations, we would not
   have discovered the partitioning problem.

### Why fc Scaling Works (and Why It’s Not Just “Squaring NDVI”)

The original concern was that using `kcb = f(NDVI)` and `fc = f(NDVI)` in
`kc_act = fc × ks × kcb + ke` might “square a fraction” and suppress transpiration.
Empirically (and structurally), `fc` helps because it is not just a redundant
multiplier—it changes the model’s degrees of freedom and closes important
loopholes during calibration.

1. **Structural coupling that enforces canopy closure physics**
   - As canopy cover increases, *both* of these happen together:
     - transpiring area increases (`T ∝ fc`)
     - exposed/wet soil area decreases (`few = 1 - fc`, limiting `Ke`)
   - This coupled behavior is hard to reproduce by only changing the NDVI→Kcb
     curve (sigmoid / power sigmoid / linear), because those alternatives only
     reshape transpiration demand and do not provide an equivalent constraint on
     evaporation.

2. **Regularization against E/T equifinality**
   - With only total-ET targets, the model can fit the same ET time series with
     very different partitions by trading off `Kcb` and `Ke`.
   - Removing `fc` makes it easier for calibration to “buy ET” by inflating
     evaporation (`Ke`) and suppressing transpiration (`Kcb`), producing
     physically implausible partitions (e.g., evaporation-dominant ET at full
     canopy).
   - Including `fc` reduces that freedom by forcing canopy closure to both raise
     transpiration and clamp evaporation opportunity.

3. **Canopy-closure gating without extreme Kcb functional forms**
   - `fc` provides an explicit “amount of canopy” term so `ndvi_0`/`ndvi_k` do not
     have to do all the gating by pushing the sigmoid into extreme regimes.
   - This is consistent with the observed shift toward more interpretable
     `ndvi_0` values when `fc` is included in `kc_act`.

4. **It’s a thresholded/convex transform, not a naive square**
   - In the current implementation, `fc` is a bounded, thresholded function of
     `Kcb` (via `kc_min` and `kc_max`), so the effective transpiration coefficient
     behaves like a convex mapping of `Kcb` for much of the range.
   - That convexity is useful: it suppresses unrealistically large transpiration
     during partial cover while still allowing high transpiration fractions once
     the canopy is truly closed.

### Practical Justification (How to Explain It)

Even if this is not the literal FAO-56 “basal coefficient” interpretation, it
is easy to justify as an **area-weighted transpiration model**:

- Interpret `Kcb` as transpiration *capacity per unit vegetated area* (set by
  NDVI and local calibration).
- Interpret `fc` as the **fraction of the field effectively contributing to
  transpiration** (canopy cover / active fraction).
- Then `T = fc × ks × Kcb × ETref` is simply an area weighting, while `Ke`
  governs soil evaporation from the exposed fraction.

This framing matches the key empirical result: accurate total ET is achievable
with many structures, but **realistic E/T partitioning requires an explicit
canopy cover constraint**.

### Management Value (Why This Helps Operations, Not Just Fit)

Once `fc` is in `kc_act`, the model’s internal partitioning becomes usable for
management questions:

- **Irrigation scheduling can target “beneficial ET” (T)** instead of total ET.
  Without `fc`, the model can match total ET with evaporation-dominant solutions
  that would mislead any decision logic based on transpiration.
- **Canopy-altering actions become representable** (cutting/grazing/harvest,
  poor stand establishment, residue/cover effects) because changing effective
  cover immediately changes both transpiration demand (`fc`) and evaporation
  opportunity (`few`).
- **Soft physical priors become possible** even without direct E/T observations:
  e.g., for irrigated dense canopy (NDVI > 0.7), transpiration fraction should
  generally dominate. This can be used as a calibration guardrail to prevent
  “Ke does everything” solutions.
- **Cleaner land-cover defaults**: letting `fc` handle cover/shading physics
  makes `ndvi_0`/`ndvi_k` closer to phenology/greenness parameters rather than
  acting as compensators for missing cover effects.

### Status: RESOLVED

fc restored as default. The FAO-56 dual crop coefficient formulation
`kc_act = fc × ks × kcb + ke` is retained for realistic E/T partitioning.

## Fix: Irrigation-Dependent MAD Bounds (2026-01-28)

### Problem

PEST calibration was collapsing MAD to near-zero for all sites:
- Fort Peck (grassland): 0.6 → 0.047
- Crane (irrigated): 0.02 → 0.011

This is physically unrealistic. Natural grasslands should tolerate significant
soil water depletion before stress (MAD ~ 0.4-0.5), while irrigated crops
trigger irrigation early (MAD ~ 0.1-0.2).

The root cause: MAD bounds were [0.01, 0.9] for all sites, allowing PEST to
find unrealistic low-MAD solutions that compensate for other model errors.

### Solution

Constrain MAD bounds by irrigation status in `pest_builder.py`:

| Irrigation | Initial MAD | Bounds (old) | Bounds (new) |
|------------|-------------|--------------|--------------|
| Irrigated (>20%) | 0.02 | [0.01, 0.9] | [0.01, 0.30] |
| Non-irrigated | 0.50 | [0.01, 0.9] | [0.30, 0.80] |

### Results: Fort Peck (grassland)

| Metric | Previous (MAD→0.047) | Constrained MAD |
|--------|---------------------|-----------------|
| Uncalibrated R² | 0.676 | 0.676 |
| Calibrated R² | 0.664 | **0.676** |
| Calibrated Bias | -0.092 mm | **-0.091 mm** |
| Calibrated RMSE | 0.710 mm | **0.697 mm** |
| Calibrated MAD | 0.047 | **0.312** |

**Key finding:** Constraining MAD to physically realistic bounds:
1. Eliminated unrealistic MAD collapse (0.047 → 0.312)
2. Improved calibrated R² (0.664 → 0.676)
3. Calibrated model now matches uncalibrated performance

### Calibrated Parameters (Fort Peck, constrained MAD)

| Parameter | Mean | Range |
|-----------|------|-------|
| mad | 0.312 | 0.300-0.333 |
| ndvi_0 | 0.137 | 0.108-0.162 |
| ndvi_k | 6.31 | 5.46-7.02 |
| kr_alpha | 0.945 | 0.677-1.000 |
| ks_alpha | 0.790 | 0.425-1.000 |
| aw | 355 mm | 323-382 mm |

### Physical Interpretation

The constrained calibration finds a more realistic parameter set:
- **MAD = 0.31**: Grassland tolerates ~31% depletion before stress (reasonable)
- **ndvi_0 = 0.14**: Transpiration begins at low NDVI (appropriate for grass)
- **kr_alpha = 0.95**: Fast evaporation response to rain (important for dryland)

Without constraints, PEST was using near-zero MAD to artificially increase
soil water availability, compensating for other model limitations.

### Files Changed

- `src/swimrs/calibrate/pest_builder.py`: Added irrigation-dependent MAD bounds
