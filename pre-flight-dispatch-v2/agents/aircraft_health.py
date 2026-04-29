"""
Aircraft Health Agent (V2)
Checks MEL deferrals, maintenance status, C-check due dates, and
RAGs against Airworthiness Directives via Vector Search.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any

from tools.sql_tools import query_table
from tools.vector_search_tools import search_airworthiness_directives
from tools.llm_tools import llm_call

logger = logging.getLogger("agents.aircraft_health")


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


def run(aircraft_reg: str) -> dict[str, Any]:
    """
    Run aircraft health check for the given registration.

    Returns:
        dict with keys: status, findings, recommendations, applicable_ads, details
    """
    findings: list[str] = []
    recommendations: list[str] = []
    applicable_ads: list[dict] = []
    status = "GREEN"
    details: dict[str, Any] = {}

    try:
        # ── 1. Aircraft fleet status ───────────────────────────────────────
        fleet_rows = query_table(
            "aircraft_fleet",
            where_clause=f"aircraft_reg = '{aircraft_reg}'",
        )

        if not fleet_rows:
            return {
                "status": "RED",
                "findings": [f"Aircraft {aircraft_reg} not found in fleet database"],
                "recommendations": ["Verify aircraft registration"],
                "applicable_ads": [],
                "details": {},
            }

        aircraft = fleet_rows[0]
        details["aircraft"] = aircraft

        # Check serviceable status
        if aircraft.get("status") != "SERVICEABLE":
            status = "RED"
            findings.append(
                f"Aircraft status is {aircraft.get('status')} - not serviceable"
            )
            recommendations.append(
                f"Aircraft {aircraft_reg} cannot be dispatched. Swap to alternate aircraft."
            )

        # Check C-check due date
        next_c = _parse_date(aircraft.get("next_c_check_due"))
        if next_c:
            days_to_c = (next_c - date.today()).days
            if days_to_c < 0:
                status = "RED"
                findings.append(
                    f"C-Check OVERDUE by {abs(days_to_c)} days "
                    f"(was due {aircraft.get('next_c_check_due')})"
                )
                recommendations.append("Ground aircraft immediately for C-Check")
            elif days_to_c < 30:
                if status != "RED":
                    status = "AMBER"
                findings.append(
                    f"C-Check due in {days_to_c} days ({aircraft.get('next_c_check_due')})"
                )
                recommendations.append("Schedule C-Check within next maintenance window")

        # ── 2. MEL items ───────────────────────────────────────────────────
        mel_items = query_table(
            "mel_items",
            where_clause=f"aircraft_reg = '{aircraft_reg}' AND status IN ('OPEN', 'DEFERRED')",
            order_by="category, expiry_date",
        )
        details["mel_items"] = mel_items

        today = date.today()
        tomorrow = today + timedelta(days=1)
        cat_a_count = 0
        cat_b_count = 0

        for mel in mel_items:
            cat = mel.get("category", "")
            expiry = _parse_date(mel.get("expiry_date"))

            if cat == "A":
                cat_a_count += 1
                if expiry and expiry <= today:
                    status = "RED"
                    findings.append(
                        f"MEL Cat-A item {mel['item_code']} EXPIRED on {expiry} - "
                        f"'{mel.get('description', '')}'"
                    )
                    recommendations.append(
                        f"MANDATORY: Rectify {mel['item_code']} before dispatch - Cat-A deferral expired"
                    )
                elif expiry and expiry <= tomorrow:
                    status = "AMBER" if status == "GREEN" else status
                    findings.append(
                        f"MEL Cat-A item {mel['item_code']} ({mel.get('ata_chapter', '')}) "
                        f"expires {expiry} - '{mel.get('description', '')}'"
                    )
                    recommendations.append(
                        f"Rectify MEL {mel['item_code']} before dispatch or within deferral window"
                    )

            elif cat == "B":
                cat_b_count += 1
                if expiry and expiry <= today:
                    status = "RED"
                    findings.append(
                        f"MEL Cat-B item {mel['item_code']} EXPIRED on {expiry}"
                    )
                    recommendations.append(f"Rectify {mel['item_code']} before dispatch")
                elif expiry and expiry <= today + timedelta(days=3):
                    if status == "GREEN":
                        status = "AMBER"
                    findings.append(
                        f"MEL Cat-B item {mel['item_code']} expires in "
                        f"{(expiry - today).days} days - '{mel.get('description', '')}'"
                    )

        total_open = len(mel_items)
        if total_open > 0:
            findings.insert(
                0,
                f"{total_open} open MEL items ({cat_a_count} Cat-A, {cat_b_count} Cat-B)",
            )

        # ── 3. Total flight hours ──────────────────────────────────────────
        hours = aircraft.get("total_flight_hours")
        if hours and float(hours) > 40000:
            if status == "GREEN":
                status = "AMBER"
            findings.append(f"High total flight hours: {float(hours):,.0f} hours")

        # ── 4. RAG: Airworthiness Directives ───────────────────────────────
        aircraft_type = aircraft.get("aircraft_type", "")
        model_variant = aircraft.get("model_variant", "")
        mel_descriptions = " ".join(m.get("description", "") for m in mel_items[:5])

        rag_query = (
            f"Airworthiness directives for {aircraft_type} {model_variant} "
            f"aircraft. MEL items: {mel_descriptions}"
        )

        ad_results = search_airworthiness_directives(rag_query, num_results=5)

        if ad_results:
            for ad in ad_results:
                applicable_ads.append({
                    "doc_id": ad.get("doc_id", ""),
                    "title": ad.get("title", ""),
                    "section": ad.get("section", ""),
                    "content_snippet": str(ad.get("content", ""))[:300],
                    "relevance_score": ad.get("score", 0),
                })

            # Use LLM to assess AD applicability
            ad_context = "\n".join(
                f"- AD {ad.get('doc_id', 'N/A')}: {str(ad.get('content', ''))[:200]}"
                for ad in ad_results[:3]
            )

            ad_assessment = llm_call(
                system_prompt=(
                    "You are an aircraft maintenance engineer. Assess whether the following "
                    "Airworthiness Directives are applicable to this aircraft given its current "
                    "MEL items and maintenance status. Be brief (2-3 sentences max per AD)."
                ),
                user_prompt=(
                    f"Aircraft: {aircraft_reg} ({aircraft_type} {model_variant})\n"
                    f"Open MEL items: {mel_descriptions}\n"
                    f"C-Check due: {aircraft.get('next_c_check_due', 'N/A')}\n\n"
                    f"Airworthiness Directives found:\n{ad_context}\n\n"
                    f"Assess applicability and any dispatch implications."
                ),
                max_tokens=600,
            )

            if ad_assessment:
                findings.append(f"AD Assessment: {ad_assessment}")

        details["applicable_ads"] = applicable_ads

    except Exception as e:
        logger.error("Aircraft health agent error: %s", e, exc_info=True)
        return {
            "status": "RED",
            "findings": [f"Agent error: {str(e)}"],
            "recommendations": ["Manual aircraft health check required"],
            "applicable_ads": [],
            "details": {},
        }

    if not findings:
        findings.append(
            f"Aircraft {aircraft_reg} is fully serviceable with no open MEL items"
        )

    return {
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
        "applicable_ads": applicable_ads,
        "details": details,
    }
