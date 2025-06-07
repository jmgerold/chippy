"""Utility helpers – everything heavy (LLM calls, real XML parsing, smart CSV
merging) is stubbed so the app runs instantly out-of-the-box."""
from __future__ import annotations

import os
import random
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
            pass # check if the text contains the query - disabled for testing on 1 file!
        
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
#  LLM Calls
# ---------------------------------------------------------------------------#

def is_table_relevant(table: Table, schema: DatasetSchema) -> tuple[bool, str]:
    """Check if the table is relevant to the requested columns."""

    prompt = create_relevance_prompt(schema, table)

    print("PROMPT: ", prompt)

    response = client.beta.chat.completions.parse(
        model="gpt-4.1",
        messages=[
            {"role": "user", "content": prompt}
        ],
        response_format=SQL,
    ).choices[0].message.parsed

    return response.is_relevant, response.sql_command

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
            model="gpt-4.1-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format=Table,
            temperature=0.0,
        )
        
        # Extract the structured response
        structured_table = response.choices[0].message.parsed
        
        if not structured_table or not structured_table.csv:
            print("Warning: OpenAI returned empty or invalid CSV, falling back to dummy implementation")
            safe = table_xml.replace("\n", " ").replace('"', '""')
            return f'"{safe}"\n'
        
        # Log the table description for debugging/monitoring
        print(f"Table description: {structured_table.table_description}")
        
        # test if the csv is valid
        try:
            df = pd.read_csv(StringIO(structured_table.csv))
            if df.empty:
                print("CSV is empty")
                return False
        except Exception as e:
            print(f"Invalid CSV format: {e}")
            return False
        
        structured_table.csv = fix_cell_overflow(structured_table.csv)
            
        return structured_table
        
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        print("Falling back to dummy implementation")
        # Fallback to original dummy implementation on any error
        safe = table_xml.replace("\n", " ").replace('"', '""')
        print(table_xml)
        return f'"{safe}"\n'
    

# ---------------------------------------------------------------------------#
#  This code prevents text overflowing to the next line in cells
# ---------------------------------------------------------------------------#

def fix_cell_overflow(csv: str) -> str:

    df = pd.read_csv(StringIO(csv))

    new_df = pd.DataFrame()
    for idx, row in df.iterrows():
        num_not_na = row.notna().sum()
        if num_not_na == 0:
            continue
        elif num_not_na == 1 or num_not_na == 2:
            # check if the non-NA values are strings, not numeric:
            # if so, concatenate the values to the previous row.
            if len(new_df) > 0:  # Make sure there's a previous row
                # Find the columns with non-NA values
                non_na_cols = row.dropna().index
                all_strings = all(isinstance(row[col], str) for col in non_na_cols)
                
                if all_strings:
                    # Concatenate each string value to the corresponding column in the previous row
                    for col in non_na_cols:
                        new_df.loc[new_df.index[-1], col] += row[col]
        else:
            new_df = pd.concat([new_df, pd.DataFrame(row).T])
    return new_df.to_csv(index=False, na_rep='NA', quoting=1)