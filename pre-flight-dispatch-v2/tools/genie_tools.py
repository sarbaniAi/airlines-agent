"""
Genie Space integration tools — send natural-language queries to a Genie Space
for ad-hoc analytics.  Falls back to direct SQL if Genie is unavailable.
"""

import time
import logging
from typing import Optional

from databricks.sdk import WorkspaceClient

from config import GENIE_SPACE_ID
from tools.sql_tools import query_join

logger = logging.getLogger("tools.genie")

_ws: Optional[WorkspaceClient] = None


def _get_ws() -> WorkspaceClient:
    global _ws
    if _ws is None:
        _ws = WorkspaceClient()
    return _ws


def query_genie(
    question: str,
    space_id: Optional[str] = None,
    timeout_seconds: int = 60,
) -> dict:
    """
    Send a natural-language question to a Genie Space.

    Args:
        question: Natural-language analytical question.
        space_id: Override Genie Space ID (defaults to config).
        timeout_seconds: Max seconds to wait for Genie response.

    Returns:
        dict with keys: status, query (SQL generated), result (data), description, source.
    """
    sid = space_id or GENIE_SPACE_ID

    if not sid:
        logger.info("No Genie Space configured — falling back to direct SQL")
        return _fallback_sql(question)

    try:
        w = _get_ws()

        # Start a new Genie conversation
        conversation = w.genie.start_conversation(
            space_id=sid,
            content=question,
        )

        conversation_id = conversation.conversation_id
        message_id = conversation.message_id

        # Poll for completion
        start = time.time()
        result_data = None
        generated_sql = None
        description = None

        while (time.time() - start) < timeout_seconds:
            message = w.genie.get_message(
                space_id=sid,
                conversation_id=conversation_id,
                message_id=message_id,
            )

            status = message.status if hasattr(message, "status") else None

            if status == "COMPLETED":
                # Extract results from attachments
                if hasattr(message, "attachments") and message.attachments:
                    for att in message.attachments:
                        if hasattr(att, "query") and att.query:
                            generated_sql = att.query.query if hasattr(att.query, "query") else str(att.query)
                            if hasattr(att.query, "description"):
                                description = att.query.description
                        if hasattr(att, "text") and att.text:
                            if hasattr(att.text, "content"):
                                description = description or att.text.content

                # If we have generated SQL, fetch the results
                if generated_sql:
                    try:
                        result_data = query_join(generated_sql)
                    except Exception as e:
                        logger.warning("Failed to execute Genie SQL: %s", e)
                        result_data = [{"error": str(e)}]

                return {
                    "status": "success",
                    "query": generated_sql or "",
                    "result": result_data or [],
                    "description": description or "",
                    "source": "genie",
                }

            elif status in ("FAILED", "CANCELLED"):
                error_msg = ""
                if hasattr(message, "error") and message.error:
                    error_msg = str(message.error)
                logger.warning("Genie query failed: %s", error_msg)
                return _fallback_sql(question)

            time.sleep(2)

        # Timeout
        logger.warning("Genie query timed out after %ds", timeout_seconds)
        return _fallback_sql(question)

    except Exception as e:
        logger.warning("Genie API call failed (%s) — falling back to SQL", e)
        return _fallback_sql(question)


def _fallback_sql(question: str) -> dict:
    """
    Simple fallback: try to map common questions to pre-built SQL queries.
    This covers the most common analytical questions dispatchers ask.
    """
    q = question.lower()

    sql = None
    description = "Fallback SQL query (Genie unavailable)"

    if "flight" in q and ("count" in q or "how many" in q):
        if "today" in q or "this week" in q:
            sql = """
                SELECT aircraft_reg, COUNT(*) AS flight_count
                FROM flight_schedule
                GROUP BY aircraft_reg
                ORDER BY flight_count DESC
            """
            description = "Flight count by aircraft"
        else:
            sql = "SELECT COUNT(*) AS total_flights FROM flight_schedule"
            description = "Total flights in schedule"

    elif "captain" in q or "crew" in q:
        if "qualified" in q or "qualification" in q:
            sql = """
                SELECT name, rank, route_qualifications, base_airport,
                       duty_hours_last_7d, fatigue_risk_score
                FROM crew_roster
                WHERE rank IN ('CAPTAIN', 'SENIOR_FIRST_OFFICER')
                ORDER BY fatigue_risk_score ASC
            """
            description = "Qualified captains/SFOs ordered by fatigue"
        elif "available" in q or "replace" in q:
            sql = """
                SELECT name, rank, base_airport, duty_hours_last_7d,
                       rest_hours_since_last_duty, fatigue_risk_score, medical_expiry
                FROM crew_roster
                WHERE duty_hours_last_7d < 50 AND fatigue_risk_score < 60
                ORDER BY fatigue_risk_score ASC
            """
            description = "Available crew with low duty/fatigue"
        else:
            sql = """
                SELECT name, rank, base_airport, duty_hours_last_7d,
                       fatigue_risk_score, medical_expiry
                FROM crew_roster
                ORDER BY rank, name
            """
            description = "Full crew roster"

    elif "mel" in q or "maintenance" in q:
        sql = """
            SELECT aircraft_reg, item_code, ata_chapter, description,
                   category, status, expiry_date
            FROM mel_items
            WHERE status IN ('OPEN', 'DEFERRED')
            ORDER BY category, expiry_date
        """
        description = "Open/deferred MEL items"

    elif "weather" in q:
        sql = """
            SELECT airport_code, conditions, temperature_c, visibility_km,
                   wind_speed_kts, ceiling_ft, severity
            FROM weather_conditions
            ORDER BY observation_time DESC
        """
        description = "Latest weather conditions"

    elif "certificate" in q or "cert" in q:
        sql = """
            SELECT aircraft_reg, cert_type, cert_number, status, expiry_date,
                   issuing_authority
            FROM aircraft_certificates
            ORDER BY expiry_date
        """
        description = "Aircraft certificates ordered by expiry"

    else:
        # Generic: return schedule
        sql = """
            SELECT fs.flight_id, fs.flight_number, fs.origin, fs.destination,
                   fs.aircraft_reg, fs.scheduled_departure, fs.status
            FROM flight_schedule fs
            ORDER BY fs.scheduled_departure
        """
        description = "Flight schedule (default fallback)"

    try:
        result = query_join(sql)
        return {
            "status": "success",
            "query": sql.strip(),
            "result": result,
            "description": description,
            "source": "fallback_sql",
        }
    except Exception as e:
        logger.error("Fallback SQL also failed: %s", e)
        return {
            "status": "error",
            "query": sql.strip() if sql else "",
            "result": [],
            "description": f"Query failed: {e}",
            "source": "fallback_sql",
        }
