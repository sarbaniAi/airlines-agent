"""
Air India Predictive Maintenance Command Center
FastAPI application serving the dashboard and API endpoints.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.orchestrator import run_full_analysis, chat_about_fleet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("predictive_maintenance")

app = FastAPI(
    title="Air India Predictive Maintenance Command Center",
    version="1.0.0",
)

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


from db import get_db_connection


def _safe_json(obj):
    """Convert objects for JSON serialization."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


# ─── Pydantic Models ───────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


# ─── Routes ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard."""
    with open(os.path.join(static_dir, "index.html"), "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM aircraft_fleet")
        count = cur.fetchone()[0]
        conn.close()
        return {"status": "healthy", "database": "connected", "aircraft_count": count}
    except Exception as e:
        return {"status": "degraded", "database": "error", "error": str(e)}


@app.get("/api/fleet")
async def get_fleet():
    """Return fleet overview with health status."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get fleet with latest anomaly info using JOINs (Spark SQL compatible)
        cur.execute("""
            SELECT
                f.aircraft_reg,
                f.aircraft_type,
                f.engine_type,
                f.total_flight_hours,
                f.total_cycles,
                f.base_station,
                f.status,
                f.last_heavy_check,
                COALESCE(cl_agg.min_health, 100) as min_component_health,
                COALESCE(st_agg.max_anomaly, 0) as max_recent_anomaly_score,
                COALESCE(aa_agg.alert_count, 0) as critical_alert_count
            FROM aircraft_fleet f
            LEFT JOIN (
                SELECT aircraft_reg, MIN(health_score) as min_health
                FROM component_lifecycle GROUP BY aircraft_reg
            ) cl_agg ON cl_agg.aircraft_reg = f.aircraft_reg
            LEFT JOIN (
                SELECT aircraft_reg, MAX(anomaly_score) as max_anomaly
                FROM sensor_telemetry
                WHERE timestamp >= date_sub(current_timestamp(), 1)
                GROUP BY aircraft_reg
            ) st_agg ON st_agg.aircraft_reg = f.aircraft_reg
            LEFT JOIN (
                SELECT aircraft_reg, COUNT(*) as alert_count
                FROM anomaly_alerts
                WHERE status IN ('NEW', 'ACKNOWLEDGED')
                AND severity IN ('CRITICAL', 'HIGH')
                GROUP BY aircraft_reg
            ) aa_agg ON aa_agg.aircraft_reg = f.aircraft_reg
            ORDER BY
                CASE WHEN f.status = 'AOG' THEN 0
                     WHEN f.status = 'IN_MAINTENANCE' THEN 1
                     ELSE 2 END,
                COALESCE(cl_agg.min_health, 100) ASC
        """)
        fleet = cur.fetchall()

        result = []
        for ac in fleet:
            min_health = float(ac["min_component_health"] or 100)
            max_score = float(ac["max_recent_anomaly_score"] or 0)
            alert_count = int(ac["critical_alert_count"] or 0)

            # Calculate overall health
            if ac["status"] == "IN_MAINTENANCE":
                overall_health = min_health
                health_status = "IN_MAINTENANCE"
            elif alert_count > 0 or max_score > 0.8:
                overall_health = max(0, min_health - (max_score * 30))
                health_status = "CRITICAL" if max_score > 0.85 else "WARNING"
            elif max_score > 0.4 or min_health < 60:
                overall_health = min_health
                health_status = "WATCH"
            else:
                overall_health = min_health
                health_status = "NORMAL"

            result.append({
                "aircraft_reg": ac["aircraft_reg"],
                "aircraft_type": ac["aircraft_type"],
                "engine_type": ac["engine_type"],
                "total_flight_hours": ac["total_flight_hours"],
                "total_cycles": ac["total_cycles"],
                "base_station": ac["base_station"],
                "status": ac["status"],
                "last_heavy_check": str(ac["last_heavy_check"]) if ac["last_heavy_check"] else None,
                "overall_health": round(overall_health, 1),
                "health_status": health_status,
                "critical_alerts": alert_count,
                "max_anomaly_score": round(max_score, 3),
            })

        return {"fleet": result, "total": len(result)}
    finally:
        conn.close()


@app.get("/api/aircraft/{reg}")
async def get_aircraft_detail(reg: str):
    """Detailed aircraft info with latest sensor data and components."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Aircraft info
        cur.execute("SELECT * FROM aircraft_fleet WHERE aircraft_reg = %s", (reg,))
        aircraft = cur.fetchone()
        if not aircraft:
            raise HTTPException(status_code=404, detail=f"Aircraft {reg} not found")

        # Latest sensor readings
        cur.execute("""
            SELECT sensor_type, engine_position, value, unit,
                   normal_min, normal_max, anomaly_score, timestamp
            FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY sensor_type, engine_position ORDER BY timestamp DESC) as rn
                FROM sensor_telemetry
                WHERE aircraft_reg = %s
            ) t WHERE rn = 1
        """, (reg,))
        sensors = cur.fetchall()

        # Component lifecycle
        cur.execute("""
            SELECT * FROM component_lifecycle
            WHERE aircraft_reg = %s
            ORDER BY health_score ASC
        """, (reg,))
        components = cur.fetchall()

        # Active alerts
        cur.execute("""
            SELECT * FROM anomaly_alerts
            WHERE aircraft_reg = %s AND status IN ('NEW', 'ACKNOWLEDGED', 'IN_PROGRESS')
            ORDER BY severity DESC, detected_at DESC
        """, (reg,))
        alerts = cur.fetchall()

        # Recent maintenance
        cur.execute("""
            SELECT * FROM maintenance_history
            WHERE aircraft_reg = %s
            ORDER BY start_date DESC LIMIT 10
        """, (reg,))
        maintenance = cur.fetchall()

        # Upcoming flights
        cur.execute("""
            SELECT * FROM flight_schedule
            WHERE aircraft_reg = %s AND departure >= NOW()
            ORDER BY departure ASC
        """, (reg,))
        flights = cur.fetchall()

        return JSONResponse(content=json.loads(json.dumps({
            "aircraft": dict(aircraft),
            "sensors": [dict(s) for s in sensors],
            "components": [dict(c) for c in components],
            "alerts": [dict(a) for a in alerts],
            "maintenance_history": [dict(m) for m in maintenance],
            "upcoming_flights": [dict(f) for f in flights],
        }, default=_safe_json)))
    finally:
        conn.close()


@app.get("/api/alerts")
async def get_alerts(status: Optional[str] = None):
    """Get active anomaly alerts."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if status:
            cur.execute(
                "SELECT * FROM anomaly_alerts WHERE status = %s ORDER BY severity DESC, detected_at DESC",
                (status,),
            )
        else:
            cur.execute(
                "SELECT * FROM anomaly_alerts WHERE status IN ('NEW', 'ACKNOWLEDGED', 'IN_PROGRESS') ORDER BY severity DESC, detected_at DESC"
            )
        alerts = cur.fetchall()
        return JSONResponse(content=json.loads(json.dumps({
            "alerts": [dict(a) for a in alerts],
            "total": len(alerts),
        }, default=_safe_json)))
    finally:
        conn.close()


@app.post("/api/analyze/{reg}")
async def analyze_aircraft_endpoint(reg: str):
    """Run full predictive maintenance analysis for an aircraft."""
    try:
        result = run_full_analysis(reg)
        return JSONResponse(content=json.loads(json.dumps(result, default=_safe_json)))
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """Natural language Q&A about fleet/maintenance."""
    try:
        response = chat_about_fleet(request.message)
        return {"response": response}
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        return {"response": f"I apologize, I'm having trouble processing your question. Error: {str(e)}"}


@app.get("/api/sensor-history/{reg}/{sensor_type}")
async def get_sensor_history(reg: str, sensor_type: str, engine_position: Optional[str] = None):
    """Get sensor trend data for charts."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if engine_position:
            cur.execute("""
                SELECT timestamp, value, unit, normal_min, normal_max, anomaly_score, engine_position
                FROM sensor_telemetry
                WHERE aircraft_reg = %s AND sensor_type = %s AND engine_position = %s
                AND timestamp >= NOW() - INTERVAL '7 days'
                ORDER BY timestamp ASC
            """, (reg, sensor_type, engine_position))
        else:
            cur.execute("""
                SELECT timestamp, value, unit, normal_min, normal_max, anomaly_score, engine_position
                FROM sensor_telemetry
                WHERE aircraft_reg = %s AND sensor_type = %s
                AND timestamp >= NOW() - INTERVAL '7 days'
                ORDER BY engine_position, timestamp ASC
            """, (reg, sensor_type))

        rows = cur.fetchall()

        # Group by engine position
        series = {}
        for row in rows:
            ep = row["engine_position"]
            if ep not in series:
                series[ep] = {
                    "engine_position": ep,
                    "unit": row["unit"],
                    "normal_min": float(row["normal_min"]),
                    "normal_max": float(row["normal_max"]),
                    "data_points": [],
                }
            series[ep]["data_points"].append({
                "timestamp": str(row["timestamp"]),
                "value": float(row["value"]),
                "anomaly_score": float(row["anomaly_score"]),
            })

        return JSONResponse(content=json.loads(json.dumps({
            "aircraft_reg": reg,
            "sensor_type": sensor_type,
            "series": list(series.values()),
        }, default=_safe_json)))
    finally:
        conn.close()
