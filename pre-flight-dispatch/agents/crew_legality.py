"""
Crew Legality Agent
Checks DGCA duty hour limits, fatigue rules, certifications, and route qualifications.
"""

import os
import logging
from datetime import date, datetime
from typing import Any


def _parse_date(val):
    """Parse a date value that may be a string, date, or None."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

import psycopg2
import psycopg2.extras

from db import get_db

logger = logging.getLogger("agents.crew_legality")

# DGCA CAR Section 5 — Flight Duty Time Limitations
DGCA_LIMITS = {
    "duty_hours_7d": 55.0,       # Max 55 hours in any 7 consecutive days
    "duty_hours_28d": 180.0,     # Max 180 hours in any 28 consecutive days
    "min_rest_hours": 12.0,      # Minimum rest between duties (domestic)
    "min_rest_hours_intl": 14.0, # Minimum rest for international (ultra long haul)
    "fatigue_amber_threshold": 50.0,
    "fatigue_red_threshold": 75.0,
}

# Route qualification mapping
DESTINATION_QUALIFICATIONS = {
    "YYZ": ["NAM", "ETOPS"],
    "YVR": ["NAM", "ETOPS"],
    "JFK": ["NAM", "ETOPS"],
    "SFO": ["NAM", "ETOPS"],
    "LHR": ["EUR", "ETOPS"],
    "SIN": ["APAC"],
    "BOM": ["DOM"],
    "DEL": ["DOM"],
    "BLR": ["DOM"],
}




def _check_crew_member(crew: dict, destination: str, is_international: bool) -> dict:
    """Check a single crew member against DGCA regulations."""
    findings = []
    recommendations = []
    status = "GREEN"

    name = crew["name"]
    rank = crew["rank"]

    # 1. Duty hours — 7-day limit
    hours_7d = float(crew["duty_hours_last_7d"])
    limit_7d = DGCA_LIMITS["duty_hours_7d"]
    remaining_7d = limit_7d - hours_7d

    if hours_7d >= limit_7d:
        status = "RED"
        findings.append(
            f"{name} ({rank}): EXCEEDS 7-day duty limit — "
            f"{hours_7d}h / {limit_7d}h max"
        )
        recommendations.append(f"Replace {name} — 7-day duty limit exceeded")
    elif remaining_7d <= 5:
        status = "AMBER"
        findings.append(
            f"{name} ({rank}): Approaching 7-day duty limit — "
            f"{hours_7d}h / {limit_7d}h (only {remaining_7d}h remaining)"
        )
        recommendations.append(
            f"Monitor {name}'s duty hours closely; consider replacement if flight exceeds {remaining_7d}h"
        )

    # 2. Duty hours — 28-day limit
    hours_28d = float(crew["duty_hours_last_28d"])
    limit_28d = DGCA_LIMITS["duty_hours_28d"]
    remaining_28d = limit_28d - hours_28d

    if hours_28d >= limit_28d:
        status = "RED"
        findings.append(
            f"{name} ({rank}): EXCEEDS 28-day duty limit — "
            f"{hours_28d}h / {limit_28d}h max"
        )
        recommendations.append(f"Replace {name} — 28-day duty limit exceeded")
    elif remaining_28d <= 20:
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{name} ({rank}): Approaching 28-day limit — "
            f"{hours_28d}h / {limit_28d}h ({remaining_28d}h remaining)"
        )

    # 3. Rest period
    rest_hours = float(crew["rest_hours_since_last_duty"])
    min_rest = (
        DGCA_LIMITS["min_rest_hours_intl"]
        if is_international
        else DGCA_LIMITS["min_rest_hours"]
    )
    if rest_hours < min_rest:
        status = "RED"
        findings.append(
            f"{name} ({rank}): Insufficient rest — {rest_hours}h "
            f"(minimum {min_rest}h required for {'international' if is_international else 'domestic'})"
        )
        recommendations.append(
            f"Replace {name} or delay departure until rest requirement met"
        )

    # 4. Fatigue risk score
    fatigue = float(crew["fatigue_risk_score"])
    if fatigue >= DGCA_LIMITS["fatigue_red_threshold"]:
        status = "RED"
        findings.append(
            f"{name} ({rank}): HIGH fatigue risk score — {fatigue}/100"
        )
        recommendations.append(f"Replace {name} due to high fatigue risk")
    elif fatigue >= DGCA_LIMITS["fatigue_amber_threshold"]:
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{name} ({rank}): Elevated fatigue risk score — {fatigue}/100"
        )

    # 5. Medical certificate validity
    medical_exp = _parse_date(crew["medical_expiry"])
    if medical_exp and medical_exp < date.today():
        status = "RED"
        findings.append(
            f"{name} ({rank}): Medical certificate EXPIRED on {medical_exp}"
        )
        recommendations.append(
            f"GROUND {name} — expired medical certificate. Replace immediately."
        )
    elif medical_exp and (medical_exp - date.today()).days < 30:
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{name} ({rank}): Medical certificate expiring in "
            f"{(medical_exp - date.today()).days} days ({medical_exp})"
        )

    # 6. Route qualifications
    required_quals = DESTINATION_QUALIFICATIONS.get(destination, [])
    crew_quals = crew["route_qualifications"] or []
    missing_quals = [q for q in required_quals if q not in crew_quals]

    if missing_quals:
        status = "RED"
        findings.append(
            f"{name} ({rank}): Missing route qualifications for {destination}: "
            f"{', '.join(missing_quals)}"
        )
        recommendations.append(
            f"Replace {name} — not qualified for {destination} route"
        )

    return {
        "crew_id": crew["crew_id"],
        "name": name,
        "rank": rank,
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
    }


async def run(captain_id: str, first_officer_id: str, destination: str) -> dict[str, Any]:
    """
    Run crew legality check for the assigned crew.

    Returns:
        dict with keys: status, findings, recommendations, details
    """
    findings = []
    recommendations = []
    status = "GREEN"
    details = {"crew_checks": []}

    is_international = destination not in ("DEL", "BOM", "BLR", "MAA", "CCU", "HYD")

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        for crew_id in [captain_id, first_officer_id]:
            cur.execute("SELECT * FROM crew_roster WHERE crew_id = %s", (crew_id,))
            crew = cur.fetchone()

            if not crew:
                findings.append(f"Crew member {crew_id} not found in roster")
                status = "RED"
                recommendations.append(f"Verify crew assignment for {crew_id}")
                continue

            check_result = _check_crew_member(dict(crew), destination, is_international)
            details["crew_checks"].append(check_result)

            # Roll up status
            if check_result["status"] == "RED":
                status = "RED"
            elif check_result["status"] == "AMBER" and status != "RED":
                status = "AMBER"

            findings.extend(check_result["findings"])
            recommendations.extend(check_result["recommendations"])

        cur.close()
        conn.close()

    except psycopg2.Error as e:
        logger.error(f"Database error in crew legality agent: {e}")
        return {
            "status": "RED",
            "findings": [f"Database error: {str(e)}"],
            "recommendations": ["Check Lakebase connectivity"],
            "details": {},
        }

    if not findings:
        findings.append("All crew members meet DGCA duty time and qualification requirements")

    return {
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
        "details": details,
    }
