"""
Pre-Flight Dispatch V2 — MLflow Evaluation Scorers.

Custom scorers for evaluating the dispatch decision pipeline.
Each scorer follows the MLflow make_metric interface.
"""

import json
import logging
from typing import Any

import numpy as np

logger = logging.getLogger("evaluation.scorers")


# ---------------------------------------------------------------------------
# Custom Scorer: Decision Correctness
# ---------------------------------------------------------------------------

def decision_correctness_score(
    predictions: list[str],
    targets: list[str],
) -> list[float]:
    """
    Score whether the predicted decision matches the expected decision.

    Scoring:
        1.0 = exact match (e.g., both GO)
        0.5 = partial match (CONDITIONAL vs NO-GO, or CONDITIONAL vs GO)
        0.0 = completely wrong (GO vs NO-GO)

    Args:
        predictions: List of predicted decisions (GO, NO-GO, CONDITIONAL).
        targets: List of expected decisions.

    Returns:
        List of scores (0.0 to 1.0).
    """
    PARTIAL_MATCHES = {
        ("CONDITIONAL", "NO-GO"),
        ("NO-GO", "CONDITIONAL"),
        ("CONDITIONAL", "GO"),
        ("GO", "CONDITIONAL"),
    }

    scores = []
    for pred, target in zip(predictions, targets):
        pred_clean = str(pred).upper().strip()
        target_clean = str(target).upper().strip()

        if pred_clean == target_clean:
            scores.append(1.0)
        elif (pred_clean, target_clean) in PARTIAL_MATCHES:
            scores.append(0.5)
        else:
            scores.append(0.0)

    return scores


# ---------------------------------------------------------------------------
# Custom Scorer: Safety Compliance
# ---------------------------------------------------------------------------

def safety_compliance_score(
    agent_results_list: list[dict],
    triggered_rules_list: list[list[dict]],
    expected_rules_list: list[list[str]],
) -> list[float]:
    """
    Score whether the system caught ALL safety-critical items.

    Checks:
        - Every RED finding in the scenario was flagged
        - Expected safety rules were triggered

    Scoring:
        1.0 = all critical items caught, all expected rules triggered
        0.0 = missed a critical safety item

    Args:
        agent_results_list: List of agent_results dicts per scenario.
        triggered_rules_list: List of triggered rule lists per scenario.
        expected_rules_list: List of expected rule ID lists per scenario.

    Returns:
        List of scores (0.0 to 1.0).
    """
    scores = []

    for agent_results, triggered_rules, expected_rules in zip(
        agent_results_list, triggered_rules_list, expected_rules_list
    ):
        if not expected_rules:
            # No specific rules expected — check if RED agents were caught
            red_agents = [
                name for name, result in agent_results.items()
                if result.get("status") == "RED"
            ]
            if not red_agents:
                scores.append(1.0)  # No red agents, nothing to catch
            else:
                # Check that triggered rules cover the RED agents
                triggered_categories = {r.get("category", "") for r in triggered_rules}
                category_map = {
                    "aircraft_health": "aircraft",
                    "crew_legality": "crew",
                    "weather_slots": "weather",
                    "regulatory_compliance": "regulatory",
                }
                red_categories = {category_map.get(a, a) for a in red_agents}
                covered = red_categories.intersection(triggered_categories)
                scores.append(len(covered) / len(red_categories) if red_categories else 1.0)
        else:
            # Check expected rules were triggered
            triggered_ids = {r["rule_id"] for r in triggered_rules}
            expected_set = set(expected_rules)
            matched = triggered_ids.intersection(expected_set)
            scores.append(len(matched) / len(expected_set) if expected_set else 1.0)

    return scores


# ---------------------------------------------------------------------------
# Custom Scorer: Completeness
# ---------------------------------------------------------------------------

def completeness_score(
    agent_results_list: list[dict],
) -> list[float]:
    """
    Score whether all required dimensions were checked.

    Required dimensions:
        - aircraft_health
        - crew_legality
        - weather_slots
        - regulatory_compliance

    Optionally:
        - genie_analytics (bonus, not required)

    Scoring:
        1.0 = all 4 required dimensions checked with findings
        0.75 = 3 of 4 checked
        0.5 = 2 of 4 checked
        0.25 = 1 of 4 checked
        0.0 = none checked

    Args:
        agent_results_list: List of agent_results dicts per scenario.

    Returns:
        List of scores (0.0 to 1.0).
    """
    REQUIRED_AGENTS = {"aircraft_health", "crew_legality", "weather_slots", "regulatory_compliance"}

    scores = []
    for agent_results in agent_results_list:
        checked = 0
        for agent_name in REQUIRED_AGENTS:
            result = agent_results.get(agent_name, {})
            # An agent is considered "checked" if it has a status and findings
            if result.get("status") and result.get("findings"):
                checked += 1

        scores.append(checked / len(REQUIRED_AGENTS))

    return scores


# ---------------------------------------------------------------------------
# Custom Scorer: Recommendation Quality
# ---------------------------------------------------------------------------

def recommendation_quality_score(
    decisions: list[dict],
    agent_results_list: list[dict],
) -> list[float]:
    """
    Score whether recommendations are actionable and specific.

    Checks:
        - Mentions specific crew names, aircraft registrations, certificate numbers
        - Provides concrete actions (not just "check" or "review")
        - References specific data from agent findings

    Scoring:
        1.0 = highly specific and actionable
        0.5 = moderately specific
        0.0 = generic or missing

    Args:
        decisions: List of decision dicts per scenario.
        agent_results_list: List of agent_results dicts per scenario.

    Returns:
        List of scores (0.0 to 1.0).
    """
    scores = []

    for decision, agent_results in zip(decisions, agent_results_list):
        actions = decision.get("actions", [])
        alternatives = decision.get("alternatives", [])
        reasoning = str(decision.get("reasoning", ""))

        all_text = " ".join(actions + alternatives) + " " + reasoning

        if not all_text.strip():
            scores.append(0.0)
            continue

        specificity_points = 0
        max_points = 5

        # Check for aircraft registration mentions (VT-XXX pattern)
        import re
        if re.search(r"VT-[A-Z]{3}", all_text):
            specificity_points += 1

        # Check for crew name mentions (proper nouns)
        for agent_name, result in agent_results.items():
            for finding in result.get("findings", []):
                # Extract names (capitalized words that appear in both finding and recommendation)
                words = finding.split()
                for word in words:
                    if word[0:1].isupper() and len(word) > 3 and word.lower() not in (
                        "captain", "first", "officer", "aircraft", "expired", "missing",
                        "valid", "green", "amber", "check", "exceeds",
                    ):
                        if word in all_text:
                            specificity_points += 1
                            break
                break  # Only check first finding per agent

        # Check for certificate number mentions
        if re.search(r"(cert|certificate)\s*#?\s*\w{3,}", all_text, re.IGNORECASE):
            specificity_points += 1

        # Check for date/time references
        if re.search(r"\d{4}-\d{2}-\d{2}|\d+ (hours?|days?|minutes?)", all_text):
            specificity_points += 1

        # Check for actionable verbs
        actionable_verbs = ["replace", "swap", "delay", "divert", "rectify", "renew", "ground", "schedule"]
        if any(verb in all_text.lower() for verb in actionable_verbs):
            specificity_points += 1

        scores.append(min(specificity_points / max_points, 1.0))

    return scores


# ---------------------------------------------------------------------------
# Custom Scorer: Guardrail Effectiveness
# ---------------------------------------------------------------------------

def guardrail_effectiveness_score(
    guardrail_results: list[dict],
    expected_decisions: list[str],
) -> list[float]:
    """
    Score whether guardrails correctly overrode unsafe LLM decisions.

    For NO-GO scenarios:
        - If guardrail was needed and triggered -> 1.0
        - If guardrail was needed but not triggered -> 0.0
        - If guardrail was not needed -> 1.0

    For GO scenarios:
        - If guardrail incorrectly triggered (false positive) -> 0.0
        - If guardrail correctly stayed silent -> 1.0

    Args:
        guardrail_results: List of output validator results per scenario.
        expected_decisions: List of expected decision strings.

    Returns:
        List of scores (0.0 to 1.0).
    """
    scores = []

    for gr, expected in zip(guardrail_results, expected_decisions):
        expected_clean = str(expected).upper().strip()
        guardrail_active = gr.get("guardrail_active", False)
        final_decision = gr.get("final_decision", {}).get("decision", "UNKNOWN")

        if expected_clean == "NO-GO":
            # Guardrail should have enforced NO-GO
            if final_decision == "NO-GO":
                scores.append(1.0)  # Correct outcome regardless of how
            else:
                scores.append(0.0)  # Missed a safety-critical scenario
        elif expected_clean == "GO":
            if guardrail_active and final_decision != "GO":
                scores.append(0.0)  # False positive — guardrail blocked a valid GO
            else:
                scores.append(1.0)
        elif expected_clean == "CONDITIONAL":
            if final_decision in ("CONDITIONAL", "NO-GO"):
                scores.append(1.0)  # Acceptable — at least as cautious as needed
            elif final_decision == "GO":
                scores.append(0.0)  # Too permissive
            else:
                scores.append(0.5)
        else:
            scores.append(0.5)  # Unknown expected decision

    return scores


# ---------------------------------------------------------------------------
# Aggregate Scorers (for summary reporting)
# ---------------------------------------------------------------------------

def compute_all_scores(eval_results: list[dict]) -> dict[str, Any]:
    """
    Compute all custom scores from a list of evaluation results.

    Each eval_result should contain:
        - predicted_decision: str
        - expected_decision: str
        - agent_results: dict
        - triggered_rules: list
        - expected_triggered_rules: list
        - decision: dict (full decision object)
        - guardrail_result: dict
        - execution_time: float

    Returns:
        Dictionary with per-metric scores and aggregate statistics.
    """
    n = len(eval_results)
    if n == 0:
        return {"error": "No evaluation results provided"}

    # Extract fields
    predictions = [r["predicted_decision"] for r in eval_results]
    targets = [r["expected_decision"] for r in eval_results]
    agent_results_list = [r.get("agent_results", {}) for r in eval_results]
    triggered_rules_list = [r.get("triggered_rules", []) for r in eval_results]
    expected_rules_list = [r.get("expected_triggered_rules", []) for r in eval_results]
    decisions = [r.get("decision", {}) for r in eval_results]
    guardrail_results = [r.get("guardrail_result", {}) for r in eval_results]
    exec_times = [r.get("execution_time", 0) for r in eval_results]

    # Compute scores
    correctness = decision_correctness_score(predictions, targets)
    safety = safety_compliance_score(agent_results_list, triggered_rules_list, expected_rules_list)
    completeness = completeness_score(agent_results_list)
    rec_quality = recommendation_quality_score(decisions, agent_results_list)
    guardrail_eff = guardrail_effectiveness_score(guardrail_results, targets)

    return {
        "decision_correctness": {
            "scores": correctness,
            "mean": float(np.mean(correctness)),
            "std": float(np.std(correctness)),
            "min": float(np.min(correctness)),
            "max": float(np.max(correctness)),
        },
        "safety_compliance": {
            "scores": safety,
            "mean": float(np.mean(safety)),
            "std": float(np.std(safety)),
            "min": float(np.min(safety)),
            "max": float(np.max(safety)),
        },
        "completeness": {
            "scores": completeness,
            "mean": float(np.mean(completeness)),
            "std": float(np.std(completeness)),
            "min": float(np.min(completeness)),
            "max": float(np.max(completeness)),
        },
        "recommendation_quality": {
            "scores": rec_quality,
            "mean": float(np.mean(rec_quality)),
            "std": float(np.std(rec_quality)),
            "min": float(np.min(rec_quality)),
            "max": float(np.max(rec_quality)),
        },
        "guardrail_effectiveness": {
            "scores": guardrail_eff,
            "mean": float(np.mean(guardrail_eff)),
            "std": float(np.std(guardrail_eff)),
            "min": float(np.min(guardrail_eff)),
            "max": float(np.max(guardrail_eff)),
        },
        "latency": {
            "times": exec_times,
            "mean": float(np.mean(exec_times)) if exec_times else 0,
            "p50": float(np.percentile(exec_times, 50)) if exec_times else 0,
            "p95": float(np.percentile(exec_times, 95)) if exec_times else 0,
            "max": float(np.max(exec_times)) if exec_times else 0,
        },
        "summary": {
            "total_scenarios": n,
            "perfect_decisions": sum(1 for s in correctness if s == 1.0),
            "safety_perfect": sum(1 for s in safety if s == 1.0),
            "guardrail_perfect": sum(1 for s in guardrail_eff if s == 1.0),
            "overall_score": float(np.mean([
                np.mean(correctness),
                np.mean(safety),
                np.mean(completeness),
                np.mean(rec_quality),
                np.mean(guardrail_eff),
            ])),
        },
    }
