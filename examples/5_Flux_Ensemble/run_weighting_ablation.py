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


def _find_par_csv(results_dir, project):
    """Find the highest-iteration par.csv in a results directory."""
    for i in range(10, -1, -1):
        candidate = os.path.join(results_dir, f"{project}.{i}.par.csv")
        if os.path.exists(candidate):
            return candidate
    return None


def run_evaluation(cfg, experiment_id, results_dir, mode="daily", debug_fields=None):
    """Run canonical evaluation for one experiment.

    mode: 'daily' (volk source), 'monthly', or 'etf'.
    When debug_fields is set, limits evaluation to that subset only.
    """
    from evaluate import evaluate, evaluate_etf, evaluate_monthly, load_config

    from swimrs.container import SwimContainer

    project = cfg.project_name
    par_csv = _find_par_csv(results_dir, project)
    if par_csv is None:
        print(f"  WARNING: no par.csv found in {results_dir}, skipping evaluation")
        return

    container_path = os.path.join(cfg.data_dir, f"{project}.swim")
    container = SwimContainer.open(container_path, mode="r")
    flux_dir = os.path.join(cfg.data_dir, "daily_flux_files")

    if debug_fields is not None:
        fids = [f for f in debug_fields if f in container.field_uids]
    else:
        fids = container.field_uids

    eval_cfg = load_config()

    try:
        if mode == "monthly":
            metrics = evaluate_monthly(eval_cfg, container, par_csv, fids, flux_dir)
            out_csv = os.path.join(results_dir, "evaluation_monthly_metrics.csv")
        elif mode == "etf":
            metrics = evaluate_etf(eval_cfg, container, par_csv, fids)
            out_csv = os.path.join(results_dir, "evaluation_etf_metrics.csv")
        else:
            metrics = evaluate(eval_cfg, container, par_csv, fids, flux_dir, openet_source="volk")
            out_csv = os.path.join(results_dir, "evaluation_metrics.csv")
        metrics.to_csv(out_csv)
        print(f"  {experiment_id} {mode} metrics -> {out_csv}")
    finally:
        container.close()


def _build_paired_deltas(e1_path, e2_path, summary_dir, label):
    """Build paired delta CSV for one timescale/evaluation mode."""
    import pandas as pd

    if not os.path.exists(e1_path) or not os.path.exists(e2_path):
        print(f"  Skipping {label} comparison (missing files)")
        return None, None

    e1 = pd.read_csv(e1_path, index_col=0)
    e2 = pd.read_csv(e2_path, index_col=0)
    common = e1.index.intersection(e2.index)
    e1, e2 = e1.loc[common], e2.loc[common]

    paired = pd.DataFrame(index=common)
    for metric in ["r2_swim", "rmse_swim", "bias_swim", "r2", "rmse", "bias"]:
        e1_col = metric if metric in e1.columns else None
        e2_col = metric if metric in e2.columns else None
        if e1_col and e2_col:
            paired[f"e1_{metric}"] = e1[metric]
            paired[f"e2_{metric}"] = e2[metric]
            paired[f"delta_{metric}"] = e1[metric] - e2[metric]

    r2_col = "r2_swim" if "r2_swim" in e1.columns else ("r2" if "r2" in e1.columns else None)
    if r2_col:
        paired["e1_wins_r2"] = e1[r2_col] > e2[r2_col]
        if "n" in e1.columns:
            paired["n_paired"] = e1["n"]

    out_path = os.path.join(summary_dir, f"paired_site_deltas_{label}.csv")
    paired.to_csv(out_path)
    print(f"  Paired deltas ({label}): {out_path}")
    return e1, e2


def _build_weight_summary(exp_dir, summary_dir, exp_id):
    """Build per-site weight summary from weight audit CSV."""
    import pandas as pd

    audit_path = os.path.join(exp_dir, "etf_weight_audit.csv")
    if not os.path.exists(audit_path):
        return
    audit = pd.read_csv(audit_path)
    if audit.empty:
        return

    grouped = audit.groupby("fid")
    rows = []
    wcol = "weight_final" if "weight_final" in audit.columns else "weight"
    total_weight_all = audit.loc[audit[wcol] > 0, wcol].sum()
    for fid, grp in grouped:
        nonzero = grp[grp[wcol] > 0]
        rows.append(
            {
                "fid": fid,
                "n_captures": len(grp),
                "n_eligible": int(grp["eligible"].sum()),
                "n_nonzero_weight": len(nonzero),
                "total_weight": nonzero[wcol].sum(),
                "weight_share": nonzero[wcol].sum() / total_weight_all
                if total_weight_all > 0
                else 0,
                "mean_weight": nonzero[wcol].mean() if len(nonzero) > 0 else 0,
                "max_weight": nonzero[wcol].max() if len(nonzero) > 0 else 0,
                "mean_member_std": grp["member_std"].mean(),
            }
        )

    df = pd.DataFrame(rows).set_index("fid")
    out_path = os.path.join(summary_dir, f"etf_weight_summary_by_site_{exp_id}.csv")
    df.to_csv(out_path)
    print(f"  Weight summary ({exp_id}): {out_path}")


def _build_phi_summary(results_root, summary_dir):
    """Parse phi.meas.csv from both runs and write phi_summary.csv."""
    import pandas as pd

    rows = []
    for exp_id, tag in [
        ("e1_spread", "ablation_e1_spread"),
        ("e2_fixed_sd", "ablation_e2_fixed_sd"),
    ]:
        exp_dir = os.path.join(results_root, tag)
        phi_path = os.path.join(exp_dir, "5_Flux_Ensemble.phi.meas.csv")
        rt_path = os.path.join(exp_dir, "runtime.json")

        if not os.path.exists(phi_path):
            continue

        phi = pd.read_csv(phi_path, index_col=0)
        # phi.meas.csv: rows are realizations, columns are iterations
        # Mean phi per iteration
        iter_means = phi.mean(axis=0)
        row = {"experiment_id": exp_id}
        for j, val in enumerate(iter_means):
            row[f"phi_iter_{j}"] = round(float(val), 1)
        row["phi_initial"] = round(float(iter_means.iloc[0]), 1)
        row["phi_final"] = round(float(iter_means.iloc[-1]), 1)
        row["phi_reduction_pct"] = (
            round(100 * (1 - iter_means.iloc[-1] / iter_means.iloc[0]), 1)
            if iter_means.iloc[0] > 0
            else 0
        )
        row["n_iterations"] = len(iter_means)

        if os.path.exists(rt_path):
            with open(rt_path) as f:
                rt = json.load(f)
            row["wall_minutes"] = rt.get("wall_minutes", None)

        rows.append(row)

    if rows:
        df = pd.DataFrame(rows)
        out_path = os.path.join(summary_dir, "phi_summary.csv")
        df.to_csv(out_path, index=False)
        print(f"  Phi summary: {out_path}")


def _build_ablation_summary(results_root, summary_dir):
    """Build single ablation_summary.csv with one row per experiment."""
    import pandas as pd

    rows = []
    for exp_id, tag in [
        ("e1_spread", "ablation_e1_spread"),
        ("e2_fixed_sd", "ablation_e2_fixed_sd"),
    ]:
        exp_dir = os.path.join(results_root, tag)
        row = {"experiment_id": exp_id}

        # Runtime
        rt_path = os.path.join(exp_dir, "runtime.json")
        if os.path.exists(rt_path):
            with open(rt_path) as f:
                rt = json.load(f)
            row.update(
                {
                    k: rt[k]
                    for k in ["weighting_mode", "realizations", "workers", "wall_minutes"]
                    if k in rt
                }
            )

        # Daily metrics
        daily_path = os.path.join(exp_dir, "evaluation_metrics.csv")
        if os.path.exists(daily_path):
            d = pd.read_csv(daily_path, index_col=0)
            valid = d["r2_swim"].dropna()
            row["daily_n_sites"] = len(valid)
            row["daily_r2_median"] = round(valid.median(), 3)
            row["daily_rmse_median"] = round(d["rmse_swim"].dropna().median(), 3)
            row["daily_bias_median"] = round(d["bias_swim"].dropna().median(), 3)

        # Monthly metrics
        monthly_path = os.path.join(exp_dir, "evaluation_monthly_metrics.csv")
        if os.path.exists(monthly_path):
            m = pd.read_csv(monthly_path, index_col=0)
            valid = m["r2_swim"].dropna()
            row["monthly_n_sites"] = len(valid)
            row["monthly_r2_median"] = round(valid.median(), 3)
            row["monthly_rmse_median"] = round(m["rmse_swim"].dropna().median(), 2)
            row["monthly_bias_median"] = round(m["bias_swim"].dropna().median(), 2)

        # Phi
        phi_path = os.path.join(exp_dir, "5_Flux_Ensemble.phi.meas.csv")
        if os.path.exists(phi_path):
            phi = pd.read_csv(phi_path, index_col=0)
            iter_means = phi.mean(axis=0)
            row["phi_initial"] = round(float(iter_means.iloc[0]), 1)
            row["phi_final"] = round(float(iter_means.iloc[-1]), 1)

        rows.append(row)

    if rows:
        df = pd.DataFrame(rows)
        out_path = os.path.join(summary_dir, "ablation_summary.csv")
        df.to_csv(out_path, index=False)
        print(f"  Ablation summary: {out_path}")


def summarize_ablation(results_root):
    """Produce all paired comparison and diagnostic artifacts for E1 vs E2."""
    e1_dir = os.path.join(results_root, "ablation_e1_spread")
    e2_dir = os.path.join(results_root, "ablation_e2_fixed_sd")
    summary_dir = os.path.join(results_root, "ablation_summary")
    os.makedirs(summary_dir, exist_ok=True)

    # Paired deltas: daily, monthly, ETf
    for label, suffix in [
        ("daily", "_metrics.csv"),
        ("monthly", "_monthly_metrics.csv"),
        ("etf", "_etf_metrics.csv"),
    ]:
        _build_paired_deltas(
            os.path.join(e1_dir, f"evaluation{suffix}"),
            os.path.join(e2_dir, f"evaluation{suffix}"),
            summary_dir,
            label,
        )

    # Per-site weight summaries
    _build_weight_summary(e1_dir, summary_dir, "e1_spread")
    _build_weight_summary(e2_dir, summary_dir, "e2_fixed_sd")

    # Phi convergence summary
    _build_phi_summary(results_root, summary_dir)

    # One-row-per-experiment ablation summary
    _build_ablation_summary(results_root, summary_dir)


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

    # Phase 2: Evaluation (daily + monthly + ETf)
    for exp_id in run_ids:
        exp_dir = os.path.join(results_root, f"ablation_{exp_id}")
        if not os.path.exists(exp_dir):
            print(f"  Skipping evaluation for {exp_id} (no results dir)")
            continue
        print(f"\nEvaluating {exp_id}...")
        run_evaluation(cfg, exp_id, exp_dir, mode="daily", debug_fields=debug_fields)
        run_evaluation(cfg, exp_id, exp_dir, mode="monthly", debug_fields=debug_fields)
        run_evaluation(cfg, exp_id, exp_dir, mode="etf", debug_fields=debug_fields)

    # Phase 3: Summary
    print("\nSummarizing ablation...")
    summarize_ablation(results_root)


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    main()
