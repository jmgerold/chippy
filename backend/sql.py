import duckdb
from .formats import DatasetSchema
import sys

def get_sql_conn(schema: DatasetSchema) -> duckdb.duckdb.DuckDBPyConnection:

    conn = duckdb.connect()

    # Create column definitions from schema
    column_definitions = []
    for column_name, column_type in zip(schema.columns, schema.types):
        quoted_name = f'"{column_name}"'
        column_definitions.append(f"{quoted_name} {column_type}")    
    columns_sql = ",\n        ".join(column_definitions)
    
    create_table_sql = f"""
    CREATE TABLE primary_table (
        {columns_sql}
    );
    """
    
    conn.execute(create_table_sql)
    
    return conn

def add_secondary_sql_table(conn: duckdb.duckdb.DuckDBPyConnection, csv: str, sql_command: str = "") -> bool:

    try: 
        with open('/tmp/secondary_table.csv', 'w') as f:
            f.write(csv)

        conn.execute("DROP TABLE IF EXISTS secondary_table;")
        conn.execute("DROP TABLE IF EXISTS csv_read;")

        conn.execute("""
        CREATE TABLE csv_read AS 
        SELECT * FROM read_csv_auto('/tmp/secondary_table.csv',
            header=true,
            nullstr='NA',
            sample_size=-1,
            auto_type_candidates=['BIGINT'],
            ignore_errors=true
        );
        """)

        # filter out empty rows:

        columns = conn.execute("PRAGMA table_info(csv_read)").fetchall()
        column_names = [col[1] for col in columns]
        
        conditions = " AND ".join([f"{col} IS NULL" for col in column_names])

        conn.execute(f"""
        CREATE TABLE secondary_table AS
        SELECT * FROM csv_read WHERE NOT ({conditions});
        """)
        
        # Execute the SQL command from the relevance check if provided
        if sql_command:
            print(f"Executing SQL command: {sql_command}", file=sys.stderr)
            conn.execute(sql_command)
    
    except Exception as e:
        print(f"Error in add_secondary_sql_table: {e}", file=sys.stderr)
        return False
    
    return True

def get_sql_types(conn: duckdb.duckdb.DuckDBPyConnection) -> dict:
    
    secondary_table_metadata = conn.execute("DESCRIBE secondary_table").df()
    secondary_table_metadata = dict(zip(secondary_table_metadata['column_name'], secondary_table_metadata['column_type']))

    return secondary_table_metadata

def get_sql_head(conn: duckdb.duckdb.DuckDBPyConnection) -> str:
    # Execute a SQL query to get the first row from the secondary_table
    data_head_df = conn.execute("SELECT * FROM secondary_table LIMIT 3").df()

    # Convert the DataFrame to a JSON string
    data_head_str = data_head_df.to_json(orient='records')

    return data_head_str