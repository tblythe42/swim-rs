import copy
import json
import netrc
import os
import time
from datetime import datetime

import pandas as pd
import requests
from requests.exceptions import JSONDecodeError, RequestException

EXCLUDE_FROM_REQUEST = [
    "tier",
    "error",
    "status",
    "created",
    "task_id",
    "updated",
    "user_id",
    "estimate",
    "retry_at",
    "has_swath",
    "api_version",
    "svc_version",
    "web_version",
    "has_nsidc_daac",
    "expires_on",
    "attempts",
]


def get_earthdata_creds_from_netrc(netrc_path=None):
    machine_name = "urs.earthdata.nasa.gov"
    username = None
    password = None
    try:
        if netrc_path is None:
            netrc_file = os.path.join(os.path.expanduser("~"), ".netrc")
        else:
            netrc_file = netrc_path
        if os.path.exists(netrc_file):
            info = netrc.netrc(netrc_file)
            auths = info.authenticators(machine_name)
            if auths:
                username = auths[0]
                password = auths[2]
    except (FileNotFoundError, netrc.NetrcParseError, Exception):
        pass
    return username, password


def authenticate_appeears(login_url, username: str, password: str) -> str:
    try:
        response = requests.post(login_url, auth=(username, password), timeout=60)
        response.raise_for_status()
        token_data = response.json()
        token = token_data.get("token")
        if not token:
            raise ValueError("Authentication failed: Token not found in response.")
        print("Authentication successful.")
        return token
    except (RequestException, ValueError) as e:
        print(f"Authentication error: {e}")
        raise e


def submit_task(appeears_endpoint, head, task_payload, task_name):
    try:
        task_post_response = requests.post(
            f"{appeears_endpoint}task", json=task_payload, headers=head, timeout=60
        )
        task_post_response.raise_for_status()
        task_response_data = task_post_response.json()
        task_id = task_response_data["task_id"]
        return task_id
    except (RequestException, JSONDecodeError, KeyError) as e:
        print(f"  -> Failed to submit task {task_name}: {e}", flush=True)
        if "task_post_response" in locals():
            print(f"     Status Code: {task_post_response.status_code}", flush=True)
            print(f"     Response Text: {task_post_response.text[:200]}...", flush=True)
        return None


def check_task_status(appeears_endpoint, head, task_id):
    status_url = f"{appeears_endpoint}task/{task_id}"
    try:
        status_response = requests.get(status_url, headers=head, timeout=30)
        if status_response.status_code == 200:
            status_data = status_response.json()
            return status_data.get("status", "unknown_status")
        else:
            print(
                f"  WARN: Received status {status_response.status_code} checking task {task_id}. Retrying later.",
                flush=True,
            )
            return "error_checking"
    except (RequestException, JSONDecodeError) as e:
        print(f"  WARN: Error checking status for task {task_id}: {e}. Retrying later.", flush=True)
        return "error_checking"


def download_task_results(appeears_endpoint, head, task_id, task_name, download_dir):
    print(f"  Downloading results for {task_name} ({task_id})...", flush=True)
    bundle_url = f"{appeears_endpoint}/bundle/{task_id}"
    tif_ct = 0
    downloaded_count = 0
    try:
        bundle_response = requests.get(bundle_url, headers=head, timeout=60)
        bundle_response.raise_for_status()
        bundle_data = bundle_response.json()
        files_info = bundle_data.get("files", [])
        os.makedirs(download_dir, exist_ok=True)

        for file_info in files_info:
            if file_info.get("file_type") != "tif":
                continue
            tif_ct += 1
            file_id = file_info.get("file_id")
            file_name = os.path.basename(file_info.get("file_name"))
            if not file_id or not file_name:
                print(
                    f"  WARN: Missing file_id or file_name in bundle for task {task_id}. Skipping file.",
                    flush=True,
                )
                continue

            file_download_url = f"{bundle_url}/{file_id}"
            local_filepath = os.path.join(download_dir, file_name)

            if os.path.exists(local_filepath):
                print(f"    Skipping already downloaded file: {file_name}", flush=True)
                downloaded_count += 1
                continue

            print(f"    Downloading {file_name}...", flush=True)
            dl_response = requests.get(file_download_url, headers=head, stream=True, timeout=300)
            if dl_response.status_code == 200:
                with open(local_filepath, "wb") as f:
                    for chunk in dl_response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                downloaded_count += 1
            else:
                print(
                    f"  ERROR: Failed download for {file_name} (Task {task_id}). Status: {dl_response.status_code}",
                    flush=True,
                )

        print(
            f"  Finished download for task {task_id}: {downloaded_count}/{tif_ct} files.",
            flush=True,
        )
        return True

    except (RequestException, JSONDecodeError, KeyError, OSError) as e:
        print(
            f"  ERROR: Failed processing bundle/download for task {task_id} ({task_name}): {e}",
            flush=True,
        )
        return False


def run_concurrent_tasks(
    download_dir,
    token,
    monitor=False,
    desc="flux_intl",
    template_request="flux-intl-request.json",
    debug=False,
):
    head = {"Authorization": f"Bearer {token}"}
    appeears_endpoint = "https://appeears.earthdatacloud.nasa.gov/api/"
    sleep_interval = 180
    now = datetime.now().strftime("%Y%m%d%H%M")
    task_id_map_file = f"task_ids_{now}.json"

    tasks_to_submit, task_base = [], None
    print("Generating task list...", flush=True)

    if debug:
        print("DEBUG MODE: Using single test date range (09-01-2022 to 09-03-2022)", flush=True)
        starts = pd.to_datetime(["2022-09-01"])
        ends = pd.to_datetime(["2022-09-03"])
    else:
        starts = pd.date_range("2018-08-01", "2026-01-01", freq="2d")
        ends = pd.date_range("2018-08-02", "2026-01-02", freq="2d")

    for enum, (sdt, edt) in enumerate(zip(starts, ends)):
        if task_base is None:
            try:
                print(f"Using template {template_request}")
                with open(template_request) as fp:
                    task_base = json.load(fp)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"ERROR: Cannot load/decode flux-intl-request.json: {e}. Exiting.")
                return

        start_date = sdt.strftime("%m-%d-%Y")
        end_date = edt.strftime("%m-%d-%Y")
        task_name = f"{desc}_{start_date}"

        task_payload = copy.deepcopy(task_base)
        task_payload["params"].update({"dates": [{"startDate": start_date, "endDate": end_date}]})
        task_payload["params"].update({"task_name": task_name})
        task_payload.update({"task_name": task_name})

        for exclude in EXCLUDE_FROM_REQUEST:
            task_payload.pop(exclude, None)

        tasks_to_submit.append(
            {"payload": task_payload, "name": task_name, "start_date": start_date}
        )

    print(f"Generated {len(tasks_to_submit)} tasks.", flush=True)

    active_tasks = {}
    task_id_map = {}
    print("\nSubmitting tasks...", flush=True)
    for task_info in tasks_to_submit:
        task_id = submit_task(appeears_endpoint, head, task_info["payload"], task_info["name"])
        if task_id:
            active_tasks[task_id] = task_info["name"]
            task_id_map[task_info["start_date"]] = task_id
        time.sleep(1)
    print(f"Finished submitting tasks. {len(active_tasks)} tasks active.", flush=True)

    print(f"Writing task ID map to {task_id_map_file}...", flush=True)
    try:
        with open(task_id_map_file, "w") as f:
            json.dump(task_id_map, f, indent=4)
        print("Task ID map saved.", flush=True)
    except OSError as e:
        print(f"ERROR: Could not write task ID map to {task_id_map_file}: {e}", flush=True)

    if not active_tasks:
        print("No tasks were submitted successfully or none were generated.", flush=True)
        return

    if monitor:
        print("\n--- Starting Monitoring Loop ---", flush=True)
        while active_tasks:
            print(f"\nChecking status of {len(active_tasks)} active tasks...", flush=True)
            tasks_to_remove = []

            for task_id in list(active_tasks.keys()):
                task_name = active_tasks[task_id]
                current_status = check_task_status(appeears_endpoint, head, task_id)
                print(f"  Task {task_name} ({task_id}) status: {current_status}", flush=True)

                if current_status == "done":
                    download_task_results(appeears_endpoint, head, task_id, task_name, download_dir)
                    tasks_to_remove.append(task_id)
                elif current_status in ["failed", "error"]:
                    print(f"  Task {task_name} ({task_id}) failed.", flush=True)
                    tasks_to_remove.append(task_id)
                elif current_status == "error_checking":
                    pass

                time.sleep(0.5)

            if tasks_to_remove:
                print(f"\n{len(tasks_to_remove)} tasks finished or failed this cycle.", flush=True)
                for task_id in tasks_to_remove:
                    active_tasks.pop(task_id, None)

            if active_tasks:
                print(
                    f"\n{len(active_tasks)} tasks remaining. Waiting for {sleep_interval} seconds...",
                    flush=True,
                )
                time.sleep(sleep_interval)
            else:
                print("\nAll submitted tasks have completed or failed.", flush=True)
                break

        print("--- Monitoring Loop Finished ---", flush=True)


def download_from_task_id_file(json_filepath, download_dir, token=None):
    """Reads task IDs from JSON file and downloads completed task results."""
    appeears_endpoint = "https://appeears.earthdatacloud.nasa.gov/api/"
    login_url = f"{appeears_endpoint}login"
    task_id_map = {}

    try:
        with open(json_filepath) as f:
            task_id_map = json.load(f)
        if not task_id_map:
            print(f"No tasks found in {json_filepath}", flush=True)
            return
        print(f"Loaded {len(task_id_map)} task references from {json_filepath}", flush=True)
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        print(f"ERROR: Could not read/parse {json_filepath}: {e}", flush=True)
        return

    if token is None:
        try:
            username, password = get_earthdata_creds_from_netrc()
            if not username or not password:
                raise ValueError("Could not get Earthdata credentials from .netrc")
            token = authenticate_appeears(login_url, username, password)
        except Exception as auth_err:
            print(f"Authentication failed: {auth_err}. Cannot proceed.", flush=True)
            return

    head = {"Authorization": f"Bearer {token}"}
    os.makedirs(download_dir, exist_ok=True)

    print("\nChecking task statuses and attempting downloads for completed tasks...", flush=True)
    total_tasks = len(task_id_map)
    completed_downloads = 0
    skipped_tasks = 0

    for i, (start_date, task_id) in enumerate(task_id_map.items()):
        # Reconstruct task name assuming original 'eu_ecostress_{start_date}' format
        task_name = f"eu_ecostress_{start_date}"
        print(f"\n[{i + 1}/{total_tasks}] Processing Task: {task_name} ({task_id})", flush=True)

        # Check status before attempting download
        current_status = check_task_status(appeears_endpoint, head, task_id)
        print(f"  Status: {current_status}", flush=True)

        if current_status == "done":
            # Attempt download only if status is 'done'
            success = download_task_results(
                appeears_endpoint, head, task_id, task_name, download_dir
            )
            if success:
                completed_downloads += 1
        else:
            skipped_tasks += 1
            print(f"  Skipping download (Status: {current_status})", flush=True)

        time.sleep(0.5)  # Small delay between tasks

    print(
        f"\nFinished processing. Successfully completed downloads for {completed_downloads}/{total_tasks - skipped_tasks} checked 'done' tasks.",
        flush=True,
    )
    if skipped_tasks > 0:
        print(f"Skipped {skipped_tasks} tasks (not 'done' or status check failed).", flush=True)


if __name__ == "__main__":
    project = "6_Flux_International"
    root = "/data/ssd2/swim"
    data_dir = os.path.join(root, project, "data")
    if not os.path.isdir(root):
        root = "/home/dgketchum/code/swim-rs"
        data_dir = os.path.join(root, "tutorials", project, "data")
    ecostress_ = os.path.join(data_dir, "ecostress")
    chips_dir = os.path.join(ecostress_, "chips")

    print("Authenticating with Earthdata...", flush=True)
    username, password = get_earthdata_creds_from_netrc()
    if not username or not password:
        print(
            "ERROR: Could not retrieve Earthdata credentials from .netrc file. Please check ~/.netrc",
            flush=True,
        )
        exit(1)

    token_ = None
    try:
        token_ = authenticate_appeears(
            "https://appeears.earthdatacloud.nasa.gov/api/login", username, password
        )
    except Exception as auth_err:
        print(f"Authentication failed: {auth_err}. Exiting.", flush=True)
        exit(1)

    # Note flux-intl-request.json is the original ET daily and ET inst uncertainty
    #      flux-intl-2-request.json is a follow-up with ET inst
    #      flux-intl-3-request.json is a follow-up with cloud mask
    #      flux-intl-3-request.json is a follow-up with cloud mask

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template = os.path.join(project_root, "flux-intl-29DEC2025-request.json")

    run_concurrent_tasks(
        download_dir=chips_dir,
        token=token_,
        monitor=False,
        desc="flux-intl-29DEC2025",
        template_request=template,
        debug=False,
    )

    task_ids_ = "task_ids_202512300833.json"

    download_from_task_id_file(download_dir=chips_dir, json_filepath=task_ids_, token=token_)

    print("\nScript finished.", flush=True)

# ========================= EOF ====================================================================
