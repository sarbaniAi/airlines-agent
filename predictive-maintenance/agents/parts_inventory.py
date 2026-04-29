"""
Parts & Inventory Agent
Checks parts availability across stations, plans logistics transfers if needed.
"""

import os
import logging
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

from db import get_db_connection

logger = logging.getLogger("parts_inventory_agent")

# Station metadata
STATIONS = {
    "DEL": {"name": "Delhi (Indira Gandhi International)", "code": "DEL"},
    "BOM": {"name": "Mumbai (Chhatrapati Shivaji Maharaj)", "code": "BOM"},
    "BLR": {"name": "Bangalore (Kempegowda International)", "code": "BLR"},
    "MAA": {"name": "Chennai (Chennai International)", "code": "MAA"},
    "HYD": {"name": "Hyderabad (Rajiv Gandhi International)", "code": "HYD"},
}

# Transfer times between stations (hours) — via Air India cargo/ferry
TRANSFER_TIMES = {
    ("DEL", "BOM"): 3.0, ("BOM", "DEL"): 3.0,
    ("DEL", "BLR"): 3.5, ("BLR", "DEL"): 3.5,
    ("DEL", "MAA"): 3.5, ("MAA", "DEL"): 3.5,
    ("DEL", "HYD"): 2.5, ("HYD", "DEL"): 2.5,
    ("BOM", "BLR"): 2.0, ("BLR", "BOM"): 2.0,
    ("BOM", "MAA"): 2.5, ("MAA", "BOM"): 2.5,
    ("BOM", "HYD"): 1.5, ("HYD", "BOM"): 1.5,
    ("BLR", "MAA"): 1.0, ("MAA", "BLR"): 1.0,
    ("BLR", "HYD"): 1.5, ("HYD", "BLR"): 1.5,
    ("MAA", "HYD"): 1.5, ("HYD", "MAA"): 1.5,
}

# Add ground handling + paperwork overhead
LOGISTICS_OVERHEAD_HOURS = 3.0  # Packing, customs paperwork, ground transport




def check_parts_availability(work_order_result: dict, anomaly_result: dict) -> dict:
    """
    Check parts availability for all work orders.
    Plans transfers if parts not at base station.
    """
    aircraft_reg = work_order_result.get("aircraft_reg", "UNKNOWN")
    base_station = anomaly_result.get("base_station", "DEL")
    work_orders = work_order_result.get("work_orders", [])

    if not work_orders:
        return {
            "aircraft_reg": aircraft_reg,
            "base_station": base_station,
            "parts_report": [],
            "all_parts_available": True,
            "message": "No parts required.",
        }

    conn = get_db_connection()
    parts_report = []
    transfers_needed = []
    total_transfer_cost = 0.0
    max_transfer_time = 0.0

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Collect all unique part numbers from work orders
        all_parts = set()
        for wo in work_orders:
            for part in wo.get("parts_needed", []):
                all_parts.add(part["part_number"])

        if not all_parts:
            # If no specific parts listed, look up based on component category
            for wo in work_orders:
                component = wo.get("component", "")
                if "N2 Turbine Bearing" in component:
                    all_parts.add("PN-GE-N2B-7892")
                    all_parts.add("PN-GE-N2B-7893")
                elif "Hydraulic" in component:
                    all_parts.add("PN-HYD-SEAL-01")
                    all_parts.add("PN-HYD-FITTING-01")
                elif "Oil" in component:
                    all_parts.add("PN-2055843")
                    all_parts.add("PN-OIL-SAMPLE-KIT")

        station_col_map = {
            "DEL": "quantity_del",
            "BOM": "quantity_bom",
            "BLR": "quantity_blr",
            "MAA": "quantity_maa",
            "HYD": "quantity_hyd",
        }

        for part_number in all_parts:
            cur.execute(
                """
                SELECT part_number, description, component_category,
                       quantity_del, quantity_bom, quantity_blr,
                       quantity_maa, quantity_hyd,
                       unit_cost_usd, lead_time_days, min_stock,
                       compatible_aircraft
                FROM parts_inventory
                WHERE part_number = %s
                """,
                (part_number,),
            )
            part = cur.fetchone()
            if not part:
                parts_report.append({
                    "part_number": part_number,
                    "status": "NOT_FOUND",
                    "description": "Part not found in inventory system",
                    "available_at_base": False,
                })
                continue

            base_col = station_col_map.get(base_station, "quantity_del")
            base_qty = part[base_col]
            all_station_stock = {
                station: part[col]
                for station, col in station_col_map.items()
            }

            part_entry = {
                "part_number": part["part_number"],
                "description": part["description"],
                "category": part["component_category"],
                "unit_cost_usd": float(part["unit_cost_usd"]),
                "lead_time_days_if_ordered": part["lead_time_days"],
                "stock_by_station": all_station_stock,
                "base_station": base_station,
                "quantity_at_base": base_qty,
                "available_at_base": base_qty > 0,
            }

            if base_qty > 0:
                part_entry["status"] = "AVAILABLE_AT_BASE"
                part_entry["transfer_required"] = False
                part_entry["logistics"] = None
            else:
                # Find nearest station with stock
                best_source = None
                best_time = float("inf")
                for station, qty in all_station_stock.items():
                    if qty > 0 and station != base_station:
                        transfer_key = (station, base_station)
                        flight_time = TRANSFER_TIMES.get(transfer_key, 5.0)
                        total_time = flight_time + LOGISTICS_OVERHEAD_HOURS
                        if total_time < best_time:
                            best_time = total_time
                            best_source = station

                if best_source:
                    transfer_cost = 2500.0  # Estimated AOG shipping cost
                    flight_time = TRANSFER_TIMES.get((best_source, base_station), 5.0)
                    total_transfer_time = flight_time + LOGISTICS_OVERHEAD_HOURS

                    transfer = {
                        "from_station": best_source,
                        "from_station_name": STATIONS[best_source]["name"],
                        "to_station": base_station,
                        "to_station_name": STATIONS[base_station]["name"],
                        "flight_time_hours": flight_time,
                        "logistics_overhead_hours": LOGISTICS_OVERHEAD_HOURS,
                        "total_transfer_time_hours": total_transfer_time,
                        "transfer_cost_usd": transfer_cost,
                        "available_quantity_at_source": all_station_stock[best_source],
                        "estimated_arrival": (
                            datetime.utcnow() + timedelta(hours=total_transfer_time)
                        ).isoformat(),
                    }

                    part_entry["status"] = "TRANSFER_REQUIRED"
                    part_entry["transfer_required"] = True
                    part_entry["logistics"] = transfer
                    transfers_needed.append({
                        "part_number": part["part_number"],
                        "description": part["description"],
                        **transfer,
                    })
                    total_transfer_cost += transfer_cost
                    max_transfer_time = max(max_transfer_time, total_transfer_time)
                else:
                    # Not available anywhere — need to order
                    part_entry["status"] = "OUT_OF_STOCK"
                    part_entry["transfer_required"] = False
                    part_entry["logistics"] = {
                        "action": "EMERGENCY_ORDER",
                        "lead_time_days": part["lead_time_days"],
                        "estimated_arrival": (
                            datetime.utcnow() + timedelta(days=part["lead_time_days"])
                        ).isoformat(),
                        "note": "Part not available at any station. Emergency order required from OEM.",
                    }

            parts_report.append(part_entry)

    finally:
        conn.close()

    all_available = all(p.get("available_at_base", False) or p.get("status") == "AVAILABLE_AT_BASE" for p in parts_report)
    any_out_of_stock = any(p.get("status") == "OUT_OF_STOCK" for p in parts_report)

    if all_available:
        overall_status = "ALL_AVAILABLE"
        message = f"All required parts are available at {base_station}. Ready for maintenance."
    elif transfers_needed and not any_out_of_stock:
        overall_status = "TRANSFERS_NEEDED"
        message = (
            f"{len(transfers_needed)} part(s) require transfer to {base_station}. "
            f"Estimated max transfer time: {max_transfer_time:.1f} hours. "
            f"Transfer cost: ${total_transfer_cost:,.0f}."
        )
    elif any_out_of_stock:
        overall_status = "PARTIAL_SHORTAGE"
        oos_parts = [p["part_number"] for p in parts_report if p.get("status") == "OUT_OF_STOCK"]
        message = (
            f"SHORTAGE: {len(oos_parts)} part(s) not available at any station: {', '.join(oos_parts)}. "
            f"Emergency order required."
        )
    else:
        overall_status = "UNKNOWN"
        message = "Unable to determine parts availability."

    return {
        "aircraft_reg": aircraft_reg,
        "base_station": base_station,
        "base_station_name": STATIONS.get(base_station, {}).get("name", base_station),
        "overall_status": overall_status,
        "all_parts_available_at_base": all_available,
        "parts_report": parts_report,
        "transfers_needed": transfers_needed,
        "total_transfer_cost_usd": round(total_transfer_cost, 2),
        "max_transfer_time_hours": round(max_transfer_time, 1),
        "parts_ready_by": (
            datetime.utcnow() + timedelta(hours=max_transfer_time)
        ).isoformat() if max_transfer_time > 0 else datetime.utcnow().isoformat(),
        "message": message,
        "checked_at": datetime.utcnow().isoformat(),
    }
