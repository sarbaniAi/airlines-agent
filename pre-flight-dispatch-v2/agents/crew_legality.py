"""
Crew Legality Agent (V2)
Validates crew against DGCA FDTL limits with RAG-backed regulatory citations.
"""

import logging
from datetime import date, datetime
from typing import Any

from tools.sql_tools import query_table
from tools.vector_search_tools import search_dgca_cars
from tools.llm_tools import llm_call

logger = logging.getLogger("agents.crew_legality")


def _parse_date(val) -> date | None:
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


# DGCA CAR Section 5 — Flight Duty Time Limitations
DGCA_LIMITS = {
    "duty_hours_7d": 55.0,
    "duty_hours_28d": 180.0,
    "min_rest_hours": 12.0,
    "min_rest_hours_intl": 14.0,
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

DOMESTIC_AIRPORTS = {"DEL", "BOM", "BLR", "MAA", "CCU", "HYD"}


def _check_crew_member(crew: dict, destination: str, is_international: bool) -> dict:
    """Check a single crew member against DGCA regulations."""
    findings = []
    recommendations = []
    regulatory_refs = []
    status = "GREEN"

    name = crew.get("name", "Unknown")
    rank = crew.get("rank", "Unknown")

    # 1. Duty hours - 7-day limit
    hours_7d = float(crew.get("duty_hours_last_7d", 0))
    limit_7d = DGCA_LIMITS["duty_hours_7d"]
    remaining_7d = limit_7d - hours_7d

    if hours_7d >= limit_7d:
        status = "RED"
        findings.append(
            f"{name} ({rank}): EXCEEDS 7-day duty limit - "
            f"{hours_7d}h / {limit_7d}h max"
        )
        recommendations.append(f"Replace {name} - 7-day duty limit exceeded")
        regulatory_refs.append("DGCA CAR Section 5 Series J Part I - 7-day FDTL limit")
    elif remaining_7d <= 5:
        status = "AMBER"
        findings.append(
            f"{name} ({rank}): Approaching 7-day duty limit - "
            f"{hours_7d}h / {limit_7d}h (only {remaining_7d}h remaining)"
        )
        recommendations.append(
            f"Monitor {name}'s duty hours closely; consider replacement if flight exceeds {remaining_7d}h"
        )
        regulatory_refs.append("DGCA CAR Section 5 Series J Part I - 7-day FDTL limit")

    # 2. Duty hours - 28-day limit
    hours_28d = float(crew.get("duty_hours_last_28d", 0))
    limit_28d = DGCA_LIMITS["duty_hours_28d"]
    remaining_28d = limit_28d - hours_28d

    if hours_28d >= limit_28d:
        status = "RED"
        findings.append(
            f"{name} ({rank}): EXCEEDS 28-day duty limit - "
            f"{hours_28d}h / {limit_28d}h max"
        )
        recommendations.append(f"Replace {name} - 28-day duty limit exceeded")
        regulatory_refs.append("DGCA CAR Section 5 Series J Part I - 28-day FDTL limit")
    elif remaining_28d <= 20:
        if status == "GREEN":
            status = "AMBER"
        findings.append(
            f"{name} ({rank}): Approaching 28-day limit - "
            f"{hours_28d}h / {limit_28d}h ({remaining_28d}h remaining)"
        )

    # 3. Rest period
    rest_hours = float(crew.get("rest_hours_since_last_duty", 0))
    min_rest = (
        DGCA_LIMITS["min_rest_hours_intl"] if is_international
        else DGCA_LIMITS["min_rest_hours"]
    )
    if rest_hours < min_rest:
        status = "RED"
        route_type = "international" if is_international else "domestic"
        findings.append(
            f"{name} ({rank}): Insufficient rest - {rest_hours}h "
            f"(minimum {min_rest}h required for {route_type})"
        )
        recommendations.append(
            f"Replace {name} or delay departure until rest requirement met"
        )
        regulatory_refs.append(f"DGCA CAR Section 5 - Minimum rest period ({route_type})")

    # 4. Fatigue risk score
    fatigue = float(crew.get("fatigue_risk_score", 0))
    if fatigue >= DGCA_LIMITS["fatigue_red_threshold"]:
        status = "RED"
        findings.append(f"{name} ({rank}): HIGH fatigue risk score - {fatigue}/100")
        recommendations.append(f"Replace {name} due to high fatigue risk")
    elif fatigue >= DGCA_LIMITS["fatigue_amber_threshold"]:
        if status == "GREEN":
            status = "AMBER"
        findings.append(f"{name} ({rank}): Elevated fatigue risk score - {fatigue}/100")

    # 5. Medical certificate validity
    medical_exp = _parse_date(crew.get("medical_expiry"))
    if medical_exp and medical_exp < date.today():
        status = "RED"
        findings.append(
            f"{name} ({rank}): Medical certificate EXPIRED on {medical_exp}"
        )
        recommendations.append(
            f"GROUND {name} - expired medical certificate. Replace immediately."
        )
        regulatory_refs.append("DGCA CAR Section 5 Series F Part III - Medical certification")
    elif medical_exp and (medical_exp - date.today()).days < 30:
        if status == "GREEN":
            status = "AMBER"
        days_left = (medical_exp - date.today()).days
        findings.append(
            f"{name} ({rank}): Medical certificate expiring in {days_left} days ({medical_exp})"
        )

    # 6. Route qualifications
    required_quals = DESTINATION_QUALIFICATIONS.get(destination, [])
    crew_quals = crew.get("route_qualifications") or []
    if isinstance(crew_quals, str):
        import json as _json
        try:
            crew_quals = _json.loads(crew_quals)
        except (ValueError, TypeError):
            crew_quals = [q.strip().strip('"').strip("'") for q in crew_quals.strip("[]").split(",")]
    if isinstance(crew_quals, list):
        crew_quals = [str(q).strip().strip('"').strip("'") for q in crew_quals]
    missing_quals = [q for q in required_quals if q not in crew_quals]

    if missing_quals:
        status = "RED"
        findings.append(
            f"{name} ({rank}): Missing route qualifications for {destination}: "
            f"{', '.join(missing_quals)}"
        )
        recommendations.append(
            f"Replace {name} - not qualified for {destination} route"
        )
        regulatory_refs.append("DGCA CAR Section 7 - Route/Area qualification requirements")

    return {
        "crew_id": crew.get("crew_id", ""),
        "name": name,
        "rank": rank,
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
        "regulatory_references": regulatory_refs,
    }


def run(captain_id: str, first_officer_id: str, destination: str) -> dict[str, Any]:
    """
    Run crew legality check for the assigned crew.

    Returns:
        dict with keys: status, findings, recommendations, regulatory_references, details
    """
    findings: list[str] = []
    recommendations: list[str] = []
    regulatory_references: list[str] = []
    status = "GREEN"
    details: dict[str, Any] = {"crew_checks": []}

    is_international = destination not in DOMESTIC_AIRPORTS

    try:
        for crew_id in [captain_id, first_officer_id]:
            crew_rows = query_table(
                "crew_roster",
                where_clause=f"crew_id = '{crew_id}'",
            )

            if not crew_rows:
                findings.append(f"Crew member {crew_id} not found in roster")
                status = "RED"
                recommendations.append(f"Verify crew assignment for {crew_id}")
                continue

            crew = crew_rows[0]
            check_result = _check_crew_member(crew, destination, is_international)
            details["crew_checks"].append(check_result)

            # Roll up status
            if check_result["status"] == "RED":
                status = "RED"
            elif check_result["status"] == "AMBER" and status != "RED":
                status = "AMBER"

            findings.extend(check_result["findings"])
            recommendations.extend(check_result["recommendations"])
            regulatory_references.extend(check_result["regulatory_references"])

        # ── RAG: DGCA CARs for regulatory context ─────────────────────────
        rag_query = (
            f"DGCA flight duty time limitations for {'international' if is_international else 'domestic'} "
            f"flights crew rest requirements fatigue management"
        )
        dgca_docs = search_dgca_cars(rag_query, num_results=3)

        if dgca_docs and (status != "GREEN"):
            # Use LLM to provide regulatory context for any issues found
            doc_context = "\n".join(
                f"- {d.get('doc_id', 'N/A')}: {str(d.get('content', ''))[:300]}"
                for d in dgca_docs
            )

            reg_assessment = llm_call(
                system_prompt=(
                    "You are a DGCA regulatory expert. Given crew duty/rest findings and "
                    "relevant DGCA CARs, provide specific regulatory citations that apply. "
                    "Be precise with CAR section numbers. Keep response under 200 words."
                ),
                user_prompt=(
                    f"Crew findings:\n" + "\n".join(findings) + "\n\n"
                    f"Relevant DGCA CARs:\n{doc_context}\n\n"
                    f"Provide applicable regulatory citations."
                ),
                max_tokens=400,
            )

            if reg_assessment:
                regulatory_references.append(f"DGCA CAR Analysis: {reg_assessment}")

            # Add doc references
            for d in dgca_docs:
                regulatory_references.append(
                    f"Ref: {d.get('doc_id', 'N/A')} - {d.get('title', d.get('section', ''))}"
                )

    except Exception as e:
        logger.error("Crew legality agent error: %s", e, exc_info=True)
        return {
            "status": "RED",
            "findings": [f"Agent error: {str(e)}"],
            "recommendations": ["Manual crew legality check required"],
            "regulatory_references": [],
            "details": {},
        }

    if not findings:
        findings.append(
            "All crew members meet DGCA duty time and qualification requirements"
        )

    # Deduplicate regulatory references
    regulatory_references = list(dict.fromkeys(regulatory_references))

    return {
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
        "regulatory_references": regulatory_references,
        "details": details,
    }
