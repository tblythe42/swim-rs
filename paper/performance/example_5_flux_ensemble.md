# Example 5: Flux Ensemble — Performance Summary

**Status:** Current canonical Example 5 validation uses the March 31, 2026
paired rerun. Older February 19, 2026 tables are deprecated because they
predated the paired-comparison policy and produced non-comparable denominators.

**Run:** Run 11 (reference calibration)
**Validation policy:** `examples/5_Flux_Ensemble/VALIDATION_POLICY.md`
**Canonical evaluation date:** March 31, 2026
**Evaluation files:** `/data/ssd1/swim/5_Flux_Ensemble/results/evaluation_metrics.csv`,
`/data/ssd1/swim/5_Flux_Ensemble/results/evaluation_monthly_metrics.csv`

## Run Configuration

| Setting | Value |
|---------|-------|
| Calibration configuration | 60 US cropland flux tower sites |
| Validation exclusion list | `MB_Pch` |
| Evaluation candidate cohort | 59 sites |
| Period | 1995-01-01 to 2025-12-31 (11,323 days) |
| Calibration target | Ensemble mean of 6 OpenET Landsat models |
| Ensemble members | SSEBop, PT-JPL, SIMS, geeSEBAL, eeMETRIC, DisALEXI |
| ETf observation period | 2016-2025 |
| Parameters | 8 per site: aw, ndvi_k, ndvi_0, mad, kr_alpha, ks_alpha, swe_alpha, swe_beta |
| PEST++ IES | 200 realizations, 3 iterations |
| Workers | 40 |
| Runtime | 108.6 min |
| Meteorology | GridMET |
| Snow | SNODAS (2004+) |
| Soils | SSURGO |
| mask_mode | none |
| kc_max floor | 1.35 |
| max_irr_rate | 100 mm/day |
| runoff_process | cn |
| refet_type | eto |

## Canonical Comparison Policy

- Headline ET benchmark: Volk et al. 3x3 OpenET ensemble ET.
- Headline comparison mode: paired.
- Daily headline metrics use the exact same valid day set for SWIM and the
  ensemble within each site.
- Monthly headline metrics use the exact same valid month set for SWIM and the
  ensemble within each site, after requiring at least 20 valid daily flux
  observations in a month.
- Headline aggregate tables include only sites with finite SWIM and ensemble
  metrics in the paired output.
- Historical pre-fairness or experimental "independent" summaries are
  diagnostic-only and are not the canonical Example 5 benchmark.

## Daily ET (mm/day) — Canonical Paired Benchmark

58 paired sites with finite SWIM and ensemble metrics.

| Model | R² mean | R² median | RMSE mean | Bias mean |
|-------|---------|-----------|-----------|-----------|
| SWIM | 0.392 | 0.652 | 1.277 | -0.151 |
| Ensemble | 0.323 | 0.567 | 1.382 | -0.099 |

## Monthly ET (mm/month) — Canonical Paired Benchmark

33 paired sites with finite SWIM and ensemble metrics.

| Model | R² mean | R² median | RMSE mean | Bias mean |
|-------|---------|-----------|-----------|-----------|
| SWIM | 0.814 | 0.845 | 21.451 | -0.774 |
| Ensemble | 0.799 | 0.859 | 21.224 | -5.877 |

## Interpretation

1. The March 31, 2026 paired rerun materially lowers the daily headline SWIM
   score relative to the older February 19, 2026 summaries because SWIM is no
   longer scored on a broader date set than the benchmark.
2. At the monthly scale, SWIM remains slightly higher on mean R², while the
   ensemble retains a slightly higher median R² and lower RMSE.
3. SWIM remains much less negatively biased than the ensemble at the monthly
   scale.
4. Future Example 5 tables and figure captions should cite the policy note and
   report the paired cohort size explicitly.

## Data Paths

| Resource | Path |
|----------|------|
| Daily metrics | `/data/ssd1/swim/5_Flux_Ensemble/results/evaluation_metrics.csv` |
| Monthly metrics | `/data/ssd1/swim/5_Flux_Ensemble/results/evaluation_monthly_metrics.csv` |
| ETf metrics | `/data/ssd1/swim/5_Flux_Ensemble/results/evaluation_etf_metrics.csv` |
| Calibrated parameters | `/data/ssd1/swim/5_Flux_Ensemble/results/run11_full_period/5_Flux_Ensemble.3.par.csv` |
| Phi convergence | `/data/ssd1/swim/5_Flux_Ensemble/results/run11_full_period/5_Flux_Ensemble.phi.meas.csv` |
| Validation policy | `examples/5_Flux_Ensemble/VALIDATION_POLICY.md` |
| Run 11 reference doc | `examples/5_Flux_Ensemble/RUN11_REFERENCE.md` |

## Historical Note

The February 19, 2026 Example 5 validation tables were generated before the
paired-comparison policy above. They are preserved only as historical context
and should not be cited as the current Example 5 benchmark.
