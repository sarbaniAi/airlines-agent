"""
Pre-Flight Dispatch V2 — Evaluation Runner.

Loads labeled scenarios, runs each through the dispatch pipeline,
scores with all custom metrics, and logs results to MLflow.

Usage:
    python evaluation/run_eval.py
    python evaluation/run_eval.py --category nogo
    python evaluation/run_eval.py --scenario NOGO-001
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
from evaluation.scorers import compute_all_scores
from guardrails.output_validator import run_all_output_validations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("evaluation.runner")


# ---------------------------------------------------------------------------
# Mock dispatch function for dry-run / unit test mode
# ---------------------------------------------------------------------------

def _mock_dispatch_result(scenario: dict) -> dict:
    """Generate a mock dispatch result for dry-run testing."""
    decision_map = {
        "GO": {
            "decision": "GO",
            "confidence": 0.95,
            "risk_level": "LOW",
            "summary": f"Mock GO decision for {scenario['scenario_id']}",
            "reasoning": "All systems green in mock mode.",
            "actions": [],
            "alternatives": [],
        },
        "NO-GO": {
            "decision": "NO-GO",
            "confidence": 0.98,
            "risk_level": "CRITICAL",
            "summary": f"Mock NO-GO decision for {scenario['scenario_id']}",
            "reasoning": "Critical issues found in mock mode.",
            "actions": ["Address critical issue before dispatch"],
            "alternatives": ["Swap aircraft", "Swap crew"],
        },
        "CONDITIONAL": {
            "decision": "CONDITIONAL",
            "confidence": 0.80,
            "risk_level": "MEDIUM",
            "summary": f"Mock CONDITIONAL decision for {scenario['scenario_id']}",
            "reasoning": "Multiple amber findings in mock mode.",
            "actions": ["Monitor conditions", "Prepare backup plan"],
            "alternatives": [],
        },
    }

    expected = scenario["expected_decision"]
    agent_statuses = {
        "GO": {"aircraft_health": "GREEN", "crew_legality": "GREEN", "weather_slots": "GREEN", "regulatory_compliance": "GREEN"},
        "NO-GO": {"aircraft_health": "RED", "crew_legality": "GREEN", "weather_slots": "GREEN", "regulatory_compliance": "GREEN"},
        "CONDITIONAL": {"aircraft_health": "AMBER", "crew_legality": "AMBER", "weather_slots": "GREEN", "regulatory_compliance": "GREEN"},
    }

    statuses = agent_statuses.get(expected, agent_statuses["CONDITIONAL"])
    agent_results = {}
    for agent_name, status in statuses.items():
        agent_results[agent_name] = {
            "status": status,
            "findings": [f"Mock finding for {agent_name}"],
            "recommendations": [f"Mock recommendation for {agent_name}"] if status != "GREEN" else [],
            "details": {},
        }

    return {
        "flight_id": scenario["flight_id"],
        "flight_info": {"flight_id": scenario["flight_id"], "flight_number": f"AI {scenario['flight_id'].split('-')[1]}"},
        "agent_results": agent_results,
        "decision": decision_map.get(expected, decision_map["CONDITIONAL"]),
        "execution_time_seconds": 0.5,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Live dispatch function (imports the real orchestrator)
# ---------------------------------------------------------------------------

async def _run_live_dispatch(flight_id: str) -> dict:
    """Run a live dispatch check through the actual pipeline."""
    try:
        from orchestrator import run_dispatch_check  # type: ignore
        result = await run_dispatch_check(flight_id)
        return result
    except ImportError:
        logger.warning("Orchestrator not available. Using V1 orchestrator.")
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "..", "pre-flight-dispatch"))
        from agents.orchestrator import run_dispatch_check as v1_dispatch  # type: ignore
        result = await v1_dispatch(flight_id)
        return result


# ---------------------------------------------------------------------------
# Evaluate a single scenario
# ---------------------------------------------------------------------------

async def evaluate_scenario(
    scenario: dict,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Run a single evaluation scenario.

    Args:
        scenario: The scenario dict from the JSON file.
        dry_run: If True, use mock data instead of live dispatch.

    Returns:
        Evaluation result dict.
    """
    scenario_id = scenario["scenario_id"]
    flight_id = scenario["flight_id"]
    expected_decision = scenario["expected_decision"]
    expected_risk = scenario.get("expected_risk", "UNKNOWN")
    expected_rules = scenario.get("expected_triggered_rules", [])

    logger.info(f"Evaluating {scenario_id}: {scenario['description'][:80]}...")

    start = time.time()

    # Run dispatch
    if dry_run:
        dispatch_result = _mock_dispatch_result(scenario)
    else:
        try:
            dispatch_result = await _run_live_dispatch(flight_id)
        except Exception as e:
            logger.error(f"Dispatch failed for {scenario_id}: {e}")
            return {
                "scenario_id": scenario_id,
                "status": "ERROR",
                "error": str(e),
                "predicted_decision": "ERROR",
                "expected_decision": expected_decision,
                "execution_time": time.time() - start,
            }

    exec_time = time.time() - start

    # Extract results
    agent_results = dispatch_result.get("agent_results", {})
    raw_decision = dispatch_result.get("decision", {})

    # Run guardrails
    guardrail_result = run_all_output_validations(raw_decision, agent_results)
    final_decision = guardrail_result["final_decision"]
    predicted_decision = final_decision.get("decision", "UNKNOWN")

    return {
        "scenario_id": scenario_id,
        "flight_id": flight_id,
        "description": scenario["description"],
        "category": scenario.get("category", "unknown"),
        "status": "OK",
        "predicted_decision": predicted_decision,
        "expected_decision": expected_decision,
        "predicted_risk": final_decision.get("risk_level", "UNKNOWN"),
        "expected_risk": expected_risk,
        "decision": final_decision,
        "agent_results": agent_results,
        "triggered_rules": guardrail_result.get("triggered_rules", []),
        "expected_triggered_rules": expected_rules,
        "safety_overrides": guardrail_result.get("safety_overrides", []),
        "guardrail_active": guardrail_result.get("guardrail_active", False),
        "guardrail_result": guardrail_result,
        "hallucination_issues": guardrail_result.get("hallucination_issues", []),
        "validation_errors": guardrail_result.get("validation_errors", []),
        "execution_time": exec_time,
    }


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

async def run_evaluation(
    category: str | None = None,
    scenario_id: str | None = None,
    dry_run: bool = False,
    log_to_mlflow: bool = True,
) -> dict[str, Any]:
    """
    Run the full evaluation suite.

    Args:
        category: Optional filter — "go", "nogo", "conditional".
        scenario_id: Optional single scenario to run.
        dry_run: Use mock data instead of live dispatch.
        log_to_mlflow: Whether to log results to MLflow.

    Returns:
        Complete evaluation report.
    """
    # Load scenarios
    scenarios = load_scenarios(category)

    if scenario_id:
        scenarios = [s for s in scenarios if s["scenario_id"] == scenario_id]
        if not scenarios:
            logger.error(f"Scenario {scenario_id} not found")
            return {"error": f"Scenario {scenario_id} not found"}

    logger.info(f"Running evaluation: {len(scenarios)} scenarios (dry_run={dry_run})")

    # Set up MLflow
    if log_to_mlflow:
        try:
            mlflow.set_experiment(MLFLOW_EXPERIMENT)
        except Exception as e:
            logger.warning(f"Could not set MLflow experiment: {e}")
            log_to_mlflow = False

    eval_results: list[dict] = []
    errors: list[dict] = []

    # Run each scenario
    for i, scenario in enumerate(scenarios):
        logger.info(f"[{i+1}/{len(scenarios)}] {scenario['scenario_id']}")
        result = await evaluate_scenario(scenario, dry_run=dry_run)

        if result.get("status") == "ERROR":
            errors.append(result)
        eval_results.append(result)

    # Compute scores
    valid_results = [r for r in eval_results if r.get("status") == "OK"]
    scores = compute_all_scores(valid_results) if valid_results else {"error": "No valid results"}

    # Build report
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_scenarios": len(scenarios),
        "completed": len(valid_results),
        "errors": len(errors),
        "dry_run": dry_run,
        "scores": scores,
        "error_details": errors,
        "per_scenario": [
            {
                "scenario_id": r["scenario_id"],
                "expected": r["expected_decision"],
                "predicted": r["predicted_decision"],
                "correct": r["predicted_decision"] == r["expected_decision"],
                "guardrail_active": r.get("guardrail_active", False),
                "overrides": len(r.get("safety_overrides", [])),
                "exec_time": round(r.get("execution_time", 0), 2),
            }
            for r in eval_results
        ],
    }

    # Log to MLflow
    if log_to_mlflow and valid_results:
        try:
            with mlflow.start_run(run_name=f"eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"):
                # Log aggregate metrics
                summary = scores.get("summary", {})
                mlflow.log_metric("overall_score", summary.get("overall_score", 0))
                mlflow.log_metric("decision_correctness_mean", scores.get("decision_correctness", {}).get("mean", 0))
                mlflow.log_metric("safety_compliance_mean", scores.get("safety_compliance", {}).get("mean", 0))
                mlflow.log_metric("completeness_mean", scores.get("completeness", {}).get("mean", 0))
                mlflow.log_metric("recommendation_quality_mean", scores.get("recommendation_quality", {}).get("mean", 0))
                mlflow.log_metric("guardrail_effectiveness_mean", scores.get("guardrail_effectiveness", {}).get("mean", 0))
                mlflow.log_metric("latency_mean", scores.get("latency", {}).get("mean", 0))
                mlflow.log_metric("latency_p95", scores.get("latency", {}).get("p95", 0))
                mlflow.log_metric("total_scenarios", len(scenarios))
                mlflow.log_metric("errors", len(errors))

                # Log params
                mlflow.log_param("category", category or "all")
                mlflow.log_param("dry_run", dry_run)
                mlflow.log_param("scenario_count", len(scenarios))

                # Log report as artifact
                report_path = os.path.join(PROJECT_ROOT, "evaluation", "latest_report.json")
                with open(report_path, "w") as f:
                    json.dump(report, f, indent=2, default=str)
                mlflow.log_artifact(report_path)

                logger.info("Results logged to MLflow")
        except Exception as e:
            logger.warning(f"Failed to log to MLflow: {e}")

    return report


# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------

def print_report(report: dict):
    """Pretty-print the evaluation report to stdout."""
    print("\n" + "=" * 80)
    print("  AIR INDIA PRE-FLIGHT DISPATCH V2 — EVALUATION REPORT")
    print("=" * 80)
    print(f"  Timestamp:  {report['timestamp']}")
    print(f"  Scenarios:  {report['total_scenarios']} total, {report['completed']} completed, {report['errors']} errors")
    print(f"  Mode:       {'DRY RUN (mock data)' if report['dry_run'] else 'LIVE'}")

    scores = report.get("scores", {})
    summary = scores.get("summary", {})

    print(f"\n  OVERALL SCORE: {summary.get('overall_score', 0):.1%}")
    print("-" * 80)

    metrics = [
        ("Decision Correctness", "decision_correctness"),
        ("Safety Compliance", "safety_compliance"),
        ("Completeness", "completeness"),
        ("Recommendation Quality", "recommendation_quality"),
        ("Guardrail Effectiveness", "guardrail_effectiveness"),
    ]

    for label, key in metrics:
        m = scores.get(key, {})
        mean = m.get("mean", 0)
        bar = "#" * int(mean * 30)
        print(f"  {label:30s} {mean:6.1%}  [{bar:30s}]")

    latency = scores.get("latency", {})
    print(f"\n  Latency: mean={latency.get('mean', 0):.1f}s, p50={latency.get('p50', 0):.1f}s, p95={latency.get('p95', 0):.1f}s")

    print(f"\n  Perfect decisions: {summary.get('perfect_decisions', 0)}/{report['completed']}")
    print(f"  Safety perfect:    {summary.get('safety_perfect', 0)}/{report['completed']}")
    print(f"  Guardrail perfect: {summary.get('guardrail_perfect', 0)}/{report['completed']}")

    # Per-scenario details
    print("\n" + "-" * 80)
    print(f"  {'Scenario':<12} {'Expected':<14} {'Predicted':<14} {'Match':>6} {'Guard':>6} {'Time':>8}")
    print("-" * 80)

    for r in report.get("per_scenario", []):
        match_icon = "OK" if r["correct"] else "MISS"
        guard_icon = "YES" if r["guardrail_active"] else "-"
        print(
            f"  {r['scenario_id']:<12} {r['expected']:<14} {r['predicted']:<14} "
            f"{match_icon:>6} {guard_icon:>6} {r['exec_time']:>7.1f}s"
        )

    print("=" * 80 + "\n")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pre-Flight Dispatch V2 Evaluation Runner")
    parser.add_argument("--category", choices=["go", "nogo", "conditional"], default=None,
                        help="Run only scenarios in this category")
    parser.add_argument("--scenario", default=None,
                        help="Run a single scenario by ID (e.g., NOGO-001)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use mock data instead of live dispatch")
    parser.add_argument("--no-mlflow", action="store_true",
                        help="Do not log results to MLflow")

    args = parser.parse_args()

    report = asyncio.run(
        run_evaluation(
            category=args.category,
            scenario_id=args.scenario,
            dry_run=args.dry_run,
            log_to_mlflow=not args.no_mlflow,
        )
    )

    print_report(report)

    # Save report
    report_path = os.path.join(PROJECT_ROOT, "evaluation", "latest_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
