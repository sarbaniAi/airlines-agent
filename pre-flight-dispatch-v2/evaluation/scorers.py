"""
Pre-Flight Dispatch Agent V2 -- Evaluation Scorers
12 scorers: 4 LLM-judge (via ai_query) + 3 guidelines-based + 5 code-based

All LLM calls go through tools.llm_tools.llm_call() which uses ai_query
via the SQL Statement Execution SDK.  No direct OpenAI SDK.  No
mlflow.metrics.genai (the service principal cannot call serving endpoints).
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger("evaluation.scorers")

# ---------------------------------------------------------------------------
# Lazy import of llm_call (allows unit-testing with mocks)
# ---------------------------------------------------------------------------
_llm_call = None


def _get_llm_call():
    global _llm_call
    if _llm_call is None:
        from tools.llm_tools import llm_call
        _llm_call = llm_call
    return _llm_call


# ---------------------------------------------------------------------------
# Helper: parse a score from an LLM response
# ---------------------------------------------------------------------------

def _parse_llm_score(text: str) -> tuple[float, str]:
    """
    Parse a float score and reason from an LLM response.

    Tries, in order:
      1. JSON with {"score": ..., "reason": ...}
      2. Markdown-wrapped JSON
      3. First float-like number found in the text
      4. Fallback 0.0

    Returns (score, reason).
    """
    if not text or not text.strip():
        return 0.0, "Empty LLM response"

    # --- attempt 1: direct JSON ------------------------------------------
    try:
        obj = json.loads(text.strip())
        return float(obj.get("score", 0.0)), str(obj.get("reason", ""))
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # --- attempt 2: markdown code block -----------------------------------
    for delim in ("```json", "```"):
        if delim in text:
            try:
                body = text.split(delim, 1)[1].split("```", 1)[0]
                obj = json.loads(body.strip())
                return float(obj.get("score", 0.0)), str(obj.get("reason", ""))
            except (json.JSONDecodeError, ValueError, TypeError, IndexError):
                continue

    # --- attempt 3: bare number ------------------------------------------
    m = re.search(r"(?:score\s*[:=]\s*)?([01](?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        return float(m.group(1)), text.strip()[:200]

    return 0.0, f"Could not parse score from: {text[:200]}"


# =========================================================================
# LLM-Judge Scorers (1-4)
# =========================================================================

def score_answer_correctness(
    prediction: str,
    expected: str,
    context: str = "",
) -> float:
    """1. LLM-judge: is the predicted decision correct vs expected?"""
    llm = _get_llm_call()
    system = (
        "You are an aviation safety evaluation judge. "
        "Evaluate whether the predicted dispatch decision matches the expected decision. "
        "Respond ONLY with JSON: {\"score\": <0.0-1.0>, \"reason\": \"...\"}\n"
        "Score 1.0 = exact match, 0.5 = partially correct (e.g. CONDITIONAL vs NO-GO), "
        "0.0 = completely wrong (e.g. GO vs NO-GO)."
    )
    user = (
        f"Expected decision: {expected}\n"
        f"Predicted decision: {prediction}\n"
    )
    if context:
        user += f"Additional context: {context}\n"

    try:
        resp = llm(system, user, max_tokens=300, temperature=0.0)
        score, _ = _parse_llm_score(resp)
        return max(0.0, min(1.0, score))
    except Exception as e:
        logger.warning("score_answer_correctness LLM call failed: %s", e)
        return 0.0


def score_faithfulness(
    reasoning: str,
    agent_findings: str,
) -> float:
    """2. LLM-judge: does the reasoning only cite supported facts?"""
    llm = _get_llm_call()
    system = (
        "You are an aviation safety evaluation judge. "
        "Determine if the dispatch reasoning only makes claims that are supported "
        "by the agent findings provided.  Score 0-1 for faithfulness.  "
        "1.0 = every claim is grounded in findings, 0.0 = fabricated or hallucinated. "
        "Respond ONLY with JSON: {\"score\": <0.0-1.0>, \"reason\": \"...\"}"
    )
    user = (
        f"Agent findings:\n{agent_findings}\n\n"
        f"Dispatch reasoning:\n{reasoning}\n"
    )

    try:
        resp = llm(system, user, max_tokens=400, temperature=0.0)
        score, _ = _parse_llm_score(resp)
        return max(0.0, min(1.0, score))
    except Exception as e:
        logger.warning("score_faithfulness LLM call failed: %s", e)
        return 0.0


def score_relevance(
    findings: str,
    flight_context: str,
) -> float:
    """3. LLM-judge: are the findings relevant to this specific flight?"""
    llm = _get_llm_call()
    system = (
        "You are an aviation safety evaluation judge. "
        "Evaluate whether the listed agent findings are relevant to the specific "
        "flight described in the context.  Score 0-1 for relevance.  "
        "1.0 = all findings are directly relevant, 0.0 = findings are generic or irrelevant. "
        "Respond ONLY with JSON: {\"score\": <0.0-1.0>, \"reason\": \"...\"}"
    )
    user = (
        f"Flight context:\n{flight_context}\n\n"
        f"Agent findings:\n{findings}\n"
    )

    try:
        resp = llm(system, user, max_tokens=400, temperature=0.0)
        score, _ = _parse_llm_score(resp)
        return max(0.0, min(1.0, score))
    except Exception as e:
        logger.warning("score_relevance LLM call failed: %s", e)
        return 0.0


def score_chunk_relevance(
    rag_references: str,
    query_context: str,
) -> float:
    """4. LLM-judge: are retrieved regulatory references useful?"""
    llm = _get_llm_call()
    system = (
        "You are an aviation safety evaluation judge. "
        "Evaluate whether the retrieved regulatory document references are useful "
        "for making this dispatch decision.  Score 0-1 for chunk relevance.  "
        "1.0 = all chunks are directly useful, 0.0 = none are relevant. "
        "Respond ONLY with JSON: {\"score\": <0.0-1.0>, \"reason\": \"...\"}"
    )
    user = (
        f"Dispatch query context:\n{query_context}\n\n"
        f"Retrieved regulatory references:\n{rag_references}\n"
    )

    try:
        resp = llm(system, user, max_tokens=400, temperature=0.0)
        score, _ = _parse_llm_score(resp)
        return max(0.0, min(1.0, score))
    except Exception as e:
        logger.warning("score_chunk_relevance LLM call failed: %s", e)
        return 0.0


# =========================================================================
# Guidelines-Based Scorers (5-7)
# =========================================================================

_DECISION_ORDER = {"GO": 0, "CONDITIONAL": 1, "NO-GO": 2}


def score_decision_correctness(
    predicted_decision: str,
    expected_decision: str,
) -> float:
    """5. Code-first decision match with partial credit."""
    pred = predicted_decision.upper().strip()
    exp = expected_decision.upper().strip()

    if pred == exp:
        return 1.0

    # Same safety direction but different severity
    pred_rank = _DECISION_ORDER.get(pred)
    exp_rank = _DECISION_ORDER.get(exp)
    if pred_rank is None or exp_rank is None:
        return 0.0

    diff = abs(pred_rank - exp_rank)
    if diff == 1:
        return 0.5  # adjacent (CONDITIONAL vs GO, CONDITIONAL vs NO-GO)
    return 0.0  # opposite ends (GO vs NO-GO)


def score_safety_compliance(
    agent_results: dict,
    expected_red_items: list[str],
) -> float:
    """
    6. Check that every expected RED / safety-critical finding was flagged.

    expected_red_items: list of key_check strings from the scenario that the
    agents should have caught (e.g. ["captain_medical_expired", "aircraft_aog"]).
    If empty, returns 1.0 (nothing critical was expected).
    """
    if not expected_red_items:
        return 1.0

    # Collect all agent statuses and findings text
    flagged_red_count = 0
    all_statuses = []
    all_text = ""

    for name, result in (agent_results or {}).items():
        if not isinstance(result, dict):
            continue
        status = result.get("status", "")
        all_statuses.append(status)
        findings = result.get("findings", [])
        recs = result.get("recommendations", [])
        all_text += " ".join(str(f) for f in findings + recs).lower() + " "

    # Map key_check keywords to patterns we look for in agent output
    _CHECK_PATTERNS = {
        "captain_medical_expired": r"medical.*expir|expir.*medical|captain.*medical",
        "fo_medical_expired": r"first.officer.*medical|fo.*medical.*expir",
        "both_crew_medical_expired": r"medical.*expir",
        "aircraft_aog": r"aog|aircraft.on.ground|grounded",
        "aircraft_in_maintenance": r"maintenance|in.maintenance",
        "fo_duty_7d_exceeded": r"duty.*exceed|exceed.*duty|7.day.*limit",
        "captain_duty_28d_exceeded": r"duty.*exceed|28.day.*limit",
        "coa_canada_expired": r"coa.*expir|certificate.*operat.*expir",
        "airworthiness_expired": r"airworthiness.*expir|expir.*airworthiness",
        "mel_cat_a_expired": r"mel.*expir|cat.a.*expir|hydraulic",
        "c_check_overdue": r"c.check.*overdue|overdue.*c.check",
        "captain_insufficient_rest": r"rest.*insuffici|insuffici.*rest|8.hour",
        "fo_missing_nam_qualification": r"nam.*qualif|qualif.*missing|route.*qualif",
        "visibility_below_cat_iii": r"visibility.*0\.\d|below.*cat.*iii|below.*minim",
        "thunderstorm_at_destination": r"thunderstorm|cb|convective",
        "insurance_expired": r"insurance.*expir",
        "captain_critical_fatigue": r"fatigue.*critical|fatigue.*8[0-9]|fatigue.*high",
        "wind_exceeds_limits": r"wind.*exceed|crosswind.*limit|45.*kt",
        "etops_missing": r"etops.*missing|etops.*not.*found|etops.*expir",
        "rvsm_expired": r"rvsm.*expir",
        "weather_red": r"weather.*red|red.*weather",
    }

    for check in expected_red_items:
        check_lower = check.lower()
        pattern = _CHECK_PATTERNS.get(check_lower, re.escape(check_lower.replace("_", ".")))
        if re.search(pattern, all_text, re.IGNORECASE):
            flagged_red_count += 1
        elif "RED" in all_statuses:
            # At least some RED was flagged -- give partial credit
            flagged_red_count += 0.5

    score = flagged_red_count / len(expected_red_items)

    # Missing any safety-critical item when RED was expected = cap at 0
    if "RED" not in all_statuses and any(
        c in expected_red_items for c in [
            "aircraft_aog", "aircraft_in_maintenance",
            "captain_medical_expired", "both_crew_medical_expired",
            "airworthiness_expired", "insurance_expired",
        ]
    ):
        return 0.0

    return min(1.0, score)


def score_guardrail_accuracy(
    triggered_rules: list[str],
    expected_rules: list[str],
) -> float:
    """
    7. F1 of precision and recall on triggered safety rules.

    triggered_rules: rule IDs that fired (e.g. ["SR-001", "SR-004"]).
    expected_rules:  rule IDs that should have fired.
    """
    if not expected_rules and not triggered_rules:
        return 1.0  # nothing expected, nothing triggered -- perfect
    if not expected_rules:
        # Rules fired but none were expected -- precision = 0
        return 0.0
    if not triggered_rules:
        # Rules expected but none fired -- recall = 0
        return 0.0

    triggered_set = set(triggered_rules)
    expected_set = set(expected_rules)

    true_pos = len(triggered_set & expected_set)
    precision = true_pos / len(triggered_set) if triggered_set else 0.0
    recall = true_pos / len(expected_set) if expected_set else 0.0

    if precision + recall == 0:
        return 0.0
    f1 = 2 * precision * recall / (precision + recall)
    return round(f1, 4)


# =========================================================================
# Code-Based Scorers (8-12)
# =========================================================================

_REQUIRED_AGENTS = [
    "aircraft_health",
    "crew_legality",
    "weather_notam",
    "regulatory_compliance",
]


def score_completeness(agent_results: dict) -> float:
    """8. Check that all 4 agent dimensions reported with a status."""
    if not agent_results:
        return 0.0

    present = 0
    for agent_name in _REQUIRED_AGENTS:
        result = agent_results.get(agent_name)
        if isinstance(result, dict) and result.get("status"):
            present += 1

    return present / len(_REQUIRED_AGENTS)


def score_recommendation_quality(
    actions: list[str],
    alternatives: list[str],
    agent_results: dict,
) -> float:
    """
    9. How specific and actionable are the recommended actions?

    Looks for crew names (Capt./FO/SFO + Name), aircraft regs (VT-XXX),
    certificate numbers (COA-XXX), DGCA section references.
    """
    all_text = " ".join(str(a) for a in (actions or [])) + " "
    all_text += " ".join(str(a) for a in (alternatives or [])) + " "

    # Also look at agent recommendations for reference
    for _name, result in (agent_results or {}).items():
        if isinstance(result, dict):
            for rec in result.get("recommendations", []):
                all_text += f" {rec}"

    if not all_text.strip():
        return 0.0

    found = 0
    max_expected = 4

    # Crew names (Capt./FO/SFO + ProperName)
    if re.search(r"(Capt\.|Captain|FO|SFO|First\s+Officer)\s+[A-Z][a-z]+", all_text):
        found += 1

    # Aircraft registration (VT-XXX)
    if re.search(r"VT-[A-Z]{3}", all_text):
        found += 1

    # Certificate IDs (COA-XXX, SR-XXX, CERT-XXX)
    if re.search(r"(COA|CERT|SR|ETOPS|RVSM)-?\d{2,}", all_text, re.IGNORECASE):
        found += 1

    # DGCA section references
    if re.search(r"(DGCA|CAR\s+Section|DGCA\s+CAR|Section\s+\d)", all_text, re.IGNORECASE):
        found += 1

    return min(1.0, found / max(max_expected, 1))


def score_latency_budget(execution_time_seconds: float) -> float:
    """
    10. Latency scorer.
    1.0 if <= 15s, linear decrease to 0.0 at 60s.
    """
    if execution_time_seconds <= 15.0:
        return 1.0
    if execution_time_seconds >= 60.0:
        return 0.0
    return round(max(0.0, 1.0 - (execution_time_seconds - 15.0) / 45.0), 4)


def score_regulatory_citation(
    reasoning: str,
    findings: str,
) -> float:
    """
    11. Check for regulatory citations in reasoning and findings.

    Looks for: DGCA, CAR Section, SR-0xx, TCCA, FAA, EASA, regulation
    section numbers.  Score = min(1.0, citations_found / 3).
    """
    text = f"{reasoning} {findings}"
    if not text.strip():
        return 0.0

    patterns = [
        r"DGCA",
        r"CAR\s+Section\s+\d",
        r"SR-\d{3}",
        r"TCCA",
        r"\bFAA\b",
        r"\bEASA\b",
        r"Section\s+\d+\.\d+",
        r"Regulation\s+\d+",
        r"Rule\s+\d+",
        r"CAR\s+\d+",
    ]

    citations = 0
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            citations += 1

    return min(1.0, citations / 3.0)


def score_action_specificity(actions: list[str]) -> float:
    """
    12. Check each action for specific details.

    Looks for: crew names, aircraft regs (VT-), cert IDs, and specific
    verbs (swap, replace, obtain, renew, schedule, ground).
    """
    if not actions:
        return 0.0

    specific_verbs = {"swap", "replace", "obtain", "renew", "schedule", "ground",
                      "delay", "divert", "rectify", "reassign"}
    actions_with_specifics = 0

    for action in actions:
        action_lower = action.lower()
        has_specific = False

        # Crew name
        if re.search(r"(Capt\.|Captain|FO|SFO)\s+[A-Z]", action):
            has_specific = True
        # Aircraft reg
        if re.search(r"VT-[A-Z]{3}", action):
            has_specific = True
        # Cert ID
        if re.search(r"(COA|CERT|SR|ETOPS|RVSM)-?\d{2,}", action, re.IGNORECASE):
            has_specific = True
        # Specific verb
        if any(v in action_lower for v in specific_verbs):
            has_specific = True

        if has_specific:
            actions_with_specifics += 1

    return round(actions_with_specifics / len(actions), 4)


# =========================================================================
# Composite: compute_all_scores
# =========================================================================

def compute_all_scores(dispatch_result: dict, scenario: dict) -> dict[str, Any]:
    """
    Apply all 12 scorers to a single (dispatch_result, scenario) pair.

    Args:
        dispatch_result: Output of run_dispatch_check()
        scenario:        The labelled scenario dict from JSON

    Returns:
        Dict mapping scorer name -> float score.
    """
    decision = dispatch_result.get("decision", {})
    agent_results = dispatch_result.get("agent_results", {})
    flight_info = dispatch_result.get("flight_info", {})

    predicted = decision.get("decision", "UNKNOWN")
    expected = scenario.get("expected_decision", "UNKNOWN")
    reasoning = str(decision.get("reasoning", ""))
    actions = decision.get("actions", [])
    alternatives = decision.get("alternatives", [])
    exec_time = dispatch_result.get("execution_time_seconds", 0.0)

    # Build text representations for LLM judges
    agent_findings_text = ""
    findings_text = ""
    for name, result in agent_results.items():
        if isinstance(result, dict):
            findings = result.get("findings", [])
            recs = result.get("recommendations", [])
            refs = result.get("regulatory_references", result.get("sop_references", []))
            agent_findings_text += f"\n[{name}] status={result.get('status','?')}: "
            agent_findings_text += "; ".join(str(f) for f in findings[:5])
            findings_text += " ".join(str(f) for f in findings)

    flight_context = (
        f"Flight {flight_info.get('flight_number', '?')} "
        f"{flight_info.get('origin', '?')} -> {flight_info.get('destination', '?')} "
        f"Aircraft {flight_info.get('aircraft_reg', '?')} "
        f"Captain {flight_info.get('captain_name', '?')} "
        f"FO {flight_info.get('fo_name', '?')}"
    )

    # Collect regulatory references (from regulatory_compliance agent)
    reg_result = agent_results.get("regulatory_compliance", {})
    rag_refs = ""
    if isinstance(reg_result, dict):
        refs_list = reg_result.get("regulatory_references", [])
        rag_refs = "; ".join(str(r) for r in refs_list) if refs_list else ""

    # Expected red items from scenario key_checks
    expected_red_items = scenario.get("key_checks", [])
    expected_rules = scenario.get("expected_triggered_rules", [])

    # Triggered rules -- extract from decision or agent results
    triggered_rules: list[str] = []
    for name, result in agent_results.items():
        if isinstance(result, dict) and result.get("status") == "RED":
            # Infer triggered rules from RED agent statuses
            for ref in result.get("regulatory_references", result.get("compliance_gaps", [])):
                if isinstance(ref, str) and re.match(r"SR-\d+", ref):
                    triggered_rules.append(ref)

    scores: dict[str, Any] = {}

    # --- LLM-Judge scorers (1-4) ---
    try:
        scores["answer_correctness"] = score_answer_correctness(
            predicted, expected, flight_context
        )
    except Exception as e:
        logger.warning("answer_correctness failed: %s", e)
        scores["answer_correctness"] = 0.0

    try:
        scores["faithfulness"] = score_faithfulness(reasoning, agent_findings_text)
    except Exception as e:
        logger.warning("faithfulness failed: %s", e)
        scores["faithfulness"] = 0.0

    try:
        scores["relevance"] = score_relevance(findings_text[:3000], flight_context)
    except Exception as e:
        logger.warning("relevance failed: %s", e)
        scores["relevance"] = 0.0

    try:
        scores["chunk_relevance"] = score_chunk_relevance(
            rag_refs[:2000] if rag_refs else "No regulatory references retrieved.",
            flight_context,
        )
    except Exception as e:
        logger.warning("chunk_relevance failed: %s", e)
        scores["chunk_relevance"] = 0.0

    # --- Guidelines-based scorers (5-7) ---
    scores["decision_correctness"] = score_decision_correctness(predicted, expected)

    scores["safety_compliance"] = score_safety_compliance(
        agent_results,
        expected_red_items if scenario.get("expected_decision") == "NO-GO" else [],
    )

    scores["guardrail_accuracy"] = score_guardrail_accuracy(
        triggered_rules, expected_rules
    )

    # --- Code-based scorers (8-12) ---
    scores["completeness"] = score_completeness(agent_results)

    scores["recommendation_quality"] = score_recommendation_quality(
        actions, alternatives, agent_results
    )

    scores["latency_budget"] = score_latency_budget(exec_time)

    scores["regulatory_citation"] = score_regulatory_citation(
        reasoning, findings_text
    )

    scores["action_specificity"] = score_action_specificity(actions)

    return scores


# =========================================================================
# Aggregate summary across multiple scenarios
# =========================================================================

def get_score_summary(scores_list: list[dict[str, float]]) -> dict[str, Any]:
    """
    Compute aggregate stats (mean, min, max) per scorer across scenarios.

    Args:
        scores_list: List of dicts returned by compute_all_scores().

    Returns:
        Dict with per-metric stats and an overall_score.
    """
    if not scores_list:
        return {"error": "No scores to summarise", "overall_score": 0.0}

    all_keys = set()
    for s in scores_list:
        all_keys.update(s.keys())

    summary: dict[str, Any] = {}
    all_means: list[float] = []

    for key in sorted(all_keys):
        values = [s[key] for s in scores_list if key in s and isinstance(s[key], (int, float))]
        if not values:
            continue
        mean_val = sum(values) / len(values)
        summary[key] = {
            "mean": round(mean_val, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "count": len(values),
        }
        all_means.append(mean_val)

    summary["overall_score"] = round(sum(all_means) / len(all_means), 4) if all_means else 0.0
    summary["total_scenarios"] = len(scores_list)

    return summary
