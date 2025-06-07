import duckdb
import json
from .sql import add_secondary_sql_table, get_sql_types, get_sql_head

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

def create_sql_prompt(conn: duckdb.duckdb.DuckDBPyConnection, response: dict) -> str:

    try:
        response_content = json.loads(response['response']['body']['choices'][0]['message']['content'])
    except:
        return False
    
    table_description = response_content['table_description']
    column_descriptions = response_content['column_descriptions']

    if not add_secondary_sql_table(conn, response_content['csv']):
        # CSV not loaded:
        return False

    table_types = get_sql_types(conn)
    table_head = get_sql_head(conn)

    if table_types == None or table_head == None:
        return False

    return f"""
    Your goal is to produce a dataset of antisense-oligonucleotide sequences and their inhibition percentages.
    To do so you must evaluate whether two tables are compatible for stacking and if so to stack them using a SQL command.

    Required Columns in secondary_table:
    1. ASO sequence (case insensitive)
    2. One of:
       - inhibition/knockdown percentage
       -  UTC (Untreated Control) percentage
    
    Transformation Rules:
    - Numeric columns -> DOUBLE
    
    Tasks:
    1. Check compatibility:
       - Verify required columns exist
       - Validate data quality
       - Return false if validation fails
    
    2. If compatible, generate SQL:
       - Stack (INSERT INTO) secondary_table onto primary_table
       - Apply transformations as needed

    Output Format:
    - is_relevant: boolean (true/false)
    - sql_command: string containing complete SQL Command if is_relevant=true, empty string if false

    Data:
    primary_table:
    Schema:
    - aso_sequence_5_to_3 (VARCHAR): 5'-3' ASO nucleotide sequence
    - inhibition_percent (DOUBLE): target inhibition percentage, range 0-100

    secondary_table:
    Description: {table_description}
    Schema: {column_descriptions}
    Types: {table_types}
    First 3 rows: {table_head}
    """