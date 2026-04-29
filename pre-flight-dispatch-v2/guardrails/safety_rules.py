"""
Pre-Flight Dispatch V2 — Hard-Coded Safety Rules.

These rules are NEVER overridden by the LLM. They represent absolute
regulatory and safety constraints that must be enforced deterministically.
"""

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger("guardrails.safety_rules")


# ---------------------------------------------------------------------------
# Safety Rule Definitions
# ---------------------------------------------------------------------------

SAFETY_RULES: list[dict[str, Any]] = [
    {
        "id": "SR-001",
        "name": "Expired Regulatory Certificate",
        "condition": "Any mandatory certificate (COA, ETOPS, RVSM, Airworthiness, Insurance) is EXPIRED",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "regulatory",
    },
    {
        "id": "SR-002",
        "name": "Missing Mandatory Certificate",
        "condition": "Any mandatory certificate for the destination is MISSING from the database",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "regulatory",
    },
    {
        "id": "SR-003",
        "name": "Expired Airworthiness Certificate",
        "condition": "Aircraft airworthiness certificate is expired or missing",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "aircraft",
    },
    {
        "id": "SR-004",
        "name": "Aircraft Not Serviceable",
        "condition": "Aircraft status is AOG (Aircraft on Ground) or IN_MAINTENANCE",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "aircraft",
    },
    {
        "id": "SR-005",
        "name": "Expired MEL Category-A Item",
        "condition": "Any MEL Category-A deferral has expired (past its rectification deadline)",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "aircraft",
    },
    {
        "id": "SR-006",
        "name": "C-Check Overdue",
        "condition": "Aircraft C-Check is overdue (past the scheduled date)",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "aircraft",
    },
    {
        "id": "SR-007",
        "name": "Crew Medical Expired",
        "condition": "Any assigned crew member has an expired medical certificate",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "crew",
    },
    {
        "id": "SR-008",
        "name": "Crew Duty Hours Exceeded (7-Day)",
        "condition": "Any crew member exceeds the DGCA 7-day duty hour limit (55 hours)",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "crew",
    },
    {
        "id": "SR-009",
        "name": "Crew Duty Hours Exceeded (28-Day)",
        "condition": "Any crew member exceeds the DGCA 28-day duty hour limit (180 hours)",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "crew",
    },
    {
        "id": "SR-010",
        "name": "Crew Insufficient Rest",
        "condition": "Any crew member has not met minimum rest requirements (12h domestic / 14h international)",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "crew",
    },
    {
        "id": "SR-011",
        "name": "Crew Missing Route Qualification",
        "condition": "Any crew member lacks required route qualifications for the destination",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "crew",
    },
    {
        "id": "SR-012",
        "name": "Weather Below CAT III Minimums",
        "condition": "Destination visibility below CAT III minimums (< 0.2 km) with no forecast improvement",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "weather",
    },
    {
        "id": "SR-013",
        "name": "Destination Wind Exceeds Limits",
        "condition": "Destination wind speed exceeds aircraft crosswind limit (> 38 kts)",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "weather",
    },
    {
        "id": "SR-014",
        "name": "Active Thunderstorm at Destination",
        "condition": "Active thunderstorm (TS/TS+) reported at destination with RED weather status",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "weather",
    },
    {
        "id": "SR-015",
        "name": "Expired Insurance Certificate",
        "condition": "Aircraft insurance certificate is expired",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 1,
        "category": "regulatory",
    },
    {
        "id": "SR-016",
        "name": "Critical Fatigue Risk",
        "condition": "Any crew member has a fatigue risk score >= 75/100",
        "action": "NO-GO",
        "override_allowed": False,
        "priority": 2,
        "category": "crew",
    },
    {
        "id": "SR-017",
        "name": "Multiple Amber Findings",
        "condition": "Three or more agents report AMBER status simultaneously",
        "action": "CONDITIONAL",
        "override_allowed": True,
        "priority": 3,
        "category": "compound",
    },
    {
        "id": "SR-018",
        "name": "Crew Medical Expiring Within 7 Days",
        "condition": "Any crew member medical certificate expires within 7 days",
        "action": "CONDITIONAL",
        "override_allowed": True,
        "priority": 3,
        "category": "crew",
    },
]


# ---------------------------------------------------------------------------
# Rule Evaluation Engine
# ---------------------------------------------------------------------------

def _parse_date_safe(val) -> date | None:
    """Parse a date value that may be a string, date, datetime, or None."""
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


def evaluate_safety_rules(agent_results: dict[str, dict]) -> list[dict[str, Any]]:
    """
    Evaluate all hard-coded safety rules against agent results.

    Args:
        agent_results: Dict of agent_name -> agent_result (as returned by each agent).
            Expected keys: aircraft_health, crew_legality, weather_slots, regulatory_compliance

    Returns:
        List of triggered rules, each containing:
            rule_id, rule_name, category, forced_action, override_allowed,
            trigger_details (human-readable explanation of why it fired)
    """
    triggered: list[dict[str, Any]] = []
    today = date.today()

    aircraft = agent_results.get("aircraft_health", {})
    crew = agent_results.get("crew_legality", {})
    weather = agent_results.get("weather_slots", {})
    regulatory = agent_results.get("regulatory_compliance", {})

    aircraft_findings = " ".join(aircraft.get("findings", [])).lower()
    crew_findings = " ".join(crew.get("findings", [])).lower()
    weather_findings = " ".join(weather.get("findings", [])).lower()
    regulatory_findings = " ".join(regulatory.get("findings", [])).lower()

    # --- SR-001: Expired Regulatory Certificate ---
    compliance_gaps = regulatory.get("details", {}).get("compliance_gaps", [])
    for gap in compliance_gaps:
        if "expired" in str(gap.get("issue", "")).lower():
            triggered.append({
                "rule_id": "SR-001",
                "rule_name": "Expired Regulatory Certificate",
                "category": "regulatory",
                "forced_action": "NO-GO",
                "override_allowed": False,
                "trigger_details": f"Certificate expired: {gap.get('requirement', 'unknown')} "
                                   f"for {gap.get('country', 'unknown')} — {gap.get('issue', '')}",
            })

    # --- SR-002: Missing Mandatory Certificate ---
    for gap in compliance_gaps:
        if "no " in str(gap.get("issue", "")).lower() and "found" in str(gap.get("issue", "")).lower():
            triggered.append({
                "rule_id": "SR-002",
                "rule_name": "Missing Mandatory Certificate",
                "category": "regulatory",
                "forced_action": "NO-GO",
                "override_allowed": False,
                "trigger_details": f"Missing certificate: {gap.get('requirement', 'unknown')} "
                                   f"for {gap.get('country', 'unknown')}",
            })

    # --- SR-003: Expired Airworthiness ---
    if "airworthiness" in regulatory_findings and ("expired" in regulatory_findings or "missing" in regulatory_findings):
        triggered.append({
            "rule_id": "SR-003",
            "rule_name": "Expired Airworthiness Certificate",
            "category": "aircraft",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": "Airworthiness certificate is expired or missing",
        })

    # --- SR-004: Aircraft Not Serviceable ---
    aircraft_detail = aircraft.get("details", {}).get("aircraft", {})
    ac_status = str(aircraft_detail.get("status", "")).upper()
    if ac_status in ("AOG", "IN_MAINTENANCE", "GROUNDED"):
        triggered.append({
            "rule_id": "SR-004",
            "rule_name": "Aircraft Not Serviceable",
            "category": "aircraft",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": f"Aircraft status is {ac_status}",
        })

    # --- SR-005: Expired MEL Cat-A ---
    mel_items = aircraft.get("details", {}).get("mel_items", [])
    for mel in mel_items:
        if str(mel.get("category", "")).upper() == "A":
            expiry = _parse_date_safe(mel.get("expiry_date"))
            if expiry and expiry < today:
                triggered.append({
                    "rule_id": "SR-005",
                    "rule_name": "Expired MEL Category-A Item",
                    "category": "aircraft",
                    "forced_action": "NO-GO",
                    "override_allowed": False,
                    "trigger_details": f"MEL Cat-A item {mel.get('item_code', '?')} expired on {expiry}",
                })

    # --- SR-006: C-Check Overdue ---
    if "c-check overdue" in aircraft_findings or "c-check" in aircraft_findings and "overdue" in aircraft_findings:
        triggered.append({
            "rule_id": "SR-006",
            "rule_name": "C-Check Overdue",
            "category": "aircraft",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": "Aircraft C-Check is overdue",
        })

    # --- SR-007: Crew Medical Expired ---
    crew_checks = crew.get("details", {}).get("crew_checks", [])
    for cc in crew_checks:
        member_findings = " ".join(cc.get("findings", [])).lower()
        if "medical" in member_findings and "expired" in member_findings:
            triggered.append({
                "rule_id": "SR-007",
                "rule_name": "Crew Medical Expired",
                "category": "crew",
                "forced_action": "NO-GO",
                "override_allowed": False,
                "trigger_details": f"{cc.get('name', 'Unknown')} ({cc.get('rank', '?')}): Medical certificate expired",
            })

    # --- SR-008: 7-Day Duty Exceeded ---
    if "exceeds 7-day duty limit" in crew_findings:
        triggered.append({
            "rule_id": "SR-008",
            "rule_name": "Crew Duty Hours Exceeded (7-Day)",
            "category": "crew",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": "Crew member exceeds DGCA 7-day duty hour limit (55h)",
        })

    # --- SR-009: 28-Day Duty Exceeded ---
    if "exceeds 28-day duty limit" in crew_findings:
        triggered.append({
            "rule_id": "SR-009",
            "rule_name": "Crew Duty Hours Exceeded (28-Day)",
            "category": "crew",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": "Crew member exceeds DGCA 28-day duty hour limit (180h)",
        })

    # --- SR-010: Insufficient Rest ---
    if "insufficient rest" in crew_findings:
        triggered.append({
            "rule_id": "SR-010",
            "rule_name": "Crew Insufficient Rest",
            "category": "crew",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": "Crew member has not met minimum rest requirements",
        })

    # --- SR-011: Missing Route Qualifications ---
    if "missing route qualifications" in crew_findings:
        triggered.append({
            "rule_id": "SR-011",
            "rule_name": "Crew Missing Route Qualification",
            "category": "crew",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": "Crew member not qualified for the destination route",
        })

    # --- SR-012: Weather Below CAT III ---
    if "below cat iii" in weather_findings or "effectively closed" in weather_findings:
        triggered.append({
            "rule_id": "SR-012",
            "rule_name": "Weather Below CAT III Minimums",
            "category": "weather",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": "Destination visibility below CAT III minimums (< 0.2 km)",
        })

    # --- SR-013: Wind Exceeds Limits ---
    if "exceeds crosswind limit" in weather_findings:
        triggered.append({
            "rule_id": "SR-013",
            "rule_name": "Destination Wind Exceeds Limits",
            "category": "weather",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": "Destination wind speed exceeds aircraft crosswind limit",
        })

    # --- SR-014: Thunderstorm ---
    weather_airports = weather.get("details", {}).get("airports", [])
    for ap in weather_airports:
        if ap.get("role") == "destination" and ap.get("status") == "RED":
            ap_findings_lower = " ".join(ap.get("findings", [])).lower()
            if "thunderstorm" in ap_findings_lower:
                triggered.append({
                    "rule_id": "SR-014",
                    "rule_name": "Active Thunderstorm at Destination",
                    "category": "weather",
                    "forced_action": "NO-GO",
                    "override_allowed": False,
                    "trigger_details": f"Active thunderstorm at destination ({ap.get('airport_code', '?')})",
                })

    # --- SR-015: Expired Insurance ---
    if "insurance" in regulatory_findings and "expired" in regulatory_findings:
        triggered.append({
            "rule_id": "SR-015",
            "rule_name": "Expired Insurance Certificate",
            "category": "regulatory",
            "forced_action": "NO-GO",
            "override_allowed": False,
            "trigger_details": "Aircraft insurance certificate is expired",
        })

    # --- SR-016: Critical Fatigue ---
    for cc in crew_checks:
        member_findings = " ".join(cc.get("findings", [])).lower()
        if "high fatigue risk" in member_findings:
            triggered.append({
                "rule_id": "SR-016",
                "rule_name": "Critical Fatigue Risk",
                "category": "crew",
                "forced_action": "NO-GO",
                "override_allowed": False,
                "trigger_details": f"{cc.get('name', 'Unknown')}: Fatigue risk score >= 75",
            })

    # --- SR-017: Multiple Amber ---
    amber_agents = [
        name for name, result in agent_results.items()
        if result.get("status") == "AMBER"
    ]
    if len(amber_agents) >= 3:
        triggered.append({
            "rule_id": "SR-017",
            "rule_name": "Multiple Amber Findings",
            "category": "compound",
            "forced_action": "CONDITIONAL",
            "override_allowed": True,
            "trigger_details": f"AMBER status in {len(amber_agents)} agents: {', '.join(amber_agents)}",
        })

    # --- SR-018: Medical Expiring Within 7 Days ---
    for cc in crew_checks:
        member_findings = " ".join(cc.get("findings", [])).lower()
        if "medical certificate expiring in" in member_findings:
            # Extract days remaining
            import re
            days_match = re.search(r"expiring in (\d+) days", member_findings)
            if days_match and int(days_match.group(1)) <= 7:
                triggered.append({
                    "rule_id": "SR-018",
                    "rule_name": "Crew Medical Expiring Within 7 Days",
                    "category": "crew",
                    "forced_action": "CONDITIONAL",
                    "override_allowed": True,
                    "trigger_details": f"{cc.get('name', 'Unknown')}: Medical expires in {days_match.group(1)} days",
                })

    # Sort by priority (lower = higher priority)
    triggered.sort(key=lambda r: (
        0 if r["forced_action"] == "NO-GO" else 1,
        r["rule_id"],
    ))

    logger.info(f"Safety rules evaluation: {len(triggered)} rule(s) triggered")
    for t in triggered:
        logger.info(f"  [{t['rule_id']}] {t['rule_name']} -> {t['forced_action']}: {t['trigger_details']}")

    return triggered


def get_most_severe_action(triggered_rules: list[dict]) -> str:
    """Return the most severe action from a list of triggered rules."""
    if not triggered_rules:
        return "GO"
    actions = [r["forced_action"] for r in triggered_rules]
    if "NO-GO" in actions:
        return "NO-GO"
    if "CONDITIONAL" in actions:
        return "CONDITIONAL"
    return "GO"


def get_rules_summary() -> list[dict]:
    """Return a summary of all safety rules for display."""
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "condition": r["condition"],
            "action": r["action"],
            "override_allowed": r["override_allowed"],
            "category": r["category"],
        }
        for r in SAFETY_RULES
    ]
