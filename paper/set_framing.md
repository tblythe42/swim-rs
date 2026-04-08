# SWIM-RS — Application Set Framing

> **Scope:** This document records the agreed narrative logic connecting the three application studies. Manuscript and journal requirements are addressed in the RSE guide and revision plan.

---

## The narrative arc: characterize → optimize → port and stress-test

The three studies are not parallel experiments. Each answers a question the previous one raises and cannot answer itself. This logical necessity should be visible to the reader at every level — objectives, results subsection titles, discussion structure.

| Study | Calibration target | Scope | Role | Primary question |
|---|---|---|---|---|
| 1 | SSEBop NHM | CONUS, multi-LULC | Characterize | What are the framework's minimum requirements and operating limits? |
| 2 | OpenET 6-algorithm ensemble | CONUS, cropland | Optimize | Does ensemble ETf calibration with consensus weighting beat the best available ET product? |
| 3 | PT-JPL | Global, multi-LULC | Portability stress test | Does the framework port globally on available inputs, and can informative priors preserve skill when the ETf target is biased? |

---

## Study 1 — SSEBop NHM as the gateway study

The NHM's 1987–2025 record is the scientific justification for Study 1. No other available dataset makes period-of-record sensitivity testable across meaningful time windows. The older SSEBop version is not a limitation — the long record is the point.

Study 1 should answer three questions that Studies 2 and 3 depend on but cannot address themselves:

1. **How much ETf record is needed?** Calibrate against progressively shorter windows of the NHM record and track parameter convergence by LULC class.
2. **How much compute is enough?** Ablate PEST++ IES iterations and define the accuracy-compute tradeoff curve.
3. **Do parameters transfer by LULC class?** If posterior parameters cluster within LULC classes, a transferable global prior is feasible — a direct methodological input to Study 3.

The flux validation benchmark (SWIM-RS vs. SSEBop NHM on paired observations) establishes a performance floor over a conservative comparator. Frame it as such — the paper's competitive performance claim belongs to Study 2.

The NHM's status as an operational USGS national product is worth one sentence of framing in the introduction and methods. It grounds Study 1 in an operationally relevant context and acknowledges the collaboration that made the long-record ETf data available.

**Transition sentence to Study 2:** "Having established minimum data and compute requirements and confirmed that the framework adds skill over a long-record operational product, we next evaluate performance under optimal calibration conditions using the full OpenET ensemble."

---

## Study 2 — OpenET ensemble as the performance study

Study 2 carries the paper's strongest competitive result. The Volk et al. benchmark is independent (not used for calibration) and represents the current best-available operational ET product. The 87% bias reduction is the single most compelling number in the paper — it demonstrates that the water balance constraint eliminates systematic error the ensemble product cannot correct on its own.

The consensus weighting mechanism is Study 2's methodological distinction from Study 1. The six algorithm ETf series provide both the ensemble mean signal and the inter-model spread that weights individual capture dates. This should be stated clearly in the methods and revisited in the discussion when comparing Study 1 and Study 2 results.

**Transition sentence to Study 3:** "The CONUS applications establish framework performance under both operational and optimal calibration conditions. We next assess whether the same architecture ports globally using only inputs available anywhere on Earth, and whether prior-informed calibration can retain skill when the ETf target is less reliable."

---

## Study 3 — PT-JPL global application as the portability stress test

PT-JPL is the right choice for Study 3: globally available, integrated into the existing SWIM-RS workflow, and not dependent on CONUS-specific data products. Study 3 tests the framework at the edge of its operating envelope — single algorithm, no IrrMapper/LANID, ERA5-Land + HWSD replacing GridMET + SSURGO.

### What Study 3 demonstrates

Study 3 makes two distinct contributions, and the framing must separate them clearly:

1. **Parameter portability (primary result).** LULC-specific parameter medians from Study 1 (CONUS, GridMET, SSEBop) transfer to 241 sites on 5 continents using ERA5-Land and PT-JPL — without any recalibration. SWIM Defaults reduces PT-JPL ET bias from +0.41 to +0.10 mm/d and improves R² for 7 of 11 LULC classes. The physical water balance constraint is the mechanism: it smooths noisy ETf observations, fills temporal gaps, and prevents physically implausible ET. This is what operational users need — a model that works out of the box internationally.

2. **Diagnostic contribution.** The calibration attempt against PT-JPL ETf reveals LULC-dependent bias in the PT-JPL product that was not previously characterized at this scale. PT-JPL overestimates ET by 6% for cropland but 82% for woody savanna (145 flux sites, 11 LULC classes). This bias structure explains why unconstrained site-specific calibration degrades performance for forests — the model contorts parameters to fit biased targets. This quantification is itself a contribution to the remote sensing community's understanding of algorithmic ET bias.

### Regularized calibration as the bridge

The current unconstrained calibration against PT-JPL underperformed because the optimizer pushed parameters to compensatory extremes (62% of sites at `ndvi_k` lower bound, 35% at `aw` upper bound, 29% at `ks_damp` upper bound). The LULC defaults outperformed the calibrated parameters for most non-cropland classes, but this should be treated as the failure mode of an unconstrained run against a biased target, not as the final verdict on Study 3.

The next step is **regularized calibration using Study 1 posteriors as informative priors**. This is the methodological link that makes the three studies a coherent system:

- Study 1 produces LULC-specific parameter distributions (posterior means and covariances from 200-member ensembles across 161 CONUS sites)
- Study 3 uses those distributions as Tikhonov regularization targets in PEST++ IES, penalizing deviations from the LULC-class mean
- The regularization prevents the compensatory parameter drift that plagued the unconstrained run while still allowing site-specific adjustment where the data supports it

This is the correct experimental design: the prior comes from an independent dataset (CONUS SSEBop, Study 1), the calibration target comes from a different product (international PT-JPL, Study 3), and the regularization prevents the biased target from dominating the physically informed prior. If regularized calibration improves on both unconstrained calibration and raw defaults, it validates the full characterize → optimize → port-and-stress-test arc. If it doesn't, the defaults result is still strong and the diagnostic contribution stands.

The regularization experiment should be reported as a third configuration alongside the unconstrained calibration and the defaults baseline, producing a clean three-row comparison per LULC class.

### PT-JPL bias as a finding, not a limitation

The PT-JPL bias table (LULC-specific overestimation ratios from 145 flux sites) should be presented as a standalone result, not buried in the limitations section. For RSE readers, a multi-LULC characterization of algorithmic ET bias validated against flux towers at this scale is directly useful — it informs correction strategies for any study using PT-JPL internationally. Frame it as: *the inverse modeling framework serves as a diagnostic tool for the ETf product, not just a consumer of it.*

### What Study 3 must deliver

1. Parameter portability table: SWIM Defaults vs PT-JPL ET by LULC class (complete)
2. PT-JPL bias structure: overestimation ratio by LULC at 145 flux sites (complete)
3. Regularized calibration: SWIM with Study 1 priors vs defaults vs unconstrained (pending)
4. Cropland honest assessment: PT-JPL is already accurate for cropland (ratio 1.06) — the value-add is continuous daily gap-filled output, not bias correction. Study 2 already showed SWIM beats the best product when given quality targets.

---

## The calibration target rationale — state it once

The three studies use three different ETf sources. This is an asset but will confuse reviewers without explicit explanation. One short paragraph in the methods before the study subsections should state that the varying targets are deliberate — they demonstrate framework robustness and reflect three distinct operational contexts — and briefly give the rationale for each choice.

The varying ETf quality across studies is actually the paper's strongest structural argument: it shows that the framework's value-add depends on the target quality, and that the model degrades gracefully. With good targets (OpenET ensemble), calibration can outperform the source. With adequate targets (SSEBop), calibration adds modest skill. With biased targets (PT-JPL non-cropland), the physical constraint and transferable priors carry the model while unconstrained calibration underperforms and regularized calibration becomes the key test. This gradient is a feature of the experimental design, not a weakness.

---

## What Study 1 must deliver to earn the gateway role

Study 1 earns its position only if the sensitivity and efficiency experiments are completed and reported. If the period-of-record analysis, compute ablation, and LULC parameter clustering cannot be finished before submission, Study 1 reverts to a long-record benchmark study and the gateway framing should be dropped from the objectives and discussion.

Critically, Study 1's LULC parameter posteriors now serve double duty: they are both a scientific finding (parameter identifiability by land cover) and a methodological input to Study 3 (regularization priors). This strengthens the gateway framing — Study 1 doesn't just characterize performance, it produces the transferable knowledge that Study 3 consumes.

## The value gradient — structuring the discussion

The discussion should make the ETf quality gradient explicit. The three studies occupy different points on a target-quality axis:

| Target quality | Study | Primary SWIM value | Calibration outcome |
|---|---|---|---|
| High (OpenET ensemble) | 2 | Calibrated model exceeds source product | Outperforms benchmark |
| Moderate (SSEBop NHM) | 1 | Calibration adds skill over long record | Wins 65-70% of comparisons |
| Variable (PT-JPL, LULC-dependent) | 3 | Physical constraint + parameter transfer | Regularized calibration pending; defaults outperform raw PT-JPL |

This framing turns Example 6's "problem" into the paper's most interesting result: the framework's robustness degrades predictably with target quality, and regularization from upstream studies is the mechanism that maintains skill. No other ET modeling framework in the literature has demonstrated this kind of cross-study parameter transfer at continental-to-global scale.
