"""
Work Order Agent
Takes anomaly findings and creates maintenance work orders with priority,
task description, estimated duration, required skills, and tools.
"""

import os
import logging
import uuid
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

from db import get_db_connection

logger = logging.getLogger("work_order_agent")




# ATA chapter mapping for common components
ATA_CHAPTERS = {
    "ENGINE_VIBRATION_N1": "72-00",
    "ENGINE_VIBRATION_N2": "72-50",
    "OIL_TEMP": "79-20",
    "OIL_PRESSURE": "79-10",
    "EGT": "77-20",
    "HYDRAULIC_PRESSURE": "29-10",
    "FUEL_FLOW": "73-10",
    "BLEED_AIR_TEMP": "36-10",
}

# Maintenance action templates based on sensor + severity
ACTION_TEMPLATES = {
    ("ENGINE_VIBRATION_N2", "CRITICAL"): {
        "action_type": "UNSCHEDULED",
        "component": "N2 Turbine Bearing Assembly",
        "task": "Remove and replace N2 turbine bearing assembly. Perform borescope inspection of HP turbine section. Run engine ground test to verify vibration levels within limits.",
        "skills": ["Engine Mechanic (GEnx/GE90/LEAP/Trent qualified)", "NDT Inspector", "Engine Run-up Crew"],
        "tools": ["Bearing removal/installation tooling", "Borescope", "Vibration analysis equipment", "Torque wrenches", "Engine hoist"],
        "estimated_hours": 8,
        "priority": "AOG_PREVENTION",
    },
    ("ENGINE_VIBRATION_N2", "HIGH"): {
        "action_type": "UNSCHEDULED",
        "component": "N2 Turbine Section",
        "task": "Detailed borescope inspection of N2 turbine section. Oil sample analysis. Vibration signature analysis. Determine if bearing replacement is required.",
        "skills": ["Engine Mechanic", "NDT Inspector"],
        "tools": ["Borescope", "Vibration analysis equipment", "Oil sample kit"],
        "estimated_hours": 4,
        "priority": "HIGH",
    },
    ("OIL_TEMP", "CRITICAL"): {
        "action_type": "UNSCHEDULED",
        "component": "Engine Oil System",
        "task": "Inspect oil system for blockages or bearing wear. Replace oil filter. Take oil sample for spectrometric analysis. Check oil cooler function.",
        "skills": ["Engine Mechanic", "Oil Analysis Technician"],
        "tools": ["Oil sample kit", "Filter wrench", "Temperature probes"],
        "estimated_hours": 3,
        "priority": "HIGH",
    },
    ("OIL_TEMP", "HIGH"): {
        "action_type": "INSPECTION",
        "component": "Engine Oil System",
        "task": "Oil sample analysis and filter inspection. Monitor oil temperature trend.",
        "skills": ["Engine Mechanic"],
        "tools": ["Oil sample kit", "Filter wrench"],
        "estimated_hours": 2,
        "priority": "MEDIUM",
    },
    ("EGT", "CRITICAL"): {
        "action_type": "UNSCHEDULED",
        "component": "Engine Hot Section",
        "task": "Borescope inspection of combustion chamber and HP turbine. Check fuel nozzle spray pattern. Verify EGT thermocouple calibration.",
        "skills": ["Engine Mechanic", "NDT Inspector"],
        "tools": ["Borescope", "Fuel nozzle test rig", "Thermocouple tester"],
        "estimated_hours": 5,
        "priority": "HIGH",
    },
    ("EGT", "HIGH"): {
        "action_type": "INSPECTION",
        "component": "Engine EGT System",
        "task": "EGT thermocouple harness check. Engine trend monitoring review.",
        "skills": ["Engine Mechanic"],
        "tools": ["Thermocouple tester", "Trend monitoring software"],
        "estimated_hours": 2,
        "priority": "MEDIUM",
    },
    ("HYDRAULIC_PRESSURE", "CRITICAL"): {
        "action_type": "UNSCHEDULED",
        "component": "Hydraulic System Pump Assembly",
        "task": "Replace hydraulic pump seal kit. Inspect pump case drain fitting. Pressure test complete hydraulic system. Check accumulator pre-charge.",
        "skills": ["Hydraulic System Mechanic", "NDT Inspector"],
        "tools": ["Hydraulic test rig", "Seal installation kit", "Pressure gauges", "Torque wrenches"],
        "estimated_hours": 6,
        "priority": "AOG_PREVENTION",
    },
    ("HYDRAULIC_PRESSURE", "HIGH"): {
        "action_type": "UNSCHEDULED",
        "component": "Hydraulic System",
        "task": "Leak detection and repair. Hydraulic fluid top-up. System pressure check.",
        "skills": ["Hydraulic System Mechanic"],
        "tools": ["Leak detection dye", "Hydraulic test rig", "Pressure gauges"],
        "estimated_hours": 4,
        "priority": "HIGH",
    },
}

DEFAULT_ACTION = {
    "action_type": "INSPECTION",
    "component": "General Inspection",
    "task": "Inspect sensor and related system components. Run diagnostic checks.",
    "skills": ["Aircraft Mechanic"],
    "tools": ["Multimeter", "Inspection mirror"],
    "estimated_hours": 2,
    "priority": "MEDIUM",
}


def _estimate_cost(action_template: dict, parts_needed: list) -> float:
    """Estimate total cost: labor + parts."""
    labor_rate_per_hour = 150.0  # USD
    labor_cost = action_template["estimated_hours"] * labor_rate_per_hour * len(action_template["skills"])
    parts_cost = sum(p.get("unit_cost_usd", 0) for p in parts_needed)
    return round(labor_cost + parts_cost, 2)


def create_work_order(anomaly_findings: dict) -> dict:
    """
    Create maintenance work orders based on anomaly detection results.
    Returns work order details with all task information.
    """
    aircraft_reg = anomaly_findings.get("aircraft_reg", "UNKNOWN")
    anomalies = anomaly_findings.get("anomalies", [])
    diagnosis = anomaly_findings.get("diagnosis", {})
    correlated_engines = diagnosis.get("correlated_engine_issues", [])

    if not anomalies:
        return {
            "aircraft_reg": aircraft_reg,
            "work_orders": [],
            "message": "No anomalies detected. No work orders required.",
        }

    conn = get_db_connection()
    work_orders = []

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get aircraft info
        cur.execute("SELECT * FROM aircraft_fleet WHERE aircraft_reg = %s", (aircraft_reg,))
        aircraft = cur.fetchone()

        # If correlated anomalies on same engine, create a combined work order
        if correlated_engines:
            for engine in correlated_engines:
                engine_anomalies = [a for a in anomalies if a["engine_position"] == engine]
                wo = _create_combined_work_order(cur, aircraft, engine, engine_anomalies)
                work_orders.append(wo)
                # Remove processed anomalies
                anomalies = [a for a in anomalies if a["engine_position"] != engine]

        # Create individual work orders for remaining anomalies
        for anomaly in anomalies:
            wo = _create_single_work_order(cur, aircraft, anomaly)
            work_orders.append(wo)

        conn.commit()

    finally:
        conn.close()

    # Calculate total estimated cost and duration
    total_cost = sum(wo["estimated_cost_usd"] for wo in work_orders)
    total_hours = sum(wo["estimated_duration_hours"] for wo in work_orders)
    aog_cost_per_day = 100000  # Average AOG cost
    potential_aog_days = 2
    savings = (aog_cost_per_day * potential_aog_days) - total_cost

    return {
        "aircraft_reg": aircraft_reg,
        "work_orders": work_orders,
        "total_work_orders": len(work_orders),
        "total_estimated_cost_usd": round(total_cost, 2),
        "total_estimated_hours": round(total_hours, 1),
        "potential_aog_savings_usd": round(max(savings, 0), 2),
        "aog_cost_avoided_per_day": aog_cost_per_day,
        "created_at": datetime.utcnow().isoformat(),
    }


def _create_combined_work_order(cur, aircraft, engine, anomalies):
    """Create a combined work order for correlated anomalies on the same engine."""
    wo_id = f"WO-{datetime.utcnow().strftime('%Y')}-{str(uuid.uuid4())[:4].upper()}"

    # Find the most severe anomaly to drive the primary action
    max_anomaly = max(anomalies, key=lambda a: a["anomaly_score"])
    key = (max_anomaly["sensor_type"], max_anomaly["severity"])
    template = ACTION_TEMPLATES.get(key, DEFAULT_ACTION)

    # Combine tasks from all anomalies
    all_tasks = [template["task"]]
    all_skills = set(template["skills"])
    all_tools = set(template["tools"])
    total_hours = template["estimated_hours"]

    for anomaly in anomalies:
        if anomaly != max_anomaly:
            akey = (anomaly["sensor_type"], anomaly["severity"])
            atemplate = ACTION_TEMPLATES.get(akey, DEFAULT_ACTION)
            additional_task = atemplate["task"]
            if additional_task not in all_tasks:
                all_tasks.append(f"Additionally: {additional_task}")
            all_skills.update(atemplate["skills"])
            all_tools.update(atemplate["tools"])
            # Add partial time for concurrent inspection
            total_hours += atemplate["estimated_hours"] * 0.5

    # Determine parts needed
    parts_needed = _lookup_required_parts(cur, max_anomaly["sensor_type"], aircraft)

    sensor_types = [a["sensor_type"] for a in anomalies]
    description = (
        f"CORRELATED FAILURE PATTERN on {engine}: {', '.join(sensor_types)}. "
        + " ".join(all_tasks)
    )

    # Determine priority
    if any(a["severity"] == "CRITICAL" for a in anomalies):
        priority = "AOG_PREVENTION"
    elif any(a["severity"] == "HIGH" for a in anomalies):
        priority = "HIGH"
    else:
        priority = "MEDIUM"

    estimated_cost = _estimate_cost(
        {"estimated_hours": total_hours, "skills": list(all_skills)},
        parts_needed,
    )

    # Insert into database
    try:
        cur.execute(
            """
            INSERT INTO maintenance_history
            (work_order_id, aircraft_reg, component, ata_chapter, action_type,
             description, technician, start_date, status, cost_usd, parts_used)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                wo_id, aircraft["aircraft_reg"], template["component"],
                ATA_CHAPTERS.get(max_anomaly["sensor_type"], "00-00"),
                template["action_type"], description[:500],
                "ASSIGNED - Pending", datetime.utcnow(), "IN_PROGRESS",
                estimated_cost,
                ", ".join(p["part_number"] for p in parts_needed),
            ),
        )
    except Exception as e:
        logger.warning(f"Could not insert work order: {e}")

    return {
        "work_order_id": wo_id,
        "priority": priority,
        "action_type": template["action_type"],
        "component": template["component"],
        "engine_position": engine,
        "ata_chapter": ATA_CHAPTERS.get(max_anomaly["sensor_type"], "00-00"),
        "description": description,
        "tasks": all_tasks,
        "required_skills": sorted(all_skills),
        "required_tools": sorted(all_tools),
        "estimated_duration_hours": round(total_hours, 1),
        "estimated_cost_usd": estimated_cost,
        "parts_needed": parts_needed,
        "anomaly_references": [
            {"sensor": a["sensor_type"], "severity": a["severity"], "score": a["anomaly_score"]}
            for a in anomalies
        ],
        "correlated": True,
        "status": "CREATED",
    }


def _create_single_work_order(cur, aircraft, anomaly):
    """Create a work order for a single anomaly."""
    wo_id = f"WO-{datetime.utcnow().strftime('%Y')}-{str(uuid.uuid4())[:4].upper()}"

    key = (anomaly["sensor_type"], anomaly["severity"])
    template = ACTION_TEMPLATES.get(key, DEFAULT_ACTION)

    parts_needed = _lookup_required_parts(cur, anomaly["sensor_type"], aircraft)
    estimated_cost = _estimate_cost(template, parts_needed)

    description = (
        f"{anomaly['sensor_type']} anomaly on {anomaly['engine_position']}: "
        f"{anomaly['latest_value']} {anomaly['unit']} "
        f"(normal: {anomaly['normal_range']}). {template['task']}"
    )

    try:
        cur.execute(
            """
            INSERT INTO maintenance_history
            (work_order_id, aircraft_reg, component, ata_chapter, action_type,
             description, technician, start_date, status, cost_usd, parts_used)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                wo_id, aircraft["aircraft_reg"], template["component"],
                ATA_CHAPTERS.get(anomaly["sensor_type"], "00-00"),
                template["action_type"], description[:500],
                "ASSIGNED - Pending", datetime.utcnow(), "IN_PROGRESS",
                estimated_cost,
                ", ".join(p["part_number"] for p in parts_needed),
            ),
        )
    except Exception as e:
        logger.warning(f"Could not insert work order: {e}")

    return {
        "work_order_id": wo_id,
        "priority": template["priority"],
        "action_type": template["action_type"],
        "component": template["component"],
        "engine_position": anomaly["engine_position"],
        "ata_chapter": ATA_CHAPTERS.get(anomaly["sensor_type"], "00-00"),
        "description": description,
        "tasks": [template["task"]],
        "required_skills": template["skills"],
        "required_tools": template["tools"],
        "estimated_duration_hours": template["estimated_hours"],
        "estimated_cost_usd": estimated_cost,
        "parts_needed": parts_needed,
        "anomaly_references": [
            {"sensor": anomaly["sensor_type"], "severity": anomaly["severity"], "score": anomaly["anomaly_score"]}
        ],
        "correlated": False,
        "status": "CREATED",
    }


def _lookup_required_parts(cur, sensor_type, aircraft) -> list:
    """Look up parts that may be needed for the repair."""
    category_map = {
        "ENGINE_VIBRATION_N1": "ENGINE",
        "ENGINE_VIBRATION_N2": "ENGINE",
        "OIL_TEMP": "ENGINE",
        "OIL_PRESSURE": "ENGINE",
        "EGT": "ENGINE",
        "HYDRAULIC_PRESSURE": "HYDRAULIC",
        "FUEL_FLOW": "ENGINE",
        "BLEED_AIR_TEMP": "PNEUMATIC",
    }
    category = category_map.get(sensor_type, "ENGINE")
    aircraft_type = aircraft["aircraft_type"] if aircraft else ""

    cur.execute(
        """
        SELECT part_number, description, unit_cost_usd, lead_time_days, compatible_aircraft
        FROM parts_inventory
        WHERE component_category = %s
        AND (compatible_aircraft LIKE %s OR compatible_aircraft = 'All')
        LIMIT 5
        """,
        (category, f"%{aircraft_type}%"),
    )
    rows = cur.fetchall()
    return [
        {
            "part_number": r["part_number"],
            "description": r["description"],
            "unit_cost_usd": float(r["unit_cost_usd"]),
            "lead_time_days": r["lead_time_days"],
        }
        for r in rows
    ]
