"""
Anomaly Detection Agent
Analyzes sensor telemetry for specified aircraft, detects trends,
cross-references with component lifecycle, and returns structured findings.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras

from db import get_db_connection

logger = logging.getLogger("anomaly_detection_agent")




def _compute_trend(values: list[float]) -> dict:
    """Compute trend statistics from a list of chronological values."""
    if len(values) < 2:
        return {"slope": 0.0, "pct_change": 0.0, "direction": "STABLE"}
    first, last = values[0], values[-1]
    pct_change = ((last - first) / abs(first)) * 100 if first != 0 else 0.0
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    slope = numerator / denominator if denominator != 0 else 0.0
    if pct_change > 5:
        direction = "INCREASING"
    elif pct_change < -5:
        direction = "DECREASING"
    else:
        direction = "STABLE"
    return {
        "slope_per_reading": round(slope, 4),
        "pct_change_7d": round(pct_change, 2),
        "direction": direction,
        "first_value": round(first, 3),
        "last_value": round(last, 3),
    }


def _estimate_time_to_failure(current: float, limit: float, slope: float) -> Optional[float]:
    """Estimate hours until value crosses the critical threshold."""
    if slope <= 0:
        return None
    # Assume readings are ~4 hours apart
    hours_per_reading = 4.0
    readings_to_limit = (limit - current) / slope if slope > 0 else None
    if readings_to_limit is not None and readings_to_limit > 0:
        return round(readings_to_limit * hours_per_reading, 1)
    # Already past limit — estimate time to catastrophic (20% beyond limit)
    catastrophic = limit * 1.2
    readings_to_catastrophic = (catastrophic - current) / slope
    if readings_to_catastrophic > 0:
        return round(readings_to_catastrophic * hours_per_reading, 1)
    return 0.0


def _severity_from_score(score: float) -> str:
    if score >= 0.85:
        return "CRITICAL"
    elif score >= 0.65:
        return "HIGH"
    elif score >= 0.40:
        return "MEDIUM"
    else:
        return "LOW"


def analyze_aircraft(aircraft_reg: str) -> dict:
    """
    Run full anomaly detection analysis for an aircraft.
    Returns structured findings with severity levels.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get aircraft info
        cur.execute("SELECT * FROM aircraft_fleet WHERE aircraft_reg = %s", (aircraft_reg,))
        aircraft = cur.fetchone()
        if not aircraft:
            return {"error": f"Aircraft {aircraft_reg} not found", "anomalies": []}

        # Get sensor telemetry for last 7 days
        cur.execute(
            """
            SELECT sensor_type, engine_position, timestamp, value, unit,
                   normal_min, normal_max, anomaly_score
            FROM sensor_telemetry
            WHERE aircraft_reg = %s AND timestamp >= NOW() - INTERVAL '7 days'
            ORDER BY sensor_type, engine_position, timestamp
            """,
            (aircraft_reg,),
        )
        telemetry = cur.fetchall()

        # Get component lifecycle
        cur.execute(
            """
            SELECT component_id, component_type, part_number, install_date,
                   expected_life_hours, current_hours, health_score, status,
                   next_inspection_due
            FROM component_lifecycle
            WHERE aircraft_reg = %s
            ORDER BY health_score ASC
            """,
            (aircraft_reg,),
        )
        components = cur.fetchall()

        # Get recent maintenance
        cur.execute(
            """
            SELECT work_order_id, component, action_type, description, status, start_date
            FROM maintenance_history
            WHERE aircraft_reg = %s
            ORDER BY start_date DESC LIMIT 5
            """,
            (aircraft_reg,),
        )
        recent_maintenance = cur.fetchall()

        # Group telemetry by (sensor_type, engine_position)
        sensor_groups: dict[tuple, list] = {}
        for row in telemetry:
            key = (row["sensor_type"], row["engine_position"])
            if key not in sensor_groups:
                sensor_groups[key] = []
            sensor_groups[key].append(row)

        anomalies = []
        sensor_analysis = []
        overall_health = 100.0
        anomaly_count = 0

        for (sensor_type, engine_pos), readings in sensor_groups.items():
            values = [float(r["value"]) for r in readings]
            normal_min = float(readings[0]["normal_min"])
            normal_max = float(readings[0]["normal_max"])
            unit = readings[0]["unit"]
            latest_value = values[-1]
            latest_score = float(readings[-1]["anomaly_score"])

            trend = _compute_trend(values)

            # Determine if anomalous
            is_above = latest_value > normal_max
            is_below = latest_value < normal_min
            is_anomalous = is_above or is_below or latest_score > 0.5

            # Determine critical threshold for TTF
            if is_above or trend["direction"] == "INCREASING":
                # For increasing values, critical is 120% of max
                critical_limit = normal_max * 1.2
                ttf = _estimate_time_to_failure(latest_value, critical_limit, trend["slope_per_reading"])
            elif is_below or trend["direction"] == "DECREASING":
                # For decreasing values (like hydraulic pressure), critical is 80% of min
                critical_limit = normal_min * 0.8
                slope_abs = abs(trend["slope_per_reading"])
                if trend["direction"] == "DECREASING" and slope_abs > 0:
                    readings_to_crit = (latest_value - critical_limit) / slope_abs
                    ttf = round(readings_to_crit * 4.0, 1) if readings_to_crit > 0 else 0.0
                else:
                    ttf = None
            else:
                ttf = None

            severity = _severity_from_score(latest_score)
            exceedance_pct = 0.0
            if is_above:
                exceedance_pct = round(((latest_value - normal_max) / normal_max) * 100, 1)
            elif is_below:
                exceedance_pct = round(((normal_min - latest_value) / normal_min) * 100, 1)

            analysis_entry = {
                "sensor_type": sensor_type,
                "engine_position": engine_pos,
                "latest_value": round(latest_value, 3),
                "unit": unit,
                "normal_range": f"{normal_min}-{normal_max}",
                "anomaly_score": round(latest_score, 3),
                "trend": trend,
                "is_anomalous": is_anomalous,
                "severity": severity if is_anomalous else "NORMAL",
                "exceedance_pct": exceedance_pct,
                "reading_count": len(values),
            }
            sensor_analysis.append(analysis_entry)

            if is_anomalous:
                anomaly_count += 1
                health_penalty = latest_score * 25
                overall_health -= health_penalty

                anomaly_entry = {
                    "sensor_type": sensor_type,
                    "engine_position": engine_pos,
                    "severity": severity,
                    "anomaly_score": round(latest_score, 3),
                    "latest_value": round(latest_value, 3),
                    "unit": unit,
                    "normal_range": f"{normal_min}-{normal_max}",
                    "exceedance_pct": exceedance_pct,
                    "trend_direction": trend["direction"],
                    "trend_pct_change_7d": trend["pct_change_7d"],
                    "estimated_time_to_failure_hours": ttf,
                    "description": _build_anomaly_description(
                        sensor_type, engine_pos, latest_value, unit,
                        normal_min, normal_max, trend, severity, ttf
                    ),
                }
                anomalies.append(anomaly_entry)

        # Cross-reference with component lifecycle
        critical_components = []
        for comp in components:
            health = float(comp["health_score"])
            if health < 60:
                life_remaining_pct = round(
                    ((comp["expected_life_hours"] - comp["current_hours"]) / comp["expected_life_hours"]) * 100, 1
                )
                critical_components.append({
                    "component_id": comp["component_id"],
                    "component_type": comp["component_type"],
                    "part_number": comp["part_number"],
                    "health_score": health,
                    "status": comp["status"],
                    "current_hours": comp["current_hours"],
                    "expected_life_hours": comp["expected_life_hours"],
                    "life_remaining_pct": life_remaining_pct,
                    "next_inspection_due": str(comp["next_inspection_due"]) if comp["next_inspection_due"] else None,
                })

        overall_health = max(0, round(overall_health, 1))

        # Determine overall status
        if any(a["severity"] == "CRITICAL" for a in anomalies):
            overall_status = "CRITICAL"
        elif any(a["severity"] == "HIGH" for a in anomalies):
            overall_status = "WARNING"
        elif any(a["severity"] == "MEDIUM" for a in anomalies):
            overall_status = "WATCH"
        else:
            overall_status = "NORMAL"

        # Build diagnosis
        diagnosis = _build_diagnosis(anomalies, critical_components, aircraft)

        return {
            "aircraft_reg": aircraft_reg,
            "aircraft_type": aircraft["aircraft_type"],
            "engine_type": aircraft["engine_type"],
            "base_station": aircraft["base_station"],
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "overall_health_score": overall_health,
            "overall_status": overall_status,
            "anomaly_count": anomaly_count,
            "anomalies": anomalies,
            "sensor_analysis": sensor_analysis,
            "critical_components": critical_components,
            "recent_maintenance": [
                {
                    "work_order_id": m["work_order_id"],
                    "component": m["component"],
                    "action_type": m["action_type"],
                    "description": m["description"],
                    "status": m["status"],
                    "date": str(m["start_date"]) if m["start_date"] else None,
                }
                for m in recent_maintenance
            ],
            "diagnosis": diagnosis,
        }
    finally:
        conn.close()


def _build_anomaly_description(
    sensor_type, engine_pos, value, unit,
    normal_min, normal_max, trend, severity, ttf
):
    desc = f"{sensor_type} on {engine_pos}: {value} {unit} "
    if value > normal_max:
        desc += f"(EXCEEDS max {normal_max} {unit} by {round(((value - normal_max)/normal_max)*100, 1)}%). "
    elif value < normal_min:
        desc += f"(BELOW min {normal_min} {unit} by {round(((normal_min - value)/normal_min)*100, 1)}%). "
    else:
        desc += f"(within range {normal_min}-{normal_max} {unit} but score elevated). "

    desc += f"7-day trend: {trend['direction']} ({trend['pct_change_7d']}% change). "
    if ttf is not None:
        desc += f"Estimated time to critical failure: {ttf} hours."
    return desc


def _build_diagnosis(anomalies, critical_components, aircraft):
    if not anomalies:
        return {
            "summary": f"Aircraft {aircraft['aircraft_reg']} is operating within normal parameters.",
            "recommended_action": "Continue routine monitoring.",
            "urgency": "NONE",
        }

    critical_anomalies = [a for a in anomalies if a["severity"] == "CRITICAL"]
    high_anomalies = [a for a in anomalies if a["severity"] == "HIGH"]

    # Check for correlated anomalies (multiple sensors on same engine)
    engine_anomalies: dict[str, list] = {}
    for a in anomalies:
        ep = a["engine_position"]
        if ep not in engine_anomalies:
            engine_anomalies[ep] = []
        engine_anomalies[ep].append(a)

    correlated_engines = {k: v for k, v in engine_anomalies.items() if len(v) >= 2}

    lines = []
    if critical_anomalies:
        lines.append(f"CRITICAL ALERT: {len(critical_anomalies)} critical anomaly(ies) detected.")
    if high_anomalies:
        lines.append(f"HIGH ALERT: {len(high_anomalies)} high-severity anomaly(ies) detected.")

    if correlated_engines:
        for engine, eng_anomalies in correlated_engines.items():
            sensor_types = [a["sensor_type"] for a in eng_anomalies]
            lines.append(
                f"CORRELATED PATTERN on {engine}: {', '.join(sensor_types)} — "
                f"Multiple sensor degradation indicates probable component failure."
            )
            # Specific patterns
            vib_types = [s for s in sensor_types if "VIBRATION" in s]
            temp_types = [s for s in sensor_types if "TEMP" in s or "EGT" in s]
            if vib_types and temp_types:
                lines.append(
                    f"Pattern match: Vibration + Temperature increase on {engine} "
                    f"consistent with bearing degradation or rotor imbalance."
                )

    if critical_components:
        for comp in critical_components:
            lines.append(
                f"Component {comp['component_type']} (health: {comp['health_score']}%, "
                f"status: {comp['status']}) — {comp['life_remaining_pct']}% life remaining."
            )

    # Find minimum TTF
    ttfs = [a["estimated_time_to_failure_hours"] for a in anomalies if a["estimated_time_to_failure_hours"] is not None]
    min_ttf = min(ttfs) if ttfs else None

    if critical_anomalies or (min_ttf is not None and min_ttf < 120):
        urgency = "IMMEDIATE"
        action = "GROUND AIRCRAFT FOR INSPECTION. Schedule maintenance within 24 hours."
    elif high_anomalies:
        urgency = "HIGH"
        action = "Schedule maintenance within 48 hours. Restrict to essential operations."
    else:
        urgency = "MODERATE"
        action = "Schedule inspection at next convenient maintenance window."

    return {
        "summary": " ".join(lines),
        "recommended_action": action,
        "urgency": urgency,
        "estimated_time_to_failure_hours": min_ttf,
        "correlated_engine_issues": list(correlated_engines.keys()),
    }
