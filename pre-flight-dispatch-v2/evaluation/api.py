"""
Evaluation API routes for the Pre-Flight Dispatch V2 app.

Import and register these in app.py:

    from evaluation.api import register_eval_routes
    register_eval_routes(app)
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("evaluation.api")


class RunEvalRequest(BaseModel):
    category: Optional[str] = None       # "go", "nogo", "conditional", or None
    scenario_id: Optional[str] = None    # run a single scenario by ID
    max_scenarios: Optional[int] = None  # cap scenario count
    dry_run: bool = False                # use mock data


# In-memory cache of the latest eval report
_latest_report: dict = {}


def register_eval_routes(app: FastAPI) -> None:
    """Attach evaluation endpoints to the FastAPI app."""

    @app.post("/api/run-eval")
    async def run_eval_endpoint(request: RunEvalRequest):
        """
        POST /api/run-eval -- trigger an evaluation run.

        Body JSON:
            {"category": "nogo", "max_scenarios": 5, "dry_run": true}

        Returns the full evaluation report with all 12 scorer results.
        """
        global _latest_report

        try:
            from evaluation.run_eval import run_evaluation

            report = await run_evaluation(
                category=request.category,
                scenario_id=request.scenario_id,
                max_scenarios=request.max_scenarios,
                dry_run=request.dry_run,
                log_to_mlflow=True,
            )

            # Strip heavy dispatch_result payloads for the API response
            for ps in report.get("per_scenario", []):
                ps.pop("dispatch_result", None)

            _latest_report = report
            return JSONResponse(content=report)

        except Exception as e:
            logger.error("Evaluation run failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/eval-results")
    async def get_eval_results_endpoint():
        """
        GET /api/eval-results -- return the latest evaluation results.

        Returns 404 if no evaluation has been run yet.
        """
        if not _latest_report:
            raise HTTPException(
                status_code=404,
                detail="No evaluation results available. Run POST /api/run-eval first.",
            )
        return JSONResponse(content=_latest_report)

    @app.get("/api/eval-scenarios")
    async def get_eval_scenarios(
        category: Optional[str] = Query(None, description="go / nogo / conditional"),
    ):
        """
        GET /api/eval-scenarios -- list available evaluation scenarios.
        """
        try:
            from evaluation.eval_dataset import load_scenarios

            scenarios = load_scenarios(category)
            return JSONResponse(content={
                "count": len(scenarios),
                "category": category or "all",
                "scenarios": [
                    {
                        "scenario_id": s["scenario_id"],
                        "description": s["description"],
                        "flight_id": s["flight_id"],
                        "expected_decision": s["expected_decision"],
                        "expected_risk": s.get("expected_risk", "UNKNOWN"),
                        "category": s.get("category", "?"),
                    }
                    for s in scenarios
                ],
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    logger.info("Evaluation API routes registered: /api/run-eval, /api/eval-results, /api/eval-scenarios")
