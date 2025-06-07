"""Utility helpers – everything heavy (LLM calls, real XML parsing, smart CSV
merging) is stubbed so the app runs instantly out-of-the-box."""
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import List
from xml.etree import ElementTree as ET
from dotenv import load_dotenv
from openai import OpenAI

import gzip

from .prompts import create_xml_to_csv_prompt
from .formats import Table

load_dotenv()

XML_DIR = Path(os.getenv("XML_STORE_DIR", "/app/patents"))

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------------------------------------------------------#
#  XML search helpers
# ---------------------------------------------------------------------------#
def _iter_xml_files(limit: int | None = None):
    """Yield Path objects for .xml files in the store (depth-1)."""
    for i, path in enumerate(sorted(XML_DIR.glob("*.xml.gz"))):
        if limit and i >= limit:
            break
        yield path

def search_patent_files(query: str, limit: int = 3) -> List[Path]:
    """Return the first *limit* patent files whose raw text contains *query*."""
    query = query.lower()
    matches: list[Path] = []
    for path in _iter_xml_files():
        try:
            with gzip.open(path, 'rt', encoding='utf-8', errors='ignore') as f:
                text = f.read().lower()
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
#  Dummy conversions
# ---------------------------------------------------------------------------#

def is_table_relevant(csv: str, requested_columns: list[str]) -> bool:
    """Check if the table is relevant to the requested columns."""
    return True, "SELECT * FROM table"


def xml_table_to_csv(table_xml: str) -> str:
    """Convert XML table to CSV using OpenAI API.
    
    Args:
        table_xml: Raw XML string containing table data
        
    Returns:
        CSV formatted string
    """
    try:        
        # Create prompt for OpenAI
        prompt = create_xml_to_csv_prompt(table_xml)
        
        # Call OpenAI API with structured outputs
        response = client.beta.chat.completions.parse(
            model="gpt-4.1-mini",  # Using the more cost-effective model
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