# Paper — TODO Experiments

## 1. Ensemble-Derived Weighting vs Standard Weighting

**Question:** Does using inter-model spread to weight ETf observations improve
calibration outcomes compared to fixed-denominator magnitude weighting?

### Background

`PestBuilder._write_etf_obs` (pest_builder.py:1332-1342) supports two weighting modes:

- **Ensemble-derived weighting** (`members` provided): `weight = obsval / (std + 0.1)`
  where `std` is the per-timestep standard deviation across ensemble member ETf values.
  Observations where models agree strongly (low std) receive higher weight; observations
  where models disagree (high std) are down-weighted.

- **Standard weighting** (`members=None`): `weight = obsval / 0.33` (fixed denominator).
  Pure magnitude weighting with no uncertainty signal from ensemble disagreement.

Run 11 (the current Ex5 reference) uses ensemble-derived weighting with 6 members.
Ex4 uses standard weighting with a single SSEBop target (no ensemble at all).

The existing Ex4 vs Ex5 paired comparison is confounded by target model (SSEBop vs
ensemble mean), period, and code version. We need a controlled experiment that isolates
the weighting effect.

### Experiment Design

Hold constant:
- Sites: 60 cropland flux stations (Ex5 cohort)
- Period: 1995-2025
- Code version: current (irr_flag fix, kc_max=1.35, max_irr_rate=100)
- Calibration target values: ensemble mean of 6 OpenET models (SSEBop, PT-JPL,
  SIMS, geeSEBAL, eeMETRIC, DisALEXI)
- PEST++ IES: 200 realizations, 3 iterations, 40 workers
- Container: same 5_Flux_Ensemble.swim
- mask_mode: none

Vary:
- **Treatment A (ensemble-derived):** `members=["ssebop", "ptjpl", "sims", "geesebal",
  "eemetric", "disalexi"]` — weights from inter-model spread (current Run 11 approach)
- **Treatment B (standard):** `members=None` — fixed-denominator magnitude weighting,
  same ensemble-mean target values as obsval

### Implementation

Treatment A already exists (Run 11). Treatment B requires a calibration run with
`members=None` passed to `build_pest()` while keeping `target_etf="ensemble"`. This
can be done by modifying calibrate.py to pass `members=None` (or adding a CLI flag).

Store results in `results/run12_standard_weight/` (or similar).

### Evaluation

- Paired site-level daily and monthly R², RMSE, bias (same evaluate.py, same flux data)
- Site-level win rate (A vs B)
- Delta R² distribution with percentiles
- Phi convergence comparison
- Per-site weight distribution diagnostics (are a few sites dominating phi under
  standard weighting?)

### Expected Runtime

~110 min (same as Run 11: 884 model runs, 40 workers).

### Hypothesis

Ensemble-derived weighting should improve calibration by down-weighting observations
where models disagree (noisy/unreliable ETf estimates). The effect may be strongest at
sites with high inter-model variance. If the effect is small, it suggests the ensemble
mean target itself is the primary source of value, not the uncertainty-informed weighting.

### Status

- [ ] Treatment A: exists (Run 11, results in `results/run11_full_period/`)
- [ ] Treatment B: needs calibration run
- [ ] Paired evaluation
- [ ] Write up for paper
