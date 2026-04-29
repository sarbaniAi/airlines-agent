"""
Air India Pre-Flight Readiness & Dispatch Agent
FastAPI Application
"""

import os
import sys
import json
import asyncio
import logging
from datetime import date, datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import psycopg2
import psycopg2.extras

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.orchestrator import run_dispatch_check, chat_about_dispatch

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("app")

# ---------------------------------------------------------------------------
# In-memory store for dispatch results (per-session)
# ---------------------------------------------------------------------------
dispatch_cache: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _json_serial(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "__float__"):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


from db import get_db


def _safe_query(query: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return list of dicts, with error handling."""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except psycopg2.Error as e:
        logger.error(f"Database query error: {e}")
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown."""
    logger.info("Air India Pre-Flight Dispatch Agent starting up...")
    # Test DB connectivity
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        logger.info("Lakebase connection successful")
    except Exception as e:
        logger.warning(f"Lakebase connection failed (may need seeding): {e}")
    yield
    logger.info("Shutting down...")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Air India Pre-Flight Dispatch Agent",
    description="Multi-agent pre-flight readiness check system",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class DispatchCheckRequest(BaseModel):
    flight_id: str


class ChatRequest(BaseModel):
    flight_id: str
    message: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard."""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    db_ok = False
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        db_ok = True
    except Exception:
        pass

    # Also test a real data query with raw API debug
    test_count = -1
    test_err = None
    raw_debug = None
    try:
        import requests as _req
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        host = w.config.host.rstrip("/")
        tok = w.config.token
        identity = str(w.current_user.me().user_name)
        r = _req.post(
            f"{host}/api/2.0/sql/statements",
            headers={"Authorization": f"Bearer {tok}"},
            json={"warehouse_id": os.environ.get("DATABRICKS_WAREHOUSE_ID","148ccb90800933a1"),
                  "statement": f"SELECT COUNT(*) as cnt FROM sarbanimaiti_catalog.pre_flight_dispatch.flight_schedule",
                  "wait_timeout": "30s"},
            verify=False,
        )
        raw = r.json()
        test_count = raw.get("result", {}).get("data_array", [[0]])[0][0] if raw.get("status",{}).get("state") == "SUCCEEDED" else -2
        raw_debug = {"state": raw.get("status",{}).get("state"), "error": raw.get("status",{}).get("error",{}).get("message","")[:200], "identity": identity}
    except Exception as e:
        test_err = str(e)

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "version": "1.0.0",
        "flight_count": test_count,
        "test_error": test_err,
        "debug": raw_debug,
    }


@app.get("/api/flights")
async def get_flights():
    """Return today's flight schedule."""
    rows = _safe_query(
        """
        SELECT fs.flight_id, fs.flight_number, fs.origin, fs.destination,
               fs.scheduled_departure, fs.scheduled_arrival,
               fs.aircraft_reg, fs.pax_count, fs.status,
               af.aircraft_type, af.model_variant,
               c1.name as captain_name,
               c2.name as fo_name
        FROM flight_schedule fs
        JOIN aircraft_fleet af ON fs.aircraft_reg = af.aircraft_reg
        LEFT JOIN crew_roster c1 ON fs.captain_id = c1.crew_id
        LEFT JOIN crew_roster c2 ON fs.first_officer_id = c2.crew_id
        ORDER BY fs.scheduled_departure
        """
    )
    return JSONResponse(
        content=json.loads(json.dumps(rows, default=_json_serial))
    )


@app.get("/api/flight/{flight_id}")
async def get_flight_detail(flight_id: str):
    """Return detailed flight information."""
    rows = _safe_query(
        """
        SELECT fs.*,
               af.aircraft_type, af.model_variant, af.status as aircraft_status,
               af.total_flight_hours, af.base_airport as aircraft_base,
               af.last_c_check_date, af.next_c_check_due,
               c1.name as captain_name, c1.rank as captain_rank,
               c1.duty_hours_last_7d as cpt_duty_7d,
               c1.fatigue_risk_score as cpt_fatigue,
               c2.name as fo_name, c2.rank as fo_rank,
               c2.duty_hours_last_7d as fo_duty_7d,
               c2.fatigue_risk_score as fo_fatigue
        FROM flight_schedule fs
        JOIN aircraft_fleet af ON fs.aircraft_reg = af.aircraft_reg
        LEFT JOIN crew_roster c1 ON fs.captain_id = c1.crew_id
        LEFT JOIN crew_roster c2 ON fs.first_officer_id = c2.crew_id
        WHERE fs.flight_id = %s
        """,
        (flight_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Flight {flight_id} not found")

    # Also get weather for origin/dest
    flight = rows[0]
    weather = _safe_query(
        """
        SELECT airport_code, conditions, temperature_c, visibility_km,
               wind_speed_kts, ceiling_ft, severity, metar_raw
        FROM weather_conditions
        WHERE airport_code IN (%s, %s)
        ORDER BY observation_time DESC
        """,
        (flight["origin"], flight["destination"]),
    )

    # Get MEL items
    mel = _safe_query(
        """
        SELECT item_code, ata_chapter, description, category, status, expiry_date
        FROM mel_items
        WHERE aircraft_reg = %s AND status IN ('OPEN', 'DEFERRED')
        ORDER BY category, expiry_date
        """,
        (flight["aircraft_reg"],),
    )

    result = {
        "flight": flight,
        "weather": weather,
        "mel_items": mel,
    }
    return JSONResponse(
        content=json.loads(json.dumps(result, default=_json_serial))
    )


@app.post("/api/dispatch-check")
async def dispatch_check(request: DispatchCheckRequest):
    """Run the full multi-agent dispatch check for a flight."""
    logger.info(f"Starting dispatch check for flight {request.flight_id}")

    try:
        result = await run_dispatch_check(request.flight_id)
        dispatch_cache[request.flight_id] = result
        return JSONResponse(
            content=json.loads(json.dumps(result, default=_json_serial))
        )
    except Exception as e:
        logger.error(f"Dispatch check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """Follow-up chat about a dispatch decision."""
    cached = dispatch_cache.get(request.flight_id)
    if not cached:
        raise HTTPException(
            status_code=400,
            detail=f"No dispatch result cached for {request.flight_id}. Run a dispatch check first.",
        )

    try:
        response = await chat_about_dispatch(
            request.flight_id, cached, request.message
        )
        return {"response": response}
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# WebSocket for real-time agent progress
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, flight_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(flight_id, []).append(ws)

    def disconnect(self, flight_id: str, ws: WebSocket):
        if flight_id in self.active:
            self.active[flight_id] = [
                w for w in self.active[flight_id] if w != ws
            ]

    async def send_update(self, flight_id: str, data: dict):
        for ws in self.active.get(flight_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass


ws_manager = ConnectionManager()


@app.websocket("/ws/dispatch/{flight_id}")
async def websocket_dispatch(websocket: WebSocket, flight_id: str):
    """
    WebSocket endpoint for real-time dispatch check with progress updates.
    Client connects, sends {"action": "start"}, and receives agent progress.
    """
    await ws_manager.connect(flight_id, websocket)
    logger.info(f"WebSocket connected for flight {flight_id}")

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("action") == "start":
                # Progress callback
                async def progress_cb(agent_name: str, status: str, result: dict):
                    safe = json.loads(json.dumps(result, default=_json_serial))
                    await ws_manager.send_update(
                        flight_id,
                        {
                            "type": "agent_progress",
                            "agent": agent_name,
                            "status": status,
                            "data": safe,
                        },
                    )

                # Run dispatch check with progress
                try:
                    result = await run_dispatch_check(flight_id, progress_callback=progress_cb)
                    dispatch_cache[flight_id] = result
                    safe_result = json.loads(json.dumps(result, default=_json_serial))
                    await websocket.send_json({
                        "type": "dispatch_complete",
                        "data": safe_result,
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e),
                    })

            elif data.get("action") == "chat":
                cached = dispatch_cache.get(flight_id)
                if cached:
                    response = await chat_about_dispatch(
                        flight_id, cached, data.get("message", "")
                    )
                    await websocket.send_json({
                        "type": "chat_response",
                        "response": response,
                    })

    except WebSocketDisconnect:
        ws_manager.disconnect(flight_id, websocket)
        logger.info(f"WebSocket disconnected for flight {flight_id}")
    except Exception as e:
        ws_manager.disconnect(flight_id, websocket)
        logger.error(f"WebSocket error: {e}")
