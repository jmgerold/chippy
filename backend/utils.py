"""Utility helpers – everything heavy (LLM calls, real XML parsing, smart CSV
merging) is stubbed so the app runs instantly out-of-the-box."""
from __future__ import annotations

import os
import random
import uuid
from pathlib import Path
from typing import List
from xml.etree import ElementTree as ET

# Handle both Docker and Modal environments
if os.path.exists("/.dockerenv"):
    # Running in Docker
    from dotenv import load_dotenv
    load_dotenv()
    XML_DIR = Path(os.getenv("XML_STORE_DIR", "/app/patents"))
else:
    # Running in Modal or local
    XML_DIR = Path("/app/patents")

# ---------------------------------------------------------------------------#
#  XML search helpers
# ---------------------------------------------------------------------------#
def _iter_xml_files(limit: int | None = None):
    """Yield Path objects for .xml files in the store (depth-1)."""
    for i, path in enumerate(sorted(XML_DIR.glob("*.xml"))):
        if limit and i >= limit:
            break
        yield path


def search_patent_files(query: str, limit: int = 3) -> List[Path]:
    """Return the first *limit* patent files whose raw text contains *query*."""
    query = query.lower()
    matches: list[Path] = []
    for path in _iter_xml_files():
        try:
            text = path.read_text(errors="ignore").lower()
        except Exception:
            continue
        if query in text:
            matches.append(path)
        if len(matches) == limit:
            break
    return matches


# ---------------------------------------------------------------------------#
#  Table extraction
# ---------------------------------------------------------------------------#
def extract_table_nodes(xml_text: str) -> List[str]:
    """Return raw XML strings for every <table>...</table> element."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    tables = root.findall(".//table")
    return [ET.tostring(t, encoding="unicode") for t in tables]


# ---------------------------------------------------------------------------#
#  Relevance check (stubbed)
# ---------------------------------------------------------------------------#
def llm_table_relevant(table_xml: str, requested_columns: list[str]) -> bool:
    """Stub: always returns True for testing. Replace with real OpenAI call when ready."""
    # For testing: always return True so we get results
    return True
    
    # Original random logic (commented out for testing):
    # return random.choice([True, False])


# ---------------------------------------------------------------------------#
#  Dummy conversions
# ---------------------------------------------------------------------------#
def xml_table_to_csv(table_xml: str) -> str:
    """Wrap the table XML in quotes, escaping internal quotes, to form CSV.
    This is a dummy implementation - replace with real XML->CSV parser."""
    safe = table_xml.replace("\n", " ").replace('"', '""')
    return f'"{safe}"\n'


def merge_csv_blobs(blobs: list[str]) -> str:
    """Concatenate CSV fragments.
    This is a dummy implementation - replace with smart CSV merger."""
    return "".join(blobs)


# ---------------------------------------------------------------------------#
#  Orchestrator
# ---------------------------------------------------------------------------#
def build_csv_for_query(
    query: str, requested_columns: list[str]
) -> tuple[str, str]:
    """Return (csv_text, temp_file_path)."""
    matched_files = search_patent_files(query)
    if not matched_files:
        return ("", "no_matches.csv")

    pieces: list[str] = []
    for path in matched_files:
        xml_text = path.read_text(errors="ignore")
        for tbl_xml in extract_table_nodes(xml_text):
            if llm_table_relevant(tbl_xml[:4000], requested_columns):
                pieces.append(xml_table_to_csv(tbl_xml))

    final_csv = merge_csv_blobs(pieces) or "\n"
    file_name = f"results_{uuid.uuid4().hex[:8]}.csv"
    dest = Path("/tmp") / file_name
    dest.write_text(final_csv)
    return final_csv, str(dest)