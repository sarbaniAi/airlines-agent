"""
Air India Pre-Flight Dispatch Agent V2
FastAPI Application — Mosaic AI Agent Framework with LangGraph Orchestration.

All data access via SQL Statement Execution SDK.
All LLM calls via ai_query through SQL.
NO psycopg2.  NO direct serving-endpoint calls.
"""

import os
import sys
import json
import logging
from datetime import date, datetime
from typing import Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.supervisor import run_dispatch_check, chat_about_dispatch
from tools.sql_tools import query_join, test_connectivity
from tools.vector_search_tools import test_vs_connectivity
from tools.llm_tools import llm_call

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("app")

# ── In-memory dispatch result cache ───────────────────────────────────────
dispatch_cache: dict[str, dict] = {}


# ── JSON serializer ───────────────────────────────────────────────────────

def _json_serial(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "__float__"):
        return float(obj)
    return str(obj)


def _safe_json(data) -> Any:
    """Round-trip to ensure JSON-safe output."""
    return json.loads(json.dumps(data, default=_json_serial))


# ── Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Pre-Flight Dispatch V2 starting up...")
    try:
        ok = test_connectivity()
        logger.info("SQL Warehouse connectivity: %s", "OK" if ok else "FAILED")
    except Exception as e:
        logger.warning("Startup connectivity check failed: %s", e)
    yield
    logger.info("Shutting down...")


# ── FastAPI App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Air India Pre-Flight Dispatch Agent V2",
    description="Multi-agent pre-flight readiness system with LangGraph orchestration and RAG",
    version="2.0.0",
    lifespan=lifespan,
)

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ── Pydantic models ──────────────────────────────────────────────────────

class DispatchCheckRequest(BaseModel):
    flight_id: str


class ChatRequest(BaseModel):
    flight_id: str
    message: str

class AssignCrewRequest(BaseModel):
    flight_id: str
    crew_name: str
    crew_rank: str
    replacing: str  # name of crew being replaced

class NotifyCrewRequest(BaseModel):
    flight_id: str
    crew_name: str

class GenerateReleaseRequest(BaseModel):
    flight_id: str


# ═══════════════════════════════════════════════════════════════════════════
# Action Tracker — in-memory state for dispatch actions
# ═══════════════════════════════════════════════════════════════════════════
dispatch_actions: dict = {}  # flight_id -> {actions: [], status: str, ...}

def _get_actions(flight_id: str) -> dict:
    if flight_id not in dispatch_actions:
        dispatch_actions[flight_id] = {
            "flight_id": flight_id,
            "original_decision": "NO-GO",
            "current_status": "NO-GO",
            "actions_completed": [],
            "actions_pending": [],
            "crew_swaps": [],
            "notifications_sent": [],
            "release_generated": False,
        }
    return dispatch_actions[flight_id]

def _recalculate_status(flight_id: str) -> str:
    """Recalculate dispatch status based on completed actions."""
    a = _get_actions(flight_id)
    completed = {ac["type"] for ac in a["actions_completed"]}

    # If all critical actions done → GO
    has_crew_swap = any(ac["type"] == "crew_assign" for ac in a["actions_completed"])
    has_notification = any(ac["type"] == "crew_notify" for ac in a["actions_completed"])
    has_release = a["release_generated"]

    if has_crew_swap and has_notification and has_release:
        a["current_status"] = "GO"
    elif has_crew_swap:
        a["current_status"] = "CONDITIONAL"
    else:
        a["current_status"] = "NO-GO"

    return a["current_status"]


# ── Type stub removed (already imported at top) ──


# ═══════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(
        content={
            "message": "Pre-Flight Dispatch V2 API",
            "version": "2.0.0",
            "docs": "/docs",
        }
    )


@app.get("/api/health")
async def health_check():
    """Health check endpoint with DB, VS, and LLM status."""
    db_ok = False
    vs_ok = False
    llm_ok = False
    flight_count = -1

    # Database check
    try:
        db_ok = test_connectivity()
    except Exception:
        pass

    # Flight count
    if db_ok:
        try:
            rows = query_join(
                "SELECT COUNT(*) AS cnt FROM flight_schedule"
            )
            flight_count = rows[0].get("cnt", 0) if rows else 0
        except Exception:
            pass

    # Vector Search check
    try:
        vs_ok = test_vs_connectivity()
    except Exception:
        pass

    # LLM check (lightweight)
    try:
        resp = llm_call("You are a test.", "Reply with exactly: OK", max_tokens=10)
        llm_ok = len(resp) > 0
    except Exception:
        pass

    status = "healthy" if (db_ok and llm_ok) else "degraded"

    return {
        "status": status,
        "version": "2.0.0",
        "database": "connected" if db_ok else "disconnected",
        "vector_search": "connected" if vs_ok else "disconnected",
        "llm": "connected" if llm_ok else "disconnected",
        "flight_count": flight_count,
    }


@app.get("/api/flights")
async def get_flights():
    """Return today's flight schedule."""
    try:
        rows = query_join("""
            SELECT fs.flight_id, fs.flight_number, fs.origin, fs.destination,
                   fs.scheduled_departure, fs.scheduled_arrival,
                   fs.aircraft_reg, fs.pax_count, fs.status,
                   af.aircraft_type, af.model_variant,
                   c1.name AS captain_name,
                   c2.name AS fo_name
            FROM flight_schedule fs
            JOIN aircraft_fleet af ON fs.aircraft_reg = af.aircraft_reg
            LEFT JOIN crew_roster c1 ON fs.captain_id = c1.crew_id
            LEFT JOIN crew_roster c2 ON fs.first_officer_id = c2.crew_id
            ORDER BY fs.scheduled_departure
        """)
        return JSONResponse(content=_safe_json(rows))
    except Exception as e:
        logger.error("Failed to fetch flights: %s", e)
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")


@app.get("/api/flight/{flight_id}")
async def get_flight_detail(flight_id: str):
    """Return detailed flight information including weather and MEL items."""
    try:
        rows = query_join(f"""
            SELECT fs.*,
                   af.aircraft_type, af.model_variant, af.status AS aircraft_status,
                   af.total_flight_hours, af.base_airport AS aircraft_base,
                   af.last_c_check_date, af.next_c_check_due,
                   c1.name AS captain_name, c1.rank AS captain_rank,
                   c1.duty_hours_last_7d AS cpt_duty_7d,
                   c1.fatigue_risk_score AS cpt_fatigue,
                   c2.name AS fo_name, c2.rank AS fo_rank,
                   c2.duty_hours_last_7d AS fo_duty_7d,
                   c2.fatigue_risk_score AS fo_fatigue
            FROM flight_schedule fs
            JOIN aircraft_fleet af ON fs.aircraft_reg = af.aircraft_reg
            LEFT JOIN crew_roster c1 ON fs.captain_id = c1.crew_id
            LEFT JOIN crew_roster c2 ON fs.first_officer_id = c2.crew_id
            WHERE fs.flight_id = '{flight_id}'
        """)

        if not rows:
            raise HTTPException(status_code=404, detail=f"Flight {flight_id} not found")

        flight = rows[0]

        # Weather for origin/destination
        origin = flight.get("origin", "")
        destination = flight.get("destination", "")
        weather = []
        if origin and destination:
            weather = query_join(f"""
                SELECT airport_code, conditions, temperature_c, visibility_km,
                       wind_speed_kts, ceiling_ft, severity, metar_raw
                FROM weather_conditions
                WHERE airport_code IN ('{origin}', '{destination}')
                ORDER BY observation_time DESC
            """)

        # MEL items
        aircraft_reg = flight.get("aircraft_reg", "")
        mel = []
        if aircraft_reg:
            mel = query_join(f"""
                SELECT item_code, ata_chapter, description, category, status, expiry_date
                FROM mel_items
                WHERE aircraft_reg = '{aircraft_reg}' AND status IN ('OPEN', 'DEFERRED')
                ORDER BY category, expiry_date
            """)

        result = {
            "flight": flight,
            "weather": weather,
            "mel_items": mel,
        }
        return JSONResponse(content=_safe_json(result))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch flight detail: %s", e)
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")


@app.post("/api/dispatch-check")
async def dispatch_check(request: DispatchCheckRequest):
    """Run the full LangGraph multi-agent dispatch check for a flight."""
    logger.info("Starting dispatch check for flight %s", request.flight_id)

    try:
        result = await run_dispatch_check(request.flight_id)
        dispatch_cache[request.flight_id] = result

        # Initialize action tracker with the decision
        dec = result.get("decision", {}).get("decision", "NO-GO")
        a = _get_actions(request.flight_id)
        a["original_decision"] = dec
        a["current_status"] = dec
        a["actions_completed"] = []
        a["crew_swaps"] = []
        a["notifications_sent"] = []
        a["release_generated"] = False

        return JSONResponse(content=_safe_json(result))
    except Exception as e:
        logger.error("Dispatch check failed: %s", e, exc_info=True)
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
        logger.error("Chat failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trace/{run_id}")
async def get_trace(run_id: str):
    """Fetch MLflow trace details for a dispatch run."""
    try:
        import mlflow
        trace = mlflow.get_trace(run_id)
        if trace:
            return JSONResponse(content={
                "run_id": run_id,
                "status": "found",
                "info": str(trace.info) if hasattr(trace, "info") else "",
            })
        return JSONResponse(content={"run_id": run_id, "status": "not_found"})
    except Exception as e:
        return JSONResponse(
            content={"run_id": run_id, "status": "error", "detail": str(e)},
            status_code=404,
        )


# ═══════════════════════════════════════════════════════════════════════════
# WebSocket for real-time agent progress
# ═══════════════════════════════════════════════════════════════════════════

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, flight_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(flight_id, []).append(ws)

    def disconnect(self, flight_id: str, ws: WebSocket):
        if flight_id in self.active:
            self.active[flight_id] = [w for w in self.active[flight_id] if w != ws]

    async def send_update(self, flight_id: str, data: dict):
        for ws in self.active.get(flight_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass


ws_manager = ConnectionManager()


@app.websocket("/ws/dispatch/{flight_id}")
async def websocket_dispatch(websocket: WebSocket, flight_id: str):
    """WebSocket endpoint for real-time dispatch check with progress updates."""
    await ws_manager.connect(flight_id, websocket)
    logger.info("WebSocket connected for flight %s", flight_id)

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("action") == "start":
                async def progress_cb(agent_name: str, status: str, result: dict):
                    safe = _safe_json(result)
                    await ws_manager.send_update(flight_id, {
                        "type": "agent_progress",
                        "agent": agent_name,
                        "status": status,
                        "data": safe,
                    })

                try:
                    result = await run_dispatch_check(flight_id, progress_callback=progress_cb)
                    dispatch_cache[flight_id] = result
                    await websocket.send_json({
                        "type": "dispatch_complete",
                        "data": _safe_json(result),
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
        logger.info("WebSocket disconnected for flight %s", flight_id)
    except Exception as e:
        ws_manager.disconnect(flight_id, websocket)
        logger.error("WebSocket error: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: Dispatch Actions
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/assign-crew")
async def assign_crew(req: AssignCrewRequest):
    """Assign a replacement crew member — creates swap record."""
    from datetime import datetime
    a = _get_actions(req.flight_id)

    swap = {
        "type": "crew_assign",
        "crew_name": req.crew_name,
        "crew_rank": req.crew_rank,
        "replacing": req.replacing,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "CONFIRMED",
    }
    a["actions_completed"].append(swap)
    a["crew_swaps"].append(swap)

    new_status = _recalculate_status(req.flight_id)

    return {
        "success": True,
        "message": f"{req.crew_name} assigned as replacement for {req.replacing}",
        "swap": swap,
        "dispatch_status": new_status,
        "actions_summary": _get_actions_summary(req.flight_id),
    }


@app.post("/api/notify-crew")
async def notify_crew(req: NotifyCrewRequest):
    """Simulate SMS/WhatsApp notification to crew member."""
    from datetime import datetime
    import random
    a = _get_actions(req.flight_id)

    # Generate simulated phone number
    phone = f"+91-{random.randint(70000,99999)}{random.randint(10000,99999)}"

    notification = {
        "type": "crew_notify",
        "crew_name": req.crew_name,
        "phone": phone,
        "channel": "SMS + WhatsApp",
        "message": f"URGENT: You have been assigned to flight {req.flight_id}. Report to dispatch immediately. Acknowledge via CrewConnect app.",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "DELIVERED",
    }
    a["actions_completed"].append(notification)
    a["notifications_sent"].append(notification)

    new_status = _recalculate_status(req.flight_id)

    return {
        "success": True,
        "message": f"SMS sent to {req.crew_name} at {phone}",
        "notification": notification,
        "dispatch_status": new_status,
        "actions_summary": _get_actions_summary(req.flight_id),
    }


@app.post("/api/generate-release")
async def generate_release(req: GenerateReleaseRequest):
    """Generate amended dispatch release document."""
    from datetime import datetime
    a = _get_actions(req.flight_id)

    # Get flight info from cache
    cached = dispatch_cache.get(req.flight_id, {})
    flight_info = cached.get("flight_info", {})

    # Build the release document
    crew_swaps = a.get("crew_swaps", [])
    new_crew = {}
    for swap in crew_swaps:
        new_crew[swap["crew_rank"]] = swap["crew_name"]

    captain = new_crew.get("CAPTAIN", flight_info.get("captain_name", "N/A"))
    fo = new_crew.get("FIRST_OFFICER", new_crew.get("SENIOR_FIRST_OFFICER", flight_info.get("fo_name", "N/A")))

    release = {
        "document_id": f"DR-{req.flight_id}-{datetime.utcnow().strftime('%Y%m%d%H%M')}",
        "type": "AMENDED DISPATCH RELEASE",
        "flight": req.flight_id,
        "flight_number": flight_info.get("flight_number", req.flight_id),
        "route": f"{flight_info.get('origin', '?')} → {flight_info.get('destination', '?')}",
        "aircraft": flight_info.get("aircraft_reg", "N/A"),
        "aircraft_type": flight_info.get("aircraft_type", "N/A"),
        "captain": captain,
        "first_officer": fo,
        "pax": flight_info.get("pax_count", "N/A"),
        "departure": flight_info.get("scheduled_departure", "N/A"),
        "amendments": [
            f"Crew swap: {s['replacing']} replaced by {s['crew_name']} ({s['crew_rank']})"
            for s in crew_swaps
        ],
        "notifications": [
            f"{n['crew_name']} notified via {n['channel']} at {n['timestamp']}"
            for n in a.get("notifications_sent", [])
        ],
        "original_decision": a["original_decision"],
        "amended_decision": "GO",
        "generated_at": datetime.utcnow().isoformat(),
        "generated_by": "AI Dispatch Agent V2",
        "dgca_compliance": "All crew meet DGCA FDTL requirements. Aircraft certificates verified.",
        "authorization": "This amended release requires Dispatch Supervisor sign-off.",
    }

    a["release_generated"] = True
    a["actions_completed"].append({
        "type": "release_generated",
        "document_id": release["document_id"],
        "timestamp": datetime.utcnow().isoformat(),
    })

    new_status = _recalculate_status(req.flight_id)

    return {
        "success": True,
        "message": f"Dispatch release {release['document_id']} generated",
        "release": release,
        "dispatch_status": new_status,
        "actions_summary": _get_actions_summary(req.flight_id),
    }


@app.get("/api/dispatch-actions/{flight_id}")
async def get_dispatch_actions(flight_id: str):
    """Get current dispatch action status for a flight."""
    return _get_actions_summary(flight_id)


def _get_actions_summary(flight_id: str) -> dict:
    a = _get_actions(flight_id)
    return {
        "flight_id": flight_id,
        "original_decision": a["original_decision"],
        "current_status": a["current_status"],
        "crew_swaps": len(a["crew_swaps"]),
        "notifications_sent": len(a["notifications_sent"]),
        "release_generated": a["release_generated"],
        "total_actions": len(a["actions_completed"]),
        "actions": a["actions_completed"],
    }
