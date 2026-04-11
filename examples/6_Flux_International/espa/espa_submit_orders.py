# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas",
#   "requests",
# ]
# ///
"""Submit ESPA orders with bounded concurrency.

Reads the manifest, loads payload JSONs, and submits orders to the ESPA API
with a configurable cap on active orders. Updates the manifest with order IDs
and status.

Example:
    uv run examples/6_Flux_International/espa/espa_submit_orders.py \
        --manifest /data/ssd1/swim/6_Flux_International/data/remote_sensing/espa/espa_manifest.csv \
        --max-active 10
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

ESPA_API = "https://espa.cr.usgs.gov/api/v1"
SUBMIT_SLEEP = 5  # seconds between submissions


def _load_credentials(cred_file: Path) -> tuple[str, str]:
    text = cred_file.read_text().strip()
    if ":" in text:
        user, passwd = text.split(":", 1)
    else:
        lines = text.splitlines()
        user = lines[0].strip()
        passwd = lines[1].strip() if len(lines) > 1 else ""
    return user, passwd


def _get_active_order_count(auth: tuple[str, str]) -> int:
    """Count orders that are not in a terminal state.

    The ESPA list-orders endpoint returns completed orders even when filtering
    by non-terminal statuses, so we must check each order's actual status.
    """
    terminal = {"complete", "cancelled", "purged"}
    resp = requests.get(f"{ESPA_API}/list-orders", auth=auth, timeout=60)
    resp.raise_for_status()
    all_orders = resp.json()
    active = 0
    for oid in all_orders:
        resp2 = requests.get(f"{ESPA_API}/order/{oid}", auth=auth, timeout=60)
        resp2.raise_for_status()
        status = resp2.json().get("status", "")
        if status not in terminal:
            active += 1
    return active


def _submit_order(auth: tuple[str, str], payload: dict) -> dict:
    resp = requests.post(
        f"{ESPA_API}/order",
        auth=auth,
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def submit_orders(
    manifest_path: Path,
    cred_file: Path,
    max_active: int = 10,
    dry_run: bool = False,
) -> None:
    auth = _load_credentials(cred_file)
    manifest = pd.read_csv(manifest_path, dtype=str)
    log_path = manifest_path.parent / "submission_log.json"
    log_entries: list[dict] = []

    # Ensure state columns exist
    for col in ["retry_count", "last_error"]:
        if col not in manifest.columns:
            manifest[col] = ""

    # Find submittable rows: have a payload, no order_id yet (or retryable failures)
    has_payload = manifest["payload_json"].notna() & (manifest["payload_json"] != "")
    no_order = manifest["order_id"].isna() | (manifest["order_id"] == "")
    retryable = manifest["order_status"] == "submit_failed"
    submittable = manifest[has_payload & (no_order | retryable)]

    if submittable.empty:
        print("No submittable rows found.")
        return

    print(f"Submittable site-years: {len(submittable)}")

    if not dry_run:
        active = _get_active_order_count(auth)
        print(f"Currently active orders: {active}")
    else:
        active = 0

    submitted = 0
    for idx, row in submittable.iterrows():
        site = row["site"]
        year = row["year"]

        if not dry_run and active >= max_active:
            print(f"Active order cap ({max_active}) reached. Stopping submissions.")
            break

        payload_path = Path(row["payload_json"])
        if not payload_path.exists():
            print(f"  SKIP {site}/{year}: payload file missing")
            continue

        with open(payload_path) as f:
            payload = json.load(f)

        if dry_run:
            print(f"  DRY-RUN {site}/{year}: would submit {payload_path.name}")
            continue

        try:
            result = _submit_order(auth, payload)
            order_id = result.get("orderid", result.get("order_id", ""))
            status = result.get("status", "submitted")
            manifest.at[idx, "order_id"] = str(order_id)
            manifest.at[idx, "order_status"] = str(status)
            log_entries.append(
                {
                    "site": site,
                    "year": year,
                    "order_id": order_id,
                    "response": result,
                }
            )
            active += 1
            submitted += 1
            print(f"  SUBMITTED {site}/{year}: {order_id}")
            time.sleep(SUBMIT_SLEEP)
        except requests.HTTPError as e:
            msg = str(e)
            manifest.at[idx, "order_status"] = "submit_failed"
            manifest.at[idx, "last_error"] = msg[:200]
            prev = int(row.get("retry_count") or 0)
            manifest.at[idx, "retry_count"] = str(prev + 1)
            log_entries.append(
                {
                    "site": site,
                    "year": year,
                    "error": msg,
                }
            )
            print(f"  FAILED {site}/{year}: {msg}")

    manifest.to_csv(manifest_path, index=False)

    if log_entries:
        with open(log_path, "w") as f:
            json.dump(log_entries, f, indent=2)

    print(f"\nSubmitted: {submitted}")
    print(f"Manifest updated: {manifest_path}")
    if log_entries:
        print(f"Log: {log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit ESPA orders from manifest")
    parser.add_argument("--manifest", required=True, help="Path to espa_manifest.csv")
    parser.add_argument(
        "--credentials",
        default=str(Path.home() / "usgs_pswd.txt"),
        help="USGS credentials file (user:password)",
    )
    parser.add_argument("--max-active", type=int, default=10, help="Max concurrent active orders")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be submitted")
    args = parser.parse_args()

    submit_orders(
        manifest_path=Path(args.manifest),
        cred_file=Path(args.credentials),
        max_active=args.max_active,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
