"""Run the Study 2 weighting ablation: E1 (spread) vs E2 (fixed_sd).

Launches both calibration runs sequentially, then evaluates each against
flux tower ET using the canonical Ex5 evaluation, and produces paired
comparison outputs.

Usage:
    python run_weighting_ablation.py
    python run_weighting_ablation.py --dry-run --debug-fields US-Bi1,US-Ne1,US-ARM
"""

import argparse
import json
import os
import time
from pathlib import Path

EXPERIMENTS = {
    "e1_spread": {
        "etf_weighting_mode": "spread",
        "etf_weighting_fixed_sd": 0.33,
        "etf_weighting_spread_floor": 0.1,
        "etf_weighting_min_members": 2,
    },
    "e2_fixed_sd": {
        "etf_weighting_mode": "fixed_sd",
        "etf_weighting_fixed_sd": 0.33,
        "etf_weighting_spread_floor": 0.1,
        "etf_weighting_min_members": 2,
    },
}


def _load_config():
    from swimrs.swim.config import ProjectConfig

    project_dir = Path(__file__).resolve().parent
    conf = project_dir / "5_Flux_Ensemble.toml"
    cfg = ProjectConfig()
    if os.path.isdir("/data/ssd2/swim"):
        cfg.read_config(str(conf), calibrate=True)
    else:
        cfg.read_config(str(conf), project_root_override=str(project_dir.parent), calibrate=True)
    return cfg


def run_calibration(cfg, experiment_id, experiment_spec, results_dir, debug_fields=None):
    from calibrate import run_pest_sequence

    cfg.etf_weighting_mode = experiment_spec["etf_weighting_mode"]
    cfg.etf_weighting_fixed_sd = experiment_spec["etf_weighting_fixed_sd"]
    cfg.etf_weighting_spread_floor = experiment_spec["etf_weighting_spread_floor"]
    cfg.etf_weighting_min_members = experiment_spec["etf_weighting_min_members"]

    print(f"\n{'=' * 80}")
    print(f"CALIBRATION: {experiment_id} (weighting_mode={cfg.etf_weighting_mode})")
    print(f"Results: {results_dir}")
    print(f"{'=' * 80}\n")

    t0 = time.time()
    run_pest_sequence(
        cfg,
        results_dir,
        pdc_remove=False,
        debug_fields=debug_fields,
    )
    elapsed = time.time() - t0

    runtime = {
        "experiment_id": experiment_id,
        "weighting_mode": cfg.etf_weighting_mode,
        "fixed_sd": cfg.etf_weighting_fixed_sd,
        "spread_floor": cfg.etf_weighting_spread_floor,
        "min_members": cfg.etf_weighting_min_members,
        "realizations": cfg.realizations,
        "workers": cfg.workers,
        "wall_seconds": round(elapsed, 1),
        "wall_minutes": round(elapsed / 60, 1),
    }
    with open(os.path.join(results_dir, "runtime.json"), "w") as f:
        json.dump(runtime, f, indent=2)

    # Save config snapshot
    spec_path = os.path.join(results_dir, "experiment_spec.json")
    with open(spec_path, "w") as f:
        json.dump(experiment_spec, f, indent=2)

    return elapsed


def run_evaluation(cfg, experiment_id, results_dir, monthly=False):
    """Run canonical evaluation for one experiment."""
    from evaluate import evaluate, evaluate_monthly, load_config

    from swimrs.container import SwimContainer

    project = cfg.project_name
    par_csv = os.path.join(results_dir, f"{project}.3.par.csv")
    if not os.path.exists(par_csv):
        par_csv = os.path.join(results_dir, f"{project}.2.par.csv")
    if not os.path.exists(par_csv):
        print(f"  WARNING: no par.csv found in {results_dir}, skipping evaluation")
        return

    container_path = os.path.join(cfg.data_dir, f"{project}.swim")
    container = SwimContainer.open(container_path, mode="r")
    flux_dir = os.path.join(cfg.data_dir, "daily_flux_files")
    fids = container.field_uids

    eval_cfg = load_config()

    try:
        if monthly:
            metrics = evaluate_monthly(eval_cfg, container, par_csv, fids, flux_dir)
            out_csv = os.path.join(results_dir, "evaluation_monthly_metrics.csv")
        else:
            metrics = evaluate(eval_cfg, container, par_csv, fids, flux_dir)
            out_csv = os.path.join(results_dir, "evaluation_metrics.csv")
        metrics.to_csv(out_csv)
        print(f"  {experiment_id} {'monthly' if monthly else 'daily'} metrics -> {out_csv}")
    finally:
        container.close()


def summarize_ablation(results_root):
    """Produce paired comparison between E1 and E2."""
    import pandas as pd

    e1_dir = os.path.join(results_root, "ablation_e1_spread")
    e2_dir = os.path.join(results_root, "ablation_e2_fixed_sd")
    summary_dir = os.path.join(results_root, "ablation_summary")
    os.makedirs(summary_dir, exist_ok=True)

    for timescale in ["daily", "monthly"]:
        suffix = "_monthly_metrics.csv" if timescale == "monthly" else "_metrics.csv"
        e1_path = os.path.join(e1_dir, f"evaluation{suffix}")
        e2_path = os.path.join(e2_dir, f"evaluation{suffix}")

        if not os.path.exists(e1_path) or not os.path.exists(e2_path):
            print(f"  Skipping {timescale} comparison (missing files)")
            continue

        e1 = pd.read_csv(e1_path, index_col=0)
        e2 = pd.read_csv(e2_path, index_col=0)

        common = e1.index.intersection(e2.index)
        e1 = e1.loc[common]
        e2 = e2.loc[common]

        # Build paired delta table
        paired = pd.DataFrame(index=common)
        for metric in ["r2_swim", "rmse_swim", "bias_swim"]:
            if metric in e1.columns and metric in e2.columns:
                paired[f"e1_{metric}"] = e1[metric]
                paired[f"e2_{metric}"] = e2[metric]
                paired[f"delta_{metric}"] = e1[metric] - e2[metric]

        if "r2_swim" in e1.columns:
            paired["e1_wins_r2"] = e1["r2_swim"] > e2["r2_swim"]

        out_path = os.path.join(summary_dir, f"paired_site_deltas_{timescale}.csv")
        paired.to_csv(out_path)
        print(f"  Paired deltas ({timescale}): {out_path}")

        # Aggregate summary
        has_both = e1["r2_swim"].notna() & e2["r2_swim"].notna()
        n = has_both.sum()
        if n > 0:
            e1_wins = (e1.loc[has_both, "r2_swim"] > e2.loc[has_both, "r2_swim"]).sum()
            print(f"\n  {timescale.upper()} SUMMARY ({n} paired sites):")
            print(
                f"    E1 (spread):   med R2={e1.loc[has_both, 'r2_swim'].median():.3f}  "
                f"med RMSE={e1.loc[has_both, 'rmse_swim'].median():.3f}"
            )
            print(
                f"    E2 (fixed_sd): med R2={e2.loc[has_both, 'r2_swim'].median():.3f}  "
                f"med RMSE={e2.loc[has_both, 'rmse_swim'].median():.3f}"
            )
            print(f"    E1 win rate: {e1_wins}/{n} = {100 * e1_wins / n:.0f}%")

    # Phi comparison
    for exp_id, exp_dir in [("e1_spread", e1_dir), ("e2_fixed_sd", e2_dir)]:
        phi_path = os.path.join(exp_dir, "5_Flux_Ensemble.phi.meas.csv")
        if os.path.exists(phi_path):
            phi = pd.read_csv(phi_path)
            print(f"\n  PHI ({exp_id}): columns={list(phi.columns)[:5]}")

    # Runtime comparison
    rows = []
    for exp_id, exp_dir in [("e1_spread", e1_dir), ("e2_fixed_sd", e2_dir)]:
        rt_path = os.path.join(exp_dir, "runtime.json")
        if os.path.exists(rt_path):
            with open(rt_path) as f:
                rt = json.load(f)
            rows.append(rt)
    if rows:
        rt_df = pd.DataFrame(rows)
        rt_path = os.path.join(summary_dir, "runtime_comparison.csv")
        rt_df.to_csv(rt_path, index=False)
        print(f"\n  Runtime comparison: {rt_path}")


def main():
    parser = argparse.ArgumentParser(description="Run Study 2 weighting ablation (E1 vs E2)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use reduced realizations (20) for quick validation",
    )
    parser.add_argument(
        "--debug-fields",
        type=str,
        default=None,
        help="Comma-separated site IDs for debug subset",
    )
    parser.add_argument(
        "--skip-calibration",
        action="store_true",
        help="Skip calibration, only run evaluation and summary",
    )
    parser.add_argument(
        "--only",
        choices=["e1", "e2"],
        default=None,
        help="Run only one experiment (e1=spread, e2=fixed_sd)",
    )
    args = parser.parse_args()

    cfg = _load_config()
    results_root = os.path.join(cfg.project_ws, "results")

    debug_fields = None
    if args.debug_fields:
        debug_fields = [s.strip() for s in args.debug_fields.split(",")]

    if args.dry_run:
        cfg.realizations = 20
        cfg.workers = min(10, cfg.workers)
        print("DRY RUN: realizations=20, reduced workers")

    # Determine which experiments to run
    run_ids = list(EXPERIMENTS.keys())
    if args.only == "e1":
        run_ids = ["e1_spread"]
    elif args.only == "e2":
        run_ids = ["e2_fixed_sd"]

    # Phase 1: Calibration
    if not args.skip_calibration:
        for exp_id in run_ids:
            exp_dir = os.path.join(results_root, f"ablation_{exp_id}")
            run_calibration(cfg, exp_id, EXPERIMENTS[exp_id], exp_dir, debug_fields)

    # Phase 2: Evaluation (daily + monthly)
    for exp_id in run_ids:
        exp_dir = os.path.join(results_root, f"ablation_{exp_id}")
        if not os.path.exists(exp_dir):
            print(f"  Skipping evaluation for {exp_id} (no results dir)")
            continue
        print(f"\nEvaluating {exp_id}...")
        run_evaluation(cfg, exp_id, exp_dir, monthly=False)
        run_evaluation(cfg, exp_id, exp_dir, monthly=True)

    # Phase 3: Summary
    print("\nSummarizing ablation...")
    summarize_ablation(results_root)


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    main()
