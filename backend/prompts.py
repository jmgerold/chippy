import duckdb
import json
from .sql import add_secondary_sql_table, get_sql_types, get_sql_head
from .formats import DatasetSchema, Table

def create_xml_to_csv_prompt(table_xml_str: str) -> str:
    return f"""
    Using the OCR table (XML) provided, create column and table descriptions and return the table as a CSV format.

    Tasks:

    table_description:
    - Provide a verbose description of the table based on the XML structure.

    column_descriptions:
    - Make column names SQL compatible (use underscores for spaces, no dots, etc.)
    - Ensure each column name is unique
    - Add units to column names if present (e.g., time_hours, temp_celsius)
    - Preserve the original meaning of headers (e.g., "UTC Untreated control group (%)" → "utc_untreated_control_group_pct")
    - Avoid SQL reserved keywords (e.g., group, order, id)
    - Do not interpret or rename based on assumed purpose

    csv:
    - Transcribe each <row> as a separate CSV row, regardless of the number of <entry> tags it contains
    - Use "NA" for missing or empty values
    - Use comma as delimiter
    - Use double quotes around ALL fields (both text and numeric)
    - Preserve all text exactly as it appears in the XML, including descriptive elements like <sub></sub>
    - Do not merge or interpret any data

    Inputs:
    table XML:{table_xml_str}"""

def create_relevance_prompt(schema: DatasetSchema, new_table: Table) -> str:
    # Create schema description for primary table
    primary_schema_desc = []
    for col, col_type in zip(schema.columns, schema.types):
        primary_schema_desc.append(f"- {col} ({col_type})")
    
    primary_schema_str = "\n    ".join(primary_schema_desc)

    newline_char = '\n'
    
    return f"""
    Evaluate if the secondary table is compatible with the primary table for stacking (INSERT INTO).

    Goal: {schema.query}

    Tasks:
    1. Check compatibility:
    - Verify secondary table has columns that map to primary table columns
    - Validate data quality and types
    - Return false if incompatible

    2. If compatible, generate SQL:
    - Stack secondary_table into primary_table using INSERT INTO
    - Map column names appropriately

    Output Format:
    - is_relevant: boolean
    - sql_command: complete SQL if compatible, empty string if not

    Primary Table Schema:
        {primary_schema_str}

    Secondary Table:
    Description: {new_table.table_description}
    Columns: {[col.column_name + ": " + col.description for col in new_table.column_descriptions]}
    Data Sample: {new_table.csv.split(newline_char)[0:3]}"""