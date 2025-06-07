from pydantic import BaseModel, Field
from typing import Literal, List

class ColumnDescription(BaseModel):
    column_name: str
    description: str

class Table(BaseModel):
    table_description: str
    column_descriptions: list[ColumnDescription]
    csv: str

class SQL(BaseModel):
    is_relevant: bool
    sql_command: str

class DatasetSchema(BaseModel):
    query: str = Field(...)
    columns: List[str] = Field(...)
    types: List[Literal["NUMERIC", "TEXT"]] = Field(...)