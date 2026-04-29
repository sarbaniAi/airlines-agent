"""
Weather & NOTAM Agent (V2)
Checks weather at origin/destination, evaluates operational minima,
and RAGs against Dispatch SOPs for weather-related procedures.
"""

import logging
from typing import Any

from tools.sql_tools import query_table
from tools.vector_search_tools import search_dispatch_sops
from tools.llm_tools import llm_call
from tools.weather_api import get_live_weather

logger = logging.getLogger("agents.weather_notam")

# Operational minima thresholds
OPERATIONAL_LIMITS = {
    "visibility_cat_i": 0.8,       # km
    "visibility_cat_ii": 0.4,      # km
    "visibility_cat_iii": 0.2,     # km
    "ceiling_cat_i": 200,          # ft AGL
    "ceiling_cat_ii": 100,         # ft AGL
    "crosswind_limit_dry": 38,     # kts
    "crosswind_limit_wet": 25,     # kts
    "tailwind_limit": 15,          # kts
    "wind_gust_limit": 45,         # kts
    "visibility_amber": 3.0,       # km
    "ceiling_amber": 1000,         # ft
}

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
    """Evaluate weather conditions for an airport (origin or destination)."""
    findings = []
    recommendations = []
    status = "GREEN"

    airport_name = AIRPORT_NAMES.get(airport_code, airport_code)
    vis = float(weather.get("visibility_km", 10))
    wind = int(float(weather.get("wind_speed_kts", 0)))
    ceiling = weather.get("ceiling_ft")
    if ceiling is not None:
        ceiling = int(float(ceiling))
    conditions = weather.get("conditions", "")
    temp = float(weather.get("temperature_c", 20))

    # Visibility
    if vis < OPERATIONAL_LIMITS["visibility_cat_iii"]:
        status = "RED"
        findings.append(
            f"{role.upper()} ({airport_code}): Visibility {vis} km - BELOW CAT III minimums. "
            f"Airport effectively closed."
        )
        recommendations.append(f"Hold or divert from {airport_code}")
    elif vis < OPERATIONAL_LIMITS["visibility_cat_i"]:
        status = "RED" if role == "destination" else "AMBER"
        findings.append(
            f"{role.upper()} ({airport_code}): Visibility {vis} km - requires CAT II/III approach. "
            f"Verify crew CAT II/III certification."
        )
        recommendations.append("Confirm CAT II/III approach capability and crew qualification")
    elif vis < OPERATIONAL_LIMITS["visibility_amber"]:
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{role.upper()} ({airport_code}): Reduced visibility {vis} km - conditions: {conditions}"
        )

    # Ceiling
    if ceiling is not None:
        if ceiling < OPERATIONAL_LIMITS["ceiling_cat_ii"]:
            status = "RED"
            findings.append(
                f"{role.upper()} ({airport_code}): Very low ceiling {ceiling} ft AGL - "
                f"CAT III approach required"
            )
        elif ceiling < OPERATIONAL_LIMITS["ceiling_cat_i"]:
            if status != "RED":
                status = "AMBER"
            findings.append(
                f"{role.upper()} ({airport_code}): Low ceiling {ceiling} ft AGL - "
                f"CAT II/III approach may be required"
            )
        elif ceiling < OPERATIONAL_LIMITS["ceiling_amber"]:
            if status == "GREEN":
                status = "AMBER"
            findings.append(
                f"{role.upper()} ({airport_code}): Ceiling {ceiling} ft - below 1000 ft, "
                f"monitor for deterioration"
            )

    # Wind
    if wind > OPERATIONAL_LIMITS["crosswind_limit_dry"]:
        status = "RED"
        findings.append(
            f"{role.upper()} ({airport_code}): Wind {wind} kts - exceeds crosswind limit"
        )
        recommendations.append(f"Hold or divert - wind exceeds limits at {airport_code}")
    elif wind > OPERATIONAL_LIMITS["crosswind_limit_wet"]:
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{role.upper()} ({airport_code}): Wind {wind} kts - "
            f"may exceed limits if runway is wet/contaminated"
        )

    # Hazardous conditions
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
            f"{role.upper()} ({airport_code}): Snow reported - temperature {temp}C, visibility {vis} km"
        )
        recommendations.append(
            f"Check runway braking action at {airport_code}. De-icing may be required."
        )
    elif conditions == "FG":
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{role.upper()} ({airport_code}): Fog reported - visibility {vis} km"
        )

    return {
        "airport_code": airport_code,
        "airport_name": airport_name,
        "role": role,
        "status": status,
        "metar": weather.get("metar_raw", ""),
        "findings": findings,
        "recommendations": recommendations,
    }


def run(origin: str, destination: str) -> dict[str, Any]:
    """
    Run weather & NOTAM check for origin and destination airports.

    Returns:
        dict with keys: status, findings, recommendations, sop_references, details
    """
    findings: list[str] = []
    recommendations: list[str] = []
    sop_references: list[str] = []
    status = "GREEN"
    details: dict[str, Any] = {"airports": []}

    try:
        for airport_code, role in [(origin, "origin"), (destination, "destination")]:
            # Fetch REAL-TIME weather from Open-Meteo API
            wx = get_live_weather(airport_code)
            logger.info(f"Live weather for {airport_code}: {wx.get('conditions')} {wx.get('temperature_c')}C vis={wx.get('visibility_km')}km wind={wx.get('wind_speed_kts')}kts [source: {wx.get('source')}]")

            if wx.get("conditions") == "UNKNOWN" or wx.get("visibility_km") is None:
                findings.append(
                    f"No weather data available for {role} ({airport_code}) - "
                    f"manual weather check required"
                )
                if status == "GREEN":
                    status = "AMBER"
                continue

            wx_result = _evaluate_weather(wx, airport_code, role)
            # Add country + source to the result
            wx_result["country"] = wx.get("country", "")
            wx_result["source"] = wx.get("source", "")
            wx_result["hazards"] = wx.get("hazards", [])

            # Always add a real-time weather summary line (even when GREEN)
            temp = wx.get("temperature_c", "?")
            vis = wx.get("visibility_km", "?")
            wind = wx.get("wind_speed_kts", "?")
            gusts = wx.get("wind_gusts_kts", "?")
            ceil = wx.get("ceiling_ft", "?")
            cond = wx.get("conditions", "?")
            country = wx.get("country", "")
            airport_name = wx.get("airport_name", airport_code)
            summary = (
                f"{role.upper()} ({airport_code}, {country}): {airport_name} — "
                f"{temp}°C, vis {vis}km, wind {wind}kts (gusts {gusts}kts), "
                f"ceiling {ceil}ft, conditions: {cond} [{wx.get('source', 'Live')}]"
            )
            # Insert summary at the beginning of this airport's findings
            if wx_result["findings"]:
                wx_result["findings"].insert(0, summary)
            else:
                wx_result["findings"] = [summary]
            details["airports"].append(wx_result)

            if wx_result["status"] == "RED":
                status = "RED"
            elif wx_result["status"] == "AMBER" and status != "RED":
                status = "AMBER"

            findings.extend(wx_result["findings"])
            recommendations.extend(wx_result["recommendations"])

        # ── RAG: Dispatch SOPs for weather procedures ──────────────────────
        if status != "GREEN":
            # Build a targeted search query from actual weather conditions
            weather_issues = " ".join(findings[:5])
            rag_query = (
                f"Dispatch procedures for weather conditions: {weather_issues}. "
                f"Low visibility fog thunderstorm wind limits operational minima "
                f"CAT II CAT III approach"
            )

            sop_results = search_dispatch_sops(rag_query, num_results=3)

            if sop_results:
                sop_context = "\n".join(
                    f"- {d.get('doc_id', 'N/A')}: {str(d.get('content', ''))[:300]}"
                    for d in sop_results
                )

                sop_assessment = llm_call(
                    system_prompt=(
                        "You are an airline dispatch operations expert. Given the weather findings "
                        "and relevant SOPs, provide specific operational guidance and SOP references "
                        "for the dispatcher. Be precise with SOP section numbers. Keep under 200 words."
                    ),
                    user_prompt=(
                        f"Origin: {origin}, Destination: {destination}\n"
                        f"Weather findings:\n" + "\n".join(findings) + "\n\n"
                        f"Relevant SOPs:\n{sop_context}\n\n"
                        f"Provide operational guidance with SOP references."
                    ),
                    max_tokens=400,
                )

                if sop_assessment:
                    recommendations.append(f"SOP Guidance: {sop_assessment}")

                for d in sop_results:
                    sop_references.append(
                        f"Ref: {d.get('doc_id', 'N/A')} - {d.get('title', d.get('section', ''))}"
                    )

    except Exception as e:
        logger.error("Weather/NOTAM agent error: %s", e, exc_info=True)
        return {
            "status": "RED",
            "findings": [f"Agent error: {str(e)}"],
            "recommendations": ["Manual weather check required"],
            "sop_references": [],
            "details": {},
        }

    if not findings:
        findings.append(
            f"Weather conditions nominal at both {origin} and {destination} (Real-time data)"
        )

    return {
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
        "sop_references": sop_references,
        "details": details,
        "data_source": "Open-Meteo Real-Time API",
    }
