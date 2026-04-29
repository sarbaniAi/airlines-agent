"""
Pre-Flight Dispatch Orchestrator
Dispatches all 4 sub-agents in parallel, collects results,
and uses LLM to synthesize a Go/No-Go decision.
"""

import os
import sys
import asyncio
import json
import logging
import time
from datetime import date, datetime
from typing import Any, Optional, Callable

import psycopg2
import psycopg2.extras
import mlflow

from agents import aircraft_health, crew_legality, weather_slots, regulatory_compliance

logger = logging.getLogger("agents.orchestrator")

# MLflow experiment
EXPERIMENT_NAME = "/Users/sarbani.maiti@databricks.com/air-india-pre-flight-dispatch"


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import llm_call


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_db as _get_db


def _json_serializer(obj):
    """Custom JSON serializer for dates/datetimes/decimals."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "__float__"):
        return float(obj)
    return str(obj)


def _get_flight_details(flight_id: str) -> Optional[dict]:
    """Look up flight details from the schedule."""
    try:
        conn = _get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT fs.*,
                   af.aircraft_type, af.model_variant, af.status as aircraft_status,
                   af.total_flight_hours, af.base_airport as aircraft_base,
                   c1.name as captain_name, c1.rank as captain_rank,
                   c2.name as fo_name, c2.rank as fo_rank
            FROM flight_schedule fs
            JOIN aircraft_fleet af ON fs.aircraft_reg = af.aircraft_reg
            LEFT JOIN crew_roster c1 ON fs.captain_id = c1.crew_id
            LEFT JOIN crew_roster c2 ON fs.first_officer_id = c2.crew_id
            WHERE fs.flight_id = %s
            """,
            (flight_id,),
        )
        flight = cur.fetchone()
        cur.close()
        conn.close()
        return dict(flight) if flight else None
    except Exception as e:
        logger.error(f"Error fetching flight details: {e}")
        return None


SYSTEM_PROMPT = """You are the Air India Pre-Flight Dispatch Decision Engine. You are responsible for making the final Go / No-Go / Conditional-Go decision for flight dispatch.

You will receive the results from four specialized pre-flight check agents:
1. Aircraft Health Agent — MEL deferrals, maintenance status, serviceability
2. Crew Legality Agent — DGCA duty hours, fatigue, medical, route qualifications
3. Weather & Slots Agent — Weather at origin/destination, operational minima
4. Regulatory Compliance Agent — Certificates, COAs, ETOPS, RVSM compliance

Based on all findings, you must provide:

1. **DECISION**: One of:
   - **GO** — All checks passed, flight is cleared for dispatch
   - **NO-GO** — Critical issues found, flight CANNOT be dispatched as planned
   - **CONDITIONAL** — Flight can proceed IF specific conditions are met

2. **REASONING**: Detailed explanation of your decision, referencing specific findings from each agent.

3. **ACTIONS**: Numbered list of required actions (if any) before the flight can proceed.

4. **ALTERNATIVES**: If NO-GO, suggest alternatives (aircraft swap, crew swap, route change, delay).

IMPORTANT RULES:
- Any RED status from Regulatory Compliance on a MANDATORY requirement = automatic NO-GO
- Any EXPIRED certificate for the destination = automatic NO-GO
- Crew exceeding DGCA duty limits = automatic NO-GO for that crew member (but can swap)
- Weather RED at destination with no forecast improvement = NO-GO
- Multiple AMBER across different agents = CONDITIONAL (requires mitigations)

Format your response as JSON with this structure:
{
  "decision": "GO" | "NO-GO" | "CONDITIONAL",
  "confidence": 0.0-1.0,
  "summary": "One sentence summary",
  "reasoning": "Detailed multi-paragraph reasoning",
  "actions": ["Action 1", "Action 2", ...],
  "alternatives": ["Alternative 1", ...],
  "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
}
"""


@mlflow.trace(name="dispatch_check", span_type="CHAIN")
async def run_dispatch_check(
    flight_id: str,
    progress_callback: Optional[Callable] = None,
) -> dict[str, Any]:
    """
    Run the full dispatch check orchestration.

    Args:
        flight_id: The flight ID to check
        progress_callback: Optional async callback for real-time progress updates
            Called with (agent_name, status, result)

    Returns:
        Complete dispatch decision with all agent results
    """
    start_time = time.time()
    mlflow.set_experiment(EXPERIMENT_NAME)

    # 1. Get flight details
    if progress_callback:
        await progress_callback("orchestrator", "LOADING", {"message": "Loading flight details..."})

    flight = _get_flight_details(flight_id)
    if not flight:
        return {
            "flight_id": flight_id,
            "status": "ERROR",
            "error": f"Flight {flight_id} not found in schedule",
        }

    flight_info = {
        "flight_id": flight["flight_id"],
        "flight_number": flight["flight_number"],
        "origin": flight["origin"],
        "destination": flight["destination"],
        "scheduled_departure": flight["scheduled_departure"],
        "scheduled_arrival": flight["scheduled_arrival"],
        "aircraft_reg": flight["aircraft_reg"],
        "aircraft_type": flight["aircraft_type"],
        "model_variant": flight.get("model_variant"),
        "captain_id": flight["captain_id"],
        "captain_name": flight.get("captain_name"),
        "first_officer_id": flight["first_officer_id"],
        "fo_name": flight.get("fo_name"),
        "pax_count": flight["pax_count"],
        "status": flight["status"],
    }

    if progress_callback:
        await progress_callback(
            "orchestrator",
            "DISPATCHING",
            {"message": "Dispatching sub-agents...", "flight": json.loads(json.dumps(flight_info, default=_json_serializer))},
        )

    # 2. Dispatch all 4 agents in parallel
    agent_results = {}

    async def _run_agent(name: str, coro):
        if progress_callback:
            await progress_callback(name, "RUNNING", {"message": f"{name} check in progress..."})
        try:
            with mlflow.start_span(name=name, span_type="AGENT") as span:
                result = await coro
                span.set_attributes({
                    "agent.status": result.get("status", "UNKNOWN"),
                    "agent.findings_count": len(result.get("findings", [])),
                })
                span.set_outputs(result)
            agent_results[name] = result
            if progress_callback:
                await progress_callback(name, "COMPLETE", result)
        except Exception as e:
            logger.error(f"Agent {name} failed: {e}")
            error_result = {
                "status": "RED",
                "findings": [f"Agent error: {str(e)}"],
                "recommendations": [f"Manual {name} check required"],
                "details": {},
            }
            agent_results[name] = error_result
            if progress_callback:
                await progress_callback(name, "ERROR", error_result)

    await asyncio.gather(
        _run_agent(
            "aircraft_health",
            aircraft_health.run(flight["aircraft_reg"]),
        ),
        _run_agent(
            "crew_legality",
            crew_legality.run(
                flight["captain_id"],
                flight["first_officer_id"],
                flight["destination"],
            ),
        ),
        _run_agent(
            "weather_slots",
            weather_slots.run(flight["origin"], flight["destination"]),
        ),
        _run_agent(
            "regulatory_compliance",
            regulatory_compliance.run(
                flight["aircraft_reg"],
                flight["destination"],
            ),
        ),
    )

    # 3. Synthesize with LLM
    if progress_callback:
        await progress_callback(
            "orchestrator",
            "SYNTHESIZING",
            {"message": "Synthesizing Go/No-Go decision..."},
        )

    # Build LLM prompt
    agent_summary = json.dumps(
        {
            "flight": flight_info,
            "agent_results": agent_results,
        },
        default=_json_serializer,
        indent=2,
    )

    user_prompt = f"""Analyze the following pre-flight dispatch check results and provide your Go/No-Go decision.

FLIGHT: {flight_info['flight_number']} ({flight_info['origin']} -> {flight_info['destination']})
AIRCRAFT: {flight_info['aircraft_reg']} ({flight_info['aircraft_type']})
CREW: Captain {flight_info.get('captain_name', 'N/A')}, FO {flight_info.get('fo_name', 'N/A')}
PAX: {flight_info['pax_count']}
DEPARTURE: {flight_info['scheduled_departure']}

AGENT RESULTS:
{agent_summary}

Provide your dispatch decision as JSON."""

    try:
        with mlflow.start_span(name="llm_decision", span_type="LLM") as span:
            llm_output = llm_call(SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=2000)
            span.set_inputs({"prompt_length": len(user_prompt)})
            span.set_outputs({"response": llm_output})

        # Parse LLM response
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = llm_output
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            decision = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            # Fallback: derive decision from agent statuses
            decision = _fallback_decision(agent_results, flight_info)
            decision["reasoning"] = llm_output

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        decision = _fallback_decision(agent_results, flight_info)

    # 4. Build final result
    elapsed = round(time.time() - start_time, 2)

    result = {
        "flight_id": flight_id,
        "flight_info": json.loads(json.dumps(flight_info, default=_json_serializer)),
        "agent_results": json.loads(json.dumps(agent_results, default=_json_serializer)),
        "decision": decision,
        "execution_time_seconds": elapsed,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if progress_callback:
        await progress_callback("orchestrator", "COMPLETE", {
            "decision": decision,
            "execution_time": elapsed,
        })

    return result


def _fallback_decision(agent_results: dict, flight_info: dict) -> dict:
    """Fallback decision logic when LLM is unavailable."""
    statuses = [r.get("status", "RED") for r in agent_results.values()]
    all_findings = []
    all_recs = []

    for name, r in agent_results.items():
        all_findings.extend(r.get("findings", []))
        all_recs.extend(r.get("recommendations", []))

    if "RED" in statuses:
        decision = "NO-GO"
        risk = "CRITICAL"
        confidence = 0.85
    elif statuses.count("AMBER") >= 2:
        decision = "CONDITIONAL"
        risk = "HIGH"
        confidence = 0.75
    elif "AMBER" in statuses:
        decision = "CONDITIONAL"
        risk = "MEDIUM"
        confidence = 0.80
    else:
        decision = "GO"
        risk = "LOW"
        confidence = 0.95

    return {
        "decision": decision,
        "confidence": confidence,
        "summary": f"Flight {flight_info['flight_number']} {flight_info['origin']}->{flight_info['destination']}: {decision}",
        "reasoning": (
            f"Automated analysis (LLM unavailable). Agent statuses: "
            + ", ".join(f"{k}={v.get('status')}" for k, v in agent_results.items())
            + ". Key findings: "
            + "; ".join(all_findings[:5])
        ),
        "actions": all_recs[:5],
        "alternatives": [],
        "risk_level": risk,
    }


async def chat_about_dispatch(
    flight_id: str,
    dispatch_result: dict,
    user_message: str,
) -> str:
    """
    Handle follow-up questions about a dispatch decision.

    Args:
        flight_id: The flight ID
        dispatch_result: The full dispatch result from run_dispatch_check
        user_message: The user's follow-up question

    Returns:
        LLM response as string
    """
    context = json.dumps(dispatch_result, default=_json_serializer, indent=2)

    # Enrich context with live crew data for replacement/swap questions
    crew_context = ""
    replace_keywords = ["replace", "swap", "alternate", "available", "who can", "substitute", "backup"]
    if any(kw in user_message.lower() for kw in replace_keywords):
        try:
            conn = _get_db()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            flight_info = dispatch_result.get("flight_info", {})
            dest = flight_info.get("destination", "")

            cur.execute("""
                SELECT name, rank, base_airport, duty_hours_last_7d, duty_hours_last_28d,
                       fatigue_risk_score, medical_expiry, rest_hours_since_last_duty,
                       route_qualifications
                FROM crew_roster
                WHERE rank IN ('CAPTAIN', 'SENIOR_FIRST_OFFICER', 'FIRST_OFFICER')
                ORDER BY rank, fatigue_risk_score ASC
            """)
            all_crew = cur.fetchall()
            cur.close()
            conn.close()

            today_str = date.today().isoformat()
            available = []
            for c in all_crew:
                medical_ok = c["medical_expiry"] and str(c["medical_expiry"]) > today_str
                duty_7d_ok = float(c["duty_hours_last_7d"] or 0) < 50
                duty_28d_ok = float(c["duty_hours_last_28d"] or 0) < 160
                rest_ok = float(c["rest_hours_since_last_duty"] or 0) >= 12
                fatigue_ok = float(c["fatigue_risk_score"] or 0) < 70

                quals = str(c.get("route_qualifications", "") or "")
                route_qual = dest in quals if dest else True

                status_flags = []
                if not medical_ok: status_flags.append("MEDICAL_EXPIRED")
                if not duty_7d_ok: status_flags.append("DUTY_7D_EXCEEDED")
                if not rest_ok: status_flags.append("INSUFFICIENT_REST")
                if not route_qual: status_flags.append(f"NO_{dest}_QUALIFICATION")

                available.append({
                    "name": c["name"],
                    "rank": c["rank"],
                    "base": c["base_airport"],
                    "duty_7d": float(c["duty_hours_last_7d"] or 0),
                    "duty_28d": float(c["duty_hours_last_28d"] or 0),
                    "fatigue": float(c["fatigue_risk_score"] or 0),
                    "rest_hours": float(c["rest_hours_since_last_duty"] or 0),
                    "medical_valid": medical_ok,
                    "route_qualified": route_qual,
                    "eligible": len(status_flags) == 0,
                    "issues": status_flags if status_flags else ["NONE — AVAILABLE"],
                })

            crew_context = (
                f"\n\nAVAILABLE CREW ROSTER (destination: {dest}):\n"
                + json.dumps(available, indent=2, default=_json_serializer)
            )
        except Exception as e:
            logger.warning(f"Failed to enrich crew context: {e}")

    system = (
        "You are an Air India dispatch operations assistant. You have just completed "
        "a pre-flight readiness check. The user is a dispatch coordinator or base engineer. "
        "Answer their follow-up questions about the dispatch decision, using the context provided. "
        "Be concise, precise, and reference specific findings. Use aviation terminology correctly.\n"
        "IMPORTANT: When asked about crew replacements, use the AVAILABLE CREW ROSTER data to "
        "recommend SPECIFIC crew members by name. Check their eligibility (medical, duty hours, "
        "fatigue, route qualifications). Clearly state who is available and who is not, with reasons."
    )

    try:
        user_content = f"Dispatch check context:\n{context}{crew_context}\n\nQuestion: {user_message}"
        result = llm_call(system, user_content, temperature=0.3, max_tokens=1000)
        return result if result else f"Unable to process your question at this time."
    except Exception as e:
        logger.error(f"Chat LLM call failed: {e}")
        return f"Unable to process your question at this time. Error: {str(e)}"
