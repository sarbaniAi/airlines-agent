"""
Pre-Flight Dispatch V2 — Output Validation Guardrail.

Validates LLM decisions against hard safety rules, detects hallucination,
and overrides unsafe decisions when required.
"""

import logging
from datetime import date, datetime
from typing import Any

from guardrails.safety_rules import evaluate_safety_rules, get_most_severe_action

logger = logging.getLogger("guardrails.output_validator")

# ---------------------------------------------------------------------------
# Valid Decision Values
# ---------------------------------------------------------------------------

VALID_DECISIONS = {"GO", "NO-GO", "CONDITIONAL"}
VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


# ---------------------------------------------------------------------------
# Decision Validation
# ---------------------------------------------------------------------------

def validate_decision(decision_dict: dict) -> dict[str, Any]:
    """
    Validate the structure and content of an LLM-generated decision.

    Checks:
        - Required fields present (decision, confidence, summary, reasoning, risk_level)
        - Decision value is one of GO / NO-GO / CONDITIONAL
        - Confidence is between 0.0 and 1.0
        - Risk level is valid
        - Summary and reasoning are non-empty strings

    Args:
        decision_dict: The parsed LLM decision dictionary.

    Returns:
        {valid: bool, errors: list[str], corrected_decision: dict}
    """
    errors: list[str] = []
    corrected = dict(decision_dict) if decision_dict else {}

    if not decision_dict or not isinstance(decision_dict, dict):
        return {
            "valid": False,
            "errors": ["Decision is empty or not a dictionary"],
            "corrected_decision": _default_decision(),
        }

    # Check decision field
    decision_val = str(corrected.get("decision", "")).upper().strip()
    if decision_val not in VALID_DECISIONS:
        errors.append(f"Invalid decision value: '{decision_val}'. Must be GO, NO-GO, or CONDITIONAL.")
        corrected["decision"] = "CONDITIONAL"  # Safe default
    else:
        corrected["decision"] = decision_val

    # Check confidence
    try:
        conf = float(corrected.get("confidence", 0.5))
        if conf < 0.0 or conf > 1.0:
            errors.append(f"Confidence {conf} out of range [0.0, 1.0]")
            conf = max(0.0, min(1.0, conf))
        corrected["confidence"] = conf
    except (ValueError, TypeError):
        errors.append(f"Invalid confidence value: '{corrected.get('confidence')}'")
        corrected["confidence"] = 0.5

    # Check risk level
    risk = str(corrected.get("risk_level", "")).upper().strip()
    if risk not in VALID_RISK_LEVELS:
        errors.append(f"Invalid risk level: '{risk}'")
        # Infer from decision
        risk_map = {"GO": "LOW", "CONDITIONAL": "MEDIUM", "NO-GO": "CRITICAL"}
        corrected["risk_level"] = risk_map.get(corrected["decision"], "HIGH")
    else:
        corrected["risk_level"] = risk

    # Check summary
    if not corrected.get("summary") or not isinstance(corrected["summary"], str):
        errors.append("Missing or empty summary")
        corrected["summary"] = f"Decision: {corrected['decision']}"

    # Check reasoning
    if not corrected.get("reasoning") or not isinstance(corrected["reasoning"], str):
        errors.append("Missing or empty reasoning")
        corrected["reasoning"] = "No detailed reasoning provided by LLM."

    # Ensure actions and alternatives are lists
    if not isinstance(corrected.get("actions"), list):
        corrected["actions"] = []
    if not isinstance(corrected.get("alternatives"), list):
        corrected["alternatives"] = []

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "corrected_decision": corrected,
    }


def enforce_safety_rules(
    agent_results: dict[str, dict],
    decision: dict,
) -> dict[str, Any]:
    """
    Enforce hard safety rules that override the LLM decision.

    This is the primary guardrail. It evaluates all safety rules
    and overrides the LLM decision if any non-overridable rule triggers.

    Args:
        agent_results: Dict of agent_name -> agent result.
        decision: The LLM-generated (or fallback) decision dict.

    Returns:
        {
            valid: bool,
            corrected_decision: dict,
            overrides: list[dict],   # rules that forced a change
            triggered_rules: list[dict],  # all rules that fired
            guardrail_active: bool,  # whether guardrails made any change
        }
    """
    triggered_rules = evaluate_safety_rules(agent_results)
    overrides: list[dict] = []
    guardrail_active = False

    corrected = dict(decision)
    original_decision = decision.get("decision", "UNKNOWN")

    if not triggered_rules:
        return {
            "valid": True,
            "corrected_decision": corrected,
            "overrides": [],
            "triggered_rules": [],
            "guardrail_active": False,
        }

    # Determine the most severe required action
    required_action = get_most_severe_action(triggered_rules)

    # Check if override is needed
    decision_severity = {"GO": 0, "CONDITIONAL": 1, "NO-GO": 2}
    current_severity = decision_severity.get(original_decision, 0)
    required_severity = decision_severity.get(required_action, 0)

    if required_severity > current_severity:
        # The LLM decision was less severe than what safety rules require
        guardrail_active = True

        # Collect all non-overridable NO-GO rules
        nogo_rules = [r for r in triggered_rules if r["forced_action"] == "NO-GO" and not r["override_allowed"]]
        conditional_rules = [r for r in triggered_rules if r["forced_action"] == "CONDITIONAL"]

        corrected["decision"] = required_action

        # Adjust confidence — guardrail override means high confidence in the override
        corrected["confidence"] = 0.99 if required_action == "NO-GO" else 0.90

        # Adjust risk level
        if required_action == "NO-GO":
            corrected["risk_level"] = "CRITICAL"
        elif required_action == "CONDITIONAL":
            corrected["risk_level"] = "HIGH"

        # Build override explanation
        override_reasons = []
        for rule in triggered_rules:
            if not rule["override_allowed"] and rule["forced_action"] == "NO-GO":
                override_reasons.append(
                    f"[{rule['rule_id']}] {rule['rule_name']}: {rule['trigger_details']}"
                )
                overrides.append(rule)

        if not overrides and conditional_rules:
            for rule in conditional_rules:
                override_reasons.append(
                    f"[{rule['rule_id']}] {rule['rule_name']}: {rule['trigger_details']}"
                )
                overrides.append(rule)

        # Prepend safety override note to reasoning
        safety_note = (
            f"SAFETY OVERRIDE: LLM initially recommended {original_decision}, "
            f"but safety guardrails have enforced {required_action}. "
            f"Triggered rules: {'; '.join(override_reasons)}"
        )
        corrected["reasoning"] = safety_note + "\n\n" + corrected.get("reasoning", "")
        corrected["summary"] = (
            f"SAFETY OVERRIDE to {required_action}: "
            + corrected.get("summary", "Safety rules triggered.")
        )

        logger.warning(
            f"Guardrail override: {original_decision} -> {required_action}. "
            f"Rules: {[r['rule_id'] for r in overrides]}"
        )

    return {
        "valid": not guardrail_active,
        "corrected_decision": corrected,
        "overrides": overrides,
        "triggered_rules": triggered_rules,
        "guardrail_active": guardrail_active,
    }


def check_hallucination(
    decision: dict,
    agent_results: dict[str, dict],
) -> dict[str, Any]:
    """
    Verify that the LLM decision is consistent with the actual agent data.

    Detects cases where the LLM:
        - Claims all checks passed when agents reported RED
        - References findings not present in agent results
        - Gives GO when any agent is RED
        - Gives NO-GO when all agents are GREEN

    Args:
        decision: The LLM decision dict.
        agent_results: Dict of agent_name -> agent result.

    Returns:
        {
            hallucination_detected: bool,
            issues: list[str],
            corrected_decision: dict | None,
        }
    """
    issues: list[str] = []
    corrected = None

    llm_decision = str(decision.get("decision", "")).upper()
    agent_statuses = {
        name: result.get("status", "UNKNOWN")
        for name, result in agent_results.items()
    }

    has_red = "RED" in agent_statuses.values()
    all_green = all(s == "GREEN" for s in agent_statuses.values())
    amber_count = sum(1 for s in agent_statuses.values() if s == "AMBER")

    # Check 1: GO decision when any agent is RED
    if llm_decision == "GO" and has_red:
        red_agents = [n for n, s in agent_statuses.items() if s == "RED"]
        issues.append(
            f"LLM gave GO but agents have RED status: {', '.join(red_agents)}. "
            f"This is a potential hallucination — the LLM ignored critical findings."
        )
        corrected = dict(decision)
        corrected["decision"] = "NO-GO"
        corrected["risk_level"] = "CRITICAL"
        corrected["confidence"] = 0.95
        corrected["reasoning"] = (
            f"HALLUCINATION CORRECTION: LLM recommended GO despite RED status in "
            f"{', '.join(red_agents)}. Decision corrected to NO-GO.\n\n"
            + decision.get("reasoning", "")
        )

    # Check 2: NO-GO when all agents are GREEN
    if llm_decision == "NO-GO" and all_green:
        issues.append(
            "LLM gave NO-GO but all agents report GREEN status. "
            "This may be a hallucination or overly conservative analysis."
        )
        corrected = dict(decision)
        corrected["decision"] = "GO"
        corrected["risk_level"] = "LOW"
        corrected["confidence"] = 0.90
        corrected["reasoning"] = (
            "HALLUCINATION CORRECTION: LLM recommended NO-GO despite all agents "
            "reporting GREEN. Decision corrected to GO.\n\n"
            + decision.get("reasoning", "")
        )

    # Check 3: GO with multiple AMBER findings
    if llm_decision == "GO" and amber_count >= 2:
        amber_agents = [n for n, s in agent_statuses.items() if s == "AMBER"]
        issues.append(
            f"LLM gave GO with {amber_count} AMBER agents ({', '.join(amber_agents)}). "
            f"This should be at least CONDITIONAL."
        )
        corrected = dict(decision)
        corrected["decision"] = "CONDITIONAL"
        corrected["risk_level"] = "MEDIUM"
        corrected["reasoning"] = (
            f"HALLUCINATION CORRECTION: LLM recommended GO despite AMBER status in "
            f"{', '.join(amber_agents)}. Decision corrected to CONDITIONAL.\n\n"
            + decision.get("reasoning", "")
        )

    # Check 4: Verify LLM reasoning references actual findings
    reasoning = str(decision.get("reasoning", "")).lower()
    all_findings = []
    for result in agent_results.values():
        all_findings.extend(result.get("findings", []))

    if all_findings and reasoning:
        # Check if LLM reasoning mentions at least some of the actual findings
        finding_keywords = set()
        for f in all_findings:
            # Extract key terms from findings
            words = f.lower().split()
            finding_keywords.update(w for w in words if len(w) > 4)

        if finding_keywords:
            matched_keywords = sum(1 for kw in finding_keywords if kw in reasoning)
            coverage = matched_keywords / len(finding_keywords) if finding_keywords else 0

            if coverage < 0.1 and len(all_findings) > 2:
                issues.append(
                    f"LLM reasoning has very low overlap with actual agent findings "
                    f"({coverage:.0%} keyword match). The LLM may be generating "
                    f"generic reasoning rather than analyzing the specific data."
                )

    return {
        "hallucination_detected": len(issues) > 0,
        "issues": issues,
        "corrected_decision": corrected,
    }


def run_all_output_validations(
    decision: dict,
    agent_results: dict[str, dict],
) -> dict[str, Any]:
    """
    Run all output validations in sequence: structure check, hallucination
    detection, and safety rule enforcement.

    The order matters:
        1. Validate structure -> fix missing/invalid fields
        2. Check hallucination -> detect inconsistencies
        3. Enforce safety rules -> final override (highest priority)

    Args:
        decision: The raw LLM decision dict.
        agent_results: Dict of agent_name -> agent result.

    Returns:
        {
            final_decision: dict,
            validation_errors: list[str],
            hallucination_issues: list[str],
            safety_overrides: list[dict],
            triggered_rules: list[dict],
            guardrail_active: bool,
            total_issues: int,
        }
    """
    # Step 1: Structural validation
    struct_result = validate_decision(decision)
    working_decision = struct_result["corrected_decision"]

    # Step 2: Hallucination check
    halluc_result = check_hallucination(working_decision, agent_results)
    if halluc_result["corrected_decision"]:
        working_decision = halluc_result["corrected_decision"]

    # Step 3: Safety rule enforcement (final authority)
    safety_result = enforce_safety_rules(agent_results, working_decision)
    final_decision = safety_result["corrected_decision"]

    total_issues = (
        len(struct_result["errors"])
        + len(halluc_result["issues"])
        + len(safety_result["overrides"])
    )

    return {
        "final_decision": final_decision,
        "validation_errors": struct_result["errors"],
        "hallucination_issues": halluc_result["issues"],
        "safety_overrides": safety_result["overrides"],
        "triggered_rules": safety_result["triggered_rules"],
        "guardrail_active": safety_result["guardrail_active"],
        "total_issues": total_issues,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_decision() -> dict:
    """Return a safe default decision when LLM output is unparseable."""
    return {
        "decision": "CONDITIONAL",
        "confidence": 0.5,
        "summary": "Unable to parse LLM decision. Defaulting to CONDITIONAL pending manual review.",
        "reasoning": "The LLM output could not be parsed into a valid decision structure. "
                     "A manual review of all agent findings is recommended before dispatch.",
        "actions": ["Manual review of all agent findings required"],
        "alternatives": [],
        "risk_level": "HIGH",
    }
