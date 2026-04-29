"""
Weather & Slots Agent
Checks weather at origin/destination, NOTAM alerts, and operational minima.
"""

import os
import logging
from typing import Any

import psycopg2
import psycopg2.extras

from db import get_db

logger = logging.getLogger("agents.weather_slots")

# Operational minima thresholds
OPERATIONAL_LIMITS = {
    "visibility_cat_i": 0.8,     # km — CAT I minimum
    "visibility_cat_ii": 0.4,    # km — CAT II minimum
    "visibility_cat_iii": 0.2,   # km — CAT III minimum
    "ceiling_cat_i": 200,        # ft — Decision height CAT I
    "ceiling_cat_ii": 100,       # ft — Decision height CAT II
    "crosswind_limit_dry": 38,   # kts — max crosswind dry runway
    "crosswind_limit_wet": 25,   # kts — max crosswind wet/contaminated
    "tailwind_limit": 15,        # kts
    "wind_gust_limit": 45,       # kts
    "visibility_amber": 3.0,     # km — trigger amber
    "ceiling_amber": 1000,       # ft — trigger amber
}

# Airport info
AIRPORT_NAMES = {
    "DEL": "Indira Gandhi International, Delhi",
    "BOM": "Chhatrapati Shivaji Maharaj International, Mumbai",
    "YYZ": "Toronto Pearson International",
    "LHR": "London Heathrow",
    "SIN": "Singapore Changi",
    "BLR": "Kempegowda International, Bengaluru",
    "JFK": "John F. Kennedy International, New York",
    "SFO": "San Francisco International",
    "YVR": "Vancouver International",
}




def _evaluate_weather(weather: dict, airport_code: str, role: str) -> dict:
    """
    Evaluate weather conditions for an airport.
    role: 'origin' or 'destination'
    """
    findings = []
    recommendations = []
    status = "GREEN"

    airport_name = AIRPORT_NAMES.get(airport_code, airport_code)
    vis = float(weather["visibility_km"])
    wind = int(weather["wind_speed_kts"])
    ceiling = weather["ceiling_ft"]
    conditions = weather["conditions"]
    temp = float(weather["temperature_c"])

    # Visibility assessment
    if vis < OPERATIONAL_LIMITS["visibility_cat_iii"]:
        status = "RED"
        findings.append(
            f"{role.upper()} ({airport_code}): Visibility {vis} km — BELOW CAT III minimums. "
            f"Airport effectively closed."
        )
        recommendations.append(f"Hold or divert from {airport_code}")
    elif vis < OPERATIONAL_LIMITS["visibility_cat_i"]:
        status = "RED" if role == "destination" else "AMBER"
        findings.append(
            f"{role.upper()} ({airport_code}): Visibility {vis} km — requires CAT II/III approach. "
            f"Verify crew CAT II/III certification."
        )
        recommendations.append(f"Confirm CAT II/III approach capability and crew qualification")
    elif vis < OPERATIONAL_LIMITS["visibility_amber"]:
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{role.upper()} ({airport_code}): Reduced visibility {vis} km — "
            f"conditions: {conditions}"
        )

    # Ceiling assessment
    if ceiling is not None:
        if ceiling < OPERATIONAL_LIMITS["ceiling_cat_i"]:
            if status != "RED":
                status = "AMBER" if ceiling >= OPERATIONAL_LIMITS["ceiling_cat_ii"] else "RED"
            findings.append(
                f"{role.upper()} ({airport_code}): Low ceiling {ceiling} ft AGL — "
                f"{'CAT II/III approach required' if ceiling < OPERATIONAL_LIMITS['ceiling_cat_i'] else 'monitor'}"
            )
        elif ceiling < OPERATIONAL_LIMITS["ceiling_amber"]:
            if status == "GREEN":
                status = "AMBER"
            findings.append(
                f"{role.upper()} ({airport_code}): Ceiling {ceiling} ft — below 1000 ft, "
                f"monitor for deterioration"
            )

    # Wind assessment
    if wind > OPERATIONAL_LIMITS["crosswind_limit_dry"]:
        status = "RED"
        findings.append(
            f"{role.upper()} ({airport_code}): Wind {wind} kts from {weather['wind_direction']}° — "
            f"exceeds crosswind limit"
        )
        recommendations.append(f"Hold or divert — wind exceeds operating limits at {airport_code}")
    elif wind > OPERATIONAL_LIMITS["crosswind_limit_wet"]:
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{role.upper()} ({airport_code}): Wind {wind} kts — "
            f"may exceed limits if runway is wet/contaminated"
        )

    # Specific hazardous conditions
    if conditions in ("TS", "TS+"):
        status = "RED"
        findings.append(
            f"{role.upper()} ({airport_code}): Thunderstorm activity reported"
        )
        recommendations.append(f"Monitor thunderstorm movement at {airport_code}")
    elif conditions == "SN":
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{role.upper()} ({airport_code}): Snow reported — "
            f"temperature {temp}°C, visibility {vis} km"
        )
        recommendations.append(
            f"Check runway condition (braking action) at {airport_code}. "
            f"De-icing may be required on departure."
        )
    elif conditions == "FG":
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{role.upper()} ({airport_code}): Fog reported — visibility {vis} km"
        )

    return {
        "airport_code": airport_code,
        "airport_name": airport_name,
        "role": role,
        "status": status,
        "metar": weather["metar_raw"],
        "findings": findings,
        "recommendations": recommendations,
    }


async def run(origin: str, destination: str) -> dict[str, Any]:
    """
    Run weather and slots check for origin and destination airports.

    Returns:
        dict with keys: status, findings, recommendations, details
    """
    findings = []
    recommendations = []
    status = "GREEN"
    details = {"airports": []}

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        for airport_code, role in [(origin, "origin"), (destination, "destination")]:
            cur.execute(
                """
                SELECT * FROM weather_conditions
                WHERE airport_code = %s
                ORDER BY observation_time DESC
                LIMIT 1
                """,
                (airport_code,),
            )
            weather = cur.fetchone()

            if not weather:
                findings.append(
                    f"No weather data available for {role} ({airport_code}) — "
                    f"manual weather check required"
                )
                if status == "GREEN":
                    status = "AMBER"
                continue

            wx_result = _evaluate_weather(dict(weather), airport_code, role)
            details["airports"].append(wx_result)

            if wx_result["status"] == "RED":
                status = "RED"
            elif wx_result["status"] == "AMBER" and status != "RED":
                status = "AMBER"

            findings.extend(wx_result["findings"])
            recommendations.extend(wx_result["recommendations"])

        cur.close()
        conn.close()

    except psycopg2.Error as e:
        logger.error(f"Database error in weather agent: {e}")
        return {
            "status": "RED",
            "findings": [f"Database error: {str(e)}"],
            "recommendations": ["Check Lakebase connectivity"],
            "details": {},
        }

    if not findings:
        findings.append(
            f"Weather conditions nominal at both {origin} and {destination}"
        )

    return {
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
        "details": details,
    }
