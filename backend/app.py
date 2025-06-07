"""
FastAPI backend with debug logging:

POST /api/extract   – JSON {"query": str, "columns": [str], "types": [str]} → CSV file
GET  /api/health    – simple health-check
Static files from ../frontend are served at /
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List
import uuid
import gzip

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add debug logging
print("Starting app.py import...", file=sys.stderr)

from .utils import (
    search_patent_files,
    extract_table_nodes,
    is_table_relevant,
    xml_table_to_csv,
    merge_csv_blobs,
)

from .formats import DatasetSchema
from .sql import get_sql_conn, add_secondary_sql_table

app = FastAPI(title="Patent-Table Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

print("FastAPI app created, adding routes...", file=sys.stderr)

# ---------------------------------------------------------------------------#
#  Orchestrator
# ---------------------------------------------------------------------------#
def build_csv_for_query(schema: DatasetSchema) -> tuple[str, str]:
    """Return (csv_text, temp_file_path)."""
    print(f"Created schema: {schema}", file=sys.stderr)

    matched_files = search_patent_files(schema.query)
    if not matched_files:
        return ("", "no_matches.csv")

    conn = get_sql_conn(schema)

    for path in matched_files:
        xml_text = gzip.open(path, 'rt', errors='ignore').read()
        for i, tbl_xml in enumerate(extract_table_nodes(xml_text)):
            csv = xml_table_to_csv(tbl_xml)
            is_relevant, sql_command = is_table_relevant(csv, schema.columns)

            if is_relevant:
                add_secondary_sql_table(conn, csv, sql_command)

    primary_table = conn.sql("SELECT * FROM primary_table").df()

    file_name = f"results_{uuid.uuid4().hex[:8]}.csv"
    dest = Path("/tmp") / file_name
    
    primary_table.to_csv(dest, index=False)

    return str(dest)

# ---------------------------------------------------------------------------#
#  API routes
# ---------------------------------------------------------------------------#
@app.post("/api/extract")
async def extract_data(payload: DatasetSchema):
    print(f"Received POST request to /api/extract with payload: {payload}", file=sys.stderr)
    
    try:
        csv_path = build_csv_for_query(payload)
        print(f"build_csv_for_query returned, path={csv_path}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR in build_csv_for_query: {e}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    return FileResponse(
        csv_path,
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