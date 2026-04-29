"""
Schedule Alignment Agent
Finds optimal maintenance windows that don't disrupt revenue flights,
considering hangar availability and crew scheduling.
"""

import os
import logging
from datetime import datetime, timedelta


def _parse_dt(val):
    """Parse a datetime value that may be a string or datetime."""
    if val is None: return None
    if isinstance(val, datetime): return val
    try: return datetime.fromisoformat(str(val).replace("Z", "+00:00").replace(" ", "T")[:26])
    except: return datetime.utcnow()

import psycopg2
import psycopg2.extras

from db import get_db_connection

logger = logging.getLogger("schedule_alignment_agent")




def find_maintenance_window(
    work_order_result: dict,
    parts_result: dict,
    anomaly_result: dict,
) -> dict:
    """
    Find optimal maintenance window for the aircraft.
    Considers flights, hangar availability, and parts readiness.
    """
    aircraft_reg = anomaly_result.get("aircraft_reg", "UNKNOWN")
    base_station = anomaly_result.get("base_station", "DEL")
    work_orders = work_order_result.get("work_orders", [])
    parts_ready_by = parts_result.get("parts_ready_by", datetime.utcnow().isoformat())
    max_transfer_time = parts_result.get("max_transfer_time_hours", 0)

    # Calculate total maintenance hours needed
    total_mx_hours = sum(wo.get("estimated_duration_hours", 4) for wo in work_orders)
    # Add buffer for taxi, tow, and paperwork
    total_mx_hours_with_buffer = total_mx_hours + 2.0

    urgency = anomaly_result.get("diagnosis", {}).get("urgency", "MODERATE")

    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get upcoming flights for this aircraft
        cur.execute(
            """
            SELECT flight_id, flight_number, origin, destination,
                   departure, arrival, status
            FROM flight_schedule
            WHERE aircraft_reg = %s AND departure >= NOW()
            ORDER BY departure ASC
            """,
            (aircraft_reg,),
        )
        flights = cur.fetchall()

        # Get hangar availability at base station
        cur.execute(
            """
            SELECT hangar_id, hangar_type, capacity, current_occupancy,
                   available_from, available_until
            FROM hangar_availability
            WHERE station = %s
            AND capacity > current_occupancy
            AND available_until > NOW()
            ORDER BY available_from ASC
            """,
            (base_station,),
        )
        hangars = cur.fetchall()

        # Find gaps between flights (potential maintenance windows)
        windows = _find_flight_gaps(flights, base_station, total_mx_hours_with_buffer)

        # Find hangar slots
        hangar_slots = _find_hangar_slots(hangars, total_mx_hours_with_buffer)

        # Match windows with hangar availability
        viable_windows = _match_windows_with_hangars(windows, hangar_slots, parts_ready_by)

        # Select the best window
        best_window = _select_best_window(viable_windows, urgency, parts_ready_by)

        # Calculate flight impact
        flight_impact = _assess_flight_impact(best_window, flights, total_mx_hours_with_buffer)

        # Format flights for output
        upcoming_flights = [
            {
                "flight_id": f["flight_id"],
                "flight_number": f["flight_number"],
                "route": f"{f['origin']} -> {f['destination']}",
                "departure": str(f["departure"]),
                "arrival": str(f["arrival"]),
                "status": f["status"],
            }
            for f in flights
        ]

        if best_window:
            recommendation = _build_recommendation(
                best_window, flight_impact, work_orders,
                parts_result, total_mx_hours, urgency, aircraft_reg,
            )
        else:
            recommendation = {
                "status": "NO_WINDOW_FOUND",
                "message": (
                    f"No suitable maintenance window found in the next 72 hours at {base_station}. "
                    "Consider: (1) Cancelling a non-revenue flight, "
                    "(2) Ferrying aircraft to another station with availability, "
                    "(3) Emergency ground stop."
                ),
                "alternative_actions": [
                    "Ferry to BOM for maintenance (hangar available)",
                    "Cancel lowest-revenue flight to create window",
                    "Emergency AOG ground stop at current location",
                ],
            }

        return {
            "aircraft_reg": aircraft_reg,
            "base_station": base_station,
            "total_maintenance_hours_needed": round(total_mx_hours, 1),
            "total_hours_with_buffer": round(total_mx_hours_with_buffer, 1),
            "urgency": urgency,
            "upcoming_flights": upcoming_flights,
            "maintenance_windows_found": len(viable_windows),
            "viable_windows": [
                {
                    "start": str(w["start"]),
                    "end": str(w["end"]),
                    "duration_hours": round(w["duration_hours"], 1),
                    "location": w["location"],
                    "hangar": w.get("hangar_id", "TBD"),
                    "hangar_type": w.get("hangar_type", "LINE_MAINTENANCE"),
                    "parts_ready": w.get("parts_ready", False),
                    "score": w.get("score", 0),
                }
                for w in viable_windows[:5]  # Top 5 windows
            ],
            "recommended_window": best_window and {
                "start": str(best_window["start"]),
                "end": str(best_window["end"]),
                "duration_hours": round(best_window["duration_hours"], 1),
                "location": best_window["location"],
                "hangar": best_window.get("hangar_id", "TBD"),
                "hangar_type": best_window.get("hangar_type", "LINE_MAINTENANCE"),
            },
            "flight_impact": flight_impact,
            "recommendation": recommendation,
            "analyzed_at": datetime.utcnow().isoformat(),
        }

    finally:
        conn.close()


def _find_flight_gaps(flights, base_station, min_hours):
    """Find gaps between flights where maintenance can be performed."""
    windows = []

    if not flights:
        # No flights = aircraft available now
        windows.append({
            "start": datetime.utcnow(),
            "end": datetime.utcnow() + timedelta(hours=48),
            "duration_hours": 48.0,
            "location": base_station,
            "type": "NO_FLIGHTS",
        })
        return windows

    # Gap before first flight (if aircraft at base)
    first_flight = flights[0]
    now = datetime.utcnow()
    if first_flight["origin"] == base_station:
        gap_hours = (_parse_dt(first_flight["departure"]) - now).total_seconds() / 3600
        if gap_hours >= min_hours:
            windows.append({
                "start": now,
                "end": _parse_dt(first_flight["departure"]) - timedelta(hours=1),  # 1h buffer before flight
                "duration_hours": gap_hours - 1,
                "location": base_station,
                "type": "PRE_FLIGHT_GAP",
            })

    # Gaps between consecutive flights
    for i in range(len(flights) - 1):
        current_arrival = _parse_dt(flights[i]["arrival"])
        next_departure = _parse_dt(flights[i + 1]["departure"])
        arrival_station = flights[i]["destination"]
        next_origin = flights[i + 1]["origin"]

        # Only consider gaps where aircraft is at a maintenance station
        if arrival_station == next_origin:
            gap_hours = (next_departure - current_arrival).total_seconds() / 3600
            # Subtract turnaround buffer (1h arrival + 1h departure)
            effective_hours = gap_hours - 2.0
            if effective_hours >= min_hours:
                windows.append({
                    "start": current_arrival + timedelta(hours=1),
                    "end": next_departure - timedelta(hours=1),
                    "duration_hours": effective_hours,
                    "location": arrival_station,
                    "type": "INTER_FLIGHT_GAP",
                    "after_flight": flights[i]["flight_number"],
                    "before_flight": flights[i + 1]["flight_number"],
                })

    # Gap after last flight
    last_flight = flights[-1]
    last_arrival = _parse_dt(last_flight["arrival"])
    arrival_station = last_flight["destination"]
    # Assume next known commitment is 24h after last arrival
    gap_end = last_arrival + timedelta(hours=24)
    gap_hours = 24.0 - 1.0  # 1h turnaround after arrival
    if gap_hours >= min_hours:
        windows.append({
            "start": last_arrival + timedelta(hours=1),
            "end": gap_end,
            "duration_hours": gap_hours,
            "location": arrival_station,
            "type": "POST_SCHEDULE_GAP",
            "after_flight": last_flight["flight_number"],
        })

    return windows


def _find_hangar_slots(hangars, min_hours):
    """Find available hangar time slots."""
    slots = []
    for h in hangars:
        h_from = _parse_dt(h["available_from"])
        h_until = _parse_dt(h["available_until"])
        effective_start = max(h_from, datetime.utcnow()) if h_from else datetime.utcnow()
        available_hours = (h_until - effective_start).total_seconds() / 3600 if h_until else 0
        if available_hours >= min_hours:
            slots.append({
                "hangar_id": h["hangar_id"],
                "hangar_type": h["hangar_type"],
                "available_from": effective_start,
                "available_until": h_until,
                "available_hours": available_hours,
                "free_spots": h["capacity"] - h["current_occupancy"],
            })
    return slots


def _match_windows_with_hangars(windows, hangar_slots, parts_ready_by_str):
    """Match flight gaps with hangar availability."""
    try:
        parts_ready_by = datetime.fromisoformat(parts_ready_by_str)
    except (ValueError, TypeError):
        parts_ready_by = datetime.utcnow()

    viable = []
    for window in windows:
        for slot in hangar_slots:
            # Check overlap
            overlap_start = max(window["start"], slot["available_from"])
            overlap_end = min(window["end"], slot["available_until"])
            overlap_hours = (overlap_end - overlap_start).total_seconds() / 3600

            if overlap_hours > 0:
                parts_ready = overlap_start >= parts_ready_by
                # Score: prefer longer windows, parts-ready, sooner start
                hours_from_now = (overlap_start - datetime.utcnow()).total_seconds() / 3600
                score = (
                    overlap_hours * 10  # Prefer longer windows
                    + (100 if parts_ready else 0)  # Big bonus if parts ready
                    - hours_from_now * 2  # Prefer sooner
                    + (20 if window.get("type") == "INTER_FLIGHT_GAP" else 0)  # Prefer scheduled gaps
                    + (30 if slot["hangar_type"] == "ENGINE_SHOP" else 10)  # Prefer engine shop
                )

                viable.append({
                    **window,
                    "start": overlap_start,
                    "end": overlap_end,
                    "duration_hours": overlap_hours,
                    "hangar_id": slot["hangar_id"],
                    "hangar_type": slot["hangar_type"],
                    "parts_ready": parts_ready,
                    "score": round(score, 1),
                })

    # Also include windows without specific hangar match (line maintenance possible)
    for window in windows:
        if not any(v["start"] == window["start"] for v in viable):
            parts_ready = _parse_dt(window["start"]) >= parts_ready_by
            hours_from_now = (_parse_dt(window["start"]) - datetime.utcnow()).total_seconds() / 3600
            score = (
                window["duration_hours"] * 5
                + (100 if parts_ready else 0)
                - hours_from_now * 2
            )
            viable.append({
                **window,
                "hangar_id": "LINE_STAND",
                "hangar_type": "LINE_MAINTENANCE",
                "parts_ready": parts_ready,
                "score": round(score, 1),
            })

    viable.sort(key=lambda w: w["score"], reverse=True)
    return viable


def _select_best_window(viable_windows, urgency, parts_ready_by_str):
    """Select the best maintenance window based on urgency and constraints."""
    if not viable_windows:
        return None

    try:
        parts_ready_by = datetime.fromisoformat(parts_ready_by_str)
    except (ValueError, TypeError):
        parts_ready_by = datetime.utcnow()

    if urgency == "IMMEDIATE":
        # For immediate urgency, prefer the earliest window where parts will be ready
        parts_ready_windows = [w for w in viable_windows if w["parts_ready"]]
        if parts_ready_windows:
            return parts_ready_windows[0]
        # If no window has parts ready, take the earliest and plan parallel parts transfer
        return viable_windows[0]
    else:
        # For non-immediate, take the highest scored window
        return viable_windows[0]


def _assess_flight_impact(window, flights, mx_hours):
    """Assess impact on flights if the maintenance window is used."""
    if not window or not flights:
        return {
            "flights_impacted": 0,
            "flights_cancelled": 0,
            "flights_delayed": 0,
            "revenue_impact_usd": 0,
            "passengers_affected": 0,
            "description": "No flight impact.",
        }

    mx_start = window["start"]
    mx_end = window["end"]

    impacted = []
    for f in flights:
        if f["departure"] >= mx_start and f["departure"] <= mx_end:
            impacted.append({
                "flight_number": f["flight_number"],
                "route": f"{f['origin']} -> {f['destination']}",
                "departure": str(f["departure"]),
                "impact": "POTENTIAL_DELAY",
            })

    if not impacted:
        return {
            "flights_impacted": 0,
            "flights_cancelled": 0,
            "flights_delayed": 0,
            "revenue_impact_usd": 0,
            "passengers_affected": 0,
            "description": "No revenue flights impacted. Maintenance fits within natural schedule gap.",
        }

    est_revenue_per_flight = 85000  # USD average
    est_pax_per_flight = 250

    return {
        "flights_impacted": len(impacted),
        "flights_cancelled": 0,
        "flights_delayed": len(impacted),
        "impacted_flights": impacted,
        "revenue_impact_usd": len(impacted) * est_revenue_per_flight,
        "passengers_affected": len(impacted) * est_pax_per_flight,
        "description": (
            f"{len(impacted)} flight(s) may be delayed. "
            f"Consider wet-leasing substitute aircraft."
        ),
    }


def _build_recommendation(window, flight_impact, work_orders, parts_result, mx_hours, urgency, aircraft_reg):
    """Build the final schedule recommendation."""
    transfers = parts_result.get("transfers_needed", [])
    max_transfer_time = parts_result.get("max_transfer_time_hours", 0)

    # Build timeline
    timeline = []
    now = datetime.utcnow()

    if transfers:
        for t in transfers:
            timeline.append({
                "time": now.isoformat(),
                "action": f"Initiate AOG transfer of {t['description']} from {t['from_station']} to {t['to_station']}",
                "duration_hours": t["total_transfer_time_hours"],
            })

    timeline.append({
        "time": str(window["start"]),
        "action": f"Begin maintenance at {window['location']} — {window.get('hangar_type', 'LINE_MAINTENANCE')}",
        "duration_hours": 0.5,  # Setup
    })

    for wo in work_orders:
        timeline.append({
            "time": str(window["start"]),
            "action": f"Execute {wo['work_order_id']}: {wo['component']} — {wo['action_type']}",
            "duration_hours": wo["estimated_duration_hours"],
        })

    timeline.append({
        "time": str(window["end"]),
        "action": "Engine ground run test and maintenance release",
        "duration_hours": 1.5,
    })

    # Cost savings
    aog_cost_per_day = 100000
    potential_aog_days = 3  # Estimated if failure occurred in flight
    total_mx_cost = sum(wo.get("estimated_cost_usd", 0) for wo in work_orders)
    total_transfer_cost = parts_result.get("total_transfer_cost_usd", 0)
    total_cost = total_mx_cost + total_transfer_cost
    savings = (aog_cost_per_day * potential_aog_days) - total_cost

    return {
        "status": "WINDOW_FOUND",
        "summary": (
            f"Maintenance window identified for {aircraft_reg} at {window['location']}. "
            f"Start: {window['start'].strftime('%Y-%m-%d %H:%M UTC')}, "
            f"Duration: {window['duration_hours']:.1f} hours available "
            f"({mx_hours:.1f} hours needed). "
            f"{'Parts transfer required — ' + str(max_transfer_time) + ' hours.' if transfers else 'All parts available.'} "
            f"{'No revenue flights impacted.' if flight_impact['flights_impacted'] == 0 else str(flight_impact['flights_impacted']) + ' flight(s) may be affected.'}"
        ),
        "maintenance_start": str(window["start"]),
        "maintenance_end": str(_parse_dt(window["start"]) + timedelta(hours=mx_hours + 2)),
        "location": window["location"],
        "hangar": window.get("hangar_id", "LINE_STAND"),
        "hangar_type": window.get("hangar_type", "LINE_MAINTENANCE"),
        "timeline": timeline,
        "total_maintenance_cost_usd": round(total_cost, 2),
        "aog_cost_avoided_usd": round(aog_cost_per_day * potential_aog_days, 2),
        "estimated_savings_usd": round(max(savings, 0), 2),
        "flights_impacted": flight_impact["flights_impacted"],
    }
