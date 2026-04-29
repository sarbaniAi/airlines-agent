"""
Pre-Flight Dispatch V2 -- Evaluation Runner.

Loads labeled scenarios, runs each through the dispatch pipeline,
applies all 12 scorers, and logs results to MLflow.

Usage:
    python evaluation/run_eval.py
    python evaluation/run_eval.py --category nogo
    python evaluation/run_eval.py --scenario NOGO-001
    python evaluation/run_eval.py --max 5
    python evaluation/run_eval.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import mlflow

from config import MLFLOW_EXPERIMENT
from evaluation.eval_dataset import load_scenarios, get_scenario_count
from evaluation.scorers import compute_all_scores, get_score_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("evaluation.runner")


# ---------------------------------------------------------------------------
# Live dispatch
# ---------------------------------------------------------------------------

async def _run_live_dispatch(flight_id: str) -> dict:
    """Run a live dispatch check through the actual pipeline."""
    from orchestrator.supervisor import run_dispatch_check
    return await run_dispatch_check(flight_id)


# ---------------------------------------------------------------------------
# Evaluate a single scenario
# ---------------------------------------------------------------------------

async def evaluate_scenario(
    scenario: dict,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Run one evaluation scenario.

    Returns dict with:
      - scenario metadata
      - dispatch_result (full)
      - scores (all 12 metrics)
      - status ("OK" / "ERROR")
    """
    scenario_id = scenario["scenario_id"]
    flight_id = scenario["flight_id"]

    logger.info("Evaluating %s: %s", scenario_id, scenario["description"][:80])

    start = time.time()

    # ---- Run dispatch pipeline ------------------------------------------
    if dry_run:
        dispatch_result = _mock_dispatch_result(scenario)
    else:
        try:
            dispatch_result = await _run_live_dispatch(flight_id)
        except Exception as e:
            logger.error("Dispatch failed for %s: %s", scenario_id, e)
            return {
                "scenario_id": scenario_id,
                "flight_id": flight_id,
                "description": scenario["description"],
                "category": scenario.get("category", "unknown"),
                "status": "ERROR",
                "error": str(e),
                "expected_decision": scenario["expected_decision"],
                "predicted_decision": "ERROR",
                "execution_time": time.time() - start,
                "scores": {},
            }

    exec_time = time.time() - start
    dispatch_result["execution_time_seconds"] = exec_time

    # ---- Score with all 12 scorers -------------------------------------
    try:
        scores = compute_all_scores(dispatch_result, scenario)
    except Exception as e:
        logger.error("Scoring failed for %s: %s", scenario_id, e)
        scores = {"error": str(e)}

    decision = dispatch_result.get("decision", {})
    predicted = decision.get("decision", "UNKNOWN")

    return {
        "scenario_id": scenario_id,
        "flight_id": flight_id,
        "description": scenario["description"],
        "category": scenario.get("category", "unknown"),
        "status": "OK",
        "expected_decision": scenario["expected_decision"],
        "predicted_decision": predicted,
        "correct": predicted.upper() == scenario["expected_decision"].upper(),
        "expected_risk": scenario.get("expected_risk", "UNKNOWN"),
        "predicted_risk": decision.get("risk_level", "UNKNOWN"),
        "execution_time": round(exec_time, 2),
        "scores": scores,
        "dispatch_result": dispatch_result,
    }


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

async def run_evaluation(
    category: str | None = None,
    scenario_id: str | None = None,
    max_scenarios: int | None = None,
    dry_run: bool = False,
    log_to_mlflow: bool = True,
) -> dict[str, Any]:
    """
    Run the full evaluation suite.

    Args:
        category:      Optional filter -- "go", "nogo", "conditional".
        scenario_id:   Optional single scenario to run.
        max_scenarios: Cap the number of scenarios (useful for quick tests).
        dry_run:       Use mock data instead of live dispatch.
        log_to_mlflow: Whether to log results to MLflow.

    Returns:
        Complete evaluation report dict.
    """
    # ---- Load scenarios -------------------------------------------------
    scenarios = load_scenarios(category)

    if scenario_id:
        scenarios = [s for s in scenarios if s["scenario_id"] == scenario_id]
        if not scenarios:
            return {"error": f"Scenario {scenario_id} not found"}

    if max_scenarios and max_scenarios > 0:
        scenarios = scenarios[:max_scenarios]

    logger.info(
        "Running evaluation: %d scenarios (category=%s, dry_run=%s)",
        len(scenarios), category or "all", dry_run,
    )

    # ---- Set up MLflow --------------------------------------------------
    if log_to_mlflow:
        try:
            mlflow.set_experiment(MLFLOW_EXPERIMENT)
        except Exception as e:
            logger.warning("Could not set MLflow experiment: %s", e)
            log_to_mlflow = False

    # ---- Execute --------------------------------------------------------
    eval_results: list[dict] = []

    for i, scenario in enumerate(scenarios):
        logger.info("[%d/%d] %s", i + 1, len(scenarios), scenario["scenario_id"])
        result = await evaluate_scenario(scenario, dry_run=dry_run)
        eval_results.append(result)

    # ---- Aggregate scores -----------------------------------------------
    valid_results = [r for r in eval_results if r.get("status") == "OK"]
    scores_list = [r["scores"] for r in valid_results if r.get("scores") and "error" not in r["scores"]]
    score_summary = get_score_summary(scores_list) if scores_list else {"error": "No valid scores"}

    # ---- Build report ---------------------------------------------------
    report: dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_scenarios": len(scenarios),
        "completed": len(valid_results),
        "errors": len(eval_results) - len(valid_results),
        "dry_run": dry_run,
        "category": category or "all",
        "score_summary": score_summary,
        "per_scenario": [
            {
                "scenario_id": r["scenario_id"],
                "category": r.get("category", "?"),
                "expected": r["expected_decision"],
                "predicted": r.get("predicted_decision", "?"),
                "correct": r.get("correct", False),
                "exec_time": r.get("execution_time", 0),
                "scores": r.get("scores", {}),
            }
            for r in eval_results
        ],
        "error_details": [
            {"scenario_id": r["scenario_id"], "error": r.get("error", "")}
            for r in eval_results if r.get("status") == "ERROR"
        ],
    }

    # ---- Log to MLflow --------------------------------------------------
    if log_to_mlflow and scores_list:
        _log_to_mlflow(report, eval_results, score_summary)

    return report


def _log_to_mlflow(
    report: dict,
    eval_results: list[dict],
    score_summary: dict,
) -> None:
    """Log evaluation run and per-scenario child runs to MLflow."""
    try:
        run_name = f"eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        with mlflow.start_run(run_name=run_name) as parent_run:
            # -- Aggregate metrics --
            mlflow.log_param("category", report.get("category", "all"))
            mlflow.log_param("dry_run", report.get("dry_run", False))
            mlflow.log_param("scenario_count", report["total_scenarios"])

            overall = score_summary.get("overall_score", 0)
            mlflow.log_metric("overall_score", overall)

            for key in [
                "answer_correctness", "faithfulness", "relevance",
                "chunk_relevance", "decision_correctness",
                "safety_compliance", "guardrail_accuracy",
                "completeness", "recommendation_quality",
                "latency_budget", "regulatory_citation",
                "action_specificity",
            ]:
                stats = score_summary.get(key, {})
                if isinstance(stats, dict) and "mean" in stats:
                    mlflow.log_metric(f"{key}_mean", stats["mean"])
                    mlflow.log_metric(f"{key}_min", stats["min"])
                    mlflow.log_metric(f"{key}_max", stats["max"])

            mlflow.log_metric("total_scenarios", report["total_scenarios"])
            mlflow.log_metric("errors", report["errors"])
            correct_count = sum(1 for r in eval_results if r.get("correct"))
            mlflow.log_metric("correct_decisions", correct_count)

            # -- Log each scenario as a child run --------------------------
            for result in eval_results:
                if result.get("status") != "OK":
                    continue
                child_name = result["scenario_id"]
                with mlflow.start_run(
                    run_name=child_name, nested=True
                ):
                    mlflow.log_param("scenario_id", result["scenario_id"])
                    mlflow.log_param("flight_id", result["flight_id"])
                    mlflow.log_param("expected_decision", result["expected_decision"])
                    mlflow.log_param("predicted_decision", result.get("predicted_decision", "?"))
                    mlflow.log_param("correct", result.get("correct", False))

                    for metric_name, metric_val in result.get("scores", {}).items():
                        if isinstance(metric_val, (int, float)):
                            mlflow.log_metric(metric_name, metric_val)

                    mlflow.log_metric("execution_time", result.get("execution_time", 0))

            # -- Save full report as artifact ------------------------------
            report_path = os.path.join(PROJECT_ROOT, "evaluation", "latest_report.json")
            with open(report_path, "w") as f:
                # strip heavy dispatch_result from serialised report
                slim = dict(report)
                for ps in slim.get("per_scenario", []):
                    ps.pop("dispatch_result", None)
                json.dump(slim, f, indent=2, default=str)
            mlflow.log_artifact(report_path)

            logger.info(
                "Results logged to MLflow run %s (overall_score=%.3f)",
                parent_run.info.run_id, overall,
            )
    except Exception as e:
        logger.warning("Failed to log to MLflow: %s", e)


# ---------------------------------------------------------------------------
# Mock dispatch for dry-run / unit tests
# ---------------------------------------------------------------------------

def _mock_dispatch_result(scenario: dict) -> dict:
    """Generate a deterministic mock dispatch result for dry-run testing."""
    expected = scenario["expected_decision"]

    status_map = {
        "GO": {"aircraft_health": "GREEN", "crew_legality": "GREEN",
               "weather_notam": "GREEN", "regulatory_compliance": "GREEN"},
        "NO-GO": {"aircraft_health": "RED", "crew_legality": "GREEN",
                   "weather_notam": "GREEN", "regulatory_compliance": "RED"},
        "CONDITIONAL": {"aircraft_health": "AMBER", "crew_legality": "AMBER",
                        "weather_notam": "GREEN", "regulatory_compliance": "GREEN"},
    }
    statuses = status_map.get(expected, status_map["CONDITIONAL"])

    agent_results = {}
    for agent_name, status in statuses.items():
        findings = []
        recs = []
        if status == "RED":
            findings = [f"CRITICAL: {agent_name} check failed - {c}" for c in scenario.get("key_checks", ["issue detected"])]
            recs = [f"Resolve {agent_name} issues before dispatch"]
        elif status == "AMBER":
            findings = [f"WARNING: {agent_name} marginal - {c}" for c in scenario.get("key_checks", ["advisory"])]
            recs = [f"Monitor {agent_name} conditions"]
        else:
            findings = [f"{agent_name}: all checks passed"]
        agent_results[agent_name] = {
            "status": status,
            "findings": findings,
            "recommendations": recs,
            "regulatory_references": scenario.get("expected_triggered_rules", []),
            "details": {},
        }

    decision_conf = {"GO": 0.95, "NO-GO": 0.98, "CONDITIONAL": 0.80}
    risk_map = {"GO": "LOW", "NO-GO": "CRITICAL", "CONDITIONAL": "MEDIUM"}

    return {
        "flight_id": scenario["flight_id"],
        "flight_info": {
            "flight_id": scenario["flight_id"],
            "flight_number": f"AI-{scenario['flight_id'].split('-')[-1]}",
            "origin": "DEL",
            "destination": "LHR",
            "aircraft_reg": "VT-ANA",
            "captain_name": "Capt. Sharma",
            "fo_name": "FO Patel",
        },
        "agent_results": agent_results,
        "decision": {
            "decision": expected,
            "confidence": decision_conf.get(expected, 0.75),
            "summary": f"Mock {expected} decision for {scenario['scenario_id']}",
            "reasoning": (
                f"Based on analysis per DGCA CAR Section 8, "
                f"the dispatch status is {expected}. "
                f"Aircraft VT-ANA checked. "
                f"Checks: {', '.join(scenario.get('key_checks', []))}"
            ),
            "actions": [
                f"Action: swap crew per DGCA FDTL regulations" if expected != "GO" else "No actions required"
            ],
            "alternatives": [
                f"Replace with standby aircraft VT-ANB"
            ] if expected == "NO-GO" else [],
            "risk_level": risk_map.get(expected, "MEDIUM"),
        },
        "execution_time_seconds": 0.5,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Pretty-print report
# ---------------------------------------------------------------------------

def print_report(report: dict) -> None:
    """Pretty-print the evaluation report to stdout."""
    print("\n" + "=" * 80)
    print("  AIR INDIA PRE-FLIGHT DISPATCH V2 -- EVALUATION REPORT")
    print("=" * 80)
    print(f"  Timestamp:  {report['timestamp']}")
    print(f"  Scenarios:  {report['total_scenarios']} total, "
          f"{report['completed']} completed, {report['errors']} errors")
    print(f"  Category:   {report.get('category', 'all')}")
    print(f"  Mode:       {'DRY RUN (mock data)' if report['dry_run'] else 'LIVE'}")

    summary = report.get("score_summary", {})
    overall = summary.get("overall_score", 0)
    print(f"\n  OVERALL SCORE: {overall:.1%}")
    print("-" * 80)

    scorer_labels = [
        ("answer_correctness",     "Answer Correctness (LLM)"),
        ("faithfulness",           "Faithfulness (LLM)"),
        ("relevance",              "Relevance (LLM)"),
        ("chunk_relevance",        "Chunk Relevance (LLM)"),
        ("decision_correctness",   "Decision Correctness"),
        ("safety_compliance",      "Safety Compliance"),
        ("guardrail_accuracy",     "Guardrail Accuracy (F1)"),
        ("completeness",           "Completeness"),
        ("recommendation_quality", "Recommendation Quality"),
        ("latency_budget",         "Latency Budget"),
        ("regulatory_citation",    "Regulatory Citation"),
        ("action_specificity",     "Action Specificity"),
    ]

    for key, label in scorer_labels:
        stats = summary.get(key, {})
        if isinstance(stats, dict) and "mean" in stats:
            mean = stats["mean"]
            bar = "#" * int(mean * 30)
            print(f"  {label:32s} {mean:6.1%}  [{bar:30s}]  "
                  f"(min={stats['min']:.1%} max={stats['max']:.1%})")

    # Per-scenario table
    print("\n" + "-" * 80)
    print(f"  {'Scenario':<12} {'Cat':<6} {'Expected':<14} "
          f"{'Predicted':<14} {'Match':>6} {'Time':>8} {'DCorr':>6}")
    print("-" * 80)

    for r in report.get("per_scenario", []):
        match_str = "OK" if r.get("correct") else "MISS"
        dcorr = r.get("scores", {}).get("decision_correctness", "?")
        dcorr_str = f"{dcorr:.2f}" if isinstance(dcorr, (int, float)) else "?"
        print(
            f"  {r['scenario_id']:<12} {r.get('category','?'):<6} "
            f"{r['expected']:<14} {r.get('predicted','?'):<14} "
            f"{match_str:>6} {r.get('exec_time', 0):>7.1f}s {dcorr_str:>6}"
        )

    if report.get("error_details"):
        print(f"\n  ERRORS ({len(report['error_details'])}):")
        for ed in report["error_details"]:
            print(f"    {ed['scenario_id']}: {ed['error'][:100]}")

    print("=" * 80 + "\n")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Pre-Flight Dispatch V2 Evaluation Runner (12 scorers)"
    )
    parser.add_argument(
        "--category", choices=["go", "nogo", "conditional"], default=None,
        help="Run only scenarios in this category",
    )
    parser.add_argument(
        "--scenario", default=None,
        help="Run a single scenario by ID (e.g., NOGO-001)",
    )
    parser.add_argument(
        "--max", type=int, default=None, dest="max_scenarios",
        help="Cap the number of scenarios to run",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Use mock data instead of live dispatch",
    )
    parser.add_argument(
        "--no-mlflow", action="store_true",
        help="Do not log results to MLflow",
    )

    args = parser.parse_args()

    report = asyncio.run(
        run_evaluation(
            category=args.category,
            scenario_id=args.scenario,
            max_scenarios=args.max_scenarios,
            dry_run=args.dry_run,
            log_to_mlflow=not args.no_mlflow,
        )
    )

    print_report(report)

    # Save report to disk
    report_path = os.path.join(PROJECT_ROOT, "evaluation", "latest_report.json")
    slim = dict(report)
    for ps in slim.get("per_scenario", []):
        ps.pop("dispatch_result", None)
    with open(report_path, "w") as f:
        json.dump(slim, f, indent=2, default=str)
    logger.info("Report saved to %s", report_path)


if __name__ == "__main__":
    main()
