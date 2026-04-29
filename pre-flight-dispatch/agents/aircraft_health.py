"""
Aircraft Health Agent
Checks MEL deferrals, maintenance status, and aircraft serviceability.
"""

import os
import logging
from datetime import date, datetime, timedelta
from typing import Any


def _parse_date(val):
    """Parse a date value that may be a string, date, or None."""
    if val is None:
        return None
    if isinstance(val, date):
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

logger = logging.getLogger("agents.aircraft_health")




async def run(aircraft_reg: str) -> dict[str, Any]:
    """
    Run aircraft health check for the given registration.

    Returns:
        dict with keys: status (GREEN/AMBER/RED), findings, recommendations, details
    """
    findings = []
    recommendations = []
    status = "GREEN"
    details = {}

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # --- 1. Aircraft fleet status ---
        cur.execute(
            "SELECT * FROM aircraft_fleet WHERE aircraft_reg = %s", (aircraft_reg,)
        )
        aircraft = cur.fetchone()

        if not aircraft:
            return {
                "status": "RED",
                "findings": [f"Aircraft {aircraft_reg} not found in fleet database"],
                "recommendations": ["Verify aircraft registration"],
                "details": {},
            }

        details["aircraft"] = dict(aircraft)

        # Check serviceable status
        if aircraft["status"] != "SERVICEABLE":
            status = "RED"
            findings.append(
                f"Aircraft status is {aircraft['status']} — not serviceable"
            )
            recommendations.append(
                f"Aircraft {aircraft_reg} cannot be dispatched. Swap to alternate aircraft."
            )

        # Check C-check due date
        _next_c = _parse_date(aircraft["next_c_check_due"])
        if _next_c:
            days_to_c_check = (_next_c - date.today()).days
            if days_to_c_check < 0:
                status = "RED"
                findings.append(
                    f"C-Check OVERDUE by {abs(days_to_c_check)} days (was due {aircraft['next_c_check_due']})"
                )
                recommendations.append("Ground aircraft immediately for C-Check")
            elif days_to_c_check < 30:
                if status != "RED":
                    status = "AMBER"
                findings.append(
                    f"C-Check due in {days_to_c_check} days ({aircraft['next_c_check_due']})"
                )
                recommendations.append("Schedule C-Check within next maintenance window")

        # --- 2. MEL items ---
        cur.execute(
            """
            SELECT * FROM mel_items
            WHERE aircraft_reg = %s AND status IN ('OPEN', 'DEFERRED')
            ORDER BY category, expiry_date
            """,
            (aircraft_reg,),
        )
        mel_items = cur.fetchall()
        details["mel_items"] = [dict(m) for m in mel_items]

        today = date.today()
        tomorrow = today + timedelta(days=1)

        cat_a_count = 0
        cat_b_count = 0
        critical_mel = []

        for mel in mel_items:
            cat = mel["category"]
            expiry = _parse_date(mel["expiry_date"])

            if cat == "A":
                cat_a_count += 1
                if expiry and expiry <= today:
                    status = "RED"
                    findings.append(
                        f"MEL Cat-A item {mel['item_code']} EXPIRED on {expiry} — "
                        f"'{mel['description']}'"
                    )
                    recommendations.append(
                        f"MANDATORY: Rectify {mel['item_code']} before dispatch — Cat-A deferral expired"
                    )
                elif expiry and expiry <= tomorrow:
                    critical_mel.append(mel)
                    status = "AMBER" if status == "GREEN" else status
                    findings.append(
                        f"MEL Cat-A item {mel['item_code']} ({mel['ata_chapter']}) "
                        f"expires {expiry} — '{mel['description']}'"
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
                        f"{(expiry - today).days} days — '{mel['description']}'"
                    )

        # Summary
        total_open = len(mel_items)
        if total_open > 0:
            findings.insert(
                0,
                f"{total_open} open MEL items ({cat_a_count} Cat-A, {cat_b_count} Cat-B)",
            )

        # --- 3. Total flight hours check ---
        if aircraft["total_flight_hours"] and aircraft["total_flight_hours"] > 40000:
            if status == "GREEN":
                status = "AMBER"
            findings.append(
                f"High total flight hours: {aircraft['total_flight_hours']:,} hours"
            )

        cur.close()
        conn.close()

    except psycopg2.Error as e:
        logger.error(f"Database error in aircraft health agent: {e}")
        return {
            "status": "RED",
            "findings": [f"Database error: {str(e)}"],
            "recommendations": ["Check Lakebase connectivity"],
            "details": {},
        }

    if not findings:
        findings.append(f"Aircraft {aircraft_reg} is fully serviceable with no open MEL items")

    return {
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
        "details": details,
    }
