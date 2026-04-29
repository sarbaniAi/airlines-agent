"""
Predictive Maintenance Orchestrator
Dispatches agents, synthesizes results using LLM, logs to MLflow.
"""

import os
import json
import logging
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import mlflow

import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import llm_call

from agents.anomaly_detection import analyze_aircraft
from agents.work_order import create_work_order
from agents.parts_inventory import check_parts_availability
from agents.schedule_alignment import find_maintenance_window

logger = logging.getLogger("orchestrator")

EXPERIMENT_NAME = "/Users/sarbani.maiti@databricks.com/air-india-predictive-maintenance"

try:
    mlflow.set_experiment(EXPERIMENT_NAME)
except Exception as e:
    logger.warning(f"Could not set MLflow experiment: {e}")


# LLM calls use llm_call() from llm.py (via ai_query SQL function)


def _safe_serialize(obj):
    """Safely serialize an object to JSON-compatible format."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if hasattr(obj, "__dict__"):
        return str(obj)
    return str(obj)


def _synthesize_action_plan(anomaly_result, work_order_result, parts_result, schedule_result):
    """Use LLM to create a natural-language maintenance action plan."""
    try:

        context = {
            "aircraft": anomaly_result.get("aircraft_reg"),
            "aircraft_type": anomaly_result.get("aircraft_type"),
            "overall_status": anomaly_result.get("overall_status"),
            "health_score": anomaly_result.get("overall_health_score"),
            "anomalies": [
                {
                    "sensor": a["sensor_type"],
                    "engine": a["engine_position"],
                    "severity": a["severity"],
                    "value": f"{a['latest_value']} {a['unit']}",
                    "normal_range": a["normal_range"],
                    "trend": a["trend_direction"],
                    "ttf_hours": a.get("estimated_time_to_failure_hours"),
                }
                for a in anomaly_result.get("anomalies", [])
            ],
            "diagnosis": anomaly_result.get("diagnosis", {}),
            "work_orders": [
                {
                    "id": wo["work_order_id"],
                    "priority": wo["priority"],
                    "component": wo["component"],
                    "hours": wo["estimated_duration_hours"],
                    "cost": wo["estimated_cost_usd"],
                }
                for wo in work_order_result.get("work_orders", [])
            ],
            "parts_status": parts_result.get("overall_status"),
            "parts_message": parts_result.get("message"),
            "transfers": parts_result.get("transfers_needed", []),
            "schedule_recommendation": schedule_result.get("recommendation", {}),
            "flights_impacted": schedule_result.get("flight_impact", {}).get("flights_impacted", 0),
        }

        prompt = f"""You are an AI maintenance advisor for Air India. Analyze the following predictive maintenance data and create a clear, actionable maintenance action plan.

DATA:
{json.dumps(context, indent=2, default=_safe_serialize)}

Create a structured maintenance action plan with:
1. EXECUTIVE SUMMARY (2-3 sentences for VP-level audience)
2. RISK ASSESSMENT (what happens if we don't act)
3. RECOMMENDED ACTIONS (numbered steps with timeline)
4. COST-BENEFIT ANALYSIS (maintenance cost vs AOG cost avoided)
5. OPERATIONAL IMPACT (flights affected, passenger impact)

Be specific with aircraft registrations, part numbers, station codes, and timelines.
Use professional aviation maintenance language. Be concise but thorough."""

        system_msg = "You are an expert aviation maintenance planning AI for Air India. Respond with clear, structured, actionable maintenance plans."
        result = llm_call(system_msg, prompt, temperature=0.3, max_tokens=2000)
        return result if result else _template_summary(anomaly_result, work_order_result, parts_result, schedule_result)

    except Exception as e:
        logger.error(f"LLM synthesis failed: {e}")
        # Fallback to template-based summary
        return _template_summary(anomaly_result, work_order_result, parts_result, schedule_result)


def _template_summary(anomaly_result, work_order_result, parts_result, schedule_result):
    """Fallback template when LLM is unavailable."""
    aircraft = anomaly_result.get("aircraft_reg", "UNKNOWN")
    status = anomaly_result.get("overall_status", "UNKNOWN")
    health = anomaly_result.get("overall_health_score", 0)
    anomalies = anomaly_result.get("anomalies", [])
    diagnosis = anomaly_result.get("diagnosis", {})
    wo_count = work_order_result.get("total_work_orders", 0)
    total_cost = work_order_result.get("total_estimated_cost_usd", 0)
    savings = work_order_result.get("potential_aog_savings_usd", 0)
    parts_msg = parts_result.get("message", "")
    schedule_rec = schedule_result.get("recommendation", {})

    lines = [
        f"## MAINTENANCE ACTION PLAN: {aircraft}",
        f"**Status:** {status} | **Health Score:** {health}%",
        "",
        "### EXECUTIVE SUMMARY",
        diagnosis.get("summary", "Analysis complete."),
        "",
        "### RISK ASSESSMENT",
        f"Failure to act: Estimated AOG cost $100,000-$150,000/day.",
        f"Time to predicted failure: {diagnosis.get('estimated_time_to_failure_hours', 'N/A')} hours.",
        "",
        "### RECOMMENDED ACTIONS",
        f"- {wo_count} work order(s) created. Estimated cost: ${total_cost:,.0f}",
        f"- {diagnosis.get('recommended_action', 'Schedule maintenance.')}",
        "",
        "### PARTS & LOGISTICS",
        parts_msg,
        "",
        "### SCHEDULE",
        schedule_rec.get("summary", "Schedule analysis pending."),
        "",
        "### COST-BENEFIT",
        f"- Maintenance cost: ${total_cost:,.0f}",
        f"- AOG cost avoided: ${savings + total_cost:,.0f}",
        f"- **Net savings: ${savings:,.0f}**",
    ]
    return "\n".join(lines)


def run_full_analysis(aircraft_reg: str) -> dict:
    """
    Run the complete predictive maintenance analysis pipeline.

    Flow:
    1. Anomaly Detection (must run first)
    2. In parallel: Work Order + Parts + Schedule (depend on anomaly results)
    3. LLM synthesis of final action plan
    """
    start_time = time.time()

    try:
        with mlflow.start_run(run_name=f"predictive-mx-{aircraft_reg}-{datetime.utcnow().strftime('%Y%m%d-%H%M')}"):
            mlflow.log_param("aircraft_reg", aircraft_reg)
            mlflow.log_param("analysis_type", "full_predictive_maintenance")

            # Step 1: Anomaly Detection
            step1_start = time.time()
            anomaly_result = analyze_aircraft(aircraft_reg)
            step1_time = time.time() - step1_start
            mlflow.log_metric("anomaly_detection_seconds", round(step1_time, 2))
            mlflow.log_metric("anomaly_count", anomaly_result.get("anomaly_count", 0))
            mlflow.log_metric("health_score", anomaly_result.get("overall_health_score", 0))

            if anomaly_result.get("anomaly_count", 0) == 0:
                total_time = time.time() - start_time
                mlflow.log_metric("total_analysis_seconds", round(total_time, 2))
                return {
                    "aircraft_reg": aircraft_reg,
                    "status": "HEALTHY",
                    "message": f"No anomalies detected for {aircraft_reg}. All systems nominal.",
                    "anomaly_result": anomaly_result,
                    "work_order_result": {"work_orders": [], "message": "No work orders needed."},
                    "parts_result": {"message": "No parts needed."},
                    "schedule_result": {"message": "No maintenance needed."},
                    "action_plan": f"Aircraft {aircraft_reg} is operating within normal parameters. Continue routine monitoring schedule.",
                    "total_analysis_seconds": round(total_time, 2),
                }

            # Step 2: Parallel execution of Work Order, Parts, and Schedule agents
            step2_start = time.time()
            work_order_result = {}
            parts_result = {}
            schedule_result = {}

            with ThreadPoolExecutor(max_workers=3) as executor:
                wo_future = executor.submit(create_work_order, anomaly_result)
                # Parts and Schedule depend on work order, so we do WO first, then parallel
                work_order_result = wo_future.result()

            step2a_time = time.time() - step2_start
            mlflow.log_metric("work_order_seconds", round(step2a_time, 2))

            # Now parts and schedule can run in parallel (both need work order result)
            step2b_start = time.time()
            with ThreadPoolExecutor(max_workers=2) as executor:
                parts_future = executor.submit(
                    check_parts_availability, work_order_result, anomaly_result
                )
                # Schedule needs parts result too, but we can start it and it will handle
                parts_result = parts_future.result()

            # Schedule needs both work order and parts results
            schedule_result = find_maintenance_window(
                work_order_result, parts_result, anomaly_result
            )
            step2b_time = time.time() - step2b_start
            mlflow.log_metric("parts_and_schedule_seconds", round(step2b_time, 2))

            # Log key results
            mlflow.log_metric("work_orders_created", work_order_result.get("total_work_orders", 0))
            mlflow.log_metric("total_estimated_cost", work_order_result.get("total_estimated_cost_usd", 0))
            mlflow.log_metric("transfers_needed", len(parts_result.get("transfers_needed", [])))

            # Step 3: LLM Synthesis
            step3_start = time.time()
            action_plan = _synthesize_action_plan(
                anomaly_result, work_order_result, parts_result, schedule_result
            )
            step3_time = time.time() - step3_start
            mlflow.log_metric("llm_synthesis_seconds", round(step3_time, 2))

            total_time = time.time() - start_time
            mlflow.log_metric("total_analysis_seconds", round(total_time, 2))

            # Compute estimated savings
            rec = schedule_result.get("recommendation", {})
            estimated_savings = rec.get("estimated_savings_usd", 0)
            if estimated_savings == 0:
                estimated_savings = work_order_result.get("potential_aog_savings_usd", 125000)
            mlflow.log_metric("estimated_savings_usd", estimated_savings)

            result = {
                "aircraft_reg": aircraft_reg,
                "status": anomaly_result.get("overall_status", "UNKNOWN"),
                "health_score": anomaly_result.get("overall_health_score", 0),
                "anomaly_result": anomaly_result,
                "work_order_result": work_order_result,
                "parts_result": parts_result,
                "schedule_result": schedule_result,
                "action_plan": action_plan,
                "estimated_savings_usd": estimated_savings,
                "total_analysis_seconds": round(total_time, 2),
                "agent_timings": {
                    "anomaly_detection": round(step1_time, 2),
                    "work_order": round(step2a_time, 2),
                    "parts_and_schedule": round(step2b_time, 2),
                    "llm_synthesis": round(step3_time, 2),
                },
            }

            return result

    except Exception as e:
        logger.error(f"Analysis failed for {aircraft_reg}: {e}", exc_info=True)
        return {
            "aircraft_reg": aircraft_reg,
            "status": "ERROR",
            "error": str(e),
            "total_analysis_seconds": round(time.time() - start_time, 2),
        }


def chat_about_fleet(question: str) -> str:
    """
    Answer natural language questions about the fleet using LLM + database context.
    """
    import psycopg2
    import psycopg2.extras
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from db import get_db_connection

    # Gather context from database
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Fleet overview
        cur.execute("SELECT aircraft_reg, aircraft_type, base_station, status, total_flight_hours FROM aircraft_fleet ORDER BY aircraft_reg")
        fleet = cur.fetchall()

        # Active alerts
        cur.execute("SELECT alert_id, aircraft_reg, sensor_type, severity, description, status FROM anomaly_alerts WHERE status IN ('NEW', 'ACKNOWLEDGED') ORDER BY severity DESC, detected_at DESC")
        alerts = cur.fetchall()

        # Critical components
        cur.execute("SELECT aircraft_reg, component_type, health_score, status FROM component_lifecycle WHERE health_score < 60 ORDER BY health_score ASC")
        critical = cur.fetchall()

        context = {
            "fleet": [dict(r) for r in fleet],
            "active_alerts": [dict(r) for r in alerts],
            "critical_components": [dict(r) for r in critical],
            "current_time": datetime.utcnow().isoformat(),
        }
    finally:
        conn.close()

    try:
        system_msg = (
            "You are the AI maintenance advisor for Air India's fleet. "
            "Answer questions about aircraft health, maintenance needs, and fleet status. "
            "Be concise, professional, and specific. Use the provided context data.\n\n"
            f"FLEET DATA:\n{json.dumps(context, indent=2, default=_safe_serialize)}"
        )
        result = llm_call(system_msg, question, temperature=0.3, max_tokens=1000)
        if result:
            return result
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        # Fallback
        alert_count = len([a for a in context.get("active_alerts", []) if a.get("severity") in ("CRITICAL", "HIGH")])
        return (
            f"I have information about {len(fleet)} aircraft in the fleet. "
            f"There are currently {alert_count} high/critical alerts active. "
            f"However, I'm unable to process your specific question right now due to a service issue. "
            f"Please try again or check the dashboard for current fleet status."
        )
