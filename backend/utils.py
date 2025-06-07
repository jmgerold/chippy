"""Utility helpers – everything heavy (LLM calls, real XML parsing, smart CSV
merging) is stubbed so the app runs instantly out-of-the-box."""
from __future__ import annotations

import os
import random
import uuid
from pathlib import Path
from typing import List
from xml.etree import ElementTree as ET

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

XML_DIR = Path(os.getenv("XML_STORE_DIR", "/app/patents"))

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class Table(BaseModel):
    table_description: str
    csv: str


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
def create_xml_to_csv_prompt(table_xml_str: str) -> str:
    return f"""
    Using the OCR table (XML) provided, analyze and convert it to structured data with both a description and CSV format.

    You must provide:

    1. table_description:
    - Provide a verbose description of the table based on the XML structure
    - Describe what kind of data the table contains
    - Mention the number of rows and columns if apparent
    - Note any special formatting or patterns in the data

    2. csv:
    - Make column names SQL compatible (use underscores for spaces, no dots, etc.)
    - Ensure each column name is unique
    - Add units to column names if present (e.g., time_hours, temp_celsius)
    - Preserve the original meaning of headers (e.g., "UTC Untreated control group (%)" → "utc_untreated_control_group_pct")
    - Avoid SQL reserved keywords (e.g., group, order, id)
    - Do not interpret or rename based on assumed purpose
    - Transcribe each <row> as a separate CSV row, regardless of the number of <entry> tags it contains
    - Use "NA" for missing or empty values
    - Use comma as delimiter
    - Use double quotes around ALL fields (both text and numeric)
    - Preserve all text exactly as it appears in the XML, including descriptive elements like <sub></sub>
    - Do not merge or interpret any data
    - Include header row with column names

    Input XML table:
    {table_xml_str}"""

def xml_table_to_csv(table_xml: str) -> str:
    """Convert XML table to CSV using OpenAI API.
    
    Args:
        table_xml: Raw XML string containing table data
        
    Returns:
        CSV formatted string
    """
    try:
        # Check if OpenAI API key is configured
        if not os.getenv("OPENAI_API_KEY"):
            print("Warning: OPENAI_API_KEY not set, falling back to dummy implementation")
            # Fallback to dummy implementation
            safe = table_xml.replace("\n", " ").replace('"', '""')
            print(table_xml)
            return f'"{safe}"\n'
        
        # Create prompt for OpenAI
        prompt = create_xml_to_csv_prompt(table_xml)
        
        # Call OpenAI API with structured outputs
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",  # Using the more cost-effective model
            messages=[
                {"role": "system", "content": "You are an expert at converting XML table data to CSV format. You must provide both a table description and the CSV data in the specified format."},
                {"role": "user", "content": prompt}
            ],
            response_format=Table,
        )
        
        # Extract the structured response
        table_data = response.choices[0].message.parsed
        
        if not table_data or not table_data.csv:
            print("Warning: OpenAI returned empty or invalid CSV, falling back to dummy implementation")
            safe = table_xml.replace("\n", " ").replace('"', '""')
            return f'"{safe}"\n'
        
        # Log the table description for debugging/monitoring
        print(f"Table description: {table_data.table_description}")
        
        # Ensure the CSV ends with a newline
        csv_content = table_data.csv.strip()
        if not csv_content.endswith('\n'):
            csv_content += '\n'
            
        return csv_content
        
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        print("Falling back to dummy implementation")
        # Fallback to original dummy implementation on any error
        safe = table_xml.replace("\n", " ").replace('"', '""')
        print(table_xml)
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