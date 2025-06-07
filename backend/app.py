"""FastAPI backend exposing:
POST /api/extract  – JSON {query: str, columns: [str]} returns a CSV file
Serves the static frontend from /frontend.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .utils import build_csv_for_query

app = FastAPI(title="Patent‑Table Extractor")

# Mount static HTML/JS assets
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

# -----------------------------  API models  -----------------------------
class ExtractRequest(BaseModel):
    query: str = Field(..., example="battery separator")
    columns: List[str] = Field(..., example=["Material", "Thickness", "Temperature"])


# -----------------------------  API route  -----------------------------
@app.post("/api/extract")
async def extract_data(payload: ExtractRequest):
    csv_text, path = build_csv_for_query(payload.query, payload.columns)

    if not csv_text.strip():
        raise HTTPException(status_code=404, detail="No data found for that query")

    return FileResponse(path, filename="patent_tables.csv", media_type="text/csv")

# -----------------------------  Healthcheck  ---------------------------
@app.get("/api/health")
async def health():
    return JSONResponse({"status": "ok"})