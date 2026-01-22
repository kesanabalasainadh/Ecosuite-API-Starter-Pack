#!/usr/bin/env python3
"""
CLI utility to call Ecosuite APIs for one or more projects and persist results.

Flow:
- Collect project IDs from user input or CSV.
- Resolve auth token from env, auth manager, or prompt.
- Ask for date range and aggregation.
- Call project-scoped endpoints and global endpoints.
- Save each response with metadata into the output folder.
"""
import csv
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests


API_ROOT = "https://api.ecosuite.io"
# Allowed rollup granularities enforced by the API.
ALLOWED_AGGREGATIONS = {"year", "month", "day", "hour", "15minute", "5minute"}


def adjust_end_date(end_date: str) -> str:
    """Return end_date + 1 day in YYYY-MM-DD, or unchanged if parsing fails."""
    try:
        date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        return (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        return end_date


def prompt_project_ids() -> List[str]:
    """Prompt the user for how to provide project IDs and return the list."""
    print("\nChoose project input type:")
    print("1 - Single project")
    print("2 - Multiple projects (comma-separated)")
    print("3 - CSV file with project IDs")
    choice = input("Enter choice (1/2/3): ").strip()

    if choice == "1":
        project_id = input("Enter project ID: ").strip()
        return [project_id] if project_id else []
    if choice == "2":
        raw = input("Enter project IDs separated by commas: ").strip()
        return [p.strip() for p in raw.split(",") if p.strip()]
    if choice == "3":
        path = input("Enter CSV file path: ").strip()
        return read_project_ids_from_csv(path)

    print("Invalid choice. Exiting.")
    return []


def read_project_ids_from_csv(path: str) -> List[str]:
    """Load project IDs from a CSV file using best-effort header detection."""
    if not path:
        return []
    if not os.path.exists(path):
        print(f"CSV file not found: {path}")
        return []

    # Common header variants seen in project export files.
    candidates = {
        "project_id",
        "projectid",
        "project",
        "project_code",
        "projectcode",
        "code",
        "id",
    }
    project_ids: List[str] = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            sniffer = csv.Sniffer()
            sample = f.read(2048)
            f.seek(0)
            has_header = sniffer.has_header(sample)

            if has_header:
                # If a header exists, find a matching column name or fallback to first non-empty cell.
                reader = csv.DictReader(f)
                fieldnames = [fn.strip().lower() for fn in (reader.fieldnames or [])]
                key = None
                for fn in fieldnames:
                    if fn in candidates:
                        key = fn
                        break
                for row in reader:
                    if key:
                        val = (row.get(key) or "").strip()
                    else:
                        val = ""
                        for v in row.values():
                            v = (v or "").strip()
                            if v:
                                val = v
                                break
                    if val:
                        project_ids.append(val)
            else:
                # Headerless CSVs are treated as a single column of IDs.
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    val = (row[0] or "").strip()
                    if val:
                        project_ids.append(val)
    except Exception as exc:
        print(f"Failed to read CSV: {exc}")
        return []

    # Preserve input order while de-duplicating.
    deduped = []
    seen = set()
    for pid in project_ids:
        if pid not in seen:
            seen.add(pid)
            deduped.append(pid)
    return deduped


def get_api_token() -> str:
    """Resolve the API token from env, auth manager, or user prompt."""
    env_token = os.getenv("ECOSUITE_TOKEN") or os.getenv("ECOSUITE_API_TOKEN")
    if env_token:
        return env_token.strip()

    username = os.getenv("ECOSUITE_USERNAME")
    password = os.getenv("ECOSUITE_PASSWORD")

    if username and password:
        try:
            from auth_manager import get_auth_token
            return get_auth_token(username, password) or ""
        except Exception as exc:
            print(f"Failed to get token from username/password: {exc}")

    return input("Enter API token (Bearer): ").strip()


def sanitize_filename(value: str) -> str:
    """Make a filename-safe string for output file and folder names."""
    cleaned = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_", "."):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    return "".join(cleaned) or "response"


def extract_project_meta(payload: dict) -> dict:
    """Extract project name/code from different response shapes."""
    project = payload.get("project") if isinstance(payload.get("project"), dict) else payload
    return {
        "name": project.get("name")
        or project.get("projectName")
        or project.get("project_name")
        or "",
        "code": project.get("code")
        or project.get("projectCode")
        or project.get("project_code")
        or "",
    }


def build_dates_suffix(params: Optional[dict]) -> str:
    """Return a suffix based on start/end params for output filenames."""
    if not params:
        return ""
    start = (params.get("start") or params.get("startDate") or "").strip()
    end = (params.get("end") or params.get("endDate") or "").strip()
    if start or end:
        return f"_{sanitize_filename(start)}_{sanitize_filename(end)}"
    return ""


def save_response(
    output_root: Path,
    folder_name: str,
    project_code: str,
    label: str,
    url: str,
    params: Optional[dict],
    response: requests.Response,
) -> None:
    """Persist a response with metadata, grouping by project folder."""
    project_dir = output_root / sanitize_filename(folder_name or "_global")
    project_dir.mkdir(parents=True, exist_ok=True)

    # Name files by project, endpoint label, date window, and a UTC timestamp.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = sanitize_filename(label or "response")
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "application/json" in content_type:
        ext = "json"
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
    else:
        ext = "txt"
        payload = {"raw": response.text}

    payload_wrapper = {
        "meta": {
            "url": url,
            "params": params or {},
            "status_code": response.status_code,
            "content_type": response.headers.get("Content-Type"),
            "fetched_at": timestamp,
        },
        "data": payload,
    }

    safe_code = sanitize_filename(project_code or "project")
    dates_suffix = build_dates_suffix(params)
    filename = f"{safe_code}_{safe_label}{dates_suffix}_{timestamp}.{ext}"
    path = project_dir / filename
    if ext == "json":
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload_wrapper, f, ensure_ascii=True, indent=2)
    else:
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(payload_wrapper, ensure_ascii=True, indent=2))
            f.write("\n")


def api_get(
    url: str,
    headers: dict,
    params: Optional[dict] = None,
    label: str = "",
    output_root: Optional[Path] = None,
    folder_name: str = "",
    project_code: str = "",
) -> Optional[requests.Response]:
    """GET a URL, print a short status line, and optionally save the response."""
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        status = response.status_code
        size = len(response.content or b"")
        label_prefix = f"[{label}] " if label else ""
        print(f"{label_prefix}{status} {url} ({size} bytes)")
        if output_root is not None:
            save_response(output_root, folder_name, project_code, label, url, params, response)
        return response
    except requests.exceptions.RequestException as exc:
        label_prefix = f"[{label}] " if label else ""
        print(f"{label_prefix}ERROR {url}: {exc}")
        return None


def main() -> int:
    """Interactive entry point for collecting inputs and calling endpoints."""
    project_ids = prompt_project_ids()
    if not project_ids:
        print("No project IDs provided. Exiting.")
        return 1

    token = get_api_token()
    if not token:
        print("No API token provided. Exiting.")
        return 1

    start_date = input("Start date for generation/expected generation (YYYY-MM-DD): ").strip()
    end_date = input("End date for generation/expected generation (YYYY-MM-DD): ").strip()
    while True:
        # Keep prompting until we have a valid aggregation granularity.
        aggregation = input(
            "Aggregation (options: year, month, day, hour, 15minute, 5minute) [default: day]: "
        ).strip() or "day"
        if aggregation in ALLOWED_AGGREGATIONS:
            break
        print("Invalid aggregation. Choose one of: year, month, day, hour, 15minute, 5minute.")

    adjusted_end_date = adjust_end_date(end_date)
    today_utc = datetime.now(timezone.utc).date().isoformat()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Store output artifacts in a local folder relative to the project root.
    output_root = Path("output")
    output_root.mkdir(parents=True, exist_ok=True)

    print("\nCalling APIs...")

    for project_id in project_ids:
        if not project_id:
            continue

        # Fetch project metadata to label output with human-friendly names.
        project_details_resp = api_get(
            f"{API_ROOT}/projects/{project_id}",
            headers,
            label="project_details",
            output_root=None,
        )
        project_name = project_id
        project_code = project_id
        project_payload = None
        if project_details_resp is not None:
            try:
                project_payload = project_details_resp.json() or {}
                meta = extract_project_meta(project_payload)
                if meta["name"]:
                    project_name = meta["name"]
                if meta["code"]:
                    project_code = meta["code"]
            except ValueError:
                pass
        if project_details_resp is not None and output_root is not None:
            save_response(
                output_root,
                project_name,
                project_code,
                "project_details",
                f"{API_ROOT}/projects/{project_id}",
                None,
                project_details_resp,
            )
        # Project-specific endpoints.
        api_get(
            f"{API_ROOT}/projects/{project_id}/pro-forma",
            headers,
            label="price_data",
            output_root=output_root,
            folder_name=project_name,
            project_code=project_code,
        )
        api_get(
            f"{API_ROOT}/energy/datums/projects/{project_id}",
            headers,
            params={"start": start_date, "end": adjusted_end_date, "aggregation": aggregation},
            label="energy_datums",
            output_root=output_root,
            folder_name=project_name,
            project_code=project_code,
        )
        api_get(
            f"{API_ROOT}/energy/readings",
            headers,
            params={"projectId": project_id, "start": start_date, "end": adjusted_end_date},
            label="energy_readings_projectId",
            output_root=output_root,
            folder_name=project_name,
            project_code=project_code,
        )
        api_get(
            f"{API_ROOT}/energy/datums/generation/expected",
            headers,
            params={"start": start_date, "end": adjusted_end_date, "projectIds": project_id, "aggregation": aggregation},
            label="expected_generation_projectIds",
            output_root=output_root,
            folder_name=project_name,
            project_code=project_code,
        )
        api_get(
            f"{API_ROOT}/energy/datums/generation/predicted/projects/{project_id}",
            headers,
            params={"start": start_date, "end": adjusted_end_date, "aggregation": "day"},
            label="forecast_generation",
            output_root=output_root,
            folder_name=project_name,
            project_code=project_code,
        )
        api_get(
            f"{API_ROOT}/weather/datums/projects/{project_id}",
            headers,
            params={"start": start_date, "end": adjusted_end_date, "aggregation": aggregation},
            label="weather_datums",
            output_root=output_root,
            folder_name=project_name,
            project_code=project_code,
        )
        api_get(
            f"{API_ROOT}/solarnetwork/metadata/projects/{project_id}",
            headers,
            label="solarnetwork_metadata",
            output_root=output_root,
            folder_name=project_name,
            project_code=project_code,
        )
        api_get(
            f"{API_ROOT}/projects/{project_id}/records",
            headers,
            label="project_records",
            output_root=output_root,
            folder_name=project_name,
            project_code=project_code,
        )
        api_get(
            f"{API_ROOT}/projects/{project_id}/record-documents",
            headers,
            label="record_documents",
            output_root=output_root,
            folder_name=project_name,
            project_code=project_code,
        )

    # Global endpoints not scoped to a specific project.
    api_get(
        f"{API_ROOT}/events",
        headers,
        params={"start": "1970-01-01", "end": adjust_end_date(today_utc), "aggregation": aggregation},
        label="events",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )
    api_get(
        f"{API_ROOT}/solarnetwork/nodes",
        headers,
        label="solarnetwork_nodes",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )
    api_get(
        f"{API_ROOT}/users",
        headers,
        label="users",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )
    api_get(
        f"{API_ROOT}/user-groups",
        headers,
        label="user_groups",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )
    api_get(
        f"{API_ROOT}/records",
        headers,
        label="records",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )
    api_get(
        f"{API_ROOT}/projects",
        headers,
        label="projects",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )
    api_get(
        f"{API_ROOT}/portfolios",
        headers,
        label="portfolios",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )
    api_get(
        f"{API_ROOT}/energy/status",
        headers,
        label="energy_status",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )
    api_get(
        f"{API_ROOT}/energy/instantaneous",
        headers,
        label="energy_instantaneous",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )
    api_get(
        f"{API_ROOT}/dashboard/status",
        headers,
        label="dashboard_status",
        output_root=output_root,
        folder_name="_global",
        project_code="_global",
    )

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
