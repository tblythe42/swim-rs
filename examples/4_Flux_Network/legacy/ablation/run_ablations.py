"""Ex4 Study 1 ablation orchestrator.

Phase-based CLI that runs six experiments comparing period-of-record,
Sentinel-2 NDVI densification, and compute efficiency.

Usage:
    python run_ablations.py materialize
    python run_ablations.py build-container --family ls_only
    python run_ablations.py audit-container --family ls_only
    python run_ablations.py run-experiment --id P1
    python run_ablations.py evaluate-experiment --id P1
    python run_ablations.py summarize
    python run_ablations.py status

    # Dry-run on 2 sites for validation:
    python run_ablations.py run-experiment --id P1 --dry-run --debug-fields US-Bi1,US-ARM
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

# Add parent directory so we can import calibrate / evaluate
_EX4_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_EX4_DIR))

PROJECT = "4_Flux_Network"


# ---------------------------------------------------------------------------
# Config / registry helpers
# ---------------------------------------------------------------------------


def _load_registry(registry_path: str | None = None) -> dict:
    if registry_path is None:
        registry_path = str(Path(__file__).resolve().parent / "experiments.yaml")
    with open(registry_path) as f:
        return yaml.safe_load(f)


def _load_config():
    """Load ProjectConfig from the Ex4 TOML (same as calibrate.py)."""
    from swimrs.swim.config import ProjectConfig

    conf = _EX4_DIR / f"{PROJECT}.toml"
    cfg = ProjectConfig()
    if os.path.isdir("/data/ssd1/swim"):
        cfg.read_config(str(conf), calibrate=True)
    else:
        cfg.read_config(str(conf), project_root_override=str(_EX4_DIR.parent), calibrate=True)
    return cfg


def _ablation_dir(cfg) -> str:
    return os.path.join(cfg.data_dir, "ablation")


def _validate_registry(registry: dict) -> None:
    """Validate the experiment registry; raise on errors."""
    families = set(registry.get("container_families", {}).keys())
    experiments = registry.get("experiments", {})
    seen_ids = set()

    for eid, spec in experiments.items():
        if eid in seen_ids:
            raise ValueError(f"Duplicate experiment ID: {eid}")
        seen_ids.add(eid)

        fam = spec.get("container_family")
        if fam not in families:
            raise ValueError(f"{eid}: unknown container_family '{fam}'")

        cal_s = pd.to_datetime(spec["calibration_start"])
        cal_e = pd.to_datetime(spec["calibration_end"])
        eval_s = pd.to_datetime(spec["evaluation_start"])
        eval_e = pd.to_datetime(spec["evaluation_end"])

        if cal_s > cal_e:
            raise ValueError(f"{eid}: calibration_start > calibration_end")
        if eval_s > eval_e:
            raise ValueError(f"{eid}: evaluation_start > evaluation_end")
        if eval_s < cal_s:
            raise ValueError(f"{eid}: evaluation_start before calibration_start")
        if eval_e > cal_e:
            raise ValueError(f"{eid}: evaluation_end after calibration_end")
        if spec.get("realizations", 0) < 1:
            raise ValueError(f"{eid}: realizations must be >= 1")

    for comp_name, comp in registry.get("comparisons", {}).items():
        for eid in comp["experiments"]:
            if eid not in experiments:
                raise ValueError(f"comparison '{comp_name}' references unknown experiment '{eid}'")

    print(f"Registry valid: {len(experiments)} experiments, {len(families)} container families")


# ---------------------------------------------------------------------------
# Phase: materialize
# ---------------------------------------------------------------------------


def cmd_materialize(args):
    registry = _load_registry(args.registry)
    _validate_registry(registry)

    cfg = _load_config()
    abl = _ablation_dir(cfg)

    # Create directory tree
    for subdir in ("containers", "runs", "summary"):
        os.makedirs(os.path.join(abl, subdir), exist_ok=True)

    for eid, spec in registry["experiments"].items():
        exp_dir = os.path.join(abl, "runs", eid)
        os.makedirs(os.path.join(exp_dir, "results"), exist_ok=True)

        exp_json = os.path.join(exp_dir, "experiment.json")
        payload = {"experiment_id": eid, **spec}
        with open(exp_json, "w") as f:
            json.dump(payload, f, indent=2)

    print(f"Materialized {len(registry['experiments'])} experiments → {abl}")


# ---------------------------------------------------------------------------
# Phase: build-container
# ---------------------------------------------------------------------------


def cmd_build_container(args):
    registry = _load_registry(args.registry)
    family_name = args.family
    family_spec = registry["container_families"].get(family_name)
    if family_spec is None:
        raise ValueError(f"Unknown container family: {family_name}")

    cfg = _load_config()
    abl = _ablation_dir(cfg)
    output_path = os.path.join(abl, "containers", f"{family_name}.swim")

    sites = None
    if args.debug_fields:
        sites = [s.strip() for s in args.debug_fields.split(",")]

    from container_build import build_ablation_container

    build_ablation_container(
        cfg,
        family_name,
        family_spec,
        output_path,
        overwrite=args.overwrite,
        sites=sites,
    )


# ---------------------------------------------------------------------------
# Phase: audit-container
# ---------------------------------------------------------------------------


def cmd_audit_container(args):
    registry = _load_registry(args.registry)
    family_name = args.family
    if family_name not in registry["container_families"]:
        raise ValueError(f"Unknown container family: {family_name}")

    cfg = _load_config()
    abl = _ablation_dir(cfg)
    container_path = os.path.join(abl, "containers", f"{family_name}.swim")

    if not os.path.exists(container_path):
        raise FileNotFoundError(f"Container not found: {container_path}")

    from container_audit import audit_container

    output_dir = os.path.join(abl, "containers")
    _, summary, passed = audit_container(container_path, family_name, output_dir)

    if not passed:
        print("\nAUDIT FAILED — fix data issues before running experiments.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Phase: run-experiment
# ---------------------------------------------------------------------------


def _find_par_csv(results_dir: str) -> str | None:
    for i in range(10, -1, -1):
        candidate = os.path.join(results_dir, f"{PROJECT}.{i}.par.csv")
        if os.path.exists(candidate):
            return candidate
    return None


def _resolve_site_filter(
    site_filter: str,
    container_path: str,
    ablation_dir: str,
) -> list[str]:
    """Resolve the site_filter to a list of field IDs."""
    from swimrs.container import SwimContainer

    container = SwimContainer.open(container_path, mode="r")
    all_fids = list(container.field_uids)
    container.close()

    # Import exclusion policy from evaluate.py
    from evaluate import EXCLUDED_SITES

    all_fids = [f for f in all_fids if f not in EXCLUDED_SITES]

    if site_filter == "all":
        return all_fids

    if site_filter == "s2_sites":
        audit_json = os.path.join(
            ablation_dir, "containers", "container_audit_summary_ls_s2_fused.json"
        )
        if not os.path.exists(audit_json):
            raise FileNotFoundError(
                f"S2 audit not found: {audit_json}\n"
                "Run: audit-container --family ls_s2_fused first."
            )
        with open(audit_json) as f:
            s2_ids = json.load(f).get("s2_site_ids", [])
        # Intersect with container fields and exclusion policy
        return [f for f in all_fids if f in s2_ids]

    if site_filter == "lulc_representative":
        # 2 sites per LULC class with longest flux records
        REPRESENTATIVE_SITES = [
            "US-Ne1",
            "US-Ne2",  # Croplands
            "US-Me2",
            "US-Me6",  # Evergreen Forests
            "US-Wkg",
            "US-SRG",  # Grasslands
            "US-MMS",
            "US-Dk2",  # Mixed Forests
            "US-SRM",
            "US-Jo2",  # Shrublands
            "US-CMW",
            "US-Skr",  # Wetland/Riparian
        ]
        return [f for f in all_fids if f in REPRESENTATIVE_SITES]

    raise ValueError(f"Unknown site_filter: {site_filter}")


def cmd_run_experiment(args):
    registry = _load_registry(args.registry)
    exp_id = args.id
    spec = registry["experiments"].get(exp_id)
    if spec is None:
        raise ValueError(f"Unknown experiment: {exp_id}")

    cfg = _load_config()
    abl = _ablation_dir(cfg)
    exp_dir = os.path.join(abl, "runs", exp_id)
    results_dir = os.path.join(exp_dir, "results")
    os.makedirs(results_dir, exist_ok=True)

    # Override config for calibration window
    cfg.start_dt = pd.to_datetime(spec["calibration_start"])
    cfg.end_dt = pd.to_datetime(spec["calibration_end"])
    cfg.realizations = spec["realizations"]

    if args.dry_run:
        cfg.realizations = 5
        cfg.workers = min(4, cfg.workers)
        print(f"DRY RUN: realizations=5, workers={cfg.workers}")

    container_path = os.path.join(abl, "containers", f"{spec['container_family']}.swim")
    if not os.path.exists(container_path):
        raise FileNotFoundError(f"Container not found: {container_path}")

    # Enforce audit gate — container must have a passing audit
    audit_json = os.path.join(
        abl, "containers", f"container_audit_summary_{spec['container_family']}.json"
    )
    if not os.path.exists(audit_json):
        raise FileNotFoundError(
            f"No audit found for {spec['container_family']}. "
            f"Run: audit-container --family {spec['container_family']}"
        )
    with open(audit_json) as f:
        audit = json.load(f)
    if not audit.get("passed", False):
        raise RuntimeError(
            f"Container audit FAILED for {spec['container_family']}. "
            "Fix data issues before running experiments."
        )

    # Resolve site filter → calibration field list
    site_filter = spec.get("site_filter", "all")
    if args.debug_fields:
        resolved_fields = [s.strip() for s in args.debug_fields.split(",")]
        print(f"CLI debug_fields override: {len(resolved_fields)} sites")
    else:
        resolved_fields = _resolve_site_filter(site_filter, container_path, abl)
        print(f"Site filter '{site_filter}': {len(resolved_fields)} sites")

    # Write cohort manifest for provenance
    cohort_path = os.path.join(exp_dir, "cohort.json")
    cohort_record = {
        "site_filter": site_filter,
        "n_sites": len(resolved_fields),
        "sites": resolved_fields,
    }
    with open(cohort_path, "w") as f:
        json.dump(cohort_record, f, indent=2)

    print(f"\n{'=' * 80}")
    print(f"CALIBRATION: {exp_id}")
    print(f"  Window: {spec['calibration_start']} → {spec['calibration_end']}")
    print(f"  Realizations: {cfg.realizations}")
    print(f"  Sites: {len(resolved_fields) if resolved_fields else 'all'}")
    print(f"  Container: {container_path}")
    print(f"  Results: {results_dir}")
    print(f"{'=' * 80}\n")

    from calibrate import run_pest_sequence

    # Use select_fields (not debug_fields) so realization count and workers
    # are not overridden by debug mode defaults.
    t0 = time.time()
    run_pest_sequence(
        cfg,
        results_dir,
        pdc_remove=False,
        select_fields=resolved_fields,
        container_path=container_path,
    )
    elapsed = time.time() - t0

    # Write runtime.json
    runtime = {
        "experiment_id": exp_id,
        "calibration_start": spec["calibration_start"],
        "calibration_end": spec["calibration_end"],
        "realizations": cfg.realizations,
        "workers": cfg.workers,
        "site_filter": site_filter,
        "n_sites": len(resolved_fields),
        "wall_seconds": round(elapsed, 1),
        "wall_minutes": round(elapsed / 60, 1),
    }
    with open(os.path.join(exp_dir, "runtime.json"), "w") as f:
        json.dump(runtime, f, indent=2)

    # Write cost.json
    cost = {
        "experiment_id": exp_id,
        "wall_hours": round(elapsed / 3600, 2),
        "cpu_hours": round(elapsed * cfg.workers / 3600, 2),
        "workers": cfg.workers,
        "realizations": cfg.realizations,
        "n_sites": len(resolved_fields),
        "container_family": spec["container_family"],
    }
    with open(os.path.join(exp_dir, "cost.json"), "w") as f:
        json.dump(cost, f, indent=2)

    # Write config snapshot for full reproducibility
    config_snapshot = {
        "experiment_id": exp_id,
        "calibration_start": spec["calibration_start"],
        "calibration_end": spec["calibration_end"],
        "evaluation_start": spec["evaluation_start"],
        "evaluation_end": spec["evaluation_end"],
        "realizations": cfg.realizations,
        "workers": cfg.workers,
        "noptmax": getattr(cfg, "noptmax", 3),
        "pdc_remove": False,
        "container_family": spec["container_family"],
        "container_path": container_path,
        "site_filter": site_filter,
        "n_sites": len(resolved_fields),
        "sites": resolved_fields,
        "audit_json": audit_json,
    }
    with open(os.path.join(exp_dir, "config_snapshot.json"), "w") as f:
        json.dump(config_snapshot, f, indent=2)

    print(f"\n{exp_id} calibration complete: {elapsed:.1f}s ({elapsed / 60:.1f} min)")


# ---------------------------------------------------------------------------
# Phase: evaluate-experiment
# ---------------------------------------------------------------------------


def cmd_evaluate_experiment(args):
    registry = _load_registry(args.registry)
    exp_id = args.id
    spec = registry["experiments"].get(exp_id)
    if spec is None:
        raise ValueError(f"Unknown experiment: {exp_id}")

    cfg = _load_config()
    abl = _ablation_dir(cfg)
    exp_dir = os.path.join(abl, "runs", exp_id)
    results_dir = os.path.join(exp_dir, "results")
    flux_dir = os.path.join(cfg.data_dir, "daily_flux_files")

    # Override config for evaluation window
    cfg.start_dt = pd.to_datetime(spec["evaluation_start"])
    cfg.end_dt = pd.to_datetime(spec["evaluation_end"])

    container_path = os.path.join(abl, "containers", f"{spec['container_family']}.swim")
    if not os.path.exists(container_path):
        raise FileNotFoundError(f"Container not found: {container_path}")

    par_csv = _find_par_csv(results_dir)
    if par_csv is None:
        raise FileNotFoundError(f"No par.csv in {results_dir}. Run run-experiment first.")

    # Resolve site list from calibration cohort (ensures evaluation matches calibration)
    cohort_path = os.path.join(exp_dir, "cohort.json")
    if args.debug_fields:
        fids = [s.strip() for s in args.debug_fields.split(",")]
    elif os.path.exists(cohort_path):
        with open(cohort_path) as f:
            cohort = json.load(f)
        fids = cohort["sites"]
        print(f"Using calibration cohort from {cohort_path} ({len(fids)} sites)")
    else:
        fids = _resolve_site_filter(spec["site_filter"], container_path, abl)
        print("WARNING: no cohort.json found, recomputing from registry")

    print(f"\n{'=' * 80}")
    print(f"EVALUATION: {exp_id}")
    print(f"  Window: {spec['evaluation_start']} → {spec['evaluation_end']}")
    print(f"  Sites: {len(fids)}")
    print(f"  Container: {container_path}")
    print(f"  Parameters: {par_csv}")
    print(f"{'=' * 80}\n")

    from evaluate import evaluate, evaluate_etf, evaluate_monthly

    from swimrs.container import SwimContainer

    container = SwimContainer.open(container_path, mode="r")

    try:
        # Daily
        print("--- Daily evaluation ---")
        daily_df = evaluate(cfg, container, par_csv, fids, flux_dir)
        if len(daily_df):
            daily_df.to_csv(os.path.join(exp_dir, "evaluation_metrics.csv"))

        # Monthly
        print("\n--- Monthly evaluation ---")
        monthly_df = evaluate_monthly(cfg, container, par_csv, fids, flux_dir)
        if len(monthly_df):
            monthly_df.to_csv(os.path.join(exp_dir, "evaluation_monthly_metrics.csv"))

        # ETf
        print("\n--- ETf evaluation ---")
        etf_df = evaluate_etf(cfg, container, par_csv, fids)
        if len(etf_df):
            etf_df.to_csv(os.path.join(exp_dir, "evaluation_etf_metrics.csv"))

    finally:
        container.close()

    print(f"\n{exp_id} evaluation complete → {exp_dir}")


# ---------------------------------------------------------------------------
# Phase: summarize
# ---------------------------------------------------------------------------


def cmd_summarize(args):
    registry = _load_registry(args.registry)
    cfg = _load_config()
    data_dir = cfg.data_dir

    from summarize_ablation import summarize_all

    summarize_all(registry, data_dir, project=PROJECT)


# ---------------------------------------------------------------------------
# Phase: status
# ---------------------------------------------------------------------------


def cmd_status(args):
    registry = _load_registry(args.registry)
    cfg = _load_config()
    abl = _ablation_dir(cfg)

    # Container status
    print("Container Families:")
    for fam in registry["container_families"]:
        cpath = os.path.join(abl, "containers", f"{fam}.swim")
        built = os.path.exists(cpath)
        audit_json = os.path.join(abl, "containers", f"container_audit_summary_{fam}.json")
        audited = os.path.exists(audit_json)
        status = "built+audited" if (built and audited) else ("built" if built else "missing")
        print(f"  {fam:<16} {status}")

    # Experiment status
    print("\nExperiments:")
    for eid in registry["experiments"]:
        exp_dir = os.path.join(abl, "runs", eid)
        materialized = os.path.exists(os.path.join(exp_dir, "experiment.json"))
        calibrated = _find_par_csv(os.path.join(exp_dir, "results")) is not None
        evaluated = os.path.exists(os.path.join(exp_dir, "evaluation_metrics.csv"))

        parts = []
        if materialized:
            parts.append("materialized")
        if calibrated:
            parts.append("calibrated")
        if evaluated:
            parts.append("evaluated")
        status = " → ".join(parts) if parts else "pending"
        print(f"  {eid:<4} {status}")

    # Summary status
    summary_dir = os.path.join(abl, "summary")
    idx_exists = os.path.exists(os.path.join(summary_dir, "experiment_index.csv"))
    print(f"\nSummary: {'complete' if idx_exists else 'pending'}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Ex4 Study 1 ablation orchestrator",
    )
    parser.add_argument(
        "--registry",
        type=str,
        default=None,
        help="Path to experiments.yaml",
    )

    sub = parser.add_subparsers(dest="phase", required=True)

    # materialize
    sub.add_parser("materialize", help="Validate registry and create artifact dirs")

    # build-container
    p = sub.add_parser("build-container", help="Build a container family")
    p.add_argument("--family", required=True, help="Container family name")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--debug-fields", type=str, default=None)

    # audit-container
    p = sub.add_parser("audit-container", help="Audit container completeness")
    p.add_argument("--family", required=True, help="Container family name")

    # run-experiment
    p = sub.add_parser("run-experiment", help="Run calibration for one experiment")
    p.add_argument("--id", required=True, help="Experiment ID (e.g. P1)")
    p.add_argument("--dry-run", action="store_true", help="Reduced realizations for testing")
    p.add_argument("--debug-fields", type=str, default=None)

    # evaluate-experiment
    p = sub.add_parser("evaluate-experiment", help="Evaluate one experiment")
    p.add_argument("--id", required=True, help="Experiment ID")
    p.add_argument("--debug-fields", type=str, default=None)

    # summarize
    sub.add_parser("summarize", help="Build all comparison tables")

    # status
    sub.add_parser("status", help="Report experiment status")

    args = parser.parse_args()

    os.chdir(_EX4_DIR)

    dispatch = {
        "materialize": cmd_materialize,
        "build-container": cmd_build_container,
        "audit-container": cmd_audit_container,
        "run-experiment": cmd_run_experiment,
        "evaluate-experiment": cmd_evaluate_experiment,
        "summarize": cmd_summarize,
        "status": cmd_status,
    }
    dispatch[args.phase](args)


if __name__ == "__main__":
    main()
