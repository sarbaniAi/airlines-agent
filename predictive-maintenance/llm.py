"""
Shared LLM helper — calls FM API via ai_query through SQL Statement Execution.
"""
import os
import logging
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

logger = logging.getLogger("llm")

WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "148ccb90800933a1")
MODEL = "databricks-meta-llama-3-3-70b-instruct"

_ws = None

def _get_ws():
    global _ws
    if _ws is None:
        _ws = WorkspaceClient()
    return _ws


def llm_call(system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 2000) -> str:
    """Call LLM via ai_query SQL function."""
    w = _get_ws()

    # Build combined prompt and escape for SQL
    combined = f"System: {system_prompt}\n\nUser: {user_prompt}"
    escaped = combined.replace("'", "''")

    # Truncate if too long (ai_query has limits)
    if len(escaped) > 12000:
        escaped = escaped[:12000] + "...(truncated)"

    sql = f"SELECT ai_query('{MODEL}', '{escaped}') as response"

    try:
        response = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID,
            statement=sql,
            wait_timeout="50s",
        )

        if response.status and response.status.state == StatementState.FAILED:
            err = response.status.error.message if response.status.error else "Unknown"
            logger.error(f"ai_query failed: {err}")
            return ""

        if response.result and response.result.data_array:
            return response.result.data_array[0][0] or ""

        return ""
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return ""
