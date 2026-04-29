"""
Reusable SQL query tools — all data access goes through Statement Execution SDK.
NO psycopg2.  NO direct serving-endpoint calls.
"""

import re
import time
import logging
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from config import CATALOG, SCHEMA, WAREHOUSE_ID, TABLES

logger = logging.getLogger("tools.sql")

# ── Singleton WorkspaceClient ──────────────────────────────────────────────
_ws: Optional[WorkspaceClient] = None


def _get_ws() -> WorkspaceClient:
    global _ws
    if _ws is None:
        _ws = WorkspaceClient()
    return _ws


def refresh_client() -> None:
    """Force re-creation of the WorkspaceClient (token refresh)."""
    global _ws
    _ws = None


# ── Internal helpers ───────────────────────────────────────────────────────

_TYPE_INT = {"INT", "BIGINT", "SMALLINT", "TINYINT"}
_TYPE_FLOAT = {"DECIMAL", "FLOAT", "DOUBLE"}


def _qualify_tables(sql: str) -> str:
    """Replace bare table names with fully-qualified catalog.schema.table."""
    for table in TABLES:
        fqn = f"{CATALOG}.{SCHEMA}.{table}"
        sql = re.sub(rf"\b{table}\b", fqn, sql)
    return sql


def _coerce_row(row: list, columns: list[dict]) -> list:
    """Cast string values from the SQL API to native Python types."""
    typed = []
    for i, val in enumerate(row):
        if val is None:
            typed.append(None)
            continue
        col_type = columns[i]["type_text"] if i < len(columns) else ""
        if col_type in _TYPE_INT:
            try:
                typed.append(int(val))
            except (ValueError, TypeError):
                typed.append(val)
        elif col_type in _TYPE_FLOAT:
            try:
                typed.append(float(val))
            except (ValueError, TypeError):
                typed.append(val)
        elif col_type == "BOOLEAN":
            typed.append(str(val).lower() == "true")
        else:
            typed.append(val)
    return typed


def _parse_response(response) -> tuple[list[str], list[dict], list[list]]:
    """Extract column names, column metadata, and typed rows from a statement response."""
    col_names: list[str] = []
    col_meta: list[dict] = []
    rows: list[list] = []

    if response.manifest and response.manifest.schema and response.manifest.schema.columns:
        for c in response.manifest.schema.columns:
            col_names.append(c.name)
            col_meta.append({"name": c.name, "type_text": c.type_text or ""})

    if response.result and response.result.data_array:
        for raw_row in response.result.data_array:
            rows.append(_coerce_row(raw_row, col_meta))

    return col_names, col_meta, rows


def _execute_sql(sql: str, *, timeout: str = "30s", poll_interval: float = 1.0) -> list[dict]:
    """
    Execute a SQL statement via Statement Execution SDK.
    Handles PENDING state by polling.  Returns list of dicts.
    """
    w = _get_ws()

    response = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql,
        wait_timeout=timeout,
        catalog=CATALOG,
        schema=SCHEMA,
    )

    # Poll if PENDING / RUNNING
    statement_id = response.statement_id
    for _ in range(60):  # up to ~60 seconds of polling
        state = response.status.state if response.status else None
        if state in (StatementState.SUCCEEDED, StatementState.FAILED, StatementState.CANCELED, StatementState.CLOSED):
            break
        time.sleep(poll_interval)
        response = w.statement_execution.get_statement(statement_id)

    # Check for failure
    if response.status and response.status.state == StatementState.FAILED:
        err = response.status.error.message if response.status.error else "Unknown SQL error"
        logger.error("SQL failed: %s | Query: %s", err, sql[:500])
        raise RuntimeError(f"SQL Error: {err}")

    if response.status and response.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"SQL statement did not succeed. State: {response.status.state}")

    col_names, col_meta, rows = _parse_response(response)
    return [dict(zip(col_names, row)) for row in rows]


# ── Public API ─────────────────────────────────────────────────────────────

def query_table(
    table_name: str,
    where_clause: str = "",
    columns: str = "*",
    order_by: str = "",
    limit: int = 0,
) -> list[dict]:
    """
    Query a Unity Catalog table by name.

    Args:
        table_name: Bare table name (e.g. "flight_schedule").  Will be auto-qualified.
        where_clause: Optional WHERE clause (without the keyword WHERE).
        columns: Column list — default "*".
        order_by: Optional ORDER BY clause (without the keyword).
        limit: Optional LIMIT.

    Returns:
        List of dicts (one per row).
    """
    fqn = f"{CATALOG}.{SCHEMA}.{table_name}"
    sql = f"SELECT {columns} FROM {fqn}"
    if where_clause:
        sql += f" WHERE {where_clause}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit:
        sql += f" LIMIT {limit}"

    logger.debug("query_table SQL: %s", sql)
    return _execute_sql(sql)


def query_join(sql: str) -> list[dict]:
    """
    Run an arbitrary SQL statement.  Bare table names in TABLES are auto-qualified.

    Args:
        sql: Full SQL statement.

    Returns:
        List of dicts.
    """
    qualified = _qualify_tables(sql)
    logger.debug("query_join SQL: %s", qualified)
    return _execute_sql(qualified)


def execute_raw(sql: str) -> list[dict]:
    """
    Run a raw SQL statement without any table-name qualification.
    Use this for ai_query calls or other special SQL.
    """
    return _execute_sql(sql)


def test_connectivity() -> bool:
    """Quick health check — returns True if SQL warehouse responds."""
    try:
        rows = _execute_sql("SELECT 1 AS ok")
        return len(rows) > 0 and rows[0].get("ok") == 1
    except Exception as e:
        logger.warning("Connectivity test failed: %s", e)
        return False
