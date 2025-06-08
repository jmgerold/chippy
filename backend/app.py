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
from threading import RLock
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
MAX_TABLES_PER_FILE = int(os.getenv("MAX_TABLES_PER_FILE", "10"))

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
progress_lock = RLock()

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
                "created_at": datetime.now().isoformat(),
                "tables": {}
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
            # Count statuses from the tables dict
            if data['tables']:
                processed = sum(1 for t in data['tables'].values() if t['status'] != 'pending')
                relevant = sum(1 for t in data['tables'].values() if t['status'] == 'completed_relevant')
                data['processed_tables'] = processed
                data['relevant_tables'] = relevant
                data['message'] = f"Processing {processed}/{data['total_tables']} tables ({relevant} relevant found)"
            else:
                data['message'] = f"Analyzing {data['total_tables']} tables..."

        elif data["status"] == "finalizing":
            data["message"] = "Finalizing results..."
        elif data["status"] == "completed":
            relevant = sum(1 for t in data.get('tables', {}).values() if t['status'] == 'completed_relevant')
            data["message"] = f"Completed! Found {relevant} relevant tables."
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
    table_info: Tuple[Path, int, str, int, str], 
    schema: DatasetSchema, 
    task_id: str
) -> Tuple[bool, str, str, str, int]:
    """Process a single table and return (is_relevant, csv, sql_command, USPTO_ID, table_no)."""
    file_path, table_idx, table_xml, total_tables_in_file, table_uid = table_info
    
    def set_table_status(status: str):
        with progress_lock:
            if task_id in progress_store and table_uid in progress_store[task_id].get("tables", {}):
                progress_store[task_id]["tables"][table_uid]["status"] = status
                # Also trigger a global message update
                update_progress(task_id)

    try:
        set_table_status("processing")
        
        USPTO_ID = file_path.stem.split('-')[0] if '-' in file_path.stem else file_path.stem.replace('.xml', '')
        table_no = table_idx + 1
        
        print(f"[PARALLEL] Processing {file_path.name} - Table {table_no}/{total_tables_in_file}", 
              file=sys.stderr)
        
        structured_table = xml_table_to_csv(table_xml)
        if not structured_table:
            set_table_status("completed_irrelevant")
            return False, "", "", "", 0
        
        is_relevant, sql_command = is_table_relevant(structured_table, schema)
        
        print(f"[PARALLEL] {file_path.name} - Table {table_no}: relevant={is_relevant}", 
              file=sys.stderr)
        
        if is_relevant:
            set_table_status("completed_relevant")
            return True, structured_table.csv, sql_command, USPTO_ID, table_no
        else:
            set_table_status("completed_irrelevant")
            return False, "", "", "", 0
        
    except Exception as e:
        print(f"[ERROR] Processing {file_path.name} table {table_idx}: {e}", file=sys.stderr)
        set_table_status("error")
        with progress_lock:
            if task_id in progress_store:
                progress_store[task_id]["errors"].append(f"Error in {file_path.name} table {table_idx + 1}: {str(e)}")
        return False, "", "", "", 0

def run_extraction_background(all_table_tasks: list, schema: DatasetSchema, task_id: str):
    """
    This function runs in a background thread and processes the discovered tables.
    """
    print(f"[BACKGROUND] Starting processing for {len(all_table_tasks)} tables.", file=sys.stderr)
    
    conn = get_sql_conn(schema)
    conn_lock = RLock()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_table = {
            executor.submit(process_single_table, table_info, schema, task_id): table_info
            for table_info in all_table_tasks
        }
        
        print(f"[BACKGROUND] Submitted {len(future_to_table)} tasks.", file=sys.stderr)
        
        for future in as_completed(future_to_table):
            table_info = future_to_table[future]
            file_path, table_idx, _, _, _ = table_info
            
            try:
                is_relevant, csv_data, sql_command, USPTO_ID, table_no = future.result()
                
                if is_relevant:
                    with conn_lock:
                        print(f"[BACKGROUND] Adding relevant table to DB: {USPTO_ID}-{table_no}", file=sys.stderr)
                        add_secondary_sql_table(conn, csv_data, sql_command, USPTO_ID, table_no)
            except Exception as e:
                print(f"[ERROR] Future result for {file_path.name} table {table_idx}: {e}", file=sys.stderr)

    update_progress(task_id, status="finalizing")
    primary_table = conn.sql("SELECT * FROM primary_table").df()
    csv_result = primary_table.to_csv(index=False) if not primary_table.empty else ",".join(schema.columns)
    
    update_progress(task_id, status="completed", csv_result=csv_result)
    print(f"[BACKGROUND] Task {task_id} complete.", file=sys.stderr)

# ---------------------------------------------------------------------------#
#  API routes
# ---------------------------------------------------------------------------#
@app.post("/api/extract")
async def extract_data(payload: DatasetSchema):
    print(f"Received POST request to /api/extract with payload: {payload}", file=sys.stderr)
    
    cleanup_old_tasks()
    
    task_id = str(uuid.uuid4())
    update_progress(task_id, status="initializing")

    # --- Start of synchronous discovery ---
    update_progress(task_id, status="searching_files")
    matched_files = search_patent_files(payload.query)
    
    
    if not matched_files:
        update_progress(task_id, status="completed", message="No matching files found.")
        return JSONResponse({
            "task_id": task_id,
            "status": "completed",
            "message": "No matching files or tables found.",
            "tables": {}
        })

    update_progress(task_id, status="extracting_tables", total_files=len(matched_files))

    all_table_tasks = []
    tables_progress = {}
    
    for file_idx, file_path in enumerate(matched_files):
        try:
            with gzip.open(file_path, 'rt', errors='ignore') as f:
                xml_text = f.read()
            
            xml_tables = extract_table_nodes(xml_text)
            
            update_progress(task_id, processed_files=file_idx + 1)
            
            USPTO_ID = file_path.stem.split('-')[0] if '-' in file_path.stem else file_path.stem.replace('.xml', '')
            
            for i, table_xml in enumerate(xml_tables[:MAX_TABLES_PER_FILE]):
                table_no = i + 1
                table_uid = f"{USPTO_ID}-{table_no}"
                all_table_tasks.append((file_path, i, table_xml, len(xml_tables), table_uid))
                tables_progress[table_uid] = {
                    "uid": table_uid,
                    "uspto_id": USPTO_ID,
                    "table_no": table_no,
                    "status": "pending"
                }
        except Exception as e:
            print(f"[ERROR] Reading {file_path}: {e}", file=sys.stderr)
            progress = get_progress(task_id)
            update_progress(task_id, 
                errors=progress["errors"] + [f"Error reading {file_path.name}: {str(e)}"]
            )
    
    update_progress(task_id, 
        status="processing_tables",
        total_tables=len(all_table_tasks),
        tables=tables_progress
    )
    # --- End of synchronous discovery ---

    if not all_table_tasks:
        # This case is for when files are found but they contain no tables
        update_progress(task_id, status="completed", message="Files found, but they contained no tables.")
        return JSONResponse({
            "task_id": task_id,
            "status": "completed",
            "message": "Files found, but they contained no tables.",
            "tables": {}
        })

    # Offload the heavy processing to a background thread
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, run_extraction_background, all_table_tasks, payload, task_id)

    # Return task ID and the initial table list immediately
    return JSONResponse({
        "task_id": task_id,
        "status": "processing_tables",
        "message": f"Analyzing {len(all_table_tasks)} tables...",
        "tables": tables_progress
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