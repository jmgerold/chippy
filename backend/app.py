"""
FastAPI backend with debug logging:

POST /api/extract   – JSON {"query": str, "columns": [str]} → CSV file
GET  /api/health    – simple health-check
Static files from ../frontend are served at /
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add debug logging
print("Starting app.py import...", file=sys.stderr)

try:
    from .utils import build_csv_for_query
    print("Successfully imported build_csv_for_query", file=sys.stderr)
except Exception as e:
    print(f"ERROR importing utils: {e}", file=sys.stderr)
    raise

app = FastAPI(title="Patent-Table Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

print("FastAPI app created, adding routes...", file=sys.stderr)

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
    print(f"Received POST request to /api/extract with payload: {payload}", file=sys.stderr)
    
    try:
        csv_text, path = build_csv_for_query(payload.query, payload.columns)
        print(f"build_csv_for_query returned: csv_length={len(csv_text)}, path={path}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR in build_csv_for_query: {e}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

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

print("API routes added", file=sys.stderr)

# ---------------------------------------------------------------------------#
#  Static frontend (must be mounted **after** API routes so it doesn't
#  shadow /api/*)
# ---------------------------------------------------------------------------#
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
print(f"Mounting static files from: {FRONTEND_DIR}", file=sys.stderr)

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

print("App setup complete", file=sys.stderr)

# Print all registered routes for debugging
print("Registered routes:", file=sys.stderr)
for route in app.routes:
    print(f"  {route}", file=sys.stderr)