"""
LLM calling tools — all calls go through ai_query via SQL Statement Execution SDK.
The app's service principal CANNOT call serving endpoints directly.
"""

import json
import logging

from config import LLM_MODEL
from tools.sql_tools import execute_raw

logger = logging.getLogger("tools.llm")


def _escape_sql_string(text: str) -> str:
    """Escape single quotes for safe SQL embedding."""
    return text.replace("'", "''")


def _truncate(text: str, max_chars: int = 12000) -> str:
    """Truncate long prompts to stay within ai_query limits."""
    if len(text) > max_chars:
        return text[:max_chars] + "\n...(truncated)"
    return text


def llm_call(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> str:
    """
    Call the LLM via ai_query through the SQL warehouse.

    Args:
        system_prompt: System-level instructions.
        user_prompt: The user / task prompt.
        max_tokens: Maximum response tokens (informational — ai_query has its own limits).
        temperature: Sampling temperature (informational).

    Returns:
        The LLM's text response, or empty string on failure.
    """
    combined = f"System: {system_prompt}\n\nUser: {user_prompt}"
    escaped = _escape_sql_string(_truncate(combined))

    sql = f"SELECT ai_query('{LLM_MODEL}', '{escaped}') AS response"

    try:
        rows = execute_raw(sql)
        if rows and rows[0].get("response"):
            return rows[0]["response"]
        return ""
    except Exception as e:
        logger.error("llm_call failed: %s", e)
        return ""


def llm_structured_call(
    system_prompt: str,
    user_prompt: str,
    output_schema: dict | None = None,
    max_tokens: int = 2000,
) -> dict:
    """
    Call the LLM and parse the response as structured JSON.

    If ai_query's modelParameters are not available, we embed the schema
    request in the prompt and parse the JSON from the response.

    Args:
        system_prompt: System-level instructions.
        user_prompt: The user / task prompt.
        output_schema: Optional JSON schema dict describing expected output.
        max_tokens: Maximum tokens.

    Returns:
        Parsed dict, or {"error": "..."} on failure.
    """
    schema_instruction = ""
    if output_schema:
        schema_instruction = (
            "\n\nIMPORTANT: Respond ONLY with valid JSON matching this schema "
            "(no markdown, no extra text):\n"
            + json.dumps(output_schema, indent=2)
        )

    full_system = system_prompt + schema_instruction

    raw = llm_call(full_system, user_prompt, max_tokens=max_tokens, temperature=0.1)

    if not raw:
        return {"error": "Empty LLM response"}

    # Try to extract JSON from the response
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Handle markdown-wrapped JSON
    for delimiter in ("```json", "```"):
        if delimiter in raw:
            try:
                json_str = raw.split(delimiter)[1].split("```")[0]
                return json.loads(json_str.strip())
            except (json.JSONDecodeError, IndexError):
                continue

    logger.warning("Could not parse structured response — returning raw text under 'raw' key")
    return {"raw": raw}
