"""Summary and comparison layer for Ex4 ablation experiments.

Produces:
  - experiment_index.csv       one row per experiment
  - phi_summary.csv            phi convergence per experiment
  - *_paired_deltas.csv        per-site metric deltas for each comparison
  - sentinel_density_gain.csv  NDVI obs gain from S2 fusion
  - cost_summary.csv           wall time, CPU-hours, cost-efficiency

Usage (called by run_ablations.py):
    from summarize_ablation import summarize_all
    summarize_all(registry, data_dir)
"""

import json
import os

import numpy as np
import pandas as pd


def build_experiment_index(runs_dir: str, project: str) -> pd.DataFrame:
    """Build a one-row-per-experiment summary table."""
    rows = []
    for exp_id in sorted(os.listdir(runs_dir)):
        exp_dir = os.path.join(runs_dir, exp_id)
        if not os.path.isdir(exp_dir):
            continue

        row = {"experiment_id": exp_id}

        # Experiment spec
        spec_path = os.path.join(exp_dir, "experiment.json")
        if os.path.exists(spec_path):
            with open(spec_path) as f:
                spec = json.load(f)
            for k in (
                "question",
                "container_family",
                "calibration_start",
                "calibration_end",
                "evaluation_start",
                "evaluation_end",
                "realizations",
                "site_filter",
            ):
                row[k] = spec.get(k)

        # Runtime / cost
        for fname in ("runtime.json", "cost.json"):
            fp = os.path.join(exp_dir, fname)
            if os.path.exists(fp):
                with open(fp) as f:
                    row.update(json.load(f))

        # Daily metrics
        daily_path = os.path.join(exp_dir, "evaluation_metrics.csv")
        if os.path.exists(daily_path):
            d = pd.read_csv(daily_path, index_col=0)
            valid = d["r2_swim"].dropna()
            row["daily_n_sites"] = len(valid)
            row["daily_r2_median"] = round(valid.median(), 3) if len(valid) else np.nan
            row["daily_rmse_median"] = (
                round(d["rmse_swim"].dropna().median(), 3) if len(valid) else np.nan
            )
            row["daily_bias_median"] = (
                round(d["bias_swim"].dropna().median(), 3) if len(valid) else np.nan
            )

        # Monthly metrics
        monthly_path = os.path.join(exp_dir, "evaluation_monthly_metrics.csv")
        if os.path.exists(monthly_path):
            m = pd.read_csv(monthly_path, index_col=0)
            valid = m["r2_swim"].dropna()
            row["monthly_n_sites"] = len(valid)
            row["monthly_r2_median"] = round(valid.median(), 3) if len(valid) else np.nan
            row["monthly_rmse_median"] = (
                round(m["rmse_swim"].dropna().median(), 2) if len(valid) else np.nan
            )

        # Phi
        phi_path = os.path.join(exp_dir, "results", f"{project}.phi.meas.csv")
        if os.path.exists(phi_path):
            phi = pd.read_csv(phi_path, index_col=0)
            iter_means = phi.mean(axis=0)
            row["phi_initial"] = round(float(iter_means.iloc[0]), 1)
            row["phi_final"] = round(float(iter_means.iloc[-1]), 1)

        rows.append(row)

    return pd.DataFrame(rows).set_index("experiment_id") if rows else pd.DataFrame()


def build_paired_deltas(
    exp_a_dir: str,
    exp_b_dir: str,
    exp_a_id: str,
    exp_b_id: str,
    common_fids: list[str] | None,
    label: str,
    output_dir: str | None = None,
) -> pd.DataFrame | None:
    """Build paired site-level metric deltas between two experiments.

    Computes delta = exp_a - exp_b for R2, RMSE, bias. A positive delta_r2
    means exp_a is better.

    Args:
        exp_a_dir: Results directory for experiment A.
        exp_b_dir: Results directory for experiment B.
        exp_a_id: Experiment A identifier.
        exp_b_id: Experiment B identifier.
        common_fids: Site IDs to include (None = intersect both).
        label: Output label (e.g. "period", "sentinel").
        output_dir: Write CSV here if provided.

    Returns:
        DataFrame of paired deltas, or None if data missing.
    """
    # Load evaluation window bounds from experiment specs
    eval_start_a = eval_end_a = eval_start_b = eval_end_b = None
    for edir, eid in [(exp_a_dir, "a"), (exp_b_dir, "b")]:
        spec_path = os.path.join(edir, "experiment.json")
        if os.path.exists(spec_path):
            with open(spec_path) as f:
                spec = json.load(f)
            if eid == "a":
                eval_start_a = spec.get("evaluation_start")
                eval_end_a = spec.get("evaluation_end")
            else:
                eval_start_b = spec.get("evaluation_start")
                eval_end_b = spec.get("evaluation_end")

    results = {}

    for timescale, suffix in [
        ("daily", "evaluation_metrics.csv"),
        ("monthly", "evaluation_monthly_metrics.csv"),
        ("etf", "evaluation_etf_metrics.csv"),
    ]:
        a_path = os.path.join(exp_a_dir, suffix)
        b_path = os.path.join(exp_b_dir, suffix)
        if not os.path.exists(a_path) or not os.path.exists(b_path):
            continue

        a = pd.read_csv(a_path, index_col=0)
        b = pd.read_csv(b_path, index_col=0)

        if common_fids is not None:
            common = a.index.intersection(b.index).intersection(common_fids)
        else:
            common = a.index.intersection(b.index)
        if len(common) == 0:
            continue

        a, b = a.loc[common], b.loc[common]
        paired = pd.DataFrame(index=common)

        # Provenance columns
        paired["experiment_a"] = exp_a_id
        paired["experiment_b"] = exp_b_id
        paired["evaluation_start_a"] = eval_start_a
        paired["evaluation_end_a"] = eval_end_a
        paired["evaluation_start_b"] = eval_start_b
        paired["evaluation_end_b"] = eval_end_b

        # Determine metric columns based on timescale
        if timescale == "etf":
            metrics = ["r2", "rmse", "bias"]
        else:
            metrics = ["r2_swim", "rmse_swim", "bias_swim"]

        for metric in metrics:
            if metric in a.columns and metric in b.columns:
                paired[f"a_{metric}"] = a[metric]
                paired[f"b_{metric}"] = b[metric]
                paired[f"delta_{metric}"] = a[metric] - b[metric]

        # Win indicator on R2
        r2_col = "r2_swim" if "r2_swim" in a.columns else ("r2" if "r2" in a.columns else None)
        if r2_col and r2_col in a.columns:
            paired["a_wins_r2"] = a[r2_col] > b[r2_col]

        # Paired observation counts — daily uses "n", monthly uses "n_months"
        if "n" in a.columns:
            paired["n_paired"] = a["n"]
        if "n_months" in a.columns:
            paired["n_paired_months"] = a["n_months"]

        paired["timescale"] = timescale
        results[timescale] = paired

    if not results:
        return None

    combined = pd.concat(results.values())

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{label}_paired_deltas.csv")
        combined.to_csv(out_path)
        print(f"  Paired deltas ({label}): {out_path}")

    return combined


def build_phi_summary(runs_dir: str, project: str, output_dir: str | None = None) -> pd.DataFrame:
    """Parse phi.meas.csv from all experiments and build phi_summary.csv."""
    rows = []
    for exp_id in sorted(os.listdir(runs_dir)):
        phi_path = os.path.join(runs_dir, exp_id, "results", f"{project}.phi.meas.csv")
        if not os.path.exists(phi_path):
            continue

        phi = pd.read_csv(phi_path, index_col=0)
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

        rt_path = os.path.join(runs_dir, exp_id, "runtime.json")
        if os.path.exists(rt_path):
            with open(rt_path) as f:
                rt = json.load(f)
            row["wall_minutes"] = rt.get("wall_minutes")

        rows.append(row)

    df = pd.DataFrame(rows).set_index("experiment_id") if rows else pd.DataFrame()

    if output_dir and len(df):
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "phi_summary.csv")
        df.to_csv(out_path)
        print(f"  Phi summary: {out_path}")

    return df


def build_sentinel_density_gain(
    ls_only_audit_csv: str,
    ls_s2_fused_audit_csv: str,
    s2_fids: list[str],
    output_dir: str | None = None,
) -> pd.DataFrame | None:
    """Compute NDVI observation density gain from Sentinel-2 fusion."""
    if not os.path.exists(ls_only_audit_csv) or not os.path.exists(ls_s2_fused_audit_csv):
        print("  Skipping sentinel density gain (missing audit CSVs)")
        return None

    ls = pd.read_csv(ls_only_audit_csv, index_col=0)
    fused = pd.read_csv(ls_s2_fused_audit_csv, index_col=0)

    common = ls.index.intersection(fused.index).intersection(s2_fids)
    if len(common) == 0:
        return None

    result = pd.DataFrame(index=common)
    result["ls_only_ndvi_obs"] = ls.loc[common, "ndvi_obs_count"]
    result["ls_s2_fused_ndvi_obs"] = fused.loc[common, "ndvi_obs_count"]
    result["delta_ndvi_obs"] = result["ls_s2_fused_ndvi_obs"] - result["ls_only_ndvi_obs"]
    result["density_gain_pct"] = (
        100 * result["delta_ndvi_obs"] / result["ls_only_ndvi_obs"]
    ).round(1)

    if "s2_ndvi_obs_count" in fused.columns:
        result["s2_ndvi_obs_count"] = fused.loc[common, "s2_ndvi_obs_count"]

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "sentinel_density_gain.csv")
        result.to_csv(out_path)
        print(f"  Sentinel density gain: {out_path}")

    return result


def build_cost_summary(runs_dir: str, output_dir: str | None = None) -> pd.DataFrame:
    """Build cost summary from runtime.json and cost.json per experiment."""
    rows = []
    for exp_id in sorted(os.listdir(runs_dir)):
        exp_dir = os.path.join(runs_dir, exp_id)
        if not os.path.isdir(exp_dir):
            continue
        row = {"experiment_id": exp_id}

        for fname in ("runtime.json", "cost.json"):
            fp = os.path.join(exp_dir, fname)
            if os.path.exists(fp):
                with open(fp) as f:
                    row.update(json.load(f))

        if row.get("wall_minutes") and row.get("workers"):
            row["cpu_hours"] = round(row["wall_minutes"] * row["workers"] / 60, 1)

        rows.append(row)

    df = pd.DataFrame(rows).set_index("experiment_id") if rows else pd.DataFrame()

    if output_dir and len(df):
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "cost_summary.csv")
        df.to_csv(out_path)
        print(f"  Cost summary: {out_path}")

    return df


def summarize_all(registry: dict, data_dir: str, project: str = "4_Flux_Network") -> None:
    """Run all summary functions and write outputs."""
    ablation_dir = os.path.join(data_dir, "ablation")
    runs_dir = os.path.join(ablation_dir, "runs")
    summary_dir = os.path.join(ablation_dir, "summary")
    containers_dir = os.path.join(ablation_dir, "containers")

    os.makedirs(summary_dir, exist_ok=True)
    print("\n=== Summarizing Ablation ===")

    # Experiment index
    idx = build_experiment_index(runs_dir, project)
    if len(idx):
        idx.to_csv(os.path.join(summary_dir, "experiment_index.csv"))
        print(f"  Experiment index: {len(idx)} experiments")

    # Phi summary
    build_phi_summary(runs_dir, project, output_dir=summary_dir)

    # Cost summary
    build_cost_summary(runs_dir, output_dir=summary_dir)

    # Paired deltas per comparison
    comparisons = registry.get("comparisons", {})
    experiments = registry.get("experiments", {})

    # Resolve S2 site list from audit
    s2_fids = []
    s2_audit_json = os.path.join(containers_dir, "container_audit_summary_ls_s2_fused.json")
    if os.path.exists(s2_audit_json):
        with open(s2_audit_json) as f:
            s2_fids = json.load(f).get("s2_site_ids", [])

    for comp_name, comp_spec in comparisons.items():
        exp_ids = comp_spec["experiments"]
        cohort = comp_spec.get("cohort")
        common_fids = s2_fids if cohort == "s2_sites" else None

        if len(exp_ids) == 2:
            a_dir = os.path.join(runs_dir, exp_ids[0])
            b_dir = os.path.join(runs_dir, exp_ids[1])
            build_paired_deltas(
                a_dir,
                b_dir,
                exp_ids[0],
                exp_ids[1],
                common_fids,
                comp_name,
                summary_dir,
            )
        elif len(exp_ids) > 2:
            # Multi-way: pairwise against the last experiment as reference
            ref_id = exp_ids[-1]
            ref_dir = os.path.join(runs_dir, ref_id)
            for eid in exp_ids[:-1]:
                e_dir = os.path.join(runs_dir, eid)
                label = f"{comp_name}_{eid}_vs_{ref_id}"
                build_paired_deltas(
                    e_dir,
                    ref_dir,
                    eid,
                    ref_id,
                    common_fids,
                    label,
                    summary_dir,
                )

    # Sentinel density gain
    ls_audit = os.path.join(containers_dir, "container_audit_sites_ls_only.csv")
    fused_audit = os.path.join(containers_dir, "container_audit_sites_ls_s2_fused.csv")
    if s2_fids:
        build_sentinel_density_gain(ls_audit, fused_audit, s2_fids, summary_dir)

    print(f"\nSummary artifacts: {summary_dir}")
