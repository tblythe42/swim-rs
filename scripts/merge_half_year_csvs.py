# Merge half-year NDVI CSVs (_h1/_h2) into single year files.
# Run after syncing H1/H2 exports from GCS to NAS.
#
# Usage:
#   python scripts/merge_half_year_csvs.py --county-dir /nas/swim/sid/081c
#   python scripts/merge_half_year_csvs.py --county-dir /nas/swim/sid/081c --dry-run

import argparse
import os
import re
from glob import glob

import pandas as pd

FEATURE_ID = "FID"


def find_half_pairs(csv_dir):
    """Find matching _h1/_h2 CSV pairs in a directory.

    Returns list of (year, h1_path, h2_path) tuples.
    """
    h1_files = sorted(glob(os.path.join(csv_dir, "*_h1.csv")))
    pairs = []
    for h1 in h1_files:
        h2 = h1.replace("_h1.csv", "_h2.csv")
        if not os.path.exists(h2):
            print(f"  WARNING: no H2 match for {os.path.basename(h1)}, skipping")
            continue
        match = re.search(r"_(\d{4})_h1\.csv$", h1)
        if match:
            pairs.append((int(match.group(1)), h1, h2))
    return pairs


def merge_pair(h1_path, h2_path, out_path, feature_id=FEATURE_ID):
    """Merge H1 and H2 CSVs into a single year CSV.

    Both files share the same FID index; columns are scene IDs from
    different halves of the year.  Result is a column-wise concat.
    """
    h1 = pd.read_csv(h1_path)
    h2 = pd.read_csv(h2_path)

    h1.index = h1[feature_id]
    h2.index = h2[feature_id]

    h1.drop(columns=[feature_id, "geo"], inplace=True, errors="ignore")
    h2.drop(columns=[feature_id, "geo"], inplace=True, errors="ignore")

    merged = pd.concat([h1, h2], axis=1)
    merged.index.name = feature_id
    merged.to_csv(out_path)
    return merged.shape


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge half-year NDVI CSVs")
    parser.add_argument("--county-dir", required=True, help="County directory on NAS")
    parser.add_argument("--dry-run", action="store_true", help="List pairs without merging")
    parser.add_argument("--keep", action="store_true", help="Keep H1/H2 files after merge")
    args = parser.parse_args()

    for mask_type in ["irr", "inv_irr"]:
        csv_dir = os.path.join(args.county_dir, "ndvi", mask_type)
        if not os.path.isdir(csv_dir):
            continue

        pairs = find_half_pairs(csv_dir)
        if not pairs:
            print(f"{mask_type}: no H1/H2 pairs found")
            continue

        print(f"{mask_type}: {len(pairs)} pairs")
        for year, h1, h2 in pairs:
            out = re.sub(r"_h1\.csv$", ".csv", h1)
            if args.dry_run:
                print(
                    f"  {year}: {os.path.basename(h1)} + {os.path.basename(h2)} -> {os.path.basename(out)}"
                )
                continue

            shape = merge_pair(h1, h2, out)
            print(f"  {year}: {shape[0]} fields x {shape[1]} scenes -> {os.path.basename(out)}")

            if not args.keep:
                os.remove(h1)
                os.remove(h2)

# ========================= EOF ====================================================================
