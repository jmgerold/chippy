"""
FastAPI backend with table-level parallel processing and simple progress tracking:

POST /api/extract   – JSON {"query": str, "columns": [str], "types": [str]} → CSV file
GET  /api/health    – simple health-check
GET  /api/progress/{task_id} – Get current progress (simple JSON endpoint)
Static files from ../frontend are served at /
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
import uuid
import gzip
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import asyncio
from datetime import datetime
import time
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configuration
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "8"))
MAX_TABLES_PER_FILE = int(os.getenv("MAX_TABLES_PER_FILE", "100"))

# Add debug logging
print("Starting app.py import...", file=sys.stderr)
print(f"Parallel configuration: MAX_WORKERS={MAX_WORKERS}, MAX_TABLES_PER_FILE={MAX_TABLES_PER_FILE}", file=sys.stderr)

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
#  Progress Tracking (Simplified)
# ---------------------------------------------------------------------------#
# Global progress store - simple dict with task_id -> progress data
progress_store: Dict[str, Dict[str, Any]] = {}
progress_lock = Lock()

def update_progress(task_id: str, **kwargs):
    """Update progress for a task."""
    with progress_lock:
        if task_id not in progress_store:
            progress_store[task_id] = {
                "status": "initializing",
                "message": "Starting extraction...",
                "total_files": 0,
                "processed_files": 0,
                "total_tables": 0,
                "processed_tables": 0,
                "relevant_tables": 0,
                "current_action": "",
                "errors": [],
                "csv_result": None,
                "created_at": datetime.now().isoformat()
            }
        progress_store[task_id].update(kwargs)
        progress_store[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Create human-readable message
        data = progress_store[task_id]
        if data["status"] == "searching_files":
            data["message"] = "Searching patent files..."
        elif data["status"] == "extracting_tables":
            data["message"] = f"Extracting tables from {data['total_files']} files..."
        elif data["status"] == "processing_tables":
            data["message"] = f"Processing {data['processed_tables']}/{data['total_tables']} tables ({data['relevant_tables']} relevant found)"
        elif data["status"] == "finalizing":
            data["message"] = "Finalizing results..."
        elif data["status"] == "completed":
            data["message"] = f"Completed! Found {data['relevant_tables']} relevant tables."
        elif data["status"] == "error":
            data["message"] = "Error occurred during processing"

def get_progress(task_id: str) -> Dict[str, Any]:
    """Get progress for a task."""
    with progress_lock:
        return progress_store.get(task_id, {"status": "not_found"}).copy()

def cleanup_old_tasks():
    """Remove tasks older than 5 minutes."""
    with progress_lock:
        cutoff = datetime.now().timestamp() - 300
        to_remove = []
        for task_id, data in progress_store.items():
            created = datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())).timestamp()
            if created < cutoff:
                to_remove.append(task_id)
        for task_id in to_remove:
            del progress_store[task_id]

# ---------------------------------------------------------------------------#
#  Parallel Processing Functions
# ---------------------------------------------------------------------------#
def process_single_table(
    table_info: Tuple[Path, int, str, int], 
    schema: DatasetSchema, 
    task_id: str
) -> Tuple[bool, str, str]:
    """Process a single table and return (is_relevant, csv, sql_command)."""
    file_path, table_idx, table_xml, total_tables_in_file = table_info
    
    try:
        # Update current action
        update_progress(task_id, 
            current_action=f"Processing {file_path.name} - Table {table_idx + 1}/{total_tables_in_file}"
        )
        
        print(f"[PARALLEL] Processing {file_path.name} - Table {table_idx + 1}/{total_tables_in_file}", 
              file=sys.stderr)
        
        # Process the table
        structured_table = xml_table_to_csv(table_xml)
        if not structured_table:
            return False, "", ""
        
        # Check relevance
        is_relevant, sql_command = is_table_relevant(structured_table, schema)
        
        print(f"[PARALLEL] {file_path.name} - Table {table_idx + 1}: relevant={is_relevant}", 
              file=sys.stderr)
        
        if is_relevant:
            return True, structured_table.csv, sql_command
        
        return False, "", ""
        
    except Exception as e:
        print(f"[ERROR] Processing {file_path.name} table {table_idx}: {e}", file=sys.stderr)
        progress = get_progress(task_id)
        update_progress(task_id, 
            errors=progress["errors"] + [f"Error in {file_path.name} table {table_idx + 1}: {str(e)}"]
        )
        return False, "", ""

def build_csv_for_query_parallel(schema: DatasetSchema, task_id: str) -> str:
    """Parallel version that processes tables concurrently."""
    print(f"[PARALLEL] Starting extraction with schema: {schema}", file=sys.stderr)
    
    # Search for files
    update_progress(task_id, status="searching_files")
    matched_files = search_patent_files(schema.query)
    
    
    if not matched_files:
        update_progress(task_id, status="completed", processed_files=0, message="No matching files found.")
        return ",".join(schema.columns)
    
    print(f"[PARALLEL] Found {len(matched_files)} files to process", file=sys.stderr)
    update_progress(task_id, 
        status="extracting_tables",
        total_files=len(matched_files)
    )
    
    # First, extract all tables from all files
    all_table_tasks = []
    total_table_count = 0
    
    for file_idx, file_path in enumerate(matched_files):
        try:
            with gzip.open(file_path, 'rt', errors='ignore') as f:
                xml_text = f.read()
            
            xml_tables = extract_table_nodes(xml_text)
            print(f"[PARALLEL] File {file_path.name} has {len(xml_tables)} tables", file=sys.stderr)
            
            # Update progress for extracted file
            update_progress(task_id, processed_files=file_idx + 1)
            
            # Create tasks for each table
            for i, table_xml in enumerate(xml_tables[:MAX_TABLES_PER_FILE]):
                all_table_tasks.append((file_path, i, table_xml, len(xml_tables)))
                total_table_count += 1
                
        except Exception as e:
            print(f"[ERROR] Reading {file_path}: {e}", file=sys.stderr)
            progress = get_progress(task_id)
            update_progress(task_id, 
                errors=progress["errors"] + [f"Error reading {file_path.name}: {str(e)}"]
            )
    
    update_progress(task_id, 
        status="processing_tables",
        total_tables=total_table_count
    )
    
    print(f"[PARALLEL] Total tables to process: {total_table_count}", file=sys.stderr)
    
    # Initialize database
    conn = get_sql_conn(schema)
    conn_lock = Lock()
    
    # Process all tables in parallel
    processed_count = 0
    relevant_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all table processing tasks
        future_to_table = {
            executor.submit(process_single_table, table_info, schema, task_id): table_info
            for table_info in all_table_tasks
        }
        
        print(f"[PARALLEL] Submitted {len(future_to_table)} table processing tasks", file=sys.stderr)
        
        # Process completed tasks
        for future in as_completed(future_to_table):
            table_info = future_to_table[future]
            file_path, table_idx, _, _ = table_info
            
            try:
                is_relevant, csv_data, sql_command = future.result()
                
                processed_count += 1
                
                if is_relevant:
                    relevant_count += 1
                    # Add to database (thread-safe)
                    with conn_lock:
                        print(f"[PARALLEL] Adding relevant table to database from {file_path.name}", 
                              file=sys.stderr)
                        add_secondary_sql_table(conn, csv_data, sql_command)
                
                # Update progress
                update_progress(task_id, 
                    processed_tables=processed_count,
                    relevant_tables=relevant_count
                )
                
            except Exception as e:
                print(f"[ERROR] Processing future for {file_path} table {table_idx}: {e}", 
                      file=sys.stderr)
    
    # Get final results
    update_progress(task_id, status="finalizing")
    primary_table = conn.sql("SELECT * FROM primary_table").df()
    
    csv_result = primary_table.to_csv(index=False) if not primary_table.empty else ",".join(schema.columns)
    
    update_progress(task_id, 
        status="completed",
        processed_files=len(matched_files),
        csv_result=csv_result
    )
    
    print(f"[PARALLEL] Extraction complete. Processed {processed_count} tables, found {relevant_count} relevant", 
          file=sys.stderr)
    
    return csv_result

# ---------------------------------------------------------------------------#
#  API routes
# ---------------------------------------------------------------------------#
@app.post("/api/extract")
async def extract_data(payload: DatasetSchema):
    print(f"Received POST request to /api/extract with payload: {payload}", file=sys.stderr)
    
    # Clean up old tasks periodically
    cleanup_old_tasks()
    
    # Create a unique task ID for this extraction
    task_id = str(uuid.uuid4())
    update_progress(task_id, status="initializing")
    
    # Run extraction in background
        # Define a normal (sync) runner so we can catch exceptions
    def extraction_runner(schema: DatasetSchema, tid: str):
        try:
            build_csv_for_query_parallel(schema, tid)
        except Exception as e:
            print(f"ERROR in build_csv_for_query_parallel: {e}", file=sys.stderr)
            update_progress(tid, status="error", errors=[str(e)])

    # Offload to a thread so the event loop can still serve /api/progress:
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, extraction_runner, payload, task_id)

    # Return task ID immediately so frontend can start polling
    return JSONResponse({
        "task_id": task_id,
        "status": "started",
        "message": "Extraction started. Poll /api/progress/{task_id} for updates."
    })

@app.get("/api/progress/{task_id}")
async def get_progress_endpoint(task_id: str):
    """Simple JSON endpoint for progress updates."""
    progress = get_progress(task_id)
    
    # Calculate percentage
    if progress.get("total_tables", 0) > 0:
        progress["percentage"] = int(
            (progress.get("processed_tables", 0) / progress["total_tables"]) * 100
        )
    else:
        progress["percentage"] = 0
    
    return JSONResponse(progress)

@app.get("/api/download/{task_id}")
async def download_csv(task_id: str):
    """Download the CSV result for a completed task."""
    progress = get_progress(task_id)
    
    if progress.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Task not completed")
    
    csv_result = progress.get("csv_result")
    if not csv_result:
        raise HTTPException(status_code=404, detail="No CSV result found")
    
    return Response(
        content=csv_result,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=patent_tables.csv"
        }
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