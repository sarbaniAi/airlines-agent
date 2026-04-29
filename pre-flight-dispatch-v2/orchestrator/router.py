"""
Routing logic for the LangGraph supervisor.
Determines whether additional investigation is needed after the core checks.
"""

import logging

from orchestrator.state import DispatchState

logger = logging.getLogger("orchestrator.router")


def should_escalate(state: DispatchState) -> bool:
    """
    Returns True if the core check results need additional investigation via Genie.

    Conditions for escalation:
    - Multiple AMBER statuses across different agents (need more data)
    - Any agent encountered an error (partial data)
    - Specific patterns that benefit from ad-hoc queries
    """
    amber_count = 0
    error_count = 0
    has_red = False

    for key in ("aircraft_health", "crew_legality", "weather_notam", "regulatory_compliance"):
        result = state.get(key)
        if not result:
            error_count += 1
            continue
        agent_status = result.get("status", "RED")
        if agent_status == "AMBER":
            amber_count += 1
        elif agent_status == "RED":
            has_red = True

    # Don't escalate if already clearly RED (no point investigating more)
    if has_red and amber_count == 0:
        return False

    # Escalate if multiple AMBERs — supervisor may need more operational context
    if amber_count >= 2:
        return True

    # Escalate if any agent had an error (incomplete picture)
    if error_count > 0:
        return True

    # Max retries guard
    if state.get("retry_count", 0) >= 1:
        return False

    return False


def route_after_checks(state: DispatchState) -> str:
    """
    Determine the next node after the parallel checks complete.

    Returns:
        'genie_investigation' if escalation is needed, else 'synthesize_decision'.
    """
    if should_escalate(state):
        logger.info("Routing to genie_investigation — additional data needed")
        return "genie_investigation"

    logger.info("Routing to synthesize_decision — all checks sufficient")
    return "synthesize_decision"
