"""
FastAPI backend:

POST /api/extract   – JSON {"query": str, "columns": [str]} → CSV file
GET  /api/health    – simple health-check
Static files from ../frontend are served at /
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .utils import build_csv_for_query

app = FastAPI(title="Patent-Table Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------------------------------------------------------------------#
#  Pydantic model for the request body
# ---------------------------------------------------------------------------#
class ExtractRequest(BaseModel):
    query: str = Field(..., example="battery separator")
    columns: List[str] = Field(
        ..., example=["Material", "Thickness", "Temperature"]
    )


# ---------------------------------------------------------------------------#
#  API routes
# ---------------------------------------------------------------------------#
@app.post("/api/extract")
async def extract_data(payload: ExtractRequest):
    csv_text, path = build_csv_for_query(payload.query, payload.columns)

    if not csv_text.strip():
        raise HTTPException(status_code=404, detail="No data found for that query")

    return FileResponse(
        path,
        filename="patent_tables.csv",
        media_type="text/csv",
    )


@app.get("/api/health")
async def health():
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------#
#  Static frontend (must be mounted **after** API routes so it doesn’t
#  shadow /api/*)
# ---------------------------------------------------------------------------#
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
