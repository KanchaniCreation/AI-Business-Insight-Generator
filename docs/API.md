# REST API reference

Start: `uvicorn api.main:app --reload` then open **http://localhost:8000/docs** (interactive Swagger UI).

Optional security: set `API_KEY=yourSecret` in the environment; every endpoint except `/health` then needs the header `X-API-Key: yourSecret` (401 otherwise).

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness check |
| POST | `/mapping/suggest` | upload a file, get the suggested column mapping and any problems |
| POST | `/datasets` | upload + map + clean + save. Form fields: `file`, `currency` (INR/USD/EUR/GBP), `mapping` (JSON, optional), `month_first_dates` (true/false, optional) |
| GET | `/datasets` | list datasets |
| GET | `/datasets/{id}` | metadata, mapping and cleaning report |
| DELETE | `/datasets/{id}` | delete dataset (cascades to runs and reports) |
| GET | `/datasets/{id}/monthly` | monthly revenue/profit/orders computed with SQL `GROUP BY` |
| GET | `/datasets/{id}/breakdown?dimension=Region&month=2026-09` | revenue and contribution % by dimension (SQL window function) |
| POST | `/datasets/{id}/analyze` | body `{"period": "2026-09"}` (optional). Returns `run_id` and the structured JSON payload |
| GET | `/datasets/{id}/runs` | list runs |
| GET | `/runs/{run_id}` | stored payload |
| POST | `/runs/{run_id}/insights?allow_fallback=true` | generate AI (or fallback) insights |
| GET | `/runs/{run_id}/report?format=md\|docx\|json` | download the stored report |

Errors are JSON: `{"error": "message", "type": "DataValidationError"}` with status 422 (bad input), 404 (not found) or 401 (API key).

## Example with curl
```bash
curl -F "file=@data/sales_data.xlsx" -F "currency=INR" http://localhost:8000/datasets
curl -X POST http://localhost:8000/datasets/1/analyze -H "Content-Type: application/json" -d "{}"
curl -X POST http://localhost:8000/runs/1/insights
curl -o report.docx "http://localhost:8000/runs/1/report?format=docx"
```
Windows PowerShell: use `curl.exe` instead of `curl`, or just use the Swagger UI at `/docs`.

## Example with Python
```python
import requests
base = "http://localhost:8000"
with open("data/sales_data.xlsx", "rb") as f:
    ds = requests.post(f"{base}/datasets", files={"file": f}, data={"currency": "INR"}).json()
run = requests.post(f"{base}/datasets/{ds['dataset_id']}/analyze", json={}).json()
rep = requests.post(f"{base}/runs/{run['run_id']}/insights").json()
print(rep["report"]["executive_summary"])
```
