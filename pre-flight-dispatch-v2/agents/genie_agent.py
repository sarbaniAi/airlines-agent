"""
Genie Analytics Agent (V2)
Handles ad-hoc analytical questions by routing to Genie Space or fallback SQL.
Used by the supervisor when additional investigation is needed.
"""

import logging
from typing import Any

from tools.genie_tools import query_genie
from tools.llm_tools import llm_call

logger = logging.getLogger("agents.genie_agent")


def run(question: str, context: str = "") -> dict[str, Any]:
    """
    Run an ad-hoc analytical query via the Genie Space.

    Args:
        question: Natural-language analytical question from the supervisor.
        context: Optional context from the dispatch check (e.g., aircraft_reg, crew_ids).

    Returns:
        dict with keys: status, query, result, details
    """
    try:
        # Enhance the question with context if provided
        full_question = question
        if context:
            full_question = f"{question} (Context: {context})"

        genie_result = query_genie(full_question)

        genie_status = genie_result.get("status", "error")
        result_data = genie_result.get("result", [])
        generated_sql = genie_result.get("query", "")
        source = genie_result.get("source", "unknown")

        # If we got results, use LLM to summarize them
        summary = ""
        if result_data and len(result_data) > 0:
            # Truncate large result sets for LLM context
            display_data = result_data[:20]
            data_str = str(display_data)
            if len(data_str) > 3000:
                data_str = data_str[:3000] + "...(truncated)"

            summary = llm_call(
                system_prompt=(
                    "You are an airline operations analyst. Summarize the query results "
                    "in 2-3 concise sentences relevant to dispatch operations. "
                    "Highlight key numbers and any concerns."
                ),
                user_prompt=(
                    f"Question: {question}\n"
                    f"SQL: {generated_sql}\n"
                    f"Results ({len(result_data)} rows):\n{data_str}\n\n"
                    f"Provide a brief operational summary."
                ),
                max_tokens=300,
            )

        return {
            "status": "GREEN" if genie_status == "success" else "AMBER",
            "query": generated_sql,
            "result": result_data[:50],  # Cap at 50 rows
            "details": {
                "question": question,
                "source": source,
                "row_count": len(result_data),
                "summary": summary,
                "description": genie_result.get("description", ""),
            },
        }

    except Exception as e:
        logger.error("Genie analytics agent error: %s", e, exc_info=True)
        return {
            "status": "AMBER",
            "query": "",
            "result": [],
            "details": {
                "question": question,
                "error": str(e),
                "summary": f"Analytics query failed: {str(e)}",
            },
        }
