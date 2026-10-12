"""STEP 17 - REST API (FastAPI).   Run:  uvicorn api.main:app --reload     Docs: http://localhost:8000/docs

Typical flow:
  POST /datasets            upload + auto column mapping + cleaning + save      -> dataset id
  POST /datasets/{id}/analyze   KPIs, trends, drivers, forecast, anomalies      -> run id + JSON payload
  POST /runs/{id}/insights  LLM (or fallback) business insights                -> report
  GET  /runs/{id}/report?format=docx|md|json                                   -> download
"""
from __future__ import annotations

import hmac
import io
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from src.column_mapper import mapping_problems, suggest_mapping
from src.data_ingestion import load_dataset
from src.database import Database
from src.exceptions import InsightGeneratorError
from src.kpi_calculation import monthly_summary
from src.llm_generator import AIInsightReport, LLMConfig, generate_insights
from src.pipeline import prepare_dataset, run_analysis
from src.report_generator import build_docx, build_markdown
from src.config import CURRENCIES

VERSION = "1.0.0"


class AnalyzeRequest(BaseModel):
    period: Optional[str] = None          # e.g. "2026-09"; default = latest month


def create_app(db_path: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="AI Business Insight Generator API", version=VERSION,
                  description="Upload sales data, analyse KPIs/drivers/forecast, generate grounded AI insights.")
    db = Database(db_path)

    # ---------------------------------------------------------------- security (optional API key)
    def require_key(x_api_key: Optional[str] = Header(default=None)) -> None:
        expected = os.getenv("API_KEY", "")
        if expected and not (x_api_key and hmac.compare_digest(x_api_key, expected)):
            raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")

    auth = [Depends(require_key)]

    @app.exception_handler(InsightGeneratorError)
    async def handle_domain_error(_: Request, exc: InsightGeneratorError):
        status = 404 if "not found" in str(exc).lower() else 422
        return JSONResponse(status_code=status, content={"error": str(exc), "type": exc.__class__.__name__})

    # ---------------------------------------------------------------- endpoints
    @app.get("/health")
    def health() -> Dict:
        return {"status": "ok", "version": VERSION}

    @app.post("/mapping/suggest", dependencies=auth)
    async def mapping_suggest(file: UploadFile = File(...)) -> Dict:
        raw = load_dataset(io.BytesIO(await file.read()), filename=file.filename)
        mapping = suggest_mapping(raw)
        return {"columns": [str(c) for c in raw.columns], "suggested_mapping": mapping,
                "problems": mapping_problems(mapping)}

    @app.post("/datasets", status_code=201, dependencies=auth)
    async def upload_dataset(file: UploadFile = File(...), currency: str = Form("INR"),
                             mapping: Optional[str] = Form(None), month_first_dates: Optional[bool] = Form(None)) -> Dict:
        if currency.upper() not in CURRENCIES:
            raise HTTPException(422, f"Unsupported currency. Choose from {', '.join(CURRENCIES)}.")
        raw = load_dataset(io.BytesIO(await file.read()), filename=file.filename)
        try:
            chosen = json.loads(mapping) if mapping else None
        except json.JSONDecodeError:
            raise HTTPException(422, "'mapping' must be a JSON object like {\"Date\": \"Order Date\"}.")
        dayfirst = None if month_first_dates is None else (not month_first_dates)
        clean, report = prepare_dataset(raw, chosen, dayfirst)
        dataset_id = db.save_dataset(clean, file.filename or "upload", currency.upper(), report["mapping"], report, report["rows_in"])
        return {"dataset_id": dataset_id, "rows_in": report["rows_in"], "rows_out": report["rows_out"],
                "mapping": report["mapping"], "issues": report["issues"], "notes": report["notes"],
                "date_format": report["date_format"]}

    @app.get("/datasets", dependencies=auth)
    def list_datasets() -> Dict:
        return {"datasets": db.list_datasets()}

    @app.get("/datasets/{dataset_id}", dependencies=auth)
    def get_dataset(dataset_id: int) -> Dict:
        return db.get_dataset(dataset_id)

    @app.delete("/datasets/{dataset_id}", status_code=204, dependencies=auth)
    def delete_dataset(dataset_id: int) -> Response:
        db.delete_dataset(dataset_id)
        return Response(status_code=204)

    @app.get("/datasets/{dataset_id}/monthly", dependencies=auth)
    def monthly(dataset_id: int) -> Dict:
        """Monthly revenue computed by SQL (GROUP BY) inside the database."""
        db.get_dataset(dataset_id)
        return {"months": db.sql_monthly_revenue(dataset_id)}

    @app.get("/datasets/{dataset_id}/breakdown", dependencies=auth)
    def breakdown(dataset_id: int, dimension: str = "Region", month: Optional[str] = None) -> Dict:
        db.get_dataset(dataset_id)
        return {"dimension": dimension, "month": month, "rows": db.sql_revenue_by(dataset_id, dimension, month)}

    @app.post("/datasets/{dataset_id}/analyze", dependencies=auth)
    def analyze(dataset_id: int, body: AnalyzeRequest = AnalyzeRequest()) -> Dict:
        meta = db.get_dataset(dataset_id)
        result = run_analysis(db.load_sales_df(dataset_id), body.period, currency=meta["currency"])
        run_id = db.save_run(dataset_id, str(result.current_period), result.payload)
        return {"run_id": run_id, "payload": result.payload}

    @app.get("/datasets/{dataset_id}/runs", dependencies=auth)
    def runs(dataset_id: int) -> Dict:
        db.get_dataset(dataset_id)
        return {"runs": db.list_runs(dataset_id)}

    @app.get("/runs/{run_id}", dependencies=auth)
    def get_run(run_id: int) -> Dict:
        return db.get_run(run_id)

    @app.post("/runs/{run_id}/insights", dependencies=auth)
    def insights(run_id: int, allow_fallback: bool = True) -> Dict:
        run = db.get_run(run_id)
        report, meta = generate_insights(run["payload"], LLMConfig.from_env(), allow_fallback=allow_fallback)
        report_id = db.save_report(run_id, report.model_dump(), meta)
        return {"report_id": report_id, "report": report.model_dump(), "meta": meta}

    @app.get("/runs/{run_id}/report", dependencies=auth)
    def download_report(run_id: int, format: str = "md") -> Response:
        run = db.get_run(run_id)
        stored = db.get_latest_report(run_id)
        if stored is None:
            raise HTTPException(404, "No insights generated yet for this run. Call POST /runs/{id}/insights first.")
        report = AIInsightReport(**stored["report"])
        meta = {"source": stored["source"], "model": stored["model"], "warnings": stored["warnings"]}
        payload = run["payload"]
        if format == "json":
            return JSONResponse({"payload": payload, "report": stored["report"], "meta": meta})
        if format == "md":
            return Response(build_markdown(payload, report, meta), media_type="text/markdown")
        if format == "docx":
            dataset = db.get_dataset(run["dataset_id"])
            monthly_df = monthly_summary(db.load_sales_df(run["dataset_id"]))
            data = build_docx(payload, report, meta, monthly_df, dataset["cleaning_report"] or None)
            return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            headers={"Content-Disposition": f'attachment; filename="business_report_{run["period"]}.docx"'})
        raise HTTPException(422, "format must be one of: md, docx, json")

    return app


app = create_app()
