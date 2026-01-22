# Ecosuite API Starter Pack

This repository provides a small CLI script that calls a curated set of Ecosuite
API endpoints, saves each response to disk, and organizes outputs by project or
global scope.

Authoritative references:
- API documentation: https://docs.ecosuite.io/api
- OpenAPI (Swagger UI / YAML source): https://openapi.ecosuite.io/#/dashboard/dashboardStatus

## Requirements

- Python 3.9+ (3.12 recommended)
- `pip install -r requirements.txt`
- Network access to `https://api.ecosuite.io`

## Authentication

The script uses a Bearer token or username/password to obtain one.

Supported environment variables:
- `ECOSUITE_TOKEN` or `ECOSUITE_API_TOKEN` (preferred)
- `ECOSUITE_USERNAME` and `ECOSUITE_PASSWORD` (used by `auth_manager.py`)

If none are set, the script prompts for a token interactively.

## Running the script

```bash
python main.py
```

Interactive prompts:
- Project IDs (single, comma-separated list, or CSV file)
- Start date for generation data (YYYY-MM-DD)
- End date for generation data (YYYY-MM-DD)
- Aggregation (`year`, `month`, `day`, `hour`, `15minute`, `5minute`)

Notes:
- The end date is adjusted by +1 day to align with inclusive ranges in some
  Ecosuite endpoints.
- For `energy/datums/generation/predicted`, the script always uses `aggregation=day`.

### Example run

```
$ python main.py

Choose project input type:
1 - Single project
2 - Multiple projects (comma-separated)
3 - CSV file with project IDs
Enter choice (1/2/3): 2
Enter project IDs separated by commas: APCA, OP1
Start date for generation/expected generation (YYYY-MM-DD): 2026-01-01
End date for generation/expected generation (YYYY-MM-DD): 2026-01-04
Aggregation (options: year, month, day, hour, 15minute, 5minute) [default: day]: day

Calling APIs...
[project_details] 200 https://api.ecosuite.io/projects/APCA (1234 bytes)
...
Done.
```

### Using a CSV file

Provide a CSV containing a column named one of:
`project_id`, `projectid`, `project`, `project_code`, `projectcode`, `code`, `id`.

If no header exists, the first column is used.

Example:
```csv
project_id
APCA
OP1
```

## Output format and folder structure

All API responses are written to `output/` in JSON (or `.txt` if non-JSON).

Folders:
- `output/<ProjectName>/` for project-level endpoints
- `output/_global/` for universal endpoints

Filename format:
```
<project_code>_<label>_<start>_<end>_<timestamp>.json
```

Each file wraps the response payload with metadata:
```json
{
  "meta": {
    "url": "...",
    "params": { "...": "..." },
    "status_code": 200,
    "content_type": "application/json",
    "fetched_at": "20260122T153014Z"
  },
  "data": { "...response body..." }
}
```

## API calls used by this repo

All calls are GET requests to `https://api.ecosuite.io`.

Authorization header used:
```
Authorization: Bearer <token>
```

If an endpoint supports pagination or filters, consult the official docs for
supported query parameters and response shape:
- https://docs.ecosuite.io/api
- https://openapi.ecosuite.io/#/dashboard/dashboardStatus

### Project-level endpoints (per project ID)

1) Project details
- Endpoint: `/projects/{projectId}`
- Label: `project_details`
- Purpose: Fetches project metadata; used to name the output folder and file prefix.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/projects/APCA"
```

2) Project pro forma
- Endpoint: `/projects/{projectId}/pro-forma`
- Label: `price_data`
- Purpose: Returns project pro-forma data.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/projects/APCA/pro-forma"
```

3) Energy datums
- Endpoint: `/energy/datums/projects/{projectId}`
- Label: `energy_datums`
- Params: `start`, `end`, `aggregation`
- Purpose: Aggregated energy time-series for a project.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/energy/datums/projects/APCA?start=2026-01-01&end=2026-01-05&aggregation=day"
```

4) Energy readings
- Endpoint: `/energy/readings`
- Label: `energy_readings_projectId`
- Params: `projectId`, `start`, `end`
- Purpose: Raw or near-raw readings for the project.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/energy/readings?projectId=APCA&start=2026-01-01&end=2026-01-05"
```

5) Expected generation
- Endpoint: `/energy/datums/generation/expected`
- Label: `expected_generation_projectIds`
- Params: `start`, `end`, `projectIds`, `aggregation`
- Purpose: Expected generation aggregates for the project.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/energy/datums/generation/expected?start=2026-01-01&end=2026-01-05&projectIds=APCA&aggregation=day"
```

6) Forecast generation
- Endpoint: `/energy/datums/generation/predicted/projects/{projectId}`
- Label: `forecast_generation`
- Params: `start`, `end`, `aggregation=day`
- Purpose: Predicted generation time-series.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/energy/datums/generation/predicted/projects/APCA?start=2026-01-01&end=2026-01-05&aggregation=day"
```

7) Weather datums
- Endpoint: `/weather/datums/projects/{projectId}`
- Label: `weather_datums`
- Params: `start`, `end`, `aggregation`
- Purpose: Weather time-series for the project.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/weather/datums/projects/APCA?start=2026-01-01&end=2026-01-05&aggregation=day"
```

8) Solarnetwork metadata
- Endpoint: `/solarnetwork/metadata/projects/{projectId}`
- Label: `solarnetwork_metadata`
- Purpose: Metadata for Solarnetwork mapping to the project.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/solarnetwork/metadata/projects/APCA"
```

9) Project records
- Endpoint: `/projects/{projectId}/records`
- Label: `project_records`
- Purpose: Records associated with the project.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/projects/APCA/records"
```

10) Project record documents
- Endpoint: `/projects/{projectId}/record-documents`
- Label: `record_documents`
- Purpose: Documents attached to project records.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/projects/APCA/record-documents"
```

### Global/universal endpoints

11) Events
- Endpoint: `/events`
- Label: `events`
- Params: `start=1970-01-01`, `end=<today+1>`, `aggregation`
- Purpose: Global events across the portfolio.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/events?start=1970-01-01&end=2026-01-24&aggregation=day"
```

12) Solarnetwork nodes
- Endpoint: `/solarnetwork/nodes`
- Label: `solarnetwork_nodes`
- Purpose: Node list or metadata for the Solarnetwork integration.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/solarnetwork/nodes"
```

13) Users
- Endpoint: `/users`
- Label: `users`
- Purpose: User directory.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/users"
```

14) User groups
- Endpoint: `/user-groups`
- Label: `user_groups`
- Purpose: User group directory.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/user-groups"
```

15) Records
- Endpoint: `/records`
- Label: `records`
- Purpose: Global records index.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/records"
```

16) Projects
- Endpoint: `/projects`
- Label: `projects`
- Purpose: Global projects list.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/projects"
```

17) Portfolios
- Endpoint: `/portfolios`
- Label: `portfolios`
- Purpose: Portfolio list.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/portfolios"
```

18) Energy status
- Endpoint: `/energy/status`
- Label: `energy_status`
- Purpose: Overall energy status snapshot.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/energy/status"
```

19) Dashboard status
- Endpoint: `/dashboard/status`
- Label: `dashboard_status`
- Purpose: Status payload used for dashboard health/overview.
- Example:
```
curl -H "Authorization: Bearer $ECOSUITE_TOKEN" \
  "https://api.ecosuite.io/dashboard/status"
```

## How to extend

- Add new endpoints in `main.py` using the `api_get(...)` helper.
- Choose `label` values that match the filenames you want.
- Use `folder_name` for project-specific vs `_global` for universal calls.

## Troubleshooting

- 401/403: Token missing or lacks required permissions.
- 404: Project ID may be invalid or not visible to the token.
- Empty responses: Some endpoints require time ranges with data availability.
- Rate limits: If you see throttling, add delays between calls or reduce concurrency.

## Further reference

For exact fields, response schemas, and additional query parameters, use:
- https://docs.ecosuite.io/api
- https://openapi.ecosuite.io/#/dashboard/dashboardStatus
