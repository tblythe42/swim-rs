# Example 4: Flux Network — Performance Summary

**Status:** PRE-GWSUB-FIX / PRE-FAIRNESS-FIX. These numbers predate the ETf
interpolation fix in `_compute_groundwater_subsidy()` (commit 8cb426b) and the
paired-evaluation fairness fix. Wetland/riparian results will change after
container rebuild + recalibration. All comparative metrics will change after
re-evaluation with strict pairing.

**Evaluation method:** Daily and monthly metrics are computed on strictly paired
observation sets — both SWIM and SSEBop are scored on the exact same days/months
per site. Sites in the exclusion list (MB_Pch) are omitted from all outputs.

**Run date:** 2026-02-21 (evaluation), 2026-02-20 (calibration)
**Evaluation files:** `/data/ssd1/swim/4_Flux_Network/results/evaluation_metrics.csv` (Feb 21)

## Run Configuration

| Setting | Value |
|---------|-------|
| Sites | 160 US flux tower sites, 6 land cover classes |
| Period | 1987-01-01 to 2024-12-31 (13,880 days) |
| Calibration target | SSEBop NHM ETf (mask-switched irr/inv_irr) |
| Parameters | per-site: aw, ndvi_k, ndvi_0, mad, kr_alpha, ks_alpha, swe_alpha, swe_beta |
| PEST++ IES | 200 realizations, 3 iterations (noptmax=3) |
| Meteorology | GridMET (with static TIF-based ETo correction) |
| Snow | SNODAS |
| Soils | SSURGO |
| LULC | MODIS-derived root depth and perennial flags |
| mask_mode | none |
| runoff_process | cn |
| refet_type | eto |

## Validation Data

Energy-balance-corrected flux tower ET from 160 AmeriFlux/FLUXNET stations.
SSEBop NHM ET computed as interpolated ETf x ETo (no-mask mode).

## Daily ET (mm/day) — 160 sites, 318,716 site-days

### Overall

| Metric | SWIM | SSEBop NHM (no-mask) |
|--------|------|----------------------|
| R² mean | -0.461 | -0.664 |
| R² median | 0.490 | 0.419 |
| RMSE mean | 1.131 | 1.132 |
| RMSE median | 0.966 | 1.087 |
| Bias mean | -0.113 | -0.041 |
| Bias median | -0.029 | -0.051 |
| Win rate (R²) | 104/160 (65.0%) | 56/160 (35.0%) |
| Win rate (RMSE) | 104/160 (65.0%) | 56/160 (35.0%) |

### SWIM R² Distribution (daily)

| Percentile | R² |
|------------|-----|
| P10 | -0.879 |
| P25 | 0.000 |
| P50 | 0.490 |
| P75 | 0.685 |
| P90 | 0.780 |

### By Land Cover (daily, median metrics)

| Land Cover | n | SWIM R² | SSEBop R² | SWIM RMSE | SSEBop RMSE | SWIM wins |
|------------|---|---------|-----------|-----------|-------------|-----------|
| Croplands | 60 | 0.641 | 0.605 | 1.183 | 1.239 | 38/60 (63%) |
| Grasslands | 30 | 0.509 | 0.419 | 0.815 | 0.908 | 21/30 (70%) |
| Shrublands | 29 | -0.169 | -0.131 | 0.677 | 0.741 | 16/29 (55%) |
| Evergreen Forests | 18 | 0.435 | 0.039 | 0.831 | 1.169 | 16/18 (89%) |
| Mixed Forests | 14 | 0.655 | 0.582 | 1.051 | 1.111 | 9/14 (64%) |
| Wetland/Riparian | 9 | -0.117 | 0.605 | 1.325 | 1.093 | 4/9 (44%) |

## Monthly ET (mm/month) — 149 sites

### Overall

| Metric | SWIM | SSEBop NHM (no-mask) |
|--------|------|----------------------|
| R² mean | 0.301 | -0.225 |
| R² median | 0.645 | 0.542 |
| RMSE mean | 26.61 | 27.12 |
| RMSE median | 20.67 | 24.80 |
| Bias mean | -4.15 | -1.23 |
| Win rate (R²) | 104/149 (69.8%) | 45/149 (30.2%) |

### SWIM R² Distribution (monthly)

| Percentile | R² |
|------------|-----|
| P10 | -0.883 |
| P25 | 0.135 |
| P50 | 0.645 |
| P75 | 0.814 |
| P90 | 0.882 |

### By Land Cover (monthly, median metrics)

| Land Cover | n | SWIM R² | SSEBop R² | SWIM RMSE | SSEBop RMSE | SWIM wins |
|------------|---|---------|-----------|-----------|-------------|-----------|
| Croplands | 51 | 0.786 | 0.705 | 25.46 | 28.06 | 33/51 (65%) |
| Grasslands | 29 | 0.720 | 0.551 | 17.78 | 21.11 | 21/29 (72%) |
| Shrublands | 28 | 0.223 | -0.007 | 14.42 | 17.89 | 21/28 (75%) |
| Evergreen Forests | 18 | 0.572 | 0.082 | 18.87 | 31.24 | 16/18 (89%) |
| Mixed Forests | 14 | 0.740 | 0.650 | 25.39 | 26.25 | 9/14 (64%) |
| Wetland/Riparian | 9 | -0.481 | 0.711 | 38.46 | 24.84 | 4/9 (44%) |

## Key Findings

1. **SWIM wins 65% of sites daily, 70% monthly** against SSEBop NHM (the calibration
   target model) when evaluated against independent flux tower ET.

2. **Strongest classes:** Evergreen forests (89% win rate both daily and monthly),
   grasslands (70-72%), and croplands (63-65%).

3. **Weakest class:** Wetland/riparian sites (44% win rate). SWIM's precipitation-based
   soil water accounting cannot reproduce ET driven by shallow groundwater subsidy.
   These 9 sites have negative median R² at both timescales.

4. **Bias:** SWIM has slightly larger mean bias (-0.113 mm/day) than SSEBop (-0.041 mm/day)
   at the daily scale but near-zero median bias (-0.029 mm/day).

5. **Heavy tails:** Mean R² is strongly negative for both models due to a few catastrophic
   sites (P10 = -0.879). Median R² is the more informative central tendency.

6. **LULC-derived root depth** (compared to prior baseline) improved evergreen forests
   (+0.16 R² daily), shrublands (+0.17), and wetland/riparian (+0.28). Overall daily
   win rate improved from 54% to 65%.

## Data Paths

| Resource | Path |
|----------|------|
| Daily metrics | `/data/ssd1/swim/4_Flux_Network/results/evaluation_metrics.csv` |
| Monthly metrics | `/data/ssd1/swim/4_Flux_Network/results/evaluation_monthly_metrics.csv` |
| ETf metrics | `/data/ssd1/swim/4_Flux_Network/results/evaluation_etf_metrics.csv` |
| Calibrated parameters | `/data/ssd1/swim/4_Flux_Network/results/4_Flux_Network.3.par.csv` |
| TOML config | `examples/4_Flux_Network/4_Flux_Network.toml` |
| Evaluation script | `examples/4_Flux_Network/evaluate.py` |
| Shapefile (160 sites) | `/data/ssd1/swim/4_Flux_Network/data/gis/flux_fields.shp` |

## Notes

- The Feb 21 evaluation is from the same calibration run as Feb 9 (LULC-derived root depth),
  but re-evaluated with a slightly updated evaluate.py. Monthly site count rose from 144 to
  149, and some median metrics shifted slightly.
- SSEBop NHM comparison uses no-mask (full footprint) mode, which performs slightly better
  than mask-switched mode (the calibration target).
- The negative mean R² is dominated by a handful of extreme outlier sites. The median is
  more representative and more commonly reported in remote sensing ET literature.
