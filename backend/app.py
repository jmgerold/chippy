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
from fastapi.responses import FileResponse, JSONResponse, Response
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
def build_csv_for_query(schema: DatasetSchema) -> str:
    """Return csv_text."""
    print(f"Created schema: {schema}", file=sys.stderr)

    matched_files = search_patent_files(schema.query)
    if not matched_files:
        return ",".join(schema.columns)

    conn = get_sql_conn(schema)

    for path in matched_files:
        xml_text = gzip.open(path, 'rt', errors='ignore').read()

        xml_tables = extract_table_nodes(xml_text)
        for i, table_xml in enumerate(xml_tables):
            if i > 1:
                break
            print(f"Processing table {i} of {len(xml_tables)}", file=sys.stderr)
            structured_table = xml_table_to_csv(table_xml)

            if not structured_table:
                continue

            is_relevant, sql_command = is_table_relevant(structured_table, schema)

            print(f"csv: {structured_table.csv}", file=sys.stderr)

            print(f"is_relevant: {is_relevant}, sql_command: {sql_command}", file=sys.stderr)

            if is_relevant:
                add_secondary_sql_table(conn, structured_table.csv, sql_command)

    primary_table = conn.sql("SELECT * FROM primary_table").df()

    if primary_table.empty:
        return ",".join(schema.columns)

    return primary_table.to_csv(index=False)

# ---------------------------------------------------------------------------#
#  API routes
# ---------------------------------------------------------------------------#
@app.post("/api/extract")
async def extract_data(payload: DatasetSchema):
    print(f"Received POST request to /api/extract with payload: {payload}", file=sys.stderr)
    
    try:
        csv_text = build_csv_for_query(payload)
        print(f"build_csv_for_query returned, csv_text length={len(csv_text)}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR in build_csv_for_query: {e}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=patent_tables.csv"},
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