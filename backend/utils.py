"""Utility helpers – most heavy lifting here is stubbed so the app runs instantly."""
from __future__ import annotations
import os
import random
import uuid
from pathlib import Path
from typing import List
from xml.etree import ElementTree as ET

from dotenv import load_dotenv

load_dotenv()

XML_DIR = Path(os.getenv("XML_STORE_DIR", "/app/patents"))

# ---------------------------------------------------------------------------
#   XML search helpers
# ---------------------------------------------------------------------------

def _iter_xml_files(limit: int | None = None):
    """Yield Path objects for .xml files in the XML store (depth‑1)."""
    for i, path in enumerate(sorted(XML_DIR.glob("*.xml"))):
        if limit and i >= limit:
            break
        yield path


def search_patent_files(query: str, limit: int = 3) -> List[Path]:
    """Very naive search: return the first *limit* XML files whose raw text
    contains the *query* string (case‑insensitive)."""
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

# ---------------------------------------------------------------------------
#   Patent table extraction
# ---------------------------------------------------------------------------

def extract_table_nodes(xml_text: str) -> List[str]:
    """Return raw XML strings for every <table>…</table> element in the patent."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    tables = root.findall(".//table")
    return [ET.tostring(t, encoding="unicode") for t in tables]

# ---------------------------------------------------------------------------
#   Determining relevance via LLM (stub)
# ---------------------------------------------------------------------------

def llm_table_relevant(table_xml: str, requested_columns: list[str]) -> bool:
    """Stub for LLM relevance check – randomly returns True 50% of the time."""
    # Real logic would call OpenAI chat completion with prompt
    return random.choice([True, False])

# ---------------------------------------------------------------------------
#   Dummy conversions
# ---------------------------------------------------------------------------

def xml_table_to_csv(table_xml: str) -> str:
    """Dummy transform: wraps XML in quotes so it‘s valid CSV (doubles any internal quotes)."""
    safe = table_xml.replace('\n', ' ').replace('"', '""')
    return f'"{safe}"\n'

def merge_csv_blobs(blobs: list[str]) -> str:
    """Dummy merge: just concatenates text blobs."""
    return "".join(blobs)

# ---------------------------------------------------------------------------
#   Main orchestrator used by the API route
# ---------------------------------------------------------------------------

def build_csv_for_query(query: str, requested_columns: list[str]) -> tuple[str, str]:
    """Return (csv_text, generated_filename)."""
    matched_files = search_patent_files(query)
    if not matched_files:
        return ("", "no_matches.csv")

    all_relevant_csv_parts: list[str] = []
    for path in matched_files:
        xml_text = path.read_text(errors="ignore")
        table_nodes = extract_table_nodes(xml_text)
        # Only peek at first few chars to avoid heavy prompt tokens when real‑life
        for tbl_xml in table_nodes:
            if llm_table_relevant(tbl_xml[:4000], requested_columns):
                all_relevant_csv_parts.append(xml_table_to_csv(tbl_xml))

    final_csv = merge_csv_blobs(all_relevant_csv_parts) or "\n"  # always non‑empty
    fname = f"results_{uuid.uuid4().hex[:8]}.csv"
    dest = Path("/tmp") / fname
    dest.write_text(final_csv)
    return final_csv, str(dest)