"""
LangGraph Supervisor Orchestrator for Pre-Flight Dispatch V2.

Graph topology:
  START -> load_flight -> [parallel: aircraft_health, crew_legality,
                           weather_notam, regulatory_compliance]
        -> route_after_checks -> (genie_investigation | synthesize_decision)
        -> END
"""

import asyncio
import json
import logging
import time
from datetime import date, datetime
from typing import Any, Optional, Callable

import mlflow

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False
    logger = logging.getLogger("orchestrator.supervisor")
    logger.warning("langgraph not available — using sequential fallback orchestration")

from config import MLFLOW_EXPERIMENT
from orchestrator.state import DispatchState
from orchestrator.router import route_after_checks
from agents import aircraft_health, crew_legality, weather_notam, regulatory_compliance, genie_agent
from tools.sql_tools import query_join
from tools.llm_tools import llm_call

logger = logging.getLogger("orchestrator.supervisor")


def _json_serial(obj):
    """JSON serializer for dates / decimals."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "__float__"):
        return float(obj)
    return str(obj)


def _safe_json(obj) -> Any:
    """Round-trip through JSON to ensure serializability."""
    return json.loads(json.dumps(obj, default=_json_serial))


# ── Decision system prompt ─────────────────────────────────────────────────

DECISION_SYSTEM_PROMPT = """You are the Air India Pre-Flight Dispatch Decision Engine. You are responsible for making the final Go/No-Go/Conditional-Go decision for flight dispatch.

You receive results from specialized pre-flight check agents:
1. Aircraft Health Agent - MEL deferrals, maintenance status, airworthiness directives
2. Crew Legality Agent - DGCA duty hours, fatigue, medical, route qualifications
3. Weather & NOTAM Agent - Weather at origin/destination, operational minima, SOPs
4. Regulatory Compliance Agent - Certificates, COAs, ETOPS, RVSM compliance

Based on all findings, provide:

1. **DECISION**: GO | NO-GO | CONDITIONAL
2. **REASONING**: Detailed explanation referencing specific findings
3. **ACTIONS**: Required actions before the flight can proceed
4. **ALTERNATIVES**: If NO-GO, suggest alternatives (aircraft swap, crew swap, delay)

RULES:
- Any RED from Regulatory Compliance on a MANDATORY requirement = automatic NO-GO
- Any EXPIRED certificate for the destination = automatic NO-GO
- Crew exceeding DGCA duty limits = automatic NO-GO for that crew (but can swap)
- Weather RED at destination with no forecast improvement = NO-GO
- Multiple AMBER across different agents = CONDITIONAL (requires mitigations)

Respond ONLY with valid JSON:
{
  "decision": "GO" | "NO-GO" | "CONDITIONAL",
  "confidence": 0.0-1.0,
  "summary": "One sentence summary",
  "reasoning": "Detailed multi-paragraph reasoning",
  "actions": ["Action 1", "Action 2"],
  "alternatives": ["Alternative 1"],
  "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
}"""


# ═══════════════════════════════════════════════════════════════════════════
# Graph node functions
# ═══════════════════════════════════════════════════════════════════════════

def _load_flight_node(state: DispatchState) -> dict:
    """Load flight details from Unity Catalog."""
    flight_id = state["flight_id"]

    rows = query_join(f"""
        SELECT fs.*,
               af.aircraft_type, af.model_variant, af.status AS aircraft_status,
               af.total_flight_hours, af.base_airport AS aircraft_base,
               c1.name AS captain_name, c1.rank AS captain_rank,
               c2.name AS fo_name, c2.rank AS fo_rank
        FROM flight_schedule fs
        JOIN aircraft_fleet af ON fs.aircraft_reg = af.aircraft_reg
        LEFT JOIN crew_roster c1 ON fs.captain_id = c1.crew_id
        LEFT JOIN crew_roster c2 ON fs.first_officer_id = c2.crew_id
        WHERE fs.flight_id = '{flight_id}'
    """)

    if not rows:
        return {
            "flight_info": {},
            "messages": state.get("messages", []) + [
                {"role": "system", "content": f"Flight {flight_id} not found"}
            ],
            "current_agent": "load_flight",
        }

    flight = rows[0]
    flight_info = _safe_json(flight)

    return {
        "flight_info": flight_info,
        "messages": state.get("messages", []) + [
            {"role": "system", "content": f"Loaded flight {flight_id}: {flight.get('flight_number', '')} {flight.get('origin', '')} -> {flight.get('destination', '')}"}
        ],
        "current_agent": "load_flight",
    }


def _aircraft_health_node(state: DispatchState) -> dict:
    """Run the Aircraft Health agent."""
    flight_info = state.get("flight_info", {})
    aircraft_reg = flight_info.get("aircraft_reg", "")

    if not aircraft_reg:
        return {
            "aircraft_health": {
                "status": "RED",
                "findings": ["No aircraft registration in flight info"],
                "recommendations": ["Verify flight data"],
                "applicable_ads": [],
                "details": {},
            },
            "current_agent": "aircraft_health",
        }

    with mlflow.start_span(name="aircraft_health_agent", span_type="AGENT") as span:
        result = aircraft_health.run(aircraft_reg)
        span.set_attributes({
            "agent.status": result.get("status", "UNKNOWN"),
            "agent.findings_count": len(result.get("findings", [])),
        })
        span.set_outputs({"status": result.get("status")})

    return {
        "aircraft_health": _safe_json(result),
        "current_agent": "aircraft_health",
        "messages": state.get("messages", []) + [
            {"role": "agent", "content": f"Aircraft Health: {result.get('status', 'UNKNOWN')}"}
        ],
    }


def _crew_legality_node(state: DispatchState) -> dict:
    """Run the Crew Legality agent."""
    flight_info = state.get("flight_info", {})
    captain_id = flight_info.get("captain_id", "")
    fo_id = flight_info.get("first_officer_id", "")
    destination = flight_info.get("destination", "")

    if not captain_id or not fo_id:
        return {
            "crew_legality": {
                "status": "RED",
                "findings": ["Missing crew assignment in flight info"],
                "recommendations": ["Verify crew assignment"],
                "regulatory_references": [],
                "details": {},
            },
            "current_agent": "crew_legality",
        }

    with mlflow.start_span(name="crew_legality_agent", span_type="AGENT") as span:
        result = crew_legality.run(captain_id, fo_id, destination)
        span.set_attributes({
            "agent.status": result.get("status", "UNKNOWN"),
            "agent.findings_count": len(result.get("findings", [])),
        })
        span.set_outputs({"status": result.get("status")})

    return {
        "crew_legality": _safe_json(result),
        "current_agent": "crew_legality",
        "messages": state.get("messages", []) + [
            {"role": "agent", "content": f"Crew Legality: {result.get('status', 'UNKNOWN')}"}
        ],
    }


def _weather_notam_node(state: DispatchState) -> dict:
    """Run the Weather & NOTAM agent."""
    flight_info = state.get("flight_info", {})
    origin = flight_info.get("origin", "")
    destination = flight_info.get("destination", "")

    if not origin or not destination:
        return {
            "weather_notam": {
                "status": "RED",
                "findings": ["Missing origin/destination in flight info"],
                "recommendations": ["Verify flight data"],
                "sop_references": [],
                "details": {},
            },
            "current_agent": "weather_notam",
        }

    with mlflow.start_span(name="weather_notam_agent", span_type="AGENT") as span:
        result = weather_notam.run(origin, destination)
        span.set_attributes({
            "agent.status": result.get("status", "UNKNOWN"),
            "agent.findings_count": len(result.get("findings", [])),
        })
        span.set_outputs({"status": result.get("status")})

    return {
        "weather_notam": _safe_json(result),
        "current_agent": "weather_notam",
        "messages": state.get("messages", []) + [
            {"role": "agent", "content": f"Weather & NOTAM: {result.get('status', 'UNKNOWN')}"}
        ],
    }


def _regulatory_compliance_node(state: DispatchState) -> dict:
    """Run the Regulatory Compliance agent."""
    flight_info = state.get("flight_info", {})
    aircraft_reg = flight_info.get("aircraft_reg", "")
    destination = flight_info.get("destination", "")

    if not aircraft_reg or not destination:
        return {
            "regulatory_compliance": {
                "status": "RED",
                "findings": ["Missing aircraft/destination in flight info"],
                "recommendations": ["Verify flight data"],
                "compliance_gaps": [],
                "regulatory_references": [],
                "details": {},
            },
            "current_agent": "regulatory_compliance",
        }

    with mlflow.start_span(name="regulatory_compliance_agent", span_type="AGENT") as span:
        result = regulatory_compliance.run(aircraft_reg, destination)
        span.set_attributes({
            "agent.status": result.get("status", "UNKNOWN"),
            "agent.findings_count": len(result.get("findings", [])),
        })
        span.set_outputs({"status": result.get("status")})

    return {
        "regulatory_compliance": _safe_json(result),
        "current_agent": "regulatory_compliance",
        "messages": state.get("messages", []) + [
            {"role": "agent", "content": f"Regulatory Compliance: {result.get('status', 'UNKNOWN')}"}
        ],
    }


def _genie_investigation_node(state: DispatchState) -> dict:
    """
    Run Genie analytics for additional investigation.
    This node is triggered conditionally when the supervisor needs more data.
    """
    flight_info = state.get("flight_info", {})
    aircraft_reg = flight_info.get("aircraft_reg", "")
    destination = flight_info.get("destination", "")

    # Build investigation questions based on AMBER results
    questions = []

    ah = state.get("aircraft_health", {})
    if ah.get("status") == "AMBER":
        questions.append(
            f"How many flights has aircraft {aircraft_reg} operated in the last 7 days "
            f"and what is its maintenance history?"
        )

    cl = state.get("crew_legality", {})
    if cl.get("status") == "AMBER":
        questions.append(
            f"Which captains and first officers are qualified for {destination} route "
            f"with low fatigue scores and available for replacement?"
        )

    wn = state.get("weather_notam", {})
    if wn.get("status") == "AMBER":
        questions.append(
            f"What are the latest weather conditions at {destination} "
            f"and are there any active NOTAMs?"
        )

    if not questions:
        questions.append(
            f"Show operational summary for flight to {destination} "
            f"on aircraft {aircraft_reg}"
        )

    # Run the first (most relevant) question
    question = questions[0]
    context = f"aircraft_reg={aircraft_reg}, destination={destination}"

    with mlflow.start_span(name="genie_investigation", span_type="AGENT") as span:
        result = genie_agent.run(question, context=context)
        span.set_attributes({"question": question})
        span.set_outputs({"status": result.get("status")})

    return {
        "genie_analytics": _safe_json(result),
        "current_agent": "genie_investigation",
        "retry_count": state.get("retry_count", 0) + 1,
        "messages": state.get("messages", []) + [
            {"role": "agent", "content": f"Genie Analytics: {result.get('details', {}).get('summary', 'Query complete')}"}
        ],
    }


def _synthesize_decision_node(state: DispatchState) -> dict:
    """Synthesize the final Go/No-Go decision using LLM."""
    flight_info = state.get("flight_info", {})

    agent_results = {
        "aircraft_health": state.get("aircraft_health", {}),
        "crew_legality": state.get("crew_legality", {}),
        "weather_notam": state.get("weather_notam", {}),
        "regulatory_compliance": state.get("regulatory_compliance", {}),
    }

    # Include genie analytics if available
    genie = state.get("genie_analytics")
    if genie:
        agent_results["genie_analytics"] = genie

    agent_summary = json.dumps(
        {"flight": flight_info, "agent_results": agent_results},
        default=_json_serial,
        indent=2,
    )

    user_prompt = f"""Analyze the following pre-flight dispatch check results and provide your Go/No-Go decision.

FLIGHT: {flight_info.get('flight_number', 'N/A')} ({flight_info.get('origin', '?')} -> {flight_info.get('destination', '?')})
AIRCRAFT: {flight_info.get('aircraft_reg', 'N/A')} ({flight_info.get('aircraft_type', 'N/A')})
CREW: Captain {flight_info.get('captain_name', 'N/A')}, FO {flight_info.get('fo_name', 'N/A')}
PAX: {flight_info.get('pax_count', 'N/A')}
DEPARTURE: {flight_info.get('scheduled_departure', 'N/A')}

AGENT RESULTS:
{agent_summary}

Provide your dispatch decision as JSON."""

    with mlflow.start_span(name="llm_decision", span_type="LLM") as span:
        span.set_inputs({"prompt_length": len(user_prompt)})
        llm_output = llm_call(DECISION_SYSTEM_PROMPT, user_prompt, max_tokens=2000, temperature=0.1)
        span.set_outputs({"response_length": len(llm_output)})

    # Parse LLM response
    decision = _parse_decision(llm_output, agent_results, flight_info)

    return {
        "decision": decision,
        "current_agent": "synthesize_decision",
        "messages": state.get("messages", []) + [
            {"role": "system", "content": f"Decision: {decision.get('decision', 'UNKNOWN')}"}
        ],
    }


def _parse_decision(llm_output: str, agent_results: dict, flight_info: dict) -> dict:
    """Parse LLM output into a decision dict, with fallback logic."""
    if llm_output:
        # Try direct JSON parse
        try:
            return json.loads(llm_output.strip())
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code blocks
        for delimiter in ("```json", "```"):
            if delimiter in llm_output:
                try:
                    json_str = llm_output.split(delimiter)[1].split("```")[0]
                    return json.loads(json_str.strip())
                except (json.JSONDecodeError, IndexError):
                    continue

    # Fallback: derive decision from agent statuses
    return _fallback_decision(agent_results, flight_info, llm_output)


def _fallback_decision(agent_results: dict, flight_info: dict, llm_text: str = "") -> dict:
    """Deterministic fallback when LLM parsing fails."""
    statuses = [r.get("status", "RED") for r in agent_results.values() if r]
    all_findings = []
    all_recs = []

    for name, r in agent_results.items():
        if r:
            all_findings.extend(r.get("findings", []))
            all_recs.extend(r.get("recommendations", []))

    if "RED" in statuses:
        decision_val = "NO-GO"
        risk = "CRITICAL"
        confidence = 0.85
    elif statuses.count("AMBER") >= 2:
        decision_val = "CONDITIONAL"
        risk = "HIGH"
        confidence = 0.75
    elif "AMBER" in statuses:
        decision_val = "CONDITIONAL"
        risk = "MEDIUM"
        confidence = 0.80
    else:
        decision_val = "GO"
        risk = "LOW"
        confidence = 0.95

    fn = flight_info.get("flight_number", "?")
    orig = flight_info.get("origin", "?")
    dest = flight_info.get("destination", "?")

    return {
        "decision": decision_val,
        "confidence": confidence,
        "summary": f"Flight {fn} {orig}->{dest}: {decision_val}",
        "reasoning": (
            f"Automated analysis. Agent statuses: "
            + ", ".join(f"{k}={v.get('status', '?')}" for k, v in agent_results.items() if v)
            + ". " + (llm_text[:500] if llm_text else "")
        ),
        "actions": all_recs[:5],
        "alternatives": [],
        "risk_level": risk,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Build the LangGraph
# ═══════════════════════════════════════════════════════════════════════════

def build_dispatch_graph() -> StateGraph:
    """Construct and compile the LangGraph dispatch pipeline."""

    graph = StateGraph(DispatchState)

    # ── Add nodes ──────────────────────────────────────────────────────────
    graph.add_node("load_flight", _load_flight_node)
    graph.add_node("aircraft_health", _aircraft_health_node)
    graph.add_node("crew_legality", _crew_legality_node)
    graph.add_node("weather_notam", _weather_notam_node)
    graph.add_node("regulatory_compliance", _regulatory_compliance_node)
    graph.add_node("genie_investigation", _genie_investigation_node)
    graph.add_node("synthesize_decision", _synthesize_decision_node)

    # ── Edges ──────────────────────────────────────────────────────────────
    # START -> load_flight
    graph.set_entry_point("load_flight")

    # load_flight -> fan-out to all 4 parallel agents
    graph.add_edge("load_flight", "aircraft_health")
    graph.add_edge("load_flight", "crew_legality")
    graph.add_edge("load_flight", "weather_notam")
    graph.add_edge("load_flight", "regulatory_compliance")

    # All 4 agents -> merge_and_route (conditional)
    # LangGraph will wait for all parallel branches before the conditional edge
    graph.add_conditional_edges(
        "aircraft_health",
        lambda s: "wait",
        {"wait": "synthesize_decision"},
    )
    graph.add_conditional_edges(
        "crew_legality",
        lambda s: "wait",
        {"wait": "synthesize_decision"},
    )
    graph.add_conditional_edges(
        "weather_notam",
        lambda s: "wait",
        {"wait": "synthesize_decision"},
    )
    graph.add_conditional_edges(
        "regulatory_compliance",
        route_after_checks,
        {
            "synthesize_decision": "synthesize_decision",
            "genie_investigation": "genie_investigation",
        },
    )

    # genie_investigation -> synthesize_decision
    graph.add_edge("genie_investigation", "synthesize_decision")

    # synthesize_decision -> END
    graph.add_edge("synthesize_decision", END)

    return graph


# Module-level compiled graph
_compiled_graph = None


def _get_graph():
    """Return None to use sequential fallback (LangGraph parallel fan-out has state conflict issues)."""
    # Using sequential fallback for reliable execution
    # LangGraph parallel fan-out requires Annotated state keys for concurrent writes
    return None


def _run_sequential_fallback(initial_state: dict) -> dict:
    """Sequential execution fallback — merges partial state from each node."""
    state = dict(initial_state)

    def _merge(partial):
        for k, v in partial.items():
            if k == "messages" and isinstance(v, list):
                state.setdefault("messages", []).extend(v)
            else:
                state[k] = v

    _merge(_load_flight_node(state))
    if not state.get("flight_info"):
        return state

    # Run agents sequentially, merging results
    _merge(_aircraft_health_node(state))
    _merge(_crew_legality_node(state))
    _merge(_weather_notam_node(state))
    _merge(_regulatory_compliance_node(state))

    # Check if escalation needed
    route = route_after_checks(state)
    if route == "genie_investigation":
        _merge(_genie_investigation_node(state))

    # Synthesize decision
    _merge(_synthesize_decision_node(state))
    return state


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

async def run_dispatch_check(
    flight_id: str,
    progress_callback: Optional[Callable] = None,
) -> dict[str, Any]:
    """
    Run the full dispatch pipeline for a flight with MLflow tracing.
    """
    start_time = time.time()

    try:
        # Ensure tracking URI points to workspace MLflow
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        mlflow.set_tracking_uri("databricks")
        mlflow.set_registry_uri("databricks-uc")
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        logger.info("MLflow experiment set: %s", MLFLOW_EXPERIMENT)
    except Exception as e:
        logger.warning("MLflow experiment setup failed: %s", e)

    initial_state: DispatchState = {
        "flight_id": flight_id,
        "flight_info": {},
        "aircraft_health": None,
        "crew_legality": None,
        "weather_notam": None,
        "regulatory_compliance": None,
        "genie_analytics": None,
        "decision": None,
        "messages": [],
        "current_agent": "",
        "retry_count": 0,
    }

    if progress_callback:
        await progress_callback("orchestrator", "STARTING", {"message": "Starting dispatch check..."})

    # Run the pipeline with MLflow tracing
    graph = _get_graph()
    mlflow_run_id = None

    import functools
    loop = asyncio.get_event_loop()

    def _traced_run(state):
        """Run the pipeline inside an MLflow run for full tracing."""
        nonlocal mlflow_run_id
        try:
            with mlflow.start_run(run_name=f"dispatch-{flight_id}-{time.strftime('%H%M%S')}") as run:
                mlflow_run_id = run.info.run_id
                mlflow.log_param("flight_id", flight_id)
                mlflow.log_param("model", "gpt-oss-120b")
                mlflow.log_param("orchestration", "sequential_fallback")

                result = _run_sequential_fallback(state)

                # Log metrics
                dec = result.get("decision", {})
                if isinstance(dec, dict):
                    mlflow.log_param("decision", dec.get("decision", "UNKNOWN"))
                    mlflow.log_metric("confidence", float(dec.get("confidence", 0)))
                    mlflow.log_metric("execution_time", time.time() - start_time)

                    # Log per-agent status
                    for agent_key in ["aircraft_health", "crew_legality", "weather_notam", "regulatory_compliance"]:
                        agent_result = result.get(agent_key, {})
                        if isinstance(agent_result, dict):
                            status_val = {"GREEN": 0, "AMBER": 1, "RED": 2}.get(agent_result.get("status", ""), -1)
                            mlflow.log_metric(f"{agent_key}_status", status_val)
                            mlflow.log_metric(f"{agent_key}_findings", len(agent_result.get("findings", [])))

                return result
        except Exception as e:
            logger.warning("MLflow tracing failed (pipeline still runs): %s", e)
            return _run_sequential_fallback(state)

    final_state = await loop.run_in_executor(
        None,
        functools.partial(_traced_run, initial_state),
    )

    elapsed = round(time.time() - start_time, 2)

    # Build result
    result = {
        "flight_id": flight_id,
        "flight_info": _safe_json(final_state.get("flight_info", {})),
        "agent_results": {
            "aircraft_health": _safe_json(final_state.get("aircraft_health", {})),
            "crew_legality": _safe_json(final_state.get("crew_legality", {})),
            "weather_notam": _safe_json(final_state.get("weather_notam", {})),
            "regulatory_compliance": _safe_json(final_state.get("regulatory_compliance", {})),
        },
        "genie_analytics": _safe_json(final_state.get("genie_analytics")) if final_state.get("genie_analytics") else None,
        "decision": final_state.get("decision", {}),
        "mlflow_run_id": mlflow_run_id,
        "execution_time_seconds": elapsed,
        "timestamp": datetime.utcnow().isoformat(),
        "messages": final_state.get("messages", []),
    }

    if progress_callback:
        await progress_callback("orchestrator", "COMPLETE", {
            "decision": result.get("decision", {}),
            "execution_time": elapsed,
        })

    return result


async def chat_about_dispatch(
    flight_id: str,
    dispatch_result: dict,
    user_message: str,
) -> str:
    """
    Handle follow-up questions about a dispatch decision.
    Enriches context with live crew data when replacement questions are detected.
    """
    # Build a compact context (not the full JSON — too large for ai_query)
    flight_info = dispatch_result.get("flight_info", {})
    decision = dispatch_result.get("decision", {})
    compact_context = (
        f"Flight: {flight_info.get('flight_number','?')} {flight_info.get('origin','?')}->{flight_info.get('destination','?')} "
        f"Aircraft: {flight_info.get('aircraft_reg','?')} Captain: {flight_info.get('captain_name','?')} FO: {flight_info.get('fo_name','?')}\n"
        f"Decision: {decision.get('decision','?')} | Risk: {decision.get('risk_level','?')}\n"
        f"Summary: {decision.get('summary','')}\n"
        f"Actions: {'; '.join(decision.get('actions',[]))}\n"
    )
    # Add agent findings compactly
    for agent_name, agent_result in dispatch_result.get("agent_results", {}).items():
        if isinstance(agent_result, dict):
            findings = agent_result.get("findings", [])
            compact_context += f"\n{agent_name}: {agent_result.get('status','?')} — {'; '.join(str(f)[:100] for f in findings[:3])}"

    # Enrich with crew data for replacement/swap questions
    crew_context = ""
    replace_keywords = ["replace", "swap", "alternate", "available", "who can", "substitute", "backup", "kapoor", "sharma", "crew"]
    is_crew_question = any(kw in user_message.lower() for kw in replace_keywords)

    if is_crew_question:
        try:
            dest = flight_info.get("destination", "")
            all_crew = query_join("""
                SELECT name, rank, base_airport, duty_hours_last_7d, duty_hours_last_28d,
                       fatigue_risk_score, medical_expiry, rest_hours_since_last_duty,
                       route_qualifications
                FROM crew_roster
                WHERE rank IN ('CAPTAIN', 'SENIOR_FIRST_OFFICER', 'FIRST_OFFICER')
                ORDER BY rank, fatigue_risk_score ASC
            """)

            today_str = date.today().isoformat()
            eligible_list = []
            ineligible_list = []
            for c in all_crew:
                name = c.get("name", "?")
                rank = c.get("rank", "?")
                medical_ok = c.get("medical_expiry") and str(c["medical_expiry"]) > today_str
                duty_7d = float(c.get("duty_hours_last_7d", 0) or 0)
                duty_ok = duty_7d < 50
                rest_hrs = float(c.get("rest_hours_since_last_duty", 0) or 0)
                rest_ok = rest_hrs >= 14  # international rest requirement
                fatigue = float(c.get("fatigue_risk_score", 0) or 0)

                quals = str(c.get("route_qualifications", "") or "")
                # Check for destination region qualification
                required_quals = {"YYZ": "NAM", "YVR": "NAM", "JFK": "NAM", "SFO": "NAM",
                                  "LHR": "EUR", "CDG": "EUR", "FRA": "EUR",
                                  "BOM": "DOM", "DEL": "DOM", "BLR": "DOM",
                                  "SIN": "APAC", "NRT": "APAC"}
                needed = required_quals.get(dest, "")
                route_ok = needed in quals if needed else True

                issues = []
                if not medical_ok: issues.append("medical expired")
                if not duty_ok: issues.append(f"duty 7d={duty_7d}h (limit 55)")
                if not rest_ok: issues.append(f"rest={rest_hrs}h (need 14h intl)")
                if not route_ok: issues.append(f"no {needed} qual for {dest}")

                entry = f"{name} ({rank}, base={c.get('base_airport','?')}) — duty={duty_7d}h, rest={rest_hrs}h, fatigue={fatigue}"
                if not issues:
                    eligible_list.append(f"ELIGIBLE: {entry}")
                else:
                    ineligible_list.append(f"NOT ELIGIBLE: {entry} — {', '.join(issues)}")

            crew_context = (
                f"\n\nCREW ROSTER FOR {dest} ROUTE:\n"
                f"Eligible crew:\n" + "\n".join(eligible_list[:8]) +
                f"\n\nNot eligible:\n" + "\n".join(ineligible_list[:8])
            )
        except Exception as e:
            logger.warning("Failed to enrich crew context: %s", e)

    system = (
        "You are an Air India dispatch coordinator assistant. "
        "Answer the user's SPECIFIC question directly. Do NOT repeat the full dispatch summary. "
        "Be concise — use bullet points and specific names/numbers.\n"
        "If asked about crew replacement: list eligible crew BY NAME with their status. "
        "If asked about aircraft swap: suggest specific aircraft registrations. "
        "If asked general questions: answer from the dispatch context."
    )

    user_content = f"Context:\n{compact_context}{crew_context}\n\nQuestion: {user_message}"

    try:
        result = llm_call(system, user_content, max_tokens=800, temperature=0.3)
        return result if result else "Unable to process your question at this time."
    except Exception as e:
        logger.error("Chat LLM call failed: %s", e)
        return f"Unable to process your question. Error: {str(e)}"
