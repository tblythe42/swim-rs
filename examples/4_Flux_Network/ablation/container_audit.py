"""Mandatory container completeness audit for Ex4 ablation.

Checks every site for non-null ETf, NDVI, and meteorology under the no_mask
path.  Hard-fails if any site has zero ETf captures, all-null NDVI, or
all-null meteorology.

Usage (called by run_ablations.py):
    from container_audit import audit_container
    sites_df, summary, passed = audit_container(path, "ls_only")
"""

import json
import os

import numpy as np
import pandas as pd

from swimrs.container import SwimContainer


def audit_container(
    container_path: str,
    family_name: str,
    output_dir: str | None = None,
) -> tuple[pd.DataFrame, dict, bool]:
    """Run completeness audit on an ablation container.

    Args:
        container_path: Path to the .swim container.
        family_name: Container family identifier.
        output_dir: Directory for audit CSVs (written if provided).

    Returns:
        (sites_df, summary_dict, passed)
    """
    container = SwimContainer.open(container_path, mode="r")
    fids = container.field_uids
    failures = []
    rows = []

    # Pre-load arrays for batch checking
    etf_path = "remote_sensing/etf/landsat/ssebop/no_mask"
    ndvi_path = "derived/merged_ndvi/no_mask"

    has_etf_array = etf_path in container._root
    has_ndvi_array = ndvi_path in container._root

    etf_df = None
    if has_etf_array:
        try:
            etf_df = container.query.dataframe(etf_path)
        except Exception:
            has_etf_array = False

    ndvi_df = None
    if has_ndvi_array:
        try:
            ndvi_df = container.query.dataframe(ndvi_path)
        except Exception:
            has_ndvi_array = False

    met_dfs = {}
    for var in ("eto", "tmax", "tmin", "srad"):
        met_path = f"meteorology/gridmet/{var}"
        if met_path in container._root:
            try:
                met_dfs[var] = container.query.dataframe(met_path)
            except Exception:
                pass

    # Sentinel-2 NDVI (for ls_s2_fused audit)
    s2_df = None
    s2_path = "remote_sensing/ndvi/sentinel/no_mask"
    if family_name == "ls_s2_fused" and s2_path in container._root:
        try:
            s2_df = container.query.dataframe(s2_path)
        except Exception:
            pass

    for fid in fids:
        row = {"fid": fid, "container_family": family_name}

        # ETf check
        if has_etf_array and etf_df is not None and fid in etf_df.columns:
            n_etf = int(etf_df[fid].notna().sum())
        else:
            n_etf = 0
        row["etf_captures"] = n_etf
        row["has_etf"] = n_etf > 0
        if n_etf == 0:
            failures.append((fid, "zero_etf_captures"))

        # NDVI check
        if has_ndvi_array and ndvi_df is not None and fid in ndvi_df.columns:
            ndvi_col = ndvi_df[fid]
            n_ndvi = int(ndvi_col.notna().sum())
            if n_ndvi > 0:
                valid_dates = ndvi_col.dropna().index
                row["ndvi_first_date"] = str(valid_dates.min().date())
                row["ndvi_last_date"] = str(valid_dates.max().date())
            else:
                row["ndvi_first_date"] = None
                row["ndvi_last_date"] = None
        else:
            n_ndvi = 0
            row["ndvi_first_date"] = None
            row["ndvi_last_date"] = None
        row["ndvi_obs_count"] = n_ndvi
        row["has_ndvi"] = n_ndvi > 0
        if n_ndvi == 0:
            failures.append((fid, "all_null_ndvi"))

        # Meteorology check
        for var in ("eto", "tmax", "tmin", "srad"):
            if var in met_dfs and fid in met_dfs[var].columns:
                n_met = int(met_dfs[var][fid].notna().sum())
            else:
                n_met = 0
            row[f"has_{var}"] = n_met > 0
            if n_met == 0:
                failures.append((fid, f"all_null_{var}"))

        # Sentinel-2 NDVI (ls_s2_fused only)
        if family_name == "ls_s2_fused":
            if s2_df is not None and fid in s2_df.columns:
                s2_col = s2_df[fid]
                n_s2 = int(s2_col.notna().sum())
                if n_s2 > 0:
                    s2_valid = s2_col.dropna().index
                    row["s2_ndvi_obs_count"] = n_s2
                    row["s2_first_date"] = str(s2_valid.min().date())
                    row["s2_last_date"] = str(s2_valid.max().date())
                else:
                    row["s2_ndvi_obs_count"] = 0
                    row["s2_first_date"] = None
                    row["s2_last_date"] = None
            else:
                row["s2_ndvi_obs_count"] = 0
                row["s2_first_date"] = None
                row["s2_last_date"] = None
            row["has_s2_ndvi"] = row["s2_ndvi_obs_count"] > 0

        rows.append(row)

    container.close()

    sites_df = pd.DataFrame(rows).set_index("fid")
    passed = len(failures) == 0

    summary = {
        "family": family_name,
        "container_path": container_path,
        "total_sites": len(fids),
        "passed": passed,
        "n_failures": len(failures),
        "failures": failures[:50],
        "etf_coverage": int(sites_df["has_etf"].sum()),
        "ndvi_coverage": int(sites_df["has_ndvi"].sum()),
        "median_ndvi_obs": int(np.median(sites_df["ndvi_obs_count"])),
        "median_etf_captures": int(np.median(sites_df["etf_captures"])),
    }

    if family_name == "ls_s2_fused" and "has_s2_ndvi" in sites_df.columns:
        s2_sites = sites_df[sites_df["has_s2_ndvi"]]
        summary["s2_sites_count"] = len(s2_sites)
        summary["s2_site_ids"] = list(s2_sites.index)
        if len(s2_sites) > 0:
            summary["s2_median_obs"] = int(np.median(s2_sites["s2_ndvi_obs_count"]))

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, f"container_audit_sites_{family_name}.csv")
        sites_df.to_csv(csv_path)
        json_path = os.path.join(output_dir, f"container_audit_summary_{family_name}.json")
        with open(json_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Audit CSV: {csv_path}")
        print(f"Audit JSON: {json_path}")

    _print_summary(summary, sites_df)
    return sites_df, summary, passed


def get_s2_site_ids(audit_summary: dict) -> list[str]:
    """Extract the list of S2 site IDs from an ls_s2_fused audit summary."""
    return audit_summary.get("s2_site_ids", [])


def _print_summary(summary: dict, sites_df: pd.DataFrame) -> None:
    n = summary["total_sites"]
    print(f"\n{'=' * 60}")
    print(f"Container Audit: {summary['family']}")
    print(f"{'=' * 60}")
    print(f"  Sites:       {n}")
    print(f"  ETf:         {summary['etf_coverage']}/{n} sites with captures")
    print(f"  NDVI:        {summary['ndvi_coverage']}/{n} sites with observations")
    print(f"  Median ETf:  {summary['median_etf_captures']} captures")
    print(f"  Median NDVI: {summary['median_ndvi_obs']} observations")

    if "s2_sites_count" in summary:
        print(f"  S2 sites:    {summary['s2_sites_count']}/{n}")
        if summary.get("s2_median_obs"):
            print(f"  S2 median:   {summary['s2_median_obs']} observations")

    if summary["passed"]:
        print("  Result:      PASSED")
    else:
        print(f"  Result:      FAILED ({summary['n_failures']} failures)")
        for fid, reason in summary["failures"][:10]:
            print(f"    {fid}: {reason}")
        if summary["n_failures"] > 10:
            print(f"    ... and {summary['n_failures'] - 10} more")
